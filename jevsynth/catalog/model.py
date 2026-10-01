"""Modelo de datos del catálogo: tipos, parámetros, componentes y jerarquía de clases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

# Nombres especiales de TypeRef:
#   "Any", "None", "object", "Never"     tipos básicos
#   "Union"                              args = miembros
#   "Callable", "type"                   no se pueden rellenar con símbolos ni literales
#   "tuple"                              args; un último arg "..." indica tuple[X, ...]
#   "~Nombre"                            variable de tipo; args = cotas/restricciones admitidas
ANY = "Any"
NONE = "None"
UNION = "Union"

TypeJSON: TypeAlias = "str | list[TypeJSON]"


@dataclass(frozen=True)
class TypeRef:
    name: str
    args: tuple[TypeRef, ...] = ()

    def __deepcopy__(self, memo: dict[int, object]) -> TypeRef:
        return self

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, TypeRef) or hash(self) != hash(other):
            return False
        return self.name == other.name and self.args == other.args

    def __hash__(self) -> int:
        # Hash cacheado: TypeRef es inmutable y se usa mucho como clave.
        h: int | None = self.__dict__.get("_hash")
        if h is None:
            h = hash((self.name, self.args))
            object.__setattr__(self, "_hash", h)
        return h

    @property
    def is_var(self) -> bool:
        return self.name.startswith("~")

    @property
    def is_ground(self) -> bool:
        """Sin variables de tipo en ninguna parte."""
        g: bool | None = self.__dict__.get("_ground")
        if g is None:
            g = not self.is_var and all(a.is_ground for a in self.args)
            object.__setattr__(self, "_ground", g)
        return g

    def __str__(self) -> str:
        if self.name == UNION:
            return " | ".join(str(a) for a in self.args)
        if self.is_var:
            return self.name[1:]
        if self.name == LITERAL:
            return f"Literal[{', '.join(a.name for a in self.args)}]"
        if self.args:
            return f"{self.name}[{', '.join(str(a) for a in self.args)}]"
        return self.name

    def walk(self) -> list[TypeRef]:
        out: list[TypeRef] = [self]
        for a in self.args:
            out.extend(a.walk())
        return out

    def to_json(self) -> TypeJSON:
        if not self.args:
            return self.name
        return [self.name, *(a.to_json() for a in self.args)]

    @staticmethod
    def from_json(data: TypeJSON) -> TypeRef:
        if isinstance(data, str):
            return TypeRef(data)
        head = data[0]
        if not isinstance(head, str):
            raise ValueError(f"TypeRef JSON inválido: {data!r}")
        return TypeRef(head, tuple(TypeRef.from_json(a) for a in data[1:]))

    @staticmethod
    def parse(text: str) -> TypeRef:
        """Analiza la forma textual: "list[dict[str, str]]", "str | None", "~T"."""
        parser = _TypeParser(text)
        t = parser.union()
        parser.expect_end()
        return t


LITERAL = "Literal"


def literal(value: bool | int | float | str) -> TypeRef:
    """Tipo de un valor literal concreto: `Literal[<json del valor>]`."""
    return TypeRef(LITERAL, (TypeRef(json.dumps(value)),))


def literal_values(t: TypeRef) -> list[object]:
    return [json.loads(a.name) for a in t.args]


def literal_base(value: object) -> TypeRef:
    for py, name in ((bool, "bool"), (int, "int"), (float, "float"), (str, "str")):
        if isinstance(value, py):
            return TypeRef(name)
    return TypeRef(ANY)


def union(*members: TypeRef) -> TypeRef:
    """Une tipos aplanando uniones y eliminando duplicados.

    `Any` dentro de una unión con otros miembros se descarta: typeshed usa `X | Any`
    para decir "normalmente X".
    """
    flat: list[TypeRef] = []
    lit_values: list[TypeRef] = []
    for m in members:
        for x in m.args if m.name == UNION else (m,):
            if x.name == LITERAL:
                lit_values.extend(v for v in x.args if v not in lit_values)
            elif x not in flat:
                flat.append(x)
    if lit_values:
        flat.insert(0, TypeRef(LITERAL, tuple(lit_values)))
    if len(flat) > 1:
        flat = [x for x in flat if x.name != ANY] or [TypeRef(ANY)]
    if not flat:
        return TypeRef("Never")
    return flat[0] if len(flat) == 1 else TypeRef(UNION, tuple(flat))


class _TypeParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def _skip(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] == " ":
            self.pos += 1

    def _peek(self) -> str:
        self._skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect_end(self) -> None:
        if self._peek():
            raise ValueError(f"texto sobrante en {self.text!r} (pos {self.pos})")

    def union(self) -> TypeRef:
        members = [self.atom()]
        while self._peek() == "|":
            self.pos += 1
            members.append(self.atom())
        return members[0] if len(members) == 1 else TypeRef(UNION, tuple(members))

    def atom(self) -> TypeRef:
        self._skip()
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] in "_.~"):
            self.pos += 1
        name = self.text[start : self.pos]
        if not name:
            raise ValueError(f"se esperaba un tipo en {self.text!r} (pos {self.pos})")
        args: list[TypeRef] = []
        if self._peek() == "[":
            self.pos += 1
            args.append(self.union())
            while self._peek() == ",":
                self.pos += 1
                args.append(self.union())
            if self._peek() != "]":
                raise ValueError(f"falta ']' en {self.text!r}")
            self.pos += 1
        return TypeRef(name, tuple(args))


def short_type(t: TypeRef, max_literals: int = 4) -> str:
    """Forma textual compacta para etiquetas: abrevia Literal con muchos valores."""
    if t.name == LITERAL and len(t.args) > max_literals:
        shown = ", ".join(a.name for a in t.args[:max_literals])
        return f"Literal[{shown}, …]"
    if t.name == UNION:
        return " | ".join(short_type(a, max_literals) for a in t.args)
    if t.args and not t.is_var and t.name != LITERAL:
        return f"{t.name}[{', '.join(short_type(a, max_literals) for a in t.args)}]"
    return str(t)


ParamKind = Literal["pos", "pos_kw", "kw"]
ComponentKind = Literal[
    "function", "constructor", "method", "property", "classmethod", "staticmethod", "operator"
]


@dataclass(frozen=True)
class Param:
    name: str
    type: TypeRef
    has_default: bool = False
    kind: ParamKind = "pos_kw"


@dataclass(frozen=True)
class Component:
    """Una pieza de API invocable.

    `qualname` es la ruta Python (`csv.DictReader`, `str.split`, `builtins.len`);
    `id` es único en el catálogo y distingue sobrecargas (`@k`) y variantes con un
    parámetro opcional extra (`+param`).
    """

    qualname: str
    params: tuple[Param, ...]
    returns: TypeRef
    summary: str  # una frase, saneada
    id: str = ""
    kind: ComponentKind = "function"
    module: str = ""  # módulo a importar ("" para builtins)
    group: str = ""  # agrupación para elecciones jerárquicas
    doc: str = ""  # docstring más largo (saneado) para la ablación de descripciones

    def __deepcopy__(self, memo: dict[int, object]) -> Component:
        return self

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", self.qualname)
        if not self.group:
            object.__setattr__(self, "group", self.qualname.rsplit(".", 1)[0])

    @property
    def required_params(self) -> tuple[Param, ...]:
        return tuple(p for p in self.params if not p.has_default)

    @property
    def display_name(self) -> str:
        return self.qualname.removeprefix("builtins.")

    @property
    def attr(self) -> str:
        """Último segmento del nombre: método, propiedad u operador."""
        return self.qualname.rsplit(".", 1)[-1]

    def signature(self) -> str:
        args = ", ".join(f"{p.name}: {short_type(p.type)}" for p in self.required_params)
        return f"{self.display_name}({args}) -> {short_type(self.returns)}"

    def is_typed(self) -> bool:
        """Firma tipada: ningún parámetro obligatorio ni el retorno son `Any` sin más."""
        return all(p.type.name != ANY for p in self.required_params) and self.returns.name != ANY

    def to_json(self) -> dict[str, object]:
        d: dict[str, object] = {
            "id": self.id,
            "qualname": self.qualname,
            "kind": self.kind,
            "module": self.module,
            "group": self.group,
            "params": [[p.name, p.type.to_json(), p.has_default, p.kind] for p in self.params],
            "returns": self.returns.to_json(),
            "summary": self.summary,
        }
        if self.doc:
            d["doc"] = self.doc
        return d

    @staticmethod
    def from_json(d: dict[str, object]) -> Component:
        raw_params = d["params"]
        assert isinstance(raw_params, list)
        params = tuple(Param(str(n), TypeRef.from_json(t), bool(dflt), k) for n, t, dflt, k in raw_params)
        returns = d["returns"]
        assert isinstance(returns, (str, list))
        kind = d.get("kind", "function")
        return Component(
            qualname=str(d["qualname"]),
            params=params,
            returns=TypeRef.from_json(returns),
            summary=str(d["summary"]),
            id=str(d["id"]),
            kind=kind,  # type: ignore[arg-type]
            module=str(d.get("module", "")),
            group=str(d.get("group", "")),
            doc=str(d.get("doc", "")),
        )


@dataclass(frozen=True)
class ClassInfo:
    """Clase con sus variables de tipo y supertipos directos (nominales y estructurales)."""

    name: str
    typevars: tuple[str, ...] = ()
    supers: tuple[TypeRef, ...] = ()
    protocol: bool = False

    def to_json(self) -> dict[str, object]:
        d: dict[str, object] = {
            "typevars": list(self.typevars),
            "supers": [s.to_json() for s in self.supers],
        }
        if self.protocol:
            d["protocol"] = True
        return d

    @staticmethod
    def from_json(name: str, d: dict[str, object]) -> ClassInfo:
        tvs = d.get("typevars", [])
        sups = d.get("supers", [])
        assert isinstance(tvs, list) and isinstance(sups, list)
        return ClassInfo(
            name,
            tuple(str(t) for t in tvs),
            tuple(TypeRef.from_json(s) for s in sups),
            bool(d.get("protocol", False)),
        )


@dataclass(frozen=True)
class Catalog:
    components: tuple[Component, ...]
    classes: dict[str, ClassInfo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [c.id for c in self.components]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"ids de componente duplicados: {dupes[:5]}")

    def by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.components}

    def to_json(self) -> dict[str, object]:
        return {
            "components": [c.to_json() for c in self.components],
            "classes": {n: ci.to_json() for n, ci in sorted(self.classes.items())},
        }

    @staticmethod
    def from_json(d: dict[str, object]) -> Catalog:
        comps = d["components"]
        classes = d.get("classes", {})
        assert isinstance(comps, list) and isinstance(classes, dict)
        return Catalog(
            tuple(Component.from_json(c) for c in comps),
            {n: ClassInfo.from_json(n, ci) for n, ci in classes.items()},
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1) + "\n")

    @staticmethod
    def load(path: Path) -> Catalog:
        data = json.loads(path.read_text())
        assert isinstance(data, dict)
        return Catalog.from_json(data)
