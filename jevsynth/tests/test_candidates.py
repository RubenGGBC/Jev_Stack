import functools

from jevsynth.candidates import fill_assignment, fillers, generate_candidates
from jevsynth.catalog import Catalog, Component, TypeRef, load_stdlib
from jevsynth.literals import LiteralValue
from jevsynth.scope import Scope, TypeSystem, Variable

P = TypeRef.parse

SUBSET = [
    "csv.DictReader@1",
    "csv.reader",
    "builtins.len",
    "statistics.mean",
    "builtins.str.split",
    "builtins.str.upper",
    "builtins.float+x",
    "builtins.open",
    "builtins.sorted",
    "builtins.abs",
    "builtins.range",
    "json.load",
    "builtins.dict.get",
    "operator.getitem@map",
    "builtins.list",  # sin parámetros obligatorios
]


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


@functools.cache
def _ts() -> TypeSystem:
    return TypeSystem(_cat().classes)


def _subset() -> list[Component]:
    by = _cat().by_id()
    return [by[i] for i in SUBSET]


def _cands(scope: dict[str, str], literals: tuple[LiteralValue, ...] = (), **kw: object) -> set[str]:
    s = Scope([Variable(n, P(t)) for n, t in scope.items()])
    return {c.id for c in generate_candidates(s, _subset(), list(literals), _ts(), **kw)}  # type: ignore[arg-type]


def test_textio_scope() -> None:
    assert _cands({"f": "TextIO"}) == {"csv.DictReader@1", "csv.reader", "builtins.sorted", "json.load"}


def test_int_scope() -> None:
    # open(int) es válido: descriptor de fichero.
    assert _cands({"n": "int"}) == {"builtins.abs", "builtins.range", "builtins.float+x", "builtins.open"}


def test_str_scope() -> None:
    assert _cands({"path": "str"}) == {
        "csv.DictReader@1",
        "csv.reader",
        "builtins.len",
        "builtins.str.split",
        "builtins.str.upper",
        "builtins.float+x",
        "builtins.open",
        "builtins.sorted",
    }


def test_rows_with_column_literal() -> None:
    age = LiteralValue("age", "identifier")
    got = _cands({"row": "dict[str, str]"}, (age,))
    assert got == {
        # dict[str, str] itera sus claves: es un Iterable[str] y csv.reader(row) tipa.
        "csv.DictReader@1",
        "csv.reader",
        "builtins.len",
        "builtins.sorted",
        "builtins.dict.get",
        "operator.getitem@map",
        # el literal "age" es un str: rellena los parámetros str...
        "builtins.str.split",
        "builtins.str.upper",
        "builtins.float+x",
        "builtins.open",
    }
    # ...pero no colecciones: ni csv.reader("age") ni len("age").
    assert _cands({}, (age,)) == {
        "builtins.str.split",
        "builtins.str.upper",
        "builtins.float+x",
        "builtins.open",
    }


def test_numbers() -> None:
    assert _cands({"values": "list[float]"}) == {"builtins.len", "statistics.mean", "builtins.sorted"}
    assert _cands({"values": "list[str]"}) == {
        "builtins.len",
        "builtins.sorted",
        "csv.reader",  # csv.reader acepta cualquier iterable de líneas
        "csv.DictReader@1",
    }


def test_nullary_only_when_allowed() -> None:
    assert "builtins.list" not in _cands({})
    assert "builtins.list" in _cands({}, allow_nullary=True)


def test_full_catalog_textio_vs_int() -> None:
    def full(t: str) -> set[str]:
        s = Scope([Variable("x", P(t))])
        return {c.id for c in generate_candidates(s, _cat().components, [], _ts())}

    assert "csv.DictReader@1" in full("TextIO")
    assert "csv.DictReader@1" not in full("int")


def test_returns_filter() -> None:
    s = Scope([Variable("path", P("str"))])
    got = {c.id for c in generate_candidates(s, _subset(), [], _ts(), returns=P("int"))}
    assert got == {"builtins.len"}


def test_must_use() -> None:
    s = Scope([Variable("text", P("str")), Variable("row", P("dict[str, str]"))])
    lits = [LiteralValue("age", "identifier")]
    got = {c.id for c in generate_candidates(s, _subset(), lits, _ts(), must_use="row")}
    assert got == {
        "builtins.len",
        "builtins.sorted",
        "builtins.dict.get",
        "operator.getitem@map",
        "csv.reader",
        "csv.DictReader@1",
    }


def test_fillers_order_and_bindings() -> None:
    s = Scope([Variable("a", P("str")), Variable("b", P("str")), Variable("n", P("int"))])
    lits = [LiteralValue("x", "quoted")]
    got = fillers(P("str"), s, lits, _ts(), {})
    assert [f.name if isinstance(f, Variable) else f.value for f, _ in got] == ["b", "a", "x"]
    get = _cat().by_id()["builtins.dict.get"]
    s2 = Scope([Variable("d", P("dict[str, int]"))])
    b = fill_assignment(get, s2, lits, _ts())
    assert b is not None and b["~_KT"] == P("str")


def test_without_type_filter_everything_with_values() -> None:
    got = _cands({"n": "int"}, type_filter=False)
    assert got == set(SUBSET) - {"builtins.list"}
