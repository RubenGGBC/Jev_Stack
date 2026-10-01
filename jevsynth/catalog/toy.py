"""Catálogo de juguete de 5 funciones para la fase 0."""

from __future__ import annotations

from jevsynth.catalog.model import Component, Param, TypeRef

STR = TypeRef("str")
INT = TypeRef("int")
LIST_STR = TypeRef("list[str]")

TOY_CATALOG: tuple[Component, ...] = (
    Component("toy.read_text", (Param("path", STR),), STR, "Read a file and return its text."),
    Component("toy.split_lines", (Param("text", STR),), LIST_STR, "Split text into lines."),
    Component("toy.count_items", (Param("items", LIST_STR),), INT, "Count the items in a list."),
    Component("toy.to_upper", (Param("text", STR),), STR, "Convert text to upper case."),
    Component("toy.format_int", (Param("n", INT),), STR, "Format an integer as text."),
)
