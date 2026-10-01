"""Nombres de variable generados por el script a partir del tipo (nunca por el chooser)."""

from __future__ import annotations

from collections.abc import Collection

from jevsynth.catalog.model import TypeRef

_BY_NAME = {
    "str": "text",
    "int": "n",
    "float": "value",
    "bool": "ok",
    "dict": "mapping",
    "set": "unique",
    "frozenset": "unique",
    "tuple": "pair",
    "csv.DictReader": "reader",
    "csv.Reader": "reader",
    "io.TextIOWrapper": "f",
    "TextIO": "f",
    "IO": "f",
    "pathlib.Path": "path",
    "pathlib.PosixPath": "path",
    "collections.Counter": "counts",
    "collections.defaultdict": "groups",
    "re.Match": "match",
    "re.Pattern": "pattern",
    "zip": "pairs",
    "enumerate": "pairs",
    "range": "numbers",
}
_PLURAL = {"dict": "rows", "float": "values", "int": "values", "str": "items", "tuple": "pairs"}
_ELEM = {
    "io.TextIOWrapper": "line",
    "TextIO": "line",
    "csv.DictReader": "row",
    "csv.Reader": "row",
    "dict": "key",
    "collections.Counter": "key",
    "range": "i",
    "enumerate": "pair",
    "zip": "pair",
}
_ELEM_BY_TYPE = {"dict": "row", "str": "item", "float": "x", "int": "x", "tuple": "pair", "list": "row"}

RESERVED = frozenset({"print", "len", "list", "dict", "str", "int", "float", "sum", "max", "min", "open"})


def base_name(t: TypeRef) -> str:
    if t.name == "list" and t.args:
        return _PLURAL.get(t.args[0].name, "items")
    if t.name in {"list", "Iterator", "Iterable", "map", "filter", "reversed"}:
        return "items"
    return _BY_NAME.get(t.name, "result")


def elem_base_name(container: TypeRef, elem: TypeRef) -> str:
    if container.name in _ELEM:
        return _ELEM[container.name]
    return _ELEM_BY_TYPE.get(elem.name, "item")


def fresh(base: str, taken: Collection[str]) -> str:
    if base not in taken and base not in RESERVED:
        return base
    i = 2
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"
