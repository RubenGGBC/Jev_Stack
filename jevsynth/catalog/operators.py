"""Operadores del módulo `operator`, con tipos precisos escritos a mano.

Los stubs de `operator` son demasiado laxos (casi todo `Any`), así que aquí se fijan
firmas concretas. Se emiten como sintaxis (`a + b`, `d[k]`, `x in c`).
"""

from __future__ import annotations

import operator

from jevsynth.catalog.model import Component, Param, TypeRef
from jevsynth.catalog.sanitize import summarize

T = TypeRef.parse

# nombre del operador → lista de (sufijo de id, tipos de parámetros, retorno)
_SIGS: dict[str, list[tuple[str, tuple[str, ...], str]]] = {
    "getitem": [
        ("map", ("Mapping[~K, ~V]", "~K"), "~V"),
        ("seq", ("Sequence[~T]", "int"), "~T"),
    ],
    "add": [
        ("int", ("int", "int"), "int"),
        ("float", ("float", "float"), "float"),
        ("str", ("str", "str"), "str"),
        ("list", ("list[~T]", "list[~T]"), "list[~T]"),
    ],
    "sub": [("int", ("int", "int"), "int"), ("float", ("float", "float"), "float")],
    "mul": [("int", ("int", "int"), "int"), ("float", ("float", "float"), "float")],
    "truediv": [("", ("float", "float"), "float")],
    "floordiv": [("", ("int", "int"), "int")],
    "mod": [("", ("int", "int"), "int")],
    "neg": [("", ("float",), "float")],
    "lt": [("num", ("float", "float"), "bool"), ("str", ("str", "str"), "bool")],
    "le": [("num", ("float", "float"), "bool"), ("str", ("str", "str"), "bool")],
    "gt": [("num", ("float", "float"), "bool"), ("str", ("str", "str"), "bool")],
    "ge": [("num", ("float", "float"), "bool"), ("str", ("str", "str"), "bool")],
    "eq": [("", ("object", "object"), "bool")],
    "ne": [("", ("object", "object"), "bool")],
    "contains": [("", ("Container[Any]", "object"), "bool")],
    "not_": [("", ("object",), "bool")],
}

# Forma emitida de cada operador (la usa emit/).
BINARY = {
    "add": "+",
    "sub": "-",
    "mul": "*",
    "truediv": "/",
    "floordiv": "//",
    "mod": "%",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
    "eq": "==",
    "ne": "!=",
}


def components() -> list[Component]:
    out: list[Component] = []
    for name, sigs in _SIGS.items():
        summary = summarize(getattr(operator, name).__doc__, f"operator {name}.")
        for suffix, ptypes, ret in sigs:
            names = ("a", "b")[: len(ptypes)]
            out.append(
                Component(
                    qualname=f"operator.{name}",
                    params=tuple(Param(n, T(t), False, "pos") for n, t in zip(names, ptypes, strict=True)),
                    returns=T(ret),
                    summary=summary,
                    id=f"operator.{name}" + (f"@{suffix}" if suffix else ""),
                    kind="operator",
                    module="",
                    group="operator",
                )
            )
    return out
