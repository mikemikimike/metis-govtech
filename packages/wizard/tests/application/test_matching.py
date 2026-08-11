"""Criterion prose → metric FQN.

Written before the implementation. The property that matters most is the fallback: a matcher
that cannot reach its embedding provider must still leave the user with a working experiment,
because the alternative is an interview that stops for a reason the user cannot act on.
"""

import pytest
from fixtures.profiles import research_assistant

from metis.wizard.application.matching import (
    GENERATED_JUDGE_FQN,
    EmbeddingMatcher,
    library_catalogue,
    match_profile,
)
from metis.wizard.contracts import Criterion, MetricSpec


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


CITATION = MetricSpec(
    fqn="metis.library.metrics.orchestration.SynthesisFaithfulnessMetric",
    name="Synthesis faithfulness",
    description="Whether claims are supported by the source they cite.",
)
TURNS = MetricSpec(
    fqn="metis.library.metrics.universal.TurnBudgetMetric",
    name="Turn budget",
    description="Session completed within the allowed turn budget.",
)


def a_criterion(then: str, **kw) -> Criterion:
    return Criterion(
        id="AC-1-1", given="a question", when="it answers", then=then, **kw
    )


# ── the catalogue ──────────────────────────────────────────────────────────


def test_the_catalogue_reads_real_metrics() -> None:
    specs = library_catalogue()

    assert specs
    assert all(spec.fqn and spec.name and spec.description for spec in specs)
    assert any("TurnBudgetMetric" in spec.fqn for spec in specs)


def test_the_catalogue_covers_every_exported_metric() -> None:
    """The reader must find the whole library, not the one non-underscored module a submodule
    walk would leave. Verified against the library's own export list, so a metric dropped in
    the file split is caught rather than silently absent from the picker."""
    import inspect

    import metis.library.metrics as metrics

    exported = {
        name
        for name, obj in vars(metrics).items()
        if inspect.isclass(obj)
        and obj.__name__.endswith("Metric")
        and not obj.__name__.startswith(("Base", "Sync"))
        and obj.__module__.startswith("metis.library.metrics")
    }
    catalogued = {spec.fqn.rsplit(".", 1)[-1] for spec in library_catalogue()}
    assert catalogued == exported


def test_the_catalogue_never_instantiates_a_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Many metrics take constructor arguments; reading a display name must not build one."""
    from metis.library.metrics import TurnBudgetMetric

    def explode(*_a, **_kw):
        raise AssertionError("the catalogue instantiated a metric")

    monkeypatch.setattr(TurnBudgetMetric, "__init__", explode)

    library_catalogue.cache_clear()
    assert library_catalogue()
    library_catalogue.cache_clear()


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
    """A partial match: the criterion mentions both concepts, the metric only one."""
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


def test_a_degraded_run_still_produces_a_loadable_experiment(tmp_path) -> None:
    from metis.wizard.application.compile import write_experiment

    profile = research_assistant()
    for behaviour in profile.ticked():
        for criterion in behaviour.criteria:
            criterion.metric_fqn = None

    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder([], fails=True), specs=[CITATION], threshold=0.5
    )
    match_profile(profile, matcher)

    write_experiment(profile, "degraded", tmp_path / "experiment.yaml")

    from metis.engine.cli import _validate_inputs

    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "policy.pdf").write_text("x")
    _validate_inputs(tmp_path)  # sys.exit(1) on any problem, so returning is the pass


# ── matching over a whole profile ──────────────────────────────────────────


def test_only_criteria_without_a_metric_are_matched() -> None:
    """Re-matching a criterion that already has a metric would be a wasted call."""
    profile = research_assistant()
    embedder = FakeEmbedder(["source"])
    matcher = EmbeddingMatcher(embedder=embedder, specs=[CITATION], threshold=0.5)

    matched = match_profile(profile, matcher)

    assert matched == 0  # the fixture already has metrics on everything


def test_unticked_behaviours_are_not_matched() -> None:
    """Nothing is generated for behaviours nobody picked, matching included."""
    profile = research_assistant()
    unticked = profile.behaviour("EB-2")
    assert unticked is not None
    unticked.criteria[0].metric_fqn = None
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["source"]), specs=[CITATION], threshold=0.5
    )

    match_profile(profile, matcher)

    assert unticked.criteria[0].metric_fqn is None


def test_rematching_a_criterion_is_silent_and_free() -> None:
    """The matcher chose the previous value, so re-choosing takes nothing from the user."""
    profile = research_assistant()
    criterion = profile.behaviour("EB-1").criteria[0]  # type: ignore[union-attr]
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["turn"]), specs=[TURNS], threshold=0.5
    )

    criterion.then = "it stays within the turn budget"
    new_fqn = matcher.match(criterion)

    assert new_fqn == TURNS.fqn


# ── metric arguments ───────────────────────────────────────────────────────


def test_arguments_are_left_at_their_defaults() -> None:
    """Known debt: "within 5 turns" is judged against whatever the default is."""
    matcher = EmbeddingMatcher(
        embedder=FakeEmbedder(["turn"]), specs=[TURNS], threshold=0.5
    )
    criterion = a_criterion("it finishes within 5 turns")

    matcher.match(criterion)

    assert criterion.metric_args == {}
