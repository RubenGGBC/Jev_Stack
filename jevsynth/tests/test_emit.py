import ast
import functools

from jevsynth.catalog import Catalog, Component, TypeRef, load_stdlib
from jevsynth.emit import emit
from jevsynth.emit.ir import (
    Assign,
    Call,
    Const,
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
    With,
)
from jevsynth.emit.names import base_name, elem_base_name, fresh
from jevsynth.literals import LiteralValue

P = TypeRef.parse


@functools.cache
def _cat() -> Catalog:
    return load_stdlib()


def C(cid: str) -> Component:
    return _cat().by_id()[cid]


def _mean_age() -> Program:
    age = Const(LiteralValue("age", "identifier"))
    return Program(
        params=[("path", P("str"))],
        returns=P("float"),
        body=[
            With(
                "f",
                Call(C("builtins.open"), [Name("path")]),
                [
                    Assign("reader", Call(C("csv.DictReader@1"), [Name("f")])),
                    Assign(
                        "values",
                        ListComp(
                            Call(
                                C("builtins.float+x"), [Call(C("operator.getitem@map"), [Name("row"), age])]
                            ),
                            "row",
                            Name("reader"),
                        ),
                    ),
                ],
            ),
            Assign("result", Call(C("statistics.mean"), [Name("values")])),
            Return(Name("result")),
        ],
    )


def _compiles(code: str) -> None:
    compile(ast.parse(code), "<synth>", "exec")


def test_emit_function() -> None:
    code = emit(_mean_age())
    _compiles(code)
    assert code == (
        "import csv\n"
        "import statistics\n"
        "\n"
        "def solve(path: str) -> float:\n"
        "    with open(path) as f:\n"
        "        reader = csv.DictReader(f)\n"
        "        values = [float(row['age']) for row in reader]\n"
        "    result = statistics.mean(values)\n"
        "    return result\n"
    )


def test_emit_inline_temporaries() -> None:
    code = emit(_mean_age(), inline=True)
    _compiles(code)
    assert "values = [float(row['age']) for row in csv.DictReader(f)]" in code
    assert "return statistics.mean(values)" in code


def test_runs(tmp_path: object) -> None:
    import pathlib

    d = pathlib.Path(str(tmp_path))
    (d / "x.csv").write_text("name,age\na,10\nb,20\n")
    for inline in (False, True):
        ns: dict[str, object] = {}
        exec(emit(_mean_age(), inline=inline), ns)
        solve = ns["solve"]
        assert callable(solve)
        assert solve(str(d / "x.csv")) == 15.0


def test_methods_properties_operators_and_kwonly() -> None:
    lines = Name("lines")
    prog = Program(
        body=[
            Assign("text", Call(C("builtins.str.upper"), [Const(LiteralValue("hola", "quoted"))])),
            Assign(
                "items", Call(C("builtins.str.split+sep"), [Name("text"), Const(LiteralValue(",", "quoted"))])
            ),
            Assign("ok", Call(C("operator.contains"), [Name("items"), Const(LiteralValue("A", "quoted"))])),
            If(Call(C("operator.not_"), [Name("ok")]), [Print(Call(C("builtins.len"), [Name("items")]))]),
            For("line", lines, []),
            ExprStmt(Call(C("builtins.list.append"), [Name("items"), Name("text")])),
            Assign("name", Call(C("pathlib.PurePath.name"), [Name("p")])),
            Assign(
                "total",
                Call(C("operator.add@int"), [Name("a"), Call(C("operator.mul@int"), [Name("b"), Name("c")])]),
            ),
        ]
    )
    code = emit(prog)
    _compiles(code)
    assert "text = 'hola'.upper()" in code
    assert "items = text.split(',')" in code
    assert "ok = 'A' in items" in code
    assert "if not ok:\n    print(len(items))" in code
    assert "for line in lines:\n    pass" in code
    assert "items.append(text)" in code
    assert "name = p.name" in code
    assert "total = a + b * c" in code


def test_holes_emit_as_ellipsis_and_compile() -> None:
    prog = Program(
        params=[("text", P("str"))],
        returns=P("int"),
        body=[Assign("items", Call(C("builtins.str.split"), [HoleExpr()])), HoleStmt()],
    )
    code = emit(prog)
    _compiles(code)
    assert "items = ....split()" in code
    assert code.rstrip().endswith("...")


def test_annotations_only_for_builtin_types() -> None:
    prog = Program(params=[("f", P("io.TextIOWrapper")), ("n", P("list[int]"))], returns=P("int | None"))
    code = emit(prog)
    _compiles(code)
    assert "def solve(f, n: list[int]) -> int | None:" in code


def test_inline_respects_loops_and_multiple_uses() -> None:
    prog = Program(
        body=[
            Assign("items", Call(C("builtins.str.split"), [Name("text")])),
            For(
                "item",
                Name("items"),
                [Assign("n", Call(C("builtins.len"), [Name("item")])), Print(Name("n"))],
            ),
            Assign("k", Call(C("builtins.len"), [Name("text")])),
            Print(Name("k")),
            Print(Name("k")),
        ]
    )
    code = emit(prog, inline=True)
    _compiles(code)
    assert "for item in text.split():" in code  # cabecera del for: se evalúa una vez
    assert "print(len(item))" in code
    assert "k = len(text)" in code  # dos usos: no se pliega


def test_names() -> None:
    assert base_name(P("list[dict[str, str]]")) == "rows"
    assert base_name(P("list[float]")) == "values"
    assert base_name(P("csv.DictReader[str]")) == "reader"
    assert base_name(P("re.Match[str]")) == "match"
    assert elem_base_name(P("csv.DictReader[str]"), P("dict[str, str]")) == "row"
    assert elem_base_name(P("list[str]"), P("str")) == "item"
    assert fresh("rows", {"rows", "rows2"}) == "rows3"
    assert fresh("len", set()) == "len2"
