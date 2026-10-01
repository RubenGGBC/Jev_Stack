import math

import pytest

from jevsynth.chooser import MockChooser, Option, RandomChooser, rank

OPTS = [
    Option("toy.read_text", "toy.read_text: Read a file and return its text.", "component"),
    Option("toy.count_items", "toy.count_items: Count the items in a list.", "component"),
    Option("toy.to_upper", "toy.to_upper: Convert text to upper case.", "component"),
]


def _check_distribution(ranked: list[tuple[Option, float]], options: list[Option]) -> None:
    assert sorted(o.id for o, _ in ranked) == sorted(o.id for o in options)
    probs = [p for _, p in ranked]
    assert math.isclose(sum(probs), 1.0)
    assert probs == sorted(probs, reverse=True)
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_rank_is_stable_on_ties() -> None:
    ranked = rank(OPTS, [1.0, 1.0, 1.0])
    assert [o.id for o, _ in ranked] == [o.id for o in OPTS]


def test_rank_all_zero_is_uniform() -> None:
    assert [p for _, p in rank(OPTS, [0.0, 0.0, 0.0])] == pytest.approx([1 / 3] * 3)


def test_rank_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        rank(OPTS, [1.0])
    with pytest.raises(ValueError):
        rank(OPTS, [1.0, -1.0, 0.0])


def test_rank_empty() -> None:
    assert rank([], []) == []


def test_mock_prefers_word_overlap() -> None:
    ranked = MockChooser().choose("tarea: count the lines\nhueco: x", OPTS)
    _check_distribution(ranked, OPTS)
    assert ranked[0][0].id == "toy.count_items"


def test_mock_uses_only_task_line() -> None:
    # "upper" aparece en el programa parcial, no en la tarea: no debe puntuar.
    state = "tarea: read the file\nhueco: x\nprograma: text = toy.to_upper(upper)"
    assert MockChooser().choose(state, OPTS)[0][0].id == "toy.read_text"


def test_mock_is_done_constant() -> None:
    assert MockChooser().is_done("tarea: x") == 0.0
    assert MockChooser(done_prob=0.8).is_done("tarea: x") == 0.8
    with pytest.raises(ValueError):
        MockChooser(done_prob=1.5)


def test_random_is_reproducible_with_seed() -> None:
    a = [RandomChooser(seed=7).choose("s", OPTS) for _ in range(2)]
    assert a[0] == a[1]
    _check_distribution(a[0], OPTS)


def test_random_differs_across_seeds() -> None:
    results = {tuple(o.id for o, _ in RandomChooser(seed=s).choose("s", OPTS)) for s in range(20)}
    assert len(results) > 1


def test_random_is_done_fixed_or_random() -> None:
    assert RandomChooser(seed=1, done_prob=0.3).is_done("s") == 0.3
    p = RandomChooser(seed=1).is_done("s")
    assert 0.0 <= p <= 1.0


def test_oracle_follows_target_as_subsequence() -> None:
    from jevsynth.chooser import OracleChooser, StateText

    o = OracleChooser(["toy.read_text", "toy.count_items"])
    first = o.choose(StateText("s", ()), OPTS)
    assert first[0][0].id == "toy.read_text"
    # Decisiones no previstas en el objetivo se ignoran al casar.
    nxt = o.choose(StateText("s", ("sym:path", "toy.read_text", "sym:text")), OPTS)
    assert nxt[0][0].id == "toy.count_items"
    assert o.is_done(StateText("s", ("toy.read_text", "toy.count_items"))) > 0.5
    assert o.is_done(StateText("s", ("toy.read_text",))) < 0.5
    group = Option("group:toy", "toy", "group", members=("toy.read_text",))
    assert o.choose(StateText("s", ()), [OPTS[2], group])[0][0].id == "group:toy"


def test_noisy_oracle_accuracy_and_determinism() -> None:
    from jevsynth.chooser import NoisyOracleChooser, StateText

    hits = 0
    for i in range(400):
        o = NoisyOracleChooser(["toy.to_upper"], accuracy=0.75, seed=i)
        ranked = o.choose(StateText(f"s{i}", ()), OPTS)
        _check_distribution(ranked, OPTS)
        hits += ranked[0][0].id == "toy.to_upper"
        assert ranked == o.choose(StateText(f"s{i}", ()), OPTS)
    assert 0.65 < hits / 400 < 0.85
    perfect = NoisyOracleChooser(["toy.to_upper"], accuracy=1.0)
    assert perfect.choose(StateText("x", ()), OPTS)[0][0].id == "toy.to_upper"
