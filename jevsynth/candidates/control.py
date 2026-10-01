"""Combinadores de control: conjunto fijo y cerrado de formas de instrucción."""

from __future__ import annotations

from typing import Literal

from jevsynth.chooser.base import Option

ControlKind = Literal["with", "for", "listcomp", "if", "return", "print", "end"]

CONTROL_KINDS: tuple[ControlKind, ...] = ("with", "for", "listcomp", "if", "return", "print", "end")

LABELS: dict[ControlKind, str] = {
    "with": "with … as …: abrir un recurso (p. ej. un fichero) y usarlo dentro de un bloque",
    "for": "for … in …: repetir un bloque para cada elemento de una colección",
    "listcomp": "[… for … in …]: construir una lista transformando o filtrando cada elemento",
    "if": "if …: ejecutar un bloque solo si se cumple una condición",
    "return": "return …: devolver un valor como resultado de la función",
    "print": "print(…): mostrar un valor por pantalla",
    "end": "fin del bloque: no hay más instrucciones dentro de este bloque",
}


def control_option(kind: ControlKind) -> Option:
    return Option(id=f"control:{kind}", label=LABELS[kind], kind="control")


def control_kind(option_id: str) -> ControlKind | None:
    if not option_id.startswith("control:"):
        return None
    kind = option_id.removeprefix("control:")
    for k in CONTROL_KINDS:
        if k == kind:
            return k
    return None
