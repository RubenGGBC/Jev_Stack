"""Generación y filtrado de candidatos para un hueco."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence

from jevsynth.catalog.model import Component, TypeRef
from jevsynth.literals.model import LiteralValue
from jevsynth.scope.model import Scope, Variable
from jevsynth.scope.typesys import Bindings, TypeSystem

Filler = Variable | LiteralValue


def filler_type(f: Filler) -> TypeRef:
    return f.type


def fillers(
    formal: TypeRef,
    scope: Scope,
    literals: Iterable[LiteralValue],
    ts: TypeSystem,
    b: Bindings,
    *,
    type_filter: bool = True,
) -> list[tuple[Filler, Bindings]]:
    """Símbolos (del más reciente al más antiguo) y literales que encajan en `formal`."""
    out: list[tuple[Filler, Bindings]] = []
    pool: list[Filler] = [*reversed(scope.variables), *literals]
    for f in pool:
        if not type_filter:
            r: Bindings | None = b
        else:
            r = ts.match(f.type, formal, b, shallow=isinstance(f, LiteralValue))
        if r is not None:
            out.append((f, r))
    return out


FillerMemo = dict[tuple[TypeRef, tuple[tuple[str, TypeRef], ...]], list[tuple[Filler, Bindings]]]


def fill_assignment(
    comp: Component,
    scope: Scope,
    literals: Sequence[LiteralValue],
    ts: TypeSystem,
    *,
    type_filter: bool = True,
    must_use: str | Collection[str] | None = None,
    memo: FillerMemo | None = None,
) -> Bindings | None:
    """Busca una asignación completa de los parámetros obligatorios (con retroceso).

    `must_use`: nombre (o nombres) de variable de los que al menos uno debe aparecer como
    argumento (p. ej. la variable de una comprensión). Devuelve las ligaduras de una
    asignación válida o None.
    """
    params = comp.required_params
    must = {must_use} if isinstance(must_use, str) else set(must_use) if must_use is not None else None
    if not type_filter:
        pool_size = len(scope.variables) + len(literals)
        if must is not None and not any(scope.get(m) is not None for m in must):
            return None
        return {} if not params or pool_size > 0 else None

    def go(i: int, b: Bindings, used: bool) -> Bindings | None:
        if i == len(params):
            return b if used or must is None else None
        formal = params[i].type
        if memo is not None:
            key = (formal, tuple(sorted(b.items(), key=lambda kv: kv[0])) if b else ())
            opts = memo.get(key)
            if opts is None:
                opts = memo[key] = fillers(formal, scope, literals, ts, b)
        else:
            opts = fillers(formal, scope, literals, ts, b)
        for f, nb in opts:
            r = go(i + 1, nb, used or (must is not None and isinstance(f, Variable) and f.name in must))
            if r is not None:
                return r
        return None

    return go(0, {}, False)


def generate_candidates(
    scope: Scope,
    catalog: Iterable[Component],
    literals: Sequence[LiteralValue],
    ts: TypeSystem,
    *,
    type_filter: bool = True,
    returns: TypeRef | None = None,
    must_use: str | Collection[str] | None = None,
    allow_nullary: bool = False,
) -> list[Component]:
    """Componentes cuyos parámetros obligatorios se pueden rellenar con scope + literales.

    `returns`: si se da, solo los que devuelven algo compatible con ese tipo.
    `allow_nullary`: incluir componentes sin parámetros obligatorios (`list()`, `Path.cwd()`).
    """
    out: list[Component] = []
    memo: FillerMemo = {}
    for c in catalog:
        if not c.required_params and not allow_nullary:
            continue
        b = fill_assignment(c, scope, literals, ts, type_filter=type_filter, must_use=must_use, memo=memo)
        if b is None:
            continue
        if returns is not None and type_filter:
            ret = ts.resolve(c.returns, b)
            if ts.match(ret, returns, {}) is None:
                continue
        out.append(c)
    return out
