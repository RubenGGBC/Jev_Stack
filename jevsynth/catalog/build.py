"""Construcción offline del catálogo de la stdlib.

    python -m jevsynth.catalog.build [--typeshed RUTA] [--out RUTA]

Combina tres fuentes: el espacio de nombres real del módulo (qué existe), los stubs de
typeshed (tipos) y los docstrings en tiempo de ejecución (descripción, saneada).
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from jevsynth.catalog import operators
from jevsynth.catalog.model import ANY, Catalog, ClassInfo, Component, ComponentKind, Param, TypeRef
from jevsynth.catalog.sanitize import long_doc, summarize
from jevsynth.catalog.stubs import (
    BARE_MODULES,
    ClassCtx,
    ClassRef,
    FuncSym,
    StubIndex,
    default_typeshed,
)

MODULES = (
    "builtins",
    "csv",
    "json",
    "statistics",
    "pathlib",
    "re",
    "collections",
    "itertools",
)

# Clases que no están en esos módulos pero que devuelven sus funciones y cuyos métodos
# hacen falta (p. ej. `f.read()` sobre lo que devuelve `open`).
EXTRA_CLASSES = ("io.TextIOWrapper",)

# Nombres excluidos: peligrosos, interactivos o de introspección.
EXCLUDED = frozenset(
    {
        "eval", "exec", "compile", "__import__", "breakpoint", "input", "help", "exit", "quit",
        "copyright", "credits", "license", "globals", "locals", "vars", "setattr", "delattr",
        "getattr", "hasattr", "id", "hash", "dir", "print", "object", "type", "super",
        "property", "staticmethod", "classmethod", "memoryview", "slice", "bytearray",
        "complex", "callable", "issubclass", "isinstance", "aiter", "anext", "open_code",
        # cambian estado global del módulo
        "register_dialect", "unregister_dialect", "field_size_limit", "purge",
    }
)  # fmt: skip

DEFAULT_OUT = Path(__file__).parent / "data" / "stdlib.json"


def _public(name: str) -> bool:
    return not name.startswith("_")


def _runtime_doc(obj: object) -> str | None:
    try:
        return inspect.getdoc(obj)
    except Exception:  # pragma: no cover - objetos raros de C
        return None


class Builder:
    def __init__(self, index: StubIndex) -> None:
        self.ix = index
        self.components: list[Component] = []
        self._seen: set[tuple[str, str]] = set()
        self.harvested: set[str] = set()

    # -- utilidades -------------------------------------------------------------

    def _emit(
        self,
        *,
        qualname: str,
        params: tuple[Param, ...],
        returns: TypeRef,
        kind: ComponentKind,
        module: str,
        group: str,
        doc: str | None,
        overload: int,
    ) -> None:
        display = qualname.removeprefix("builtins.")
        summary = summarize(doc, f"{display} ({kind}).")
        variants = [(params, "")]
        extra = _extended(params)
        if extra is not None:
            variants.append(extra)
        for ps, suffix in variants:
            key = (qualname, repr((ps, returns)))
            if key in self._seen:
                continue
            self._seen.add(key)
            cid = qualname + (f"@{overload}" if overload else "") + suffix
            self.components.append(
                Component(
                    qualname=qualname,
                    params=ps,
                    returns=returns,
                    summary=summary,
                    id=cid,
                    kind=kind,
                    module=module,
                    group=group,
                    doc=long_doc(doc, summary),
                )
            )

    # -- funciones --------------------------------------------------------------

    def add_function(self, module: str, name: str, fs: FuncSym, runtime: object) -> None:
        stub_module = self._defining_module(module, name)
        for k, fn in enumerate(fs.nodes):
            params, returns, _ = self.ix.signature(fn, stub_module, None)
            params = tuple(p for p in params if p.name not in {"args", "kwargs"} or p.has_default)
            self._emit(
                qualname=f"{module}.{name}",
                params=params,
                returns=returns,
                kind="function",
                module="" if module == "builtins" else module,
                group=module,
                doc=_runtime_doc(runtime),
                overload=k,
            )

    def _defining_module(self, module: str, name: str) -> str:
        """Módulo stub donde está definido `name` (siguiendo reexportaciones)."""
        mod = self.ix.module(module)
        seen = set()
        while mod is not None and (mod.name, name) not in seen:
            seen.add((mod.name, name))
            sym = mod.symbols.get(name)
            from jevsynth.catalog.stubs import ImportSym

            if isinstance(sym, ImportSym):
                mod, name = self.ix.module(sym.module), sym.name
                continue
            if sym is None:
                for star in mod.star_imports:
                    star_mod = self.ix.module(star)
                    if star_mod is not None and name in star_mod.symbols:
                        mod = star_mod
                        break
                else:
                    return mod.name
                continue
            return mod.name
        return module

    # -- clases -----------------------------------------------------------------

    def add_class(self, module: str, name: str, ref: ClassRef, runtime: type) -> None:
        if isinstance(runtime, type) and issubclass(runtime, BaseException):
            return
        # Solo clases propias de los módulos objetivo, no reexportaciones (statistics.Decimal).
        if ref.module.lstrip("_") not in MODULES:
            return
        self.harvested.add(ref.canonical)
        ctx = self.ix.class_ctx(ref)
        qual = f"{module}.{name}"
        group = qual.removeprefix("builtins.")
        public_mod = "" if module == "builtins" else module
        self._add_constructor(qual, ref, ctx, public_mod, group, runtime)
        self._add_methods(qual, ref, ctx, public_mod, group, runtime)

    def _add_constructor(
        self, qual: str, ref: ClassRef, ctx: ClassCtx, module: str, group: str, runtime: type
    ) -> None:
        found = self._find_ctor(ref)
        if found is None:
            return
        owner, fns = found
        owner_ctx = self.ix.class_ctx(owner)
        for k, fn in enumerate(fns):
            params, returns, first = self.ix.signature(fn, owner.module, owner_ctx, drop_first=True)
            if fn.name == "__init__":
                returns = first if first is not None and first.name == ref.canonical else ctx.self_type
            elif returns.name == ANY or returns == owner_ctx.self_type:
                returns = ctx.self_type
            params = tuple(p for p in params if p.name not in {"kwargs"})
            self._emit(
                qualname=qual,
                params=params,
                returns=returns,
                kind="constructor",
                module=module,
                group=module or "builtins",
                doc=_runtime_doc(runtime),
                overload=k,
            )

    def _find_ctor(self, ref: ClassRef) -> tuple[ClassRef, list[ast.FunctionDef]] | None:
        for cls in self._mro(ref):
            if cls.canonical == "object":
                return None
            meths = self.ix.methods(cls)
            for dunder in ("__new__", "__init__"):
                fns = meths.get(dunder)
                if fns and any(len(f.args.args) + len(f.args.posonlyargs) > 1 or f.args.vararg for f in fns):
                    return cls, fns
        return None

    def _mro(self, ref: ClassRef) -> list[ClassRef]:
        out: list[ClassRef] = []
        stack = [ref]
        while stack:
            cls = stack.pop(0)
            if cls in out:
                continue
            out.append(cls)
            for b in cls.node.bases:
                base = b.value if isinstance(b, ast.Subscript) else b
                r = self.ix._resolve_expr(base, cls.module)
                if isinstance(r, ClassRef):
                    stack.append(r)
        return out

    def _add_methods(
        self, qual: str, ref: ClassRef, ctx: ClassCtx, module: str, group: str, runtime: type
    ) -> None:
        done: set[str] = set()
        for cls in self._mro(ref):
            if cls is not ref and (cls.canonical in self.harvested or cls.module in BARE_MODULES):
                continue
            if cls.canonical == "object":
                continue
            cls_ctx = self.ix.class_ctx(cls)
            for mname, fns in self.ix.methods(cls).items():
                if not _public(mname) or mname in done or not hasattr(runtime, mname):
                    continue
                done.add(mname)
                decos = {ast.unparse(d).rsplit(".", 1)[-1] for d in fns[0].decorator_list}
                kind: ComponentKind
                if "property" in decos:
                    kind = "property"
                elif "classmethod" in decos:
                    kind = "classmethod"
                elif "staticmethod" in decos:
                    kind = "staticmethod"
                else:
                    kind = "method"
                doc = _runtime_doc(getattr(runtime, mname, None))
                for k, fn in enumerate(fns):
                    params, returns, first = self.ix.signature(
                        fn, cls.module, cls_ctx, drop_first=kind != "staticmethod"
                    )
                    if returns == cls_ctx.self_type and cls is not ref:
                        returns = ctx.self_type
                    if kind in {"method", "property"}:
                        recv = first if first is not None and cls is ref else ctx.self_type
                        params = (Param("self", recv, False, "pos"), *params)
                    self._emit(
                        qualname=f"{qual}.{mname}",
                        params=params,
                        returns=returns,
                        kind=kind,
                        module=module if kind in {"classmethod", "staticmethod"} else "",
                        group=group,
                        doc=doc,
                        overload=k,
                    )

    # -- módulos ----------------------------------------------------------------

    def add_module(self, module: str) -> None:
        runtime_mod = importlib.import_module(module)
        for name in sorted(dir(runtime_mod)):
            if not _public(name) or name in EXCLUDED:
                continue
            obj = getattr(runtime_mod, name)
            if inspect.ismodule(obj):
                continue
            r = self.ix.lookup(module, name)
            if isinstance(r, FuncSym) and callable(obj):
                self.add_function(module, name, r, obj)
            elif isinstance(r, ClassRef) and isinstance(obj, type):
                self.add_class(module, name, r, obj)

    def add_extra_class(self, canonical: str) -> None:
        ref = self.ix.class_ref(canonical)
        if ref is None:
            raise LookupError(f"no encuentro la clase {canonical} en typeshed")
        mod_name, _, cls_name = canonical.rpartition(".")
        runtime = getattr(importlib.import_module(mod_name), cls_name)
        self.harvested.add(ref.canonical)
        ctx = self.ix.class_ctx(ref)
        self._add_methods(canonical, ref, ctx, "", canonical, runtime)

    # -- jerarquía de clases ----------------------------------------------------

    def class_table(self, comps: Iterable[Component]) -> dict[str, ClassInfo]:
        pending = {t.name for c in comps for t in _types_of(c)}
        table: dict[str, ClassInfo] = {}
        while pending:
            name = pending.pop()
            if name in table or name in _NON_CLASSES or name.startswith("~"):
                continue
            info = self.ix.class_info(name)
            if info is None:
                continue
            table[name] = info
            for s in info.supers:
                for t in s.walk():
                    if t.name not in table:
                        pending.add(t.name)
        return table


_NON_CLASSES = frozenset({ANY, "None", "object", "Never", "Union", "Callable", "..."})


def _types_of(c: Component) -> list[TypeRef]:
    out = list(c.returns.walk())
    for p in c.params:
        out.extend(p.type.walk())
    return out


def _extended(params: tuple[Param, ...]) -> tuple[tuple[Param, ...], str] | None:
    """Variante que también rellena el primer parámetro opcional posicional."""
    for i, p in enumerate(params):
        if p.has_default and p.kind in {"pos", "pos_kw"}:
            if p.type.name == "None":
                return None
            if any(not q.has_default for q in params[i + 1 :] if q.kind != "kw"):
                return None
            new = (*params[:i], replace(p, has_default=False), *params[i + 1 :])
            return new, f"+{p.name}"
    return None


def build(typeshed: Path | None = None) -> Catalog:
    ix = StubIndex(typeshed or default_typeshed())
    b = Builder(ix)
    for m in MODULES:
        b.add_module(m)
    for c in EXTRA_CLASSES:
        b.add_extra_class(c)
    comps = [*b.components, *operators.components()]
    return Catalog(tuple(comps), b.class_table(comps))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--typeshed", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    cat = build(args.typeshed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cat.save(args.out)
    typed = sum(c.is_typed() for c in cat.components)
    print(
        f"{len(cat.components)} componentes ({typed} con firma tipada), "
        f"{len(cat.classes)} clases → {args.out}"
    )


if __name__ == "__main__":
    main()
