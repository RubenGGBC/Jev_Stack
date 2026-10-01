"""Motor de síntesis: huecos, opciones y aplicación de decisiones sobre la IR.

El estado de búsqueda (`SearchState`) contiene el programa parcial y una agenda de
tareas. Las tareas de decisión (`StmtTask`, `SlotTask`, ...) producen opciones cerradas
para el chooser; las tareas automáticas (`BindTask`, `CheckTask`, ...) las ejecuta el
script. Cada rama de la búsqueda trabaja sobre una copia profunda del estado.
"""

from __future__ import annotations

import copy
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Literal

from jevsynth.candidates.control import ControlKind, control_option
from jevsynth.candidates.generate import fill_assignment, fillers, generate_candidates
from jevsynth.catalog.model import NONE, Catalog, Component, TypeRef
from jevsynth.chooser.base import Option
from jevsynth.emit.ir import (
    Assign,
    Call,
    Const,
    Expr,
    ExprStmt,
    For,
    HoleExpr,
    HoleStmt,
    If,
    ListComp,
    Name,
    Print,
    Program,
    Return,
    Stmt,
    With,
    walk_exprs,
)
from jevsynth.emit.lower import emit
from jevsynth.emit.names import base_name, elem_base_name, fresh
from jevsynth.literals.model import LiteralValue
from jevsynth.scope.model import Scope, Variable
from jevsynth.scope.typesys import Bindings, TypeSystem

CM = TypeRef("contextlib.AbstractContextManager", (TypeRef("Any"),))
BOOL = TypeRef("bool")
OBJECT = TypeRef("object")
NOFILTER = Option("control:nofilter", "sin filtro: quedarse con todos los elementos", "control")


@dataclass
class SynthTask:
    prompt: str
    params: list[tuple[str, TypeRef]] | None = None  # None → script
    returns: TypeRef | None = None
    max_steps: int = 6


@dataclass
class SynthConfig:
    width: int = 3  # ancho del haz
    branch: int = 4  # hijos que se generan por expansión (los que no caben van a la reserva)
    max_options: int = 30  # por encima, elección jerárquica
    done_threshold: float = 0.5
    max_expansions: int = 400  # límite duro de expansiones de la búsqueda
    max_depth: int = 2  # bloques anidados
    type_filter: bool = True
    description: Literal["short", "doc"] = "short"
    allow_nullary_constructors: bool = True
    inline: bool = True


# ---------------------------------------------------------------------------
# Tareas


@dataclass
class CallState:
    call: Call
    bindings: Bindings = field(default_factory=dict)


@dataclass
class Slot:
    """Lugar donde va una expresión: argumento i de una llamada o atributo de un nodo."""

    node: Call | Assign | Return | Print | For | With | If | ListComp
    key: int | str

    def set(self, value: Expr) -> None:
        if isinstance(self.key, int):
            assert isinstance(self.node, Call)
            self.node.args[self.key] = value
        else:
            setattr(self.node, self.key, value)

    def get(self) -> Expr | None:
        if isinstance(self.key, int):
            assert isinstance(self.node, Call)
            return self.node.args[self.key]
        value = getattr(self.node, self.key)
        assert value is None or isinstance(value, (Name, Const, Call, ListComp, HoleExpr))
        return value


@dataclass
class StmtTask:
    block: list[Stmt]
    scope: Scope
    depth: int
    where: Literal["top", "for", "with", "if"]
    with_var: str | None = None


@dataclass
class SlotTask:
    """Rellenar una expresión de tipo `formal` (argumento, valor de return/print...)."""

    slot: Slot
    formal: TypeRef
    scope: Scope
    cs: CallState | None  # ligaduras de la llamada a la que pertenece (si es argumento)
    nested: int  # niveles de llamada anidada permitidos
    hole: str
    must_use: str | None = None
    allow_nofilter: bool = False


@dataclass
class IterTask:
    """Elegir la colección a recorrer (for o comprensión) y crear la variable del bucle."""

    node: For | ListComp
    scope: Scope
    inner: Scope


@dataclass
class BindTask:
    """Tras rellenar los argumentos de una llamada de instrucción: nombrar y tipar el resultado."""

    stmt: Assign | ExprStmt
    cs: CallState
    scope: Scope


@dataclass
class CheckTask:
    """Tras rellenar una llamada anidada: comprobar su tipo contra el hueco que ocupa."""

    inner: CallState
    formal: TypeRef
    outer: CallState | None


@dataclass
class BindCtxTask:
    """Tras elegir el recurso del with: nombrar la variable `as` y tiparla."""

    stmt: With
    scope: Scope
    body: StmtTask


@dataclass
class BindListTask:
    stmt: Assign
    comp: ListComp
    inner: Scope
    scope: Scope


Task = StmtTask | SlotTask | IterTask | BindTask | CheckTask | BindCtxTask | BindListTask
DECISION_TASKS = (StmtTask, SlotTask, IterTask)


@dataclass
class SearchState:
    program: Program
    agenda: list[Task]
    taken: set[str]
    score: float = 0.0
    steps: int = 0
    decisions: tuple[str, ...] = ()
    done: bool = False

    def clone(self) -> SearchState:
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# Motor


@dataclass
class Choice:
    option: Option
    payload: object


class Engine:
    def __init__(
        self,
        task: SynthTask,
        catalog: Catalog,
        ts: TypeSystem,
        literals: Sequence[LiteralValue],
        config: SynthConfig,
    ) -> None:
        self.task = task
        self.catalog = catalog
        self.ts = ts
        self.literals = list(literals)
        self.config = config
        self.components = [c for c in catalog.components if c.kind != "constructor" or c.required_params]
        self.nullary = [
            c
            for c in catalog.components
            if c.kind == "constructor" and not c.required_params and config.allow_nullary_constructors
        ]
        self.group_of = {c.id: c.group for c in catalog.components}
        self._cand_cache: dict[tuple[object, ...], list[Component]] = {}
        self._virtual_cache: dict[tuple[object, ...], tuple[list[Variable], frozenset[str]]] = {}

    # -- estado inicial ----------------------------------------------------------

    def initial(self) -> SearchState:
        hole = HoleStmt()
        prog = Program(body=[hole], params=self.task.params, returns=self.task.returns)
        scope = Scope([Variable(n, t) for n, t in (self.task.params or [])])
        top = StmtTask(prog.body, scope, 0, "top")
        return SearchState(prog, [top], {n for n, _ in self.task.params or []})

    # -- opciones ------------------------------------------------------------------

    def option_for(self, c: Component) -> Option:
        desc = c.doc if self.config.description == "doc" and c.doc else c.summary
        return Option(c.id, f"{c.signature()}: {desc}", "component")

    @staticmethod
    def symbol_option(v: Variable) -> Option:
        return Option(f"sym:{v.name}", f"{v.name}: variable de tipo {v.type}", "symbol")

    @staticmethod
    def literal_option(lit: LiteralValue) -> Option:
        return Option(f"lit:{lit.code}", f"{lit.code}: literal de la petición", "literal")

    def _virtual(self, scope: Scope, must_use: str | None) -> tuple[Scope, set[str]]:
        """Scope ampliado con una variable virtual por cada tipo producible en un paso.

        Sirve para ofrecer en huecos con anidamiento componentes que solo se pueden
        rellenar con otra llamada (`float(row['age'])`). Devuelve el scope y los nombres
        virtuales que "usan" `must_use` (su llamada puede consumir la variable).
        """
        key = (tuple(v.type for v in scope.variables), tuple(v.name == must_use for v in scope.variables))
        hit = self._virtual_cache.get(key)
        if hit is not None:
            # Mismo perfil de tipos: reutilizar las variables virtuales con los nombres reales.
            virt, carrying_cached = hit
            ext = scope.copy()
            ext.variables.extend(virt)
            return ext, set(carrying_cached)
        ext = scope.copy()
        carrying: set[str] = set()
        seen: dict[TypeRef, str] = {}
        must_comps = {c.id for c in self._candidates(scope, must_use=must_use)} if must_use else set()
        for c in self._candidates(scope):
            if c.returns.name == NONE:
                continue
            b = fill_assignment(c, scope, self.literals, self.ts, type_filter=self.config.type_filter)
            ret = self.ts.resolve(c.returns, b or {})
            if ret.name in {"Any", NONE}:
                continue
            name = seen.get(ret)
            if name is None:
                name = f"⟨{ret}⟩"
                seen[ret] = name
                ext.variables.append(Variable(name, ret))
            if c.id in must_comps:
                carrying.add(name)
        self._virtual_cache[key] = (ext.variables[len(scope.variables) :], frozenset(carrying))
        return ext, carrying

    def _candidates(
        self,
        scope: Scope,
        *,
        returns: TypeRef | None = None,
        must_use: str | Collection[str] | None = None,
        nullary: bool = False,
    ) -> list[Component]:
        # Los candidatos solo dependen de los tipos del scope (y de los nombres en must_use).
        must_set = {must_use} if isinstance(must_use, str) else set(must_use or ())
        key = (
            tuple(v.type for v in scope.variables),
            tuple(v.name in must_set for v in scope.variables) if must_use is not None else None,
            returns,
        )
        cached = self._cand_cache.get(key)
        if cached is None:
            cached = generate_candidates(
                scope,
                self.components,
                self.literals,
                self.ts,
                type_filter=self.config.type_filter,
                returns=returns,
                must_use=must_use,
            )
            self._cand_cache[key] = cached
        comps = list(cached)
        if nullary and must_use is None:
            for c in self.nullary:
                if returns is None or self.ts.match(self.ts.resolve(c.returns, {}), returns, {}) is not None:
                    comps.append(c)
        return comps

    def hole_text(self, t: Task) -> str:
        if isinstance(t, StmtTask):
            where = {
                "top": "",
                "for": " dentro del bucle for",
                "with": " dentro del with",
                "if": " dentro del if",
            }
            return f"siguiente instrucción{where[t.where]}"
        if isinstance(t, SlotTask):
            return t.hole
        if isinstance(t, IterTask):
            return "colección a recorrer"
        return ""

    def options(self, st: SearchState, t: Task) -> list[Choice]:
        if isinstance(t, StmtTask):
            return self._stmt_options(st, t)
        if isinstance(t, SlotTask):
            return self._slot_options(t)
        assert isinstance(t, IterTask)
        out = []
        for v in reversed(t.scope.variables):
            if self.ts.element_type(v.type) is not None or not self.config.type_filter:
                out.append(Choice(self.symbol_option(v), v))
        return out

    def _stmt_options(self, st: SearchState, t: StmtTask) -> list[Choice]:
        out: list[Choice] = []
        body_len = len(t.block) - 1  # sin contar el hueco
        limit = st.steps >= self.task.max_steps
        if t.where == "top" and self.task.returns is not None and self._can_return(t.scope):
            out.append(Choice(control_option("return"), "return"))
        if t.where != "top" and body_len > 0:
            out.append(Choice(control_option("end"), "end"))
        if limit:
            return out
        comps = self._candidates(t.scope, nullary=True)
        out.extend(Choice(self.option_for(c), c) for c in comps)
        kinds: list[ControlKind] = []
        if t.depth < self.config.max_depth:
            if any(self.ts.element_type(v.type) is not None for v in t.scope.variables):
                kinds += ["for", "listcomp"]
            if self._candidates(t.scope, returns=CM):
                kinds.append("with")
            if any(self.ts.is_subtype(v.type, BOOL) for v in t.scope.variables) or self._candidates(
                t.scope, returns=BOOL
            ):
                kinds.append("if")
        elif any(self.ts.element_type(v.type) is not None for v in t.scope.variables):
            kinds.append("listcomp")
        if (self.task.returns is None or t.where != "top") and t.scope.variables:
            kinds.append("print")
        out.extend(Choice(control_option(k), k) for k in kinds)
        return out

    def _can_return(self, scope: Scope) -> bool:
        assert self.task.returns is not None
        return bool(fillers(self.task.returns, scope, self.literals, self.ts, {}))

    @staticmethod
    def _must_use(t: SlotTask) -> str | None:
        if t.must_use == "*" and isinstance(t.slot.node, ListComp):
            return t.slot.node.var  # la variable de la comprensión, ya creada
        return t.must_use

    def _slot_options(self, t: SlotTask) -> list[Choice]:
        b = t.cs.bindings if t.cs is not None else {}
        must = self._must_use(t)
        out: list[Choice] = []
        if t.allow_nofilter:
            out.append(Choice(NOFILTER, None))
        for f, _ in fillers(
            t.formal, t.scope, self.literals, self.ts, b, type_filter=self.config.type_filter
        ):
            if must is not None and not (isinstance(f, Variable) and f.name == must):
                continue  # en una comprensión solo tiene sentido la propia variable
            opt = self.symbol_option(f) if isinstance(f, Variable) else self.literal_option(f)
            out.append(Choice(opt, f))
        if t.nested > 0:
            formal = self.ts.subst(t.formal, b) if self.config.type_filter else None
            if formal is not None and (formal.is_var or formal.name == "Any"):
                formal = None  # cualquier tipo, se comprueba al cerrar la llamada
            if t.nested > 1:
                scope, carrying = self._virtual(t.scope, must)
                must_set: set[str] | None = ({must} | carrying) if must is not None else None
            else:
                scope, must_set = t.scope, ({must} if must is not None else None)
            for c in self._candidates(scope, returns=formal, must_use=must_set):
                if c.returns.name == NONE:
                    continue
                out.append(Choice(self.option_for(c), c))
        return out

    # -- aplicación ------------------------------------------------------------------

    def apply(self, st: SearchState, t: Task, ch: Choice) -> bool:
        """Aplica la decisión `ch` a la tarea `t` (ya retirada de la agenda). False = rama muerta."""
        st.decisions = (*st.decisions, ch.option.id)
        if isinstance(t, StmtTask):
            return self._apply_stmt(st, t, ch)
        if isinstance(t, SlotTask):
            return self._apply_slot(st, t, ch)
        assert isinstance(t, IterTask)
        v = ch.payload
        assert isinstance(v, Variable)
        elem = self.ts.element_type(v.type) or TypeRef("Any")
        name = fresh(elem_base_name(v.type, elem), st.taken)
        st.taken.add(name)
        t.node.iter = Name(v.name)
        t.node.var = name
        t.inner.add(Variable(name, elem))
        return True

    def _insert(self, t: StmtTask, stmt: Stmt) -> None:
        t.block.insert(len(t.block) - 1, stmt)

    def _call_tasks(
        self, cs: CallState, scope: Scope, nested: int, must_use: str | None = None
    ) -> list[Task]:
        c = cs.call.comp
        return [
            SlotTask(
                Slot(cs.call, i),
                p.type,
                scope,
                cs,
                nested,
                f"argumento '{p.name}' de {c.display_name} (tipo {p.type})",
                must_use=None,
            )
            for i, p in enumerate(c.required_params)
        ]

    def _apply_stmt(self, st: SearchState, t: StmtTask, ch: Choice) -> bool:
        p = ch.payload
        cont = StmtTask(t.block, t.scope, t.depth, t.where, t.with_var)
        if isinstance(p, Component):
            call = Call(p, [HoleExpr() for _ in p.required_params])
            cs = CallState(call)
            stmt: Assign | ExprStmt = ExprStmt(call) if p.returns.name == NONE else Assign("_", call)
            self._insert(t, stmt)
            st.steps += 1
            st.agenda[:0] = [*self._call_tasks(cs, t.scope, 0), BindTask(stmt, cs, t.scope), cont]
            return True
        kind = p
        if kind == "end":
            t.block.pop()
            if t.with_var is not None:
                t.scope.variables = [v for v in t.scope.variables if v.name != t.with_var]
            return True
        st.steps += 1
        if kind == "return":
            assert self.task.returns is not None
            ret = Return(HoleExpr())
            self._insert(t, ret)
            t.block.pop()  # tras return no hay más instrucciones
            st.agenda[:0] = [
                SlotTask(
                    Slot(ret, "value"),
                    self.task.returns,
                    t.scope,
                    None,
                    0,
                    f"valor a devolver (tipo {self.task.returns})",
                )
            ]
            return True
        if kind == "print":
            pr = Print(HoleExpr())
            self._insert(t, pr)
            st.agenda[:0] = [SlotTask(Slot(pr, "value"), OBJECT, t.scope, None, 0, "valor a mostrar"), cont]
            return True
        if kind == "for":
            loop = For("_", HoleExpr(), [HoleStmt()])
            self._insert(t, loop)
            inner = t.scope.copy()
            st.agenda[:0] = [
                IterTask(loop, t.scope, inner),
                StmtTask(loop.body, inner, t.depth + 1, "for"),
                cont,
            ]
            return True
        if kind == "listcomp":
            lc = ListComp(HoleExpr(), "_", HoleExpr(), None)
            assign = Assign("_", lc)
            self._insert(t, assign)
            inner = t.scope.copy()
            st.agenda[:0] = [
                IterTask(lc, t.scope, inner),
                SlotTask(
                    Slot(lc, "elem"),
                    TypeRef("Any"),
                    inner,
                    None,
                    2,
                    "expresión para cada elemento",
                    must_use="*",
                ),
                SlotTask(
                    Slot(lc, "cond"),
                    BOOL,
                    inner,
                    None,
                    2,
                    "condición para filtrar los elementos",
                    must_use="*",
                    allow_nofilter=True,
                ),
                BindListTask(assign, lc, inner, t.scope),
                cont,
            ]
            return True
        if kind == "with":
            w = With("_", HoleExpr(), [HoleStmt()])
            self._insert(t, w)
            body = StmtTask(w.body, t.scope, t.depth + 1, "with")
            st.agenda[:0] = [
                SlotTask(Slot(w, "ctx"), CM, t.scope, None, 1, "recurso a abrir en el with"),
                BindCtxTask(w, t.scope, body),
                body,
                cont,
            ]
            return True
        assert kind == "if"
        cond = If(HoleExpr(), [HoleStmt()])
        self._insert(t, cond)
        inner = t.scope.copy()
        st.agenda[:0] = [
            SlotTask(Slot(cond, "cond"), BOOL, t.scope, None, 1, "condición del if"),
            StmtTask(cond.body, inner, t.depth + 1, "if"),
            cont,
        ]
        return True

    def _apply_slot(self, st: SearchState, t: SlotTask, ch: Choice) -> bool:
        p = ch.payload
        if p is None:  # sin filtro
            assert isinstance(t.slot.node, ListComp)
            t.slot.node.cond = None
            return True
        b = t.cs.bindings if t.cs is not None else {}
        if isinstance(p, (Variable, LiteralValue)):
            if self.config.type_filter:
                nb = self.ts.match(p.type, t.formal, b, shallow=isinstance(p, LiteralValue))
                if nb is None:
                    return False
                if t.cs is not None:
                    t.cs.bindings = nb
            t.slot.set(Name(p.name) if isinstance(p, Variable) else Const(p))
            return True
        assert isinstance(p, Component)
        call = Call(p, [HoleExpr() for _ in p.required_params])
        inner = CallState(call)
        t.slot.set(call)
        tasks: list[Task] = [*self._call_tasks(inner, t.scope, t.nested - 1)]
        tasks.append(CheckTask(inner, t.formal, t.cs))
        st.agenda[:0] = tasks
        return True

    # -- tareas automáticas --------------------------------------------------------

    def run_auto(self, st: SearchState, t: Task) -> bool:
        if isinstance(t, BindTask):
            ret = self.ts.resolve(t.cs.call.comp.returns, t.cs.bindings)
            if isinstance(t.stmt, Assign):
                name = fresh(base_name(ret), st.taken)
                st.taken.add(name)
                t.stmt.target = name
                t.scope.add(Variable(name, ret))
            return True
        if isinstance(t, CheckTask):
            ret = self.ts.resolve(t.inner.call.comp.returns, t.inner.bindings)
            if not self.config.type_filter:
                return True
            b = t.outer.bindings if t.outer is not None else {}
            nb = self.ts.match(ret, t.formal, b)
            if nb is None:
                return False
            if t.outer is not None:
                t.outer.bindings = nb
            return True
        if isinstance(t, BindCtxTask):
            ctx_t = self._expr_type(t.stmt.ctx, t.scope)
            name = fresh(base_name(ctx_t), st.taken)
            st.taken.add(name)
            t.stmt.var = name
            t.scope.add(Variable(name, ctx_t))
            t.body.with_var = name
            return True
        if isinstance(t, BindListTask):
            lc = t.comp
            used = {
                x.name
                for e in [lc.elem] + ([lc.cond] if lc.cond else [])
                for x in walk_exprs(e)
                if isinstance(x, Name)
            }
            if lc.var not in used and not (isinstance(lc.elem, Name) and lc.cond is None):
                return False  # la comprensión debe usar su variable
            if isinstance(lc.elem, Name) and lc.elem.name == lc.var and lc.cond is None:
                return False  # [x for x in xs] no aporta nada
            elem_t = self._expr_type(lc.elem, t.inner)
            if elem_t.name == NONE:
                return False
            lt = TypeRef("list", (elem_t,))
            name = fresh(base_name(lt), st.taken)
            st.taken.add(name)
            t.stmt.target = name
            t.scope.add(Variable(name, lt))
            return True
        raise TypeError(f"tarea automática desconocida: {t!r}")

    def _expr_type(self, e: Expr, scope: Scope) -> TypeRef:
        if isinstance(e, Name):
            v = scope.get(e.name)
            return v.type if v is not None else TypeRef("Any")
        if isinstance(e, Const):
            return self.ts.widen(e.lit.type)
        if isinstance(e, Call):
            b: Bindings = {}
            for a, p in zip(e.args, e.comp.required_params, strict=True):
                nb = self.ts.match(self._expr_type(a, scope), p.type, b)
                b = nb if nb is not None else b
            return self.ts.resolve(e.comp.returns, b)
        return TypeRef("Any")

    # -- presentación ----------------------------------------------------------------

    def summary(self, st: SearchState, t: Task) -> str:
        """Código del programa parcial con el hueco actual marcado como ⟨?⟩."""
        marker: HoleExpr | HoleStmt | None = None
        if isinstance(t, StmtTask):
            last = t.block[-1]
            marker = last if isinstance(last, HoleStmt) else None
        elif isinstance(t, SlotTask):
            cur = t.slot.get()
            if cur is None and isinstance(t.slot.node, ListComp):
                t.slot.node.cond = HoleExpr()
                cur = t.slot.node.cond
            marker = cur if isinstance(cur, HoleExpr) else None
        elif isinstance(t, IterTask):
            marker = t.node.iter if isinstance(t.node.iter, HoleExpr) else None
        if marker is not None:
            marker.current = True
        try:
            return emit(st.program, imports=False).rstrip()
        finally:
            if marker is not None:
                marker.current = False

    def finalize(self, st: SearchState) -> str:
        return emit(st.program, inline=self.config.inline)


def is_decision(t: Task) -> bool:
    return isinstance(t, DECISION_TASKS)
