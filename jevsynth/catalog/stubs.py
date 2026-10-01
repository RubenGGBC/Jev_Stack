"""Lectura de los stubs de typeshed para obtener firmas tipadas de la stdlib.

La stdlib casi no tiene anotaciones en tiempo de ejecución, así que los tipos salen de
los `.pyi` de typeshed (incluidos en mypy). Esto es un paso offline: el resultado se
serializa a JSON y el sintetizador nunca lee stubs.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jevsynth.catalog.model import ANY, NONE, ClassInfo, Param, ParamKind, TypeRef, literal, union

# Módulos cuyas clases se nombran sin prefijo (tipos "universales").
BARE_MODULES = frozenset(
    {"builtins", "typing", "typing_extensions", "_typeshed", "collections.abc", "_collections_abc"}
)

# Alias de `typing` que en los stubs no son clases normales.
_TYPING_ALIASES = {
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Tuple": "tuple",
    "Type": "type",
    "Text": "str",
    "DefaultDict": "collections.defaultdict",
    "Counter": "collections.Counter",
    "Deque": "collections.deque",
    "OrderedDict": "collections.OrderedDict",
    "ChainMap": "collections.ChainMap",
    "LiteralString": "str",
    "ByteString": "bytes",
}
_TRANSPARENT = frozenset({"ClassVar", "Final", "Required", "NotRequired", "ReadOnly", "Annotated"})
_BOOLISH = frozenset({"TypeGuard", "TypeIs"})
_UNFILLABLE = frozenset({"NoReturn", "Never"})


def default_typeshed() -> Path:
    """Localiza `typeshed/stdlib` dentro de la instalación de mypy."""
    import importlib.util
    import subprocess

    spec = importlib.util.find_spec("mypy")
    if spec is not None and spec.origin is not None:
        return Path(spec.origin).parent / "typeshed" / "stdlib"
    # mypy instalado como herramienta aislada (uv/pipx): preguntarle a su intérprete.
    import shutil

    exe = shutil.which("mypy")
    if exe is not None:
        first = Path(exe).read_text(errors="ignore").splitlines()[0]
        if first.startswith("#!"):
            py = first[2:].strip()
            out = subprocess.run(
                [py, "-c", "import mypy, os; print(os.path.dirname(mypy.__file__))"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(out.stdout.strip()) / "typeshed" / "stdlib"
    raise FileNotFoundError("no encuentro typeshed: instala mypy")


# ---------------------------------------------------------------------------
# Símbolos de un módulo stub


@dataclass
class ClassSym:
    node: ast.ClassDef
    module: str


@dataclass
class FuncSym:
    nodes: list[ast.FunctionDef]


@dataclass
class TypeVarSym:
    name: str
    bounds: list[ast.expr]  # restricciones o cota (bound=)


@dataclass
class AliasSym:
    expr: ast.expr


@dataclass
class ImportSym:
    module: str
    name: str


@dataclass
class ModuleSym:
    module: str


@dataclass
class VarSym:
    annotation: ast.expr | None


Symbol = ClassSym | FuncSym | TypeVarSym | AliasSym | ImportSym | ModuleSym | VarSym


def eval_condition(node: ast.expr) -> bool:
    """Evalúa condiciones de stubs (`sys.version_info >= (3, 12)`, `sys.platform == ...`)."""
    if isinstance(node, ast.BoolOp):
        vals = [eval_condition(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not eval_condition(node.operand)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, op, right = node.left, node.ops[0], node.comparators[0]
        lhs: object
        src = ast.unparse(left)
        if src == "sys.version_info":
            lhs = sys.version_info[:3]
        elif src.startswith("sys.version_info[:"):
            lhs = sys.version_info[: int(src.split(":")[1].rstrip("]"))]
        elif src == "sys.platform":
            lhs = sys.platform
        else:
            return False
        try:
            rhs = ast.literal_eval(right)
        except ValueError:
            return False
        try:
            return bool(_compare(lhs, op, rhs))
        except TypeError:
            return False
    if isinstance(node, ast.Call) and ast.unparse(node.func) == "sys.platform.startswith":
        arg = node.args[0]
        return isinstance(arg, ast.Constant) and sys.platform.startswith(str(arg.value))
    return False


def _compare(lhs: object, op: ast.cmpop, rhs: object) -> object:
    if isinstance(lhs, tuple) and isinstance(rhs, tuple):
        lhs = lhs[: len(rhs)]
    import operator as op_mod

    ops: dict[type[ast.cmpop], Callable[[Any, Any], object]] = {
        ast.GtE: op_mod.ge,
        ast.Gt: op_mod.gt,
        ast.Lt: op_mod.lt,
        ast.LtE: op_mod.le,
        ast.Eq: op_mod.eq,
        ast.NotEq: op_mod.ne,
    }
    fn = ops.get(type(op))
    return False if fn is None else fn(lhs, rhs)


def active_body(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Recorre un cuerpo aplanando los `if` según la versión/plataforma actual."""
    for stmt in body:
        if isinstance(stmt, ast.If):
            yield from active_body(stmt.body if eval_condition(stmt.test) else stmt.orelse)
        else:
            yield stmt


def _is_typevar_call(value: ast.expr) -> bool:
    return isinstance(value, ast.Call) and ast.unparse(value.func).rsplit(".", 1)[-1] in {
        "TypeVar",
        "ParamSpec",
        "TypeVarTuple",
    }


@dataclass
class StubModule:
    name: str
    symbols: dict[str, Symbol] = field(default_factory=dict)
    star_imports: list[str] = field(default_factory=list)

    @staticmethod
    def parse(name: str, source: str) -> StubModule:
        mod = StubModule(name)
        tree = ast.parse(source)
        for stmt in active_body(tree.body):
            mod._add(stmt)
        return mod

    def _add(self, stmt: ast.stmt) -> None:
        syms = self.symbols
        if isinstance(stmt, ast.ClassDef):
            syms[stmt.name] = ClassSym(stmt, self.name)
        elif isinstance(stmt, ast.FunctionDef):
            prev = syms.get(stmt.name)
            if isinstance(prev, FuncSym) and _is_overload(stmt):
                prev.nodes.append(stmt)
            else:
                syms[stmt.name] = FuncSym([stmt])
        elif isinstance(stmt, ast.ImportFrom) and stmt.module is not None:
            target = _resolve_relative(self.name, stmt.module, stmt.level)
            for alias in stmt.names:
                if alias.name == "*":
                    self.star_imports.append(target)
                else:
                    syms[alias.asname or alias.name] = ImportSym(target, alias.name)
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    syms[alias.asname] = ModuleSym(alias.name)
                else:
                    syms[alias.name.split(".")[0]] = ModuleSym(alias.name.split(".")[0])
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            tgt = stmt.targets[0]
            if isinstance(tgt, ast.Name):
                if _is_typevar_call(stmt.value):
                    syms[tgt.id] = _typevar(tgt.id, stmt.value)
                else:
                    syms[tgt.id] = AliasSym(stmt.value)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            ann = ast.unparse(stmt.annotation)
            if ann.endswith("TypeAlias") and stmt.value is not None:
                syms[stmt.target.id] = AliasSym(stmt.value)
            else:
                syms[stmt.target.id] = VarSym(stmt.annotation)
        elif type(stmt).__name__ == "TypeAlias":  # `type X = ...` (3.12+)
            name, value = getattr(stmt, "name", None), getattr(stmt, "value", None)
            if isinstance(name, ast.Name) and isinstance(value, ast.expr):
                syms[name.id] = AliasSym(value)


def _typevar(name: str, call: ast.expr) -> TypeVarSym:
    assert isinstance(call, ast.Call)
    bounds: list[ast.expr] = list(call.args[1:])
    for kw in call.keywords:
        if kw.arg == "bound" and kw.value is not None:
            bounds.append(kw.value)
    return TypeVarSym(name, bounds)


def _is_overload(fn: ast.FunctionDef) -> bool:
    return any(ast.unparse(d).rsplit(".", 1)[-1] == "overload" for d in fn.decorator_list)


def _resolve_relative(current: str, module: str, level: int) -> str:
    if level == 0:
        return module
    parts = current.split(".")[:-level]
    return ".".join([*parts, module]) if module else ".".join(parts)


# ---------------------------------------------------------------------------
# Índice de stubs y conversión de anotaciones


@dataclass(frozen=True)
class ClassRef:
    canonical: str
    module: str
    node: ast.ClassDef


@dataclass
class ClassCtx:
    """Contexto de clase para resolver `Self` y las variables de tipo de la clase."""

    canonical: str
    typevars: tuple[str, ...]

    @property
    def self_type(self) -> TypeRef:
        return TypeRef(self.canonical, tuple(TypeRef("~" + t) for t in self.typevars))


Resolved = ClassRef | FuncSym | TypeVarSym | tuple[str, ast.expr] | str | None
# str: nombre especial de typing ("Any", "Optional", ...) o "module:<nombre>"


class StubIndex:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._modules: dict[str, StubModule | None] = {}
        self._class_info: dict[str, ClassInfo] = {}
        self._class_refs: dict[str, ClassRef] = {}
        self._public_modules = {p.stem for p in root.glob("*.pyi")} | {
            p.name for p in root.iterdir() if p.is_dir()
        }

    # -- módulos -------------------------------------------------------------

    def module(self, name: str) -> StubModule | None:
        if name not in self._modules:
            rel = Path(*name.split("."))
            mod: StubModule | None = None
            for path in (self.root / rel.with_suffix(".pyi"), self.root / rel / "__init__.pyi"):
                if path.exists():
                    mod = StubModule.parse(name, path.read_text())
                    break
            self._modules[name] = mod
        return self._modules[name]

    def lookup(self, module: str, name: str, _seen: frozenset[tuple[str, str]] = frozenset()) -> Resolved:
        """Resuelve `name` en `module` siguiendo imports y reexportaciones."""
        key = (module, name)
        if key in _seen:
            return None
        seen = _seen | {key}
        if module in {"typing", "typing_extensions"} and name in _TYPING_SPECIALS:
            return name
        if module in {"typing", "typing_extensions"} and name in _TYPING_ALIASES:
            target = _TYPING_ALIASES[name]
            mod, _, cls = target.rpartition(".")
            return self.lookup(mod or "builtins", cls, seen)
        mod_stub = self.module(module)
        if mod_stub is None:
            sub = self.module(f"{module}.{name}")
            return f"module:{module}.{name}" if sub is not None else None
        sym = mod_stub.symbols.get(name)
        if sym is None:
            for star in mod_stub.star_imports:
                r = self.lookup(star, name, seen)
                if r is not None:
                    return r
            if self.module(f"{module}.{name}") is not None:
                return f"module:{module}.{name}"
            return None
        if isinstance(sym, ClassSym):
            return ClassRef(self.canonical(sym.module, sym.node.name), sym.module, sym.node)
        if isinstance(sym, ImportSym):
            return self.lookup(sym.module, sym.name, seen)
        if isinstance(sym, ModuleSym):
            return f"module:{sym.module}"
        if isinstance(sym, AliasSym):
            # `_reader = Reader` y similares: alias a otro nombre.
            return (module, sym.expr)
        if isinstance(sym, (FuncSym, TypeVarSym)):
            return sym
        return None

    def canonical(self, module: str, name: str) -> str:
        if module in BARE_MODULES:
            return name
        public = module
        if module.startswith("_") and module[1:] in self._public_modules:
            public = module[1:]
        return f"{public}.{name}"

    # -- tipos -----------------------------------------------------------------

    def to_type(self, expr: ast.expr | None, module: str, ctx: ClassCtx | None = None) -> TypeRef:
        if expr is None:
            return TypeRef(ANY)
        return self._conv(expr, module, ctx, 0)

    def _conv(self, expr: ast.expr, module: str, ctx: ClassCtx | None, depth: int) -> TypeRef:
        if depth > 25:
            return TypeRef(ANY)
        d = depth + 1
        if isinstance(expr, ast.Constant):
            if expr.value is None:
                return TypeRef(NONE)
            if expr.value is Ellipsis:
                return TypeRef("...")
            if isinstance(expr.value, str):
                try:
                    inner = ast.parse(expr.value, mode="eval").body
                except SyntaxError:
                    return TypeRef(ANY)
                return self._conv(inner, module, ctx, d)
            return TypeRef(ANY)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            return union(self._conv(expr.left, module, ctx, d), self._conv(expr.right, module, ctx, d))
        if isinstance(expr, ast.Subscript):
            return self._subscript(expr, module, ctx, d)
        if isinstance(expr, (ast.Name, ast.Attribute)):
            r = self._resolve_expr(expr, module)
            return self._from_resolved(r, (), module, ctx, d)
        return TypeRef(ANY)

    def _resolve_expr(self, expr: ast.expr, module: str) -> Resolved:
        if isinstance(expr, ast.Name):
            r = self.lookup(module, expr.id)
            if r is None and module != "builtins":
                r = self.lookup("builtins", expr.id)
            return r
        if isinstance(expr, ast.Attribute):
            base = self._resolve_expr(expr.value, module)
            if isinstance(base, str) and base.startswith("module:"):
                return self.lookup(base.removeprefix("module:"), expr.attr)
        return None

    def _from_resolved(
        self,
        r: Resolved,
        args: tuple[TypeRef, ...],
        module: str,
        ctx: ClassCtx | None,
        depth: int,
    ) -> TypeRef:
        if isinstance(r, ClassRef):
            if r.canonical == "object":
                return TypeRef("object")
            return TypeRef(r.canonical, args)
        if isinstance(r, TypeVarSym):
            bounds = tuple(self._conv(b, module, ctx, depth) for b in r.bounds)
            return TypeRef("~" + r.name, bounds)
        if isinstance(r, tuple):
            alias_module, alias_expr = r
            t = self._conv(alias_expr, alias_module, ctx, depth)
            if args and t.args and all(a.is_var for a in t.args):
                # Alias genérico (`_DialectLike[T]`): sustituir sus variables en orden.
                return TypeRef(t.name, args)
            return t
        if isinstance(r, str):
            if r == "Self":
                return ctx.self_type if ctx is not None else TypeRef(ANY)
            if r in {"Any", "Incomplete"}:
                return TypeRef(ANY)
            if r in _UNFILLABLE:
                return TypeRef("Never")
            if r in {"Callable"}:
                return TypeRef("Callable")
        return TypeRef(ANY)

    def _subscript(self, expr: ast.Subscript, module: str, ctx: ClassCtx | None, d: int) -> TypeRef:
        base = self._resolve_expr(expr.value, module)
        sl = expr.slice
        items: list[ast.expr] = list(sl.elts) if isinstance(sl, ast.Tuple) else [sl]
        if isinstance(base, str):
            if base == "Optional":
                return union(self._conv(items[0], module, ctx, d), TypeRef(NONE))
            if base == "Union":
                return union(*(self._conv(i, module, ctx, d) for i in items))
            if base == "Literal":
                return union(*(_literal_type(i) for i in items))
            if base in _TRANSPARENT:
                return self._conv(items[0], module, ctx, d)
            if base in _BOOLISH:
                return TypeRef("bool")
            if base == "Callable":
                return TypeRef("Callable")
            if base == "Unpack" or base == "Concatenate":
                return TypeRef(ANY)
        args = tuple(self._conv(i, module, ctx, d) for i in items)
        return self._from_resolved(base, args, module, ctx, d)

    # -- clases ----------------------------------------------------------------

    def class_ref(self, canonical: str) -> ClassRef | None:
        if canonical in self._class_refs:
            return self._class_refs[canonical]
        mod, _, name = canonical.rpartition(".")
        candidates = [mod, "_" + mod] if mod else ["builtins", "typing", "_typeshed", "typing_extensions"]
        for m in candidates:
            r = self.lookup(m, name)
            if isinstance(r, ClassRef) and r.canonical == canonical:
                self._class_refs[canonical] = r
                return r
        return None

    def class_ctx(self, ref: ClassRef) -> ClassCtx:
        return ClassCtx(ref.canonical, self._typevars_of(ref))

    def _typevars_of(self, ref: ClassRef) -> tuple[str, ...]:
        explicit: list[str] = []
        implicit: list[str] = []
        for b in ref.node.bases:
            base = b.value if isinstance(b, ast.Subscript) else b
            base_name = ast.unparse(base).rsplit(".", 1)[-1]
            names = [n.id for n in ast.walk(b) if isinstance(n, ast.Name)]
            tvs = [n for n in names if isinstance(self.lookup(ref.module, n), TypeVarSym)]
            if base_name in {"Generic", "Protocol"} and tvs:
                explicit = tvs
            for t in tvs:
                if t not in implicit:
                    implicit.append(t)
        return tuple(explicit or implicit)

    def class_info(self, canonical: str) -> ClassInfo | None:
        if canonical in self._class_info:
            return self._class_info[canonical]
        ref = self.class_ref(canonical)
        if ref is None:
            return None
        ctx = self.class_ctx(ref)
        supers: list[TypeRef] = []
        for b in ref.node.bases:
            base_name = ast.unparse(b.value if isinstance(b, ast.Subscript) else b).rsplit(".", 1)[-1]
            if base_name in {"Generic", "Protocol", "object", "NamedTuple", "TypedDict", "ABC"}:
                continue
            t = self.to_type(b, ref.module, ctx)
            if t.name not in {ANY, "object"} and t not in supers:
                supers.append(t)
        for t in self._structural(ref, ctx):
            if t not in supers and t.name != canonical:
                supers.append(t)
        is_protocol = any(
            ast.unparse(b.value if isinstance(b, ast.Subscript) else b).rsplit(".", 1)[-1] == "Protocol"
            for b in ref.node.bases
        )
        info = ClassInfo(canonical, ctx.typevars, tuple(supers), is_protocol)
        self._class_info[canonical] = info
        return info

    def methods(self, ref: ClassRef) -> dict[str, list[ast.FunctionDef]]:
        out: dict[str, list[ast.FunctionDef]] = {}
        for stmt in active_body(ref.node.body):
            if isinstance(stmt, ast.FunctionDef):
                if stmt.name in out and _is_overload(stmt):
                    out[stmt.name].append(stmt)
                else:
                    out[stmt.name] = [stmt]
        return out

    def _structural(self, ref: ClassRef, ctx: ClassCtx) -> list[TypeRef]:
        """Protocolos que la clase cumple por tener ciertos métodos."""
        meths = self.methods(ref)

        def ret(name: str) -> TypeRef | None:
            fns = meths.get(name)
            if not fns:
                return None
            return self.to_type(fns[0].returns, ref.module, ctx)

        out: list[TypeRef] = []
        it = ret("__iter__")
        nxt = ret("__next__")
        if nxt is not None and it is not None:
            out.append(TypeRef("Iterator", (nxt,)))
        elif it is not None and it.name in {"Iterator", "Generator"} and it.args:
            out.append(TypeRef("Iterable", (it.args[0],)))
        if "__len__" in meths:
            out.append(TypeRef("Sized"))
        if "__index__" in meths:
            out.append(TypeRef("SupportsIndex"))
        if "__int__" in meths:
            out.append(TypeRef("SupportsInt"))
        if "__float__" in meths:
            out.append(TypeRef("SupportsFloat"))
        if (ab := ret("__abs__")) is not None:
            out.append(TypeRef("SupportsAbs", (ab,)))
        if "__lt__" in meths:
            out.append(TypeRef("SupportsDunderLT", (TypeRef(ANY),)))
        if "__gt__" in meths:
            out.append(TypeRef("SupportsDunderGT", (TypeRef(ANY),)))
        if "__add__" in meths:
            out.append(TypeRef("SupportsAdd", (TypeRef(ANY), TypeRef(ANY))))
        if "__radd__" in meths:
            out.append(TypeRef("SupportsRAdd", (TypeRef(ANY), TypeRef(ANY))))
        if (rnd := meths.get("__round__")) is not None:
            for fn in rnd:
                r = self.to_type(fn.returns, ref.module, ctx)
                n_args = len(fn.args.posonlyargs) + len(fn.args.args)
                with_digits = n_args > 1 and not (
                    fn.args.defaults
                    and isinstance(fn.args.defaults[-1], ast.Constant)
                    and fn.args.defaults[-1].value is None
                )
                out.append(TypeRef("_SupportsRound2" if with_digits else "_SupportsRound1", (r,)))
        if "__contains__" in meths:
            out.append(TypeRef("Container", (TypeRef(ANY),)))
        if "__buffer__" in meths:
            out.append(TypeRef("Buffer"))
        if (rd := ret("read")) is not None:
            out.append(TypeRef("SupportsRead", (rd,)))
        if "write" in meths:
            fn = meths["write"][0]
            ps = [a for a in fn.args.posonlyargs + fn.args.args][1:]
            if ps:
                out.append(TypeRef("SupportsWrite", (self.to_type(ps[0].annotation, ref.module, ctx),)))
        if (en := ret("__enter__")) is not None:
            out.append(TypeRef("contextlib.AbstractContextManager", (en,)))
        if (gi := meths.get("__getitem__")) and "keys" in meths:
            fn = gi[0]
            ps = [a for a in fn.args.posonlyargs + fn.args.args][1:]
            if ps:
                k = self.to_type(ps[0].annotation, ref.module, ctx)
                v = self.to_type(fn.returns, ref.module, ctx)
                out.append(TypeRef("SupportsKeysAndGetItem", (k, v)))
        return out

    # -- firmas ----------------------------------------------------------------

    def signature(
        self,
        fn: ast.FunctionDef,
        module: str,
        ctx: ClassCtx | None,
        *,
        drop_first: bool = False,
    ) -> tuple[tuple[Param, ...], TypeRef, TypeRef | None]:
        """Devuelve (parámetros, retorno, tipo anotado del primer parámetro si existe)."""
        a = fn.args
        positional = [*a.posonlyargs, *a.args]
        n_pos_only = len(a.posonlyargs)
        defaults_start = len(positional) - len(a.defaults)
        params: list[Param] = []
        first_ann: TypeRef | None = None
        for i, arg in enumerate(positional):
            if i == 0 and drop_first:
                if arg.annotation is not None:
                    first_ann = self.to_type(arg.annotation, module, ctx)
                continue
            # Convención antigua de typeshed: `__x` es solo-posicional.
            kind: ParamKind = "pos" if i < n_pos_only or arg.arg.startswith("__") else "pos_kw"
            params.append(
                Param(
                    arg.arg.lstrip("_") or arg.arg,
                    self.to_type(arg.annotation, module, ctx),
                    i >= defaults_start,
                    kind,
                )
            )
        for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
            params.append(
                Param(arg.arg, self.to_type(arg.annotation, module, ctx), default is not None, "kw")
            )
        returns = self.to_type(fn.returns, module, ctx)
        return tuple(params), returns, first_ann


def _literal_type(item: ast.expr) -> TypeRef:
    """`Literal[...]` se conserva: solo lo rellena un literal con ese valor exacto."""
    if isinstance(item, ast.Constant):
        v = item.value
        if v is None:
            return TypeRef(NONE)
        if isinstance(v, (bool, int, str)):
            return literal(v)
    return TypeRef(ANY)


_TYPING_SPECIALS = frozenset(
    {
        "Any",
        "Optional",
        "Union",
        "Literal",
        "Callable",
        "Self",
        "NoReturn",
        "Never",
        "TypeGuard",
        "TypeIs",
        "Unpack",
        "Concatenate",
        *_TRANSPARENT,
    }
)
