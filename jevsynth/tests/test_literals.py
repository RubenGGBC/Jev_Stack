import pytest

from jevsynth.candidates.control import CONTROL_KINDS, control_kind, control_option
from jevsynth.literals.extract import extract_literals


def _vals(text: str) -> list[object]:
    return [lit.value for lit in extract_literals(text)]


def test_phase3_criterion() -> None:
    assert _vals("lee datos.csv y calcula la media de age") == ["datos.csv", "age"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('cuenta las líneas que contienen "ERROR" en log.txt', ["ERROR", "log.txt"]),
        ("suma la columna precio de ventas.csv", ["precio", "ventas.csv"]),
        ("the average of the price column in sales.csv", ["price", "sales.csv"]),
        ("devuelve los 3 elementos más frecuentes", [3]),
        ("redondea a 2 decimales el valor 3.75", [2, 3.75]),
        ("agrupa por user_id", ["user_id"]),
        ("separa el texto por «;»", [";"]),
        ("lee config/app.json y devuelve la clave `port`", ["config/app.json", "port"]),
        ("ordena la lista", []),
        ("muestra la suma de los números", []),  # no cortar "números" en "n"
        ("print the sum of the numbers", []),
    ],
)
def test_extraction(text: str, expected: list[object]) -> None:
    assert _vals(text) == expected


def test_sources_and_types() -> None:
    lits = extract_literals("multiplica age por 2.5 en 'data.csv'")
    by = {lit.value: lit for lit in lits}
    assert by["data.csv"].source == "quoted"
    assert by[2.5].source == "number" and isinstance(by[2.5].value, float)
    assert by[2.5].code == "2.5"
    assert str(by["data.csv"].type) == 'Literal["data.csv"]'


def test_numbers_inside_filenames_are_not_numbers() -> None:
    assert _vals("lee datos2.csv") == ["datos2.csv"]


def test_control_options_are_fixed() -> None:
    assert CONTROL_KINDS == ("with", "for", "listcomp", "if", "return", "print", "end")
    for k in CONTROL_KINDS:
        opt = control_option(k)
        assert opt.kind == "control" and control_kind(opt.id) == k
    assert control_kind("csv.reader") is None


def test_same_literals_in_both_languages() -> None:
    from jevsynth.eval.tasks import load_tasks

    for t in load_tasks():
        assert t.prompt_en, t.id
        assert _vals(t.prompt) == _vals(t.prompt_en), t.id
