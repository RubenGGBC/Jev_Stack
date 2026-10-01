"""Casado de tipos: subtipos nominales y estructurales, uniones, Literal y TypeVar.

Simplificaciones deliberadas (prototipo):
- Todos los genéricos se tratan como covariantes.
- Un argumento genérico ausente (`list` a secas) equivale a `Any`.
- Un protocolo sin relación nominal se cumple si se cumplen todos sus supertipos.
"""

from __future__ import annotations

from collections.abc import Mapping

from jevsynth.catalog.model import ANY, LITERAL, NONE, UNION, ClassInfo, TypeRef, literal_base, literal_values

Bindings = dict[str, TypeRef]

# Promociones numéricas de PEP 484 (int vale donde se pide float).
PROMOTIONS = {"int": (TypeRef("float"),), "float": (TypeRef("complex"),)}
_UNFILLABLE = frozenset({"Never", "Callable", "type"})
COLLECTIONS = frozenset(
    {
        "Iterable", "Iterator", "Sequence", "MutableSequence", "Collection", "Container", "Sized",
        "Reversible", "Mapping", "MutableMapping", "SupportsKeysAndGetItem", "AbstractSet",
        "SupportsRead", "Buffer",
    }
)  # fmt: skip
_MAX_DEPTH = 12


class TypeSystem:
    def __init__(self, classes: Mapping[str, ClassInfo]) -> None:
        self.classes = dict(classes)
        self._supers_cache: dict[TypeRef, tuple[TypeRef, ...]] = {}
        self._ancestors_cache: dict[TypeRef, tuple[TypeRef, ...]] = {}
        self._ground_cache: dict[tuple[TypeRef, TypeRef, bool], bool] = {}

    # -- jerarquía -----------------------------------------------------------------

    def supertypes(self, t: TypeRef) -> tuple[TypeRef, ...]:
        """Supertipos directos de `t`, con las variables de la clase sustituidas."""
        cached = self._supers_cache.get(t)
        if cached is not None:
            return cached
        out: list[TypeRef] = []
        info = self.classes.get(t.name)
        if info is not None:
            b: Bindings = {}
            for i, tv in enumerate(info.typevars):
                b["~" + tv] = t.args[i] if i < len(t.args) else TypeRef(ANY)
            out.extend(self.subst(s, b) for s in info.supers)
        out.extend(PROMOTIONS.get(t.name, ()))
        result = tuple(out)
        self._supers_cache[t] = result
        return result

    def ancestors(self, t: TypeRef) -> tuple[TypeRef, ...]:
        """`t` y todos sus supertipos en orden de anchura (el más cercano primero)."""
        cached = self._ancestors_cache.get(t)
        if cached is not None:
            return cached
        seen: set[TypeRef] = {t}
        out = [t]
        i = 0
        while i < len(out) and len(out) < 200:
            for s in self.supertypes(out[i]):
                if s not in seen:
                    seen.add(s)
                    out.append(s)
            i += 1
        result = tuple(out)
        self._ancestors_cache[t] = result
        return result

    def is_subtype(self, actual: TypeRef, formal: TypeRef) -> bool:
        return self.match(actual, formal, {}) is not None

    # -- sustitución -----------------------------------------------------------------

    def subst(self, t: TypeRef, b: Mapping[str, TypeRef], *, unbound_any: bool = False) -> TypeRef:
        if t.is_var:
            if t.name in b:
                return b[t.name]
            return TypeRef(ANY) if unbound_any else t
        if not t.args or t.name == LITERAL:
            return t
        return TypeRef(t.name, tuple(self.subst(a, b, unbound_any=unbound_any) for a in t.args))

    def resolve(self, t: TypeRef, b: Mapping[str, TypeRef]) -> TypeRef:
        """Tipo concreto tras aplicar ligaduras; variables libres → Any."""
        from jevsynth.catalog.model import union

        r = self.subst(t, b, unbound_any=True)
        return union(*(self.widen(a) for a in r.args)) if r.name == UNION else r

    # -- casado ----------------------------------------------------------------------

    def match(
        self, actual: TypeRef, formal: TypeRef, b: Bindings, depth: int = 0, *, shallow: bool = False
    ) -> Bindings | None:
        """¿Puede un valor de tipo `actual` pasarse donde se pide `formal`?

        Devuelve las ligaduras de variables de tipo extendidas, o None si no encaja.
        `shallow`: no aceptar protocolos de colección por subtipado. Se usa para
        literales, para que `"age"` no rellene un `Iterable[str]` ni un `Sized`.
        """
        if depth > _MAX_DEPTH:
            return None
        if formal.is_ground:
            # Sin variables en `formal`, el resultado no depende de las ligaduras.
            key = (actual, formal, shallow)
            hit = self._ground_cache.get(key)
            if hit is None:
                hit = self._match(actual, formal, {}, depth, shallow) is not None
                self._ground_cache[key] = hit
            return b if hit else None
        return self._match(actual, formal, b, depth, shallow)

    def _match(
        self, actual: TypeRef, formal: TypeRef, b: Bindings, depth: int, shallow: bool
    ) -> Bindings | None:
        d = depth + 1
        if actual.name in _UNFILLABLE or formal.name in _UNFILLABLE:
            return b if actual.name == formal.name and actual.name != "Never" else None
        if formal.name == ANY or actual.name == ANY or actual.is_var:
            return b
        if formal.is_var:
            return self._match_var(actual, formal, b, d, shallow)
        if actual.name == UNION:
            cur: Bindings | None = b
            for m in actual.args:
                cur = self.match(m, formal, cur, d, shallow=shallow) if cur is not None else None
            return cur
        if formal.name == UNION:
            for m in formal.args:
                r = self.match(actual, m, b, d, shallow=shallow)
                if r is not None:
                    return r
            return None
        if formal.name == "object":
            return b
        if actual.name == LITERAL:
            if formal.name == LITERAL:
                allowed = literal_values(formal)
                return b if all(v in allowed for v in literal_values(actual)) else None
            cur = b
            for v in literal_values(actual):
                r = self.match(literal_base(v), formal, cur, d, shallow=shallow)
                if r is None:
                    return None
                cur = r
            return cur
        if formal.name == LITERAL or actual.name == NONE or formal.name == NONE:
            return b if actual.name == formal.name else None
        if shallow and formal.name in COLLECTIONS and actual.name != formal.name:
            return None
        return self._match_nominal(actual, formal, b, d)

    def _match_var(
        self, actual: TypeRef, formal: TypeRef, b: Bindings, d: int, shallow: bool = False
    ) -> Bindings | None:
        actual = self.widen(actual)
        bound = b.get(formal.name)
        if bound is not None:
            if self.match(actual, bound, b, d, shallow=shallow) is not None:
                return b
            if self.match(bound, actual, b, d) is not None:
                return {**b, formal.name: actual}  # ensanchar: max(int, float) → float
            return None
        if formal.args and not any(
            self.match(actual, c, b, d, shallow=shallow) is not None for c in formal.args
        ):
            return None
        return {**b, formal.name: actual}

    def _match_nominal(self, actual: TypeRef, formal: TypeRef, b: Bindings, d: int) -> Bindings | None:
        for t in self.ancestors(actual):
            if t.name == formal.name:
                # El supertipo más cercano decide: TextIOWrapper itera str aunque una base
                # lejana (_IOBase) declare Iterator[bytes].
                return self._match_args(t, formal, b, d)
        info = self.classes.get(formal.name)
        if info is not None and info.protocol and info.supers:
            # Protocolo compuesto (p. ej. _SupportsSumWithNoDefaultGiven): cumplir todos sus supertipos.
            fb: Bindings = {}
            for i, tv in enumerate(info.typevars):
                fb["~" + tv] = formal.args[i] if i < len(formal.args) else TypeRef(ANY)
            cur: Bindings | None = b
            for s in info.supers:
                cur = self.match(actual, self.subst(s, fb), cur, d) if cur is not None else None
            return cur
        return None

    def _match_args(self, actual: TypeRef, formal: TypeRef, b: Bindings, d: int) -> Bindings | None:
        if not actual.args or not formal.args:
            return b
        a_args, f_args = list(actual.args), list(formal.args)
        if actual.name == "tuple":
            a_var = a_args[-1].name == "..."
            f_var = f_args[-1].name == "..."
            if f_var:
                f_args = [f_args[0]] * (len(a_args) - (1 if a_var else 0))
                a_args = a_args[:-1] if a_var else a_args
            elif a_var:
                a_args = [a_args[0]] * len(f_args)
        if len(a_args) != len(f_args):
            return None
        cur: Bindings | None = b
        for a, f in zip(a_args, f_args, strict=True):
            cur = self.match(a, f, cur, d) if cur is not None else None
        return cur

    @staticmethod
    def widen(t: TypeRef) -> TypeRef:
        """Un literal concreto se liga a su tipo base (T := str, no Literal["age"])."""
        if t.name == LITERAL:
            from jevsynth.catalog.model import union

            return union(*(literal_base(v) for v in literal_values(t)))
        return t

    # -- utilidades para el sintetizador ----------------------------------------------

    def element_type(self, t: TypeRef) -> TypeRef | None:
        """Tipo de los elementos al iterar `t`, o None si no es iterable."""
        b = self.match(t, TypeRef("Iterable", (TypeRef("~_Elem"),)), {})
        if b is None:
            return None
        return self.resolve(TypeRef("~_Elem"), b)
