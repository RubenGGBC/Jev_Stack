"""JevChooser contra un servidor simulado (httpx2.MockTransport): sin red, SDK real."""

import ast
import json
from collections.abc import Callable
from typing import Any

import pytest

typesafe_sdk = pytest.importorskip("typesafe_sdk")
httpx2 = pytest.importorskip("httpx2")

from jevsynth.catalog import load_stdlib  # noqa: E402
from jevsynth.chooser import Option, format_state  # noqa: E402
from jevsynth.chooser.jev import JevChooser  # noqa: E402
from jevsynth.eval.tasks import load_tasks  # noqa: E402
from jevsynth.synth import SynthConfig, synthesize  # noqa: E402

OPTS = [
    Option(
        "csv.DictReader@1", "csv.DictReader(f: Iterable[str]) -> csv.DictReader[str]: Read rows.", "component"
    ),
    Option("builtins.len", "len(obj: Sized) -> int: Return the number of items.", "component"),
    Option("control:return", "return …: devolver un valor", "control"),
]
STATE = format_state("lee el csv", "siguiente instrucción", "def solve(f):\n    ⟨?⟩")


def _answer(body: dict[str, Any], pick: Callable[[list[str]], str]) -> Any:
    answers: dict[str, Any] = {}
    for name, q in body["questions"].items():
        if q["type"] == "choice":
            keys = list(q["criteria"])
            best = pick(keys)
            rest = (1 - 0.7) / max(len(keys) - 1, 1)
            probs = {k: (0.7 if k == best else rest) for k in keys}
            answers[name] = {"type": "choice", "choice": best, "confidence": 0.7, "probabilities": probs}
        else:
            answers[name] = {"type": "noul", "noul": 0.2}
    payload = {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 1}}
    return httpx2.Response(200, json=payload)


class FakeJev:
    def __init__(self, pick: Callable[[list[str]], str] = lambda ks: ks[-1], fail_first: int = 0) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.headers: list[Any] = []
        self.pick = pick
        self.fail_first = fail_first

    def __call__(self, request: Any) -> Any:
        self.headers.append(request.headers)
        if self.fail_first > 0:
            self.fail_first -= 1
            return httpx2.Response(503, json={"detail": "ocupado"})
        body = json.loads(request.content)
        self.bodies.append(body)
        return _answer(body, self.pick)


def _chooser(fake: FakeJev, **kw: Any) -> JevChooser:
    client = typesafe_sdk.TypeSafeClient(
        api_key="test-key",
        transport=httpx2.MockTransport(fake),
        retry=typesafe_sdk.RetryPolicy(max_retries=2, backoff_initial=0, backoff_max=0),
    )
    return JevChooser(client, **kw)


def test_request_shape_and_probabilities() -> None:
    fake = FakeJev()
    jev = _chooser(fake)
    ranked = jev.choose(STATE, OPTS)
    assert ranked[0][0].id == "control:return"
    assert abs(sum(p for _, p in ranked) - 1) < 1e-9
    (body,) = fake.bodies
    assert body["model"] == "jev-latest"
    # Estado mínimo y estructurado: tarea + programa; el hueco va en las instrucciones.
    assert body["state"] == {"tarea": "lee el csv", "programa": "def solve(f):\n    ⟨?⟩"}
    (q,) = body["questions"].values()
    assert q["type"] == "choice"
    assert "siguiente instrucción" in q["instructions"]
    assert q["criteria"] == {o.id: o.label for o in OPTS}
    assert fake.headers[0]["authorization"] == "Bearer test-key"


def test_noul_for_is_done() -> None:
    fake = FakeJev()
    assert _chooser(fake).is_done(STATE) == pytest.approx(0.2)
    (q,) = fake.bodies[0]["questions"].values()
    assert q["type"] == "noul" and set(q["criteria"]) == {"true", "false"}


def test_cache_avoids_repeated_requests() -> None:
    fake = FakeJev()
    jev = _chooser(fake)
    a = jev.choose(STATE, OPTS)
    b = jev.choose(STATE, OPTS)
    assert a == b and len(fake.bodies) == 1 and jev.requests == 1


def test_batch_puts_questions_in_one_request() -> None:
    fake = FakeJev()
    jev = _chooser(fake)
    ranked, done = jev.batch(STATE, [("hueco a", OPTS), ("hueco b", OPTS[:2])], done=True)
    assert len(fake.bodies) == 1
    assert set(fake.bodies[0]["questions"]) == {"q0", "q1", "done"}
    assert len(ranked) == 2 and done == pytest.approx(0.2)


def test_retries_with_backoff_then_succeeds() -> None:
    fake = FakeJev(fail_first=2)
    ranked = _chooser(fake).choose(STATE, OPTS)
    assert ranked and len(fake.headers) == 3


def test_gives_up_after_retries() -> None:
    fake = FakeJev(fail_first=10)
    with pytest.raises(typesafe_sdk.TypeSafeAPIError):
        _chooser(fake).choose(STATE, OPTS)


@pytest.mark.parametrize("style", ["id", "label", "letter"])
def test_criteria_styles_map_back(style: str) -> None:
    fake = FakeJev(pick=lambda ks: ks[1])
    ranked = _chooser(fake, criteria_style=style).choose(STATE, OPTS)
    assert ranked[0][0].id == "builtins.len"
    keys = list(next(iter(fake.bodies[0]["questions"].values()))["criteria"])
    if style == "letter":
        assert keys == ["A", "B", "C"]
    elif style == "label":
        assert keys == [o.label for o in OPTS]


def test_missing_api_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(typesafe_sdk.TypeSafeError, match="TYPESAFE_API_KEY"):
        JevChooser()


def test_end_to_end_synthesis_batches_requests() -> None:
    def overlap(keys: list[str]) -> str:
        # Servidor de juguete: prefiere opciones de csv/statistics/control.
        for pref in ("control:with", "builtins.open", "csv.", "control:listcomp", "statistics.mean"):
            for k in keys:
                if k.startswith(pref):
                    return k
        return keys[0]

    fake = FakeJev(pick=overlap)
    jev = _chooser(fake)
    task = next(t for t in load_tasks() if t.id == "mean_age")
    r = synthesize(task.synth_task(), load_stdlib(), jev, SynthConfig(width=2, max_expansions=40))
    assert r.stats.requests == len(fake.bodies)
    assert r.stats.queries >= r.stats.requests  # hay lotes con varias preguntas
    if r.code is not None:
        compile(ast.parse(r.code), "<synth>", "exec")
