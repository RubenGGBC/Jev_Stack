import functools

import pytest

from jevsynth.catalog import Catalog, TypeRef, load_stdlib
from jevsynth.catalog.model import literal
from jevsynth.scope.typesys import TypeSystem

P = TypeRef.parse


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


@functools.cache
def _ts() -> TypeSystem:
    return TypeSystem(_cat().classes)


@pytest.mark.parametrize(
    ("actual", "formal", "expected"),
    [
        ("bool", "int", True),
        ("int", "float", True),
        ("float", "int", False),
        ("int", "str", False),
        ("list[str]", "Iterable[str]", True),
        ("list[int]", "Iterable[str]", False),
        ("str", "Iterable[str]", True),
        ("str", "Sized", True),
        ("dict[str, int]", "Mapping[str, int]", True),
        ("collections.Counter[str]", "dict[str, int]", True),
        ("collections.Counter[str]", "Iterable[str]", True),
        ("csv.DictReader[str]", "Iterable[dict[str, str]]", True),
        ("io.TextIOWrapper", "Iterable[str]", True),
        ("io.TextIOWrapper", "Iterable[bytes]", False),
        ("io.TextIOWrapper", "SupportsRead[str]", True),
        ("TextIO", "Iterable[str]", True),
        ("pathlib.Path", "os.PathLike[str]", True),
        ("None", "str | None", True),
        ("str", "str | None", True),
        ("int | float", "float", True),
        ("int | str", "float", False),
        ("int", "SupportsIndex", True),
        ("float", "SupportsIndex", False),
        ("tuple[str, int]", "Iterable[Any]", True),
        ("float", "_SupportsSumWithNoDefaultGiven", True),
        ("range", "Iterable[int]", True),
        ("enumerate[str]", "Iterable[tuple[int, str]]", True),
        ("re.Match[str]", "str", False),
        ("list[str]", "object", True),
    ],
)
def test_subtyping(actual: str, formal: str, expected: bool) -> None:
    assert _ts().is_subtype(P(actual), P(formal)) is expected


def test_literals() -> None:
    ts = _ts()
    assert ts.is_subtype(literal("age"), P("str"))
    assert not ts.is_subtype(P("str"), TypeRef("Literal", (TypeRef('"r"'),)))
    mode = _cat().by_id()["builtins.open@4"].params[1].type
    assert ts.is_subtype(literal("rb"), mode)
    assert not ts.is_subtype(literal("r"), mode)
    # Un literal no rellena colecciones aunque str sea iterable...
    assert ts.match(literal("age"), P("Iterable[str]"), {}, shallow=True) is None
    assert ts.match(literal("age"), P("Sized"), {}, shallow=True) is None
    # ...pero sí protocolos escalares (round(x, 2)).
    assert ts.match(literal(2), P("SupportsIndex"), {}, shallow=True) is not None


def _call(cid: str, *args: str) -> str | None:
    comp = _cat().by_id()[cid]
    b: dict[str, TypeRef] | None = {}
    for p, a in zip(comp.required_params, args, strict=True):
        assert b is not None
        b = _ts().match(P(a), p.type, b)
        if b is None:
            return None
    assert b is not None
    return str(_ts().resolve(comp.returns, b))


def test_typevar_binding_and_constraints() -> None:
    assert _call("statistics.mean", "list[float]") == "float"
    assert _call("statistics.mean", "list[str]") is None  # _NumberT restringido a números
    assert _call("builtins.sorted", "list[str]") == "list[str]"
    assert _call("builtins.list@1", "csv.DictReader[str]") == "list[dict[str, str]]"
    assert _call("collections.Counter@3", "list[str]") == "collections.Counter[str]"
    assert _call("builtins.zip@2", "list[int]", "list[str]") == "zip[tuple[int, str]]"
    assert _call("builtins.dict.get", "dict[str, int]", "str") == "int | None"
    assert _call("operator.getitem@map", "dict[str, str]", "str") == "str"
    assert _call("builtins.round", "float") == "int"
    assert _call("builtins.max@2", "list[int]") == "int"
    assert _call("builtins.len", "csv.DictReader[str]") is None


def test_typevar_widening() -> None:
    # T ligado primero a int y luego a float: se ensancha a float.
    assert _call("builtins.max", "int", "float") == "float"


def test_element_type() -> None:
    ts = _ts()
    assert ts.element_type(P("io.TextIOWrapper")) == P("str")
    assert ts.element_type(P("csv.DictReader[str]")) == P("dict[str, str]")
    assert ts.element_type(P("dict[str, int]")) == P("str")
    assert ts.element_type(P("int")) is None
