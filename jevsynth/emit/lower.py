"""Bajada de la IR a `ast` y emisión con `ast.unparse`."""

from __future__ import annotations

import ast
import copy
import re

from jevsynth.catalog.model import Component, TypeRef
from jevsynth.catalog.operators import BINARY
from jevsynth.emit.ir import (
    CURRENT_HOLE,
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
    components_used,
    stmt_body,
    stmt_exprs,
    walk_exprs,
    walk_stmts,
)

_CMP = {
    "<": ast.Lt,
    "<=": ast.LtE,
    ">": ast.Gt,
    ">=": ast.GtE,
    "==": ast.Eq,
    "!=": ast.NotEq,
}
_BIN = {
    "+": ast.Add,
    "-": ast.Sub,
    "*": ast.Mult,
    "/": ast.Div,
    "//": ast.FloorDiv,
    "%": ast.Mod,
}


def _dotted(path: str) -> ast.expr:
    parts = path.split(".")
    node: ast.expr = ast.Name(parts[0], ast.Load())
    for p in parts[1:]:
        node = ast.Attribute(node, p, ast.Load())
    return node


def _callable_path(c: Component) -> str:
    return c.qualname.removeprefix("builtins.")


def lower_expr(e: Expr) -> ast.expr:
    if isinstance(e, Name):
        return ast.Name(e.name, ast.Load())
    if isinstance(e, Const):
        return ast.Constant(e.lit.value)
    if isinstance(e, HoleExpr):
        return ast.Name(CURRENT_HOLE, ast.Load()) if e.current else ast.Constant(Ellipsis)
    if isinstance(e, ListComp):
        gen = ast.comprehension(
            target=ast.Name(e.var, ast.Store()),
            iter=lower_expr(e.iter),
            ifs=[lower_expr(e.cond)] if e.cond is not None else [],
            is_async=0,
        )
        return ast.ListComp(lower_expr(e.elem), [gen])
    return _lower_call(e)


def _lower_call(e: Call) -> ast.expr:
    c = e.comp
    args = [lower_expr(a) for a in e.args]
    params = c.required_params
    if c.kind == "operator":
        return _lower_operator(c.attr, args)
    if c.kind == "property":
        return ast.Attribute(args[0], c.attr, ast.Load())
    if c.kind == "method":
        func: ast.expr = ast.Attribute(args[0], c.attr, ast.Load())
        args, params = args[1:], params[1:]
    else:
        func = _dotted(_callable_path(c))
    pos = [a for a, p in zip(args, params, strict=True) if p.kind != "kw"]
    kws = [ast.keyword(p.name, a) for a, p in zip(args, params, strict=True) if p.kind == "kw"]
    return ast.Call(func, pos, kws)


def _lower_operator(name: str, args: list[ast.expr]) -> ast.expr:
    if name == "getitem":
        return ast.Subscript(args[0], args[1], ast.Load())
    if name == "contains":
        return ast.Compare(args[1], [ast.In()], [args[0]])
    if name == "not_":
        return ast.UnaryOp(ast.Not(), args[0])
    if name == "neg":
        return ast.UnaryOp(ast.USub(), args[0])
    sym = BINARY[name]
    if sym in _CMP:
        return ast.Compare(args[0], [_CMP[sym]()], [args[1]])
    return ast.BinOp(args[0], _BIN[sym](), args[1])


def lower_block(body: list[Stmt]) -> list[ast.stmt]:
    out = [lower_stmt(s) for s in body]
    return out or [ast.Pass()]


def lower_stmt(s: Stmt) -> ast.stmt:
    if isinstance(s, Assign):
        return ast.Assign([ast.Name(s.target, ast.Store())], lower_expr(s.value), lineno=0)
    if isinstance(s, ExprStmt):
        return ast.Expr(lower_expr(s.value))
    if isinstance(s, Return):
        return ast.Return(lower_expr(s.value))
    if isinstance(s, Print):
        return ast.Expr(ast.Call(ast.Name("print", ast.Load()), [lower_expr(s.value)], []))
    if isinstance(s, For):
        return ast.For(ast.Name(s.var, ast.Store()), lower_expr(s.iter), lower_block(s.body), [], lineno=0)
    if isinstance(s, With):
        item = ast.withitem(lower_expr(s.ctx), ast.Name(s.var, ast.Store()))
        return ast.With([item], lower_block(s.body), lineno=0)
    if isinstance(s, If):
        return ast.If(lower_expr(s.cond), lower_block(s.body), [])
    assert isinstance(s, HoleStmt)
    return ast.Expr(ast.Name(CURRENT_HOLE, ast.Load()) if s.current else ast.Constant(Ellipsis))


_SIMPLE_ANNOTATION = re.compile(r"[A-Za-z_\[\], |]+")
_BUILTIN_TYPES = frozenset({"str", "int", "float", "bool", "list", "dict", "set", "tuple", "None"})


def _annotation(t: TypeRef | None) -> ast.expr | None:
    if t is None:
        return None
    text = str(t)
    names = set(re.findall(r"[A-Za-z_][A-Za-z_0-9.]*", text))
    if not _SIMPLE_ANNOTATION.fullmatch(text) or not names <= _BUILTIN_TYPES:
        return None
    return ast.parse(text, mode="eval").body


def lower_program(p: Program, *, imports: bool = True) -> ast.Module:
    modules = sorted({c.module for c in components_used(p) if c.module and c.kind != "method"})
    import_stmts: list[ast.stmt] = [ast.Import([ast.alias(m)]) for m in modules] if imports else []
    body = lower_block(p.body)
    if p.params is None:
        mod = ast.Module([*import_stmts, *body], [])
    else:
        args = ast.arguments(
            posonlyargs=[],
            args=[ast.arg(n, _annotation(t)) for n, t in p.params],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        )
        fn = ast.FunctionDef(p.name, args, body, [], _annotation(p.returns), lineno=0)
        mod = ast.Module([*import_stmts, fn], [])
    return ast.fix_missing_locations(mod)


def emit(p: Program, *, inline: bool = False, imports: bool = True) -> str:
    """Código Python del programa. Con `inline`, se plegan temporales de un solo uso."""
    if inline:
        p = inline_temporaries(p)
    return ast.unparse(lower_program(p, imports=imports)) + "\n"


# ---------------------------------------------------------------------------
# Plegado de temporales


def _eager(s: Stmt) -> list[Expr]:
    """Expresiones de `s` evaluadas una sola vez, de inmediato, al ejecutar `s`."""
    out: list[Expr] = []

    def visit(e: Expr) -> None:
        out.append(e)
        if isinstance(e, Call):
            for a in e.args:
                visit(a)
        elif isinstance(e, ListComp):
            visit(e.iter)  # elem y cond se evalúan por elemento: no se pliega ahí

    for e in stmt_exprs(s):
        visit(e)
    return out


def _uses(p: Program) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in walk_stmts(p.body):
        for e in stmt_exprs(s):
            for x in walk_exprs(e):
                if isinstance(x, Name):
                    counts[x.name] = counts.get(x.name, 0) + 1
    return counts


def _replace(e: Expr, name: str, value: Expr) -> Expr:
    if isinstance(e, Name) and e.name == name:
        return value
    if isinstance(e, Call):
        e.args = [_replace(a, name, value) for a in e.args]
    elif isinstance(e, ListComp):
        e.iter = _replace(e.iter, name, value)
    return e


def _set_exprs(s: Stmt, name: str, value: Expr) -> None:
    if isinstance(s, (Assign, ExprStmt, Return, Print)):
        s.value = _replace(s.value, name, value)
    elif isinstance(s, For):
        s.iter = _replace(s.iter, name, value)
    elif isinstance(s, With):
        s.ctx = _replace(s.ctx, name, value)
    elif isinstance(s, If):
        s.cond = _replace(s.cond, name, value)


def inline_temporaries(p: Program) -> Program:
    p = copy.deepcopy(p)
    changed = True
    while changed:
        changed = False
        uses = _uses(p)
        for block in [p.body, *(b for s in walk_stmts(p.body) if (b := stmt_body(s)) is not None)]:
            for i in range(len(block) - 1, 0, -1):
                prev, nxt = block[i - 1], block[i]
                if not isinstance(prev, Assign) or uses.get(prev.target, 0) != 1:
                    continue
                if not any(isinstance(x, Name) and x.name == prev.target for x in _eager(nxt)):
                    continue
                if any(isinstance(x, HoleExpr) for x in walk_exprs(prev.value)):
                    continue
                _set_exprs(nxt, prev.target, prev.value)
                del block[i - 1]
                changed = True
                break
            if changed:
                break
    return p
