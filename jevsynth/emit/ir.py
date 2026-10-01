"""Representación intermedia del programa parcial.

Es un árbol pequeño y mutable (se copia por rama de búsqueda) que se baja a `ast`
para emitir con `ast.unparse`. Los huecos son nodos `HoleExpr`/`HoleStmt`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jevsynth.catalog.model import Component, TypeRef
from jevsynth.literals.model import LiteralValue


@dataclass
class Name:
    name: str


@dataclass
class Const:
    lit: LiteralValue


@dataclass
class Call:
    comp: Component
    args: list[Expr]  # alineados con comp.required_params


@dataclass
class ListComp:
    elem: Expr
    var: str
    iter: Expr
    cond: Expr | None = None


CURRENT_HOLE = "⟨?⟩"


@dataclass
class HoleExpr:
    current: bool = False  # el hueco que se está decidiendo ahora (se emite como ⟨?⟩)


Expr = Name | Const | Call | ListComp | HoleExpr


@dataclass
class Assign:
    target: str
    value: Expr


@dataclass
class ExprStmt:
    value: Expr


@dataclass
class Return:
    value: Expr


@dataclass
class Print:
    value: Expr


@dataclass
class For:
    var: str
    iter: Expr
    body: list[Stmt] = field(default_factory=list)


@dataclass
class With:
    var: str
    ctx: Expr
    body: list[Stmt] = field(default_factory=list)


@dataclass
class If:
    cond: Expr
    body: list[Stmt] = field(default_factory=list)


@dataclass
class HoleStmt:
    current: bool = False


Stmt = Assign | ExprStmt | Return | Print | For | With | If | HoleStmt


@dataclass
class Program:
    """Función `name(params) -> returns` o, si `params is None`, un script."""

    body: list[Stmt] = field(default_factory=list)
    params: list[tuple[str, TypeRef]] | None = None
    returns: TypeRef | None = None
    name: str = "solve"

    @property
    def is_function(self) -> bool:
        return self.params is not None


def sub_exprs(e: Expr) -> list[Expr]:
    if isinstance(e, Call):
        return list(e.args)
    if isinstance(e, ListComp):
        return [e.elem, e.iter] + ([e.cond] if e.cond is not None else [])
    return []


def stmt_exprs(s: Stmt) -> list[Expr]:
    if isinstance(s, (Assign, ExprStmt, Return, Print)):
        return [s.value]
    if isinstance(s, For):
        return [s.iter]
    if isinstance(s, With):
        return [s.ctx]
    if isinstance(s, If):
        return [s.cond]
    return []


def stmt_body(s: Stmt) -> list[Stmt] | None:
    return s.body if isinstance(s, (For, With, If)) else None


def walk_exprs(e: Expr) -> list[Expr]:
    out = [e]
    for x in sub_exprs(e):
        out.extend(walk_exprs(x))
    return out


def walk_stmts(body: list[Stmt]) -> list[Stmt]:
    out: list[Stmt] = []
    for s in body:
        out.append(s)
        inner = stmt_body(s)
        if inner is not None:
            out.extend(walk_stmts(inner))
    return out


def components_used(p: Program) -> list[Component]:
    out: list[Component] = []
    for s in walk_stmts(p.body):
        for e in stmt_exprs(s):
            for x in walk_exprs(e):
                if isinstance(x, Call):
                    out.append(x.comp)
    return out


def has_holes(p: Program) -> bool:
    for s in walk_stmts(p.body):
        if isinstance(s, HoleStmt):
            return True
        for e in stmt_exprs(s):
            if any(isinstance(x, HoleExpr) for x in walk_exprs(e)):
                return True
    return False
