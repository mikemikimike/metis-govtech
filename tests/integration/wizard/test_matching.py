"""Criterion prose → grader FQN.

Written before the implementation. The property that matters most is the fallback: a matcher
that cannot reach its embedding provider must still leave the user with a working experiment,
because the alternative is an interview that stops for a reason the user cannot act on.
"""

import pytest

from metis.wizard.application.matching import (
    GENERATED_JUDGE_FQN,
    EmbeddingMatcher,
    library_catalogue,
    match_specification,
)
from metis.wizard.contracts import Criterion, GraderSpec
from tests.fixtures.wizard.specifications import research_assistant


class FakeEmbedder:
    """Embeddings as one-hot vectors keyed by a word, so similarity is predictable."""

    def __init__(self, vocabulary: list[str], *, fails: bool = False) -> None:
        self.vocabulary = vocabulary
        self.fails = fails
        self.calls = 0

    def embed(self, texts: list[str], model: str = "") -> list[list[float]]:
        self.calls += 1
        if self.fails:
            raise RuntimeError("embedding provider unavailable")
        return [
            [1.0 if word in text.lower() else 0.0 for word in self.vocabulary]
            for text in texts
        ]


CITATION = GraderSpec(
    fqn="tests.unit.engine.graders_for_tests.FixedScoreGrader",
    name="Synthesis faithfulness",
    description="Whether claims are supported by the source they cite.",
)
TURNS = GraderSpec(
    fqn="metis.library.graders.TraceBudgetGrader",
    name="Turn budget",
    description="Interview completed within the allowed turn budget.",
)


def a_criterion(then: str, **kw) -> Criterion:
    return Criterion(
        id="AC-1-1",
        name="Criterion",
        description={"given": "a question", "when": "it answers", "then": then},
        **kw,
    )


# ── the catalogue ──────────────────────────────────────────────────────────


def test_the_catalogue_reads_real_graders() -> None:
    specs = library_catalogue()

    assert specs
    assert all(spec.fqn and spec.name and spec.description for spec in specs)
    assert any("TraceBudgetGrader" in spec.fqn for spec in specs)


def test_the_catalogue_covers_every_exported_grader() -> None:
    """The reader must find the whole library: every concrete Grader the package exports."""
    import inspect

    import metis.library.graders as graders
    from metis.library.grader import Grader

    exported = {
        name
        for name, obj in vars(graders).items()
        if inspect.isclass(obj)
        and issubclass(obj, Grader)
        and not inspect.isabstract(obj)
        and obj.__module__.startswith("metis.library.graders")
    }
    catalogued = {spec.fqn.rsplit(".", 1)[-1] for spec in library_catalogue()}
    assert catalogued == exported
    assert "Grader" not in catalogued  # the contract is not a choice


def test_the_catalogue_never_instantiates_a_grader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parameters come from args_model; reading them must not build a grader."""
    from metis.library.graders import TraceBudgetGrader

    def explode(*_a, **_kw):
        raise AssertionError("the catalogue instantiated a grader")

    monkeypatch.setattr(TraceBudgetGrader, "__init__", explode)

    library_catalogue.cache_clear()
    assert library_catalogue()
    library_catalogue.cache_clear()


def test_catalogue_params_come_from_args_model() -> None:
    library_catalogue.cache_clear()
    (spec,) = [s for s in library_catalogue() if s.fqn.endswith(".TraceBudgetGrader")]
    assert [(p.name, p.type, p.default, p.required) for p in spec.params] == [
        ("threshold", "float", 0.5, False),
        ("max_traces", "int", 10, False),
    ]


def test_every_catalogued_fqn_is_importable() -> None:
    import importlib

    for spec in library_catalogue():
        module_path, _, class_name = spec.fqn.rpartition(".")
        assert hasattr(importlib.import_module(module_path), class_name), spec.fqn


# ── matching ───────────────────────────────────────────────────────────────


def test_a_close_match_is_selected() -> None:
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["source", "turn"]),
        specs=[CITATION, TURNS],
        threshold=0.5,
    )

    assert matcher.match(a_criterion("it names the source it used")) == CITATION.fqn


def test_no_match_falls_through_to_the_generated_judge() -> None:
    """Still a working experiment — the criterion text becomes the judge's instruction."""
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["source", "turn"]),
        specs=[CITATION, TURNS],
        threshold=0.5,
    )

    assert matcher.match(a_criterion("the tone is friendly")) == GENERATED_JUDGE_FQN


def test_the_threshold_is_what_decides() -> None:
    """A partial match: the criterion mentions both concepts, the grader only one."""
    criterion = a_criterion("it names the source it used, within the turn budget")
    embedder = FakeEmbedder(["source", "turn"])

    lenient = EmbeddingMatcher(embedder=embedder, specs=[CITATION], threshold=0.1)
    strict = EmbeddingMatcher(embedder=embedder, specs=[CITATION], threshold=0.99)

    assert lenient.match(criterion) == CITATION.fqn
    assert strict.match(criterion) == GENERATED_JUDGE_FQN


def test_catalogue_embeddings_are_computed_once() -> None:
    """The catalogue does not change within a run; re-embedding it per criterion would."""
    embedder = FakeEmbedder(["source", "turn"])
    matcher = EmbeddingMatcher(
        embedder=embedder, specs=[CITATION, TURNS], threshold=0.5
    )

    matcher.match(a_criterion("it names the source"))
    matcher.match(a_criterion("it stays within the turn budget"))

    assert embedder.calls == 3  # one for the catalogue, one per criterion


# ── the fallback that keeps the interview alive ────────────────────────────


def test_an_unavailable_provider_degrades_rather_than_blocking() -> None:
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder([], fails=True), specs=[CITATION], threshold=0.5
    )

    assert matcher.match(a_criterion("anything at all")) == GENERATED_JUDGE_FQN
    assert matcher.degraded


# ── matching over a whole specification ──────────────────────────────────────────


def test_only_criteria_without_a_grader_are_matched() -> None:
    """Re-matching a criterion that already has a grader would be a wasted call."""
    specification = research_assistant()
    embedder = FakeEmbedder(["source"])
    matcher = EmbeddingMatcher(embedder=embedder, specs=[CITATION], threshold=0.5)

    matched = match_specification(specification, matcher)

    assert matched == 0  # the fixture already has graders on everything


def test_dormant_criteria_also_have_graders() -> None:
    """Nothing is generated for behaviours nobody picked, matching included."""
    specification = research_assistant()
    unticked = specification.behaviour("EB-2")
    assert unticked is not None
    unticked.criteria[0].grader_fqn = None
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["source"]), specs=[CITATION], threshold=0.5
    )

    match_specification(specification, matcher)

    assert unticked.criteria[0].grader_fqn is not None


def test_rematching_a_criterion_is_silent_and_free() -> None:
    """The matcher chose the previous value, so re-choosing takes nothing from the user."""
    specification = research_assistant()
    criterion = specification.behaviour("EB-1").criteria[0]  # type: ignore[union-attr]
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["turn"]), specs=[TURNS], threshold=0.5
    )

    criterion.description.then = "it stays within the turn budget"
    new_fqn = matcher.match(criterion)

    assert new_fqn == TURNS.fqn


# ── grader arguments ───────────────────────────────────────────────────────


def test_arguments_are_left_at_their_defaults() -> None:
    """Known debt: "within 5 turns" is judged against whatever the default is."""
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["turn"]), specs=[TURNS], threshold=0.5
    )
    criterion = a_criterion("it finishes within 5 turns")

    matcher.match(criterion)

    assert criterion.grader_args == {}
