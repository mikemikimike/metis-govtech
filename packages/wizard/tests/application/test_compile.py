"""The output end: compilation, reference dropping, and the review document."""

from pathlib import Path

import pytest
import yaml
from fixtures.profiles import (
    BOUNDED_TROUBLESHOOTING,
    CITATION_METRIC,
    TURN_BUDGET,
    research_assistant,
)

from metis.wizard.application.compile import (
    SCHEMA_VERSION,
    CompilationError,
    build_experiment_document,
    compile_experiment,
    render_review,
    to_yaml,
    write_experiment,
)

EXPERIMENT_ID = "research-assistant"
GOLDEN = Path(__file__).parents[1] / "fixtures" / "golden_experiment.yaml"


def compiled() -> dict:
    return compile_experiment(research_assistant(), EXPERIMENT_ID)


# ── the golden file ────────────────────────────────────────────────────────


def test_compiles_byte_identically_across_runs() -> None:
    """Determinism is what makes the golden file meaningful."""
    assert to_yaml(compiled()) == to_yaml(compiled())


def test_matches_the_golden_file() -> None:
    """If this fails, either the compiler changed or the fixture did — check which.

    Regenerate with:
        uv run python -m tests.regenerate_golden
    """
    assert to_yaml(compiled()) == GOLDEN.read_text()


# ── the schema contract ────────────────────────────────────────────────────


def test_emits_schema_version_explicitly() -> None:
    """The engine declares it Literal[1] with no default and requires it."""
    assert compiled()["schema_version"] == SCHEMA_VERSION


def test_emits_the_default_runner_factory_ref() -> None:
    """The engine v1 schema requires it; the compiler stamps a default the loader resolves."""
    from metis.wizard.application.compile import DEFAULT_RUNNER_FACTORY_REF

    assert compiled()["runner_factory_ref"] == DEFAULT_RUNNER_FACTORY_REF


def test_nothing_is_written_when_validation_fails(tmp_path: Path) -> None:
    """A malformed experiment must never reach disk."""
    profile = research_assistant()
    profile.personas = []  # the schema requires at least one persona
    path = tmp_path / "experiment.yaml"

    with pytest.raises(CompilationError):
        write_experiment(profile, EXPERIMENT_ID, path)

    assert not path.exists()


def test_the_engine_model_accepts_the_compiled_document() -> None:
    """The schema is the stated contract; the engine's own model is the arbiter.

    This catches anything the JSON schema permits but the loader rejects — notably the
    cross-field check that every persona_ref resolves.
    """
    from metis.engine.simulation.types import Experiment

    experiment = Experiment.model_validate(compiled())

    assert experiment.schema_version == SCHEMA_VERSION
    assert len(experiment.scenarios) == 2


# ── the hand-authored door ───────────────────────────────────────────────────


def test_a_hand_authored_document_matches_an_interviewed_one() -> None:
    """The form and the interview serialise identically from the same content.

    `build_experiment_document` is what the web door's stateless compile route calls: it
    takes the fields a form submits and produces the same validated document the interview's
    compiler does — so the two doors emit byte-identical yaml. Here we feed it the pieces the
    golden profile compiles to and assert the serialisation matches.
    """
    interviewed = compiled()

    hand = build_experiment_document(
        experiment_id=interviewed["id"],
        description=interviewed["description"],
        personas=interviewed["personas"],
        scenarios=interviewed["scenarios"],
    )

    assert to_yaml(hand) == to_yaml(interviewed)


def test_a_hand_authored_document_is_validated() -> None:
    """The stateless route must refuse a document the engine would reject."""
    with pytest.raises(CompilationError):
        build_experiment_document(
            experiment_id="x",
            description="a scenario with no persona reference",
            personas=[{"id": "p", "description": "someone"}],
            scenarios=[{"id": "S-1", "description": "do a thing", "persona_refs": []}],
        )


def test_a_hand_authored_document_stamps_the_schema_version() -> None:
    """The version is the compiler's to stamp — a form never supplies it."""
    document = build_experiment_document(
        experiment_id="x",
        description="d",
        personas=[{"id": "p", "description": "someone"}],
        scenarios=[
            {"id": "S-1", "description": "do a thing", "persona_refs": ["p"]},
        ],
    )

    assert document["schema_version"] == SCHEMA_VERSION


# ── metric references ──────────────────────────────────────────────────────


def test_a_shared_metric_appears_once() -> None:
    """EB-1's two criteria resolve to the same metric; the scenario should carry it once."""
    scenario = next(t for t in compiled()["scenarios"] if t["id"] == "S-1")

    assert scenario["metric_refs"].count(CITATION_METRIC) == 1


def test_review_and_experiment_keep_the_fully_qualified_metric() -> None:
    review = render_review(research_assistant(), EXPERIMENT_ID)

    assert f"`{CITATION_METRIC}`" in review
    assert CITATION_METRIC in to_yaml(compiled())


def test_a_scenario_is_measured_only_on_what_it_covers() -> None:
    """Nothing rides along. A scenario's metrics come from its own ticked behaviours, full stop.

    S-1 covers EB-1 (ticked, citation) and EB-2 (unticked, turn budget); S-2 covers EB-3
    (ticked, bounded troubleshooting). So the turn budget metric — bound only to an unticked
    behaviour — reaches no scenario at all.
    """
    document = compiled()
    by_id = {t["id"]: t["metric_refs"] for t in document["scenarios"]}

    assert by_id["S-1"] == [CITATION_METRIC]
    assert by_id["S-2"] == [BOUNDED_TROUBLESHOOTING]
    assert not any(TURN_BUDGET in refs for refs in by_id.values())


def test_a_deleted_persona_is_not_referenced() -> None:
    """The harness raises on an unknown persona_ref rather than skipping it."""
    profile = research_assistant()
    profile.personas = [p for p in profile.personas if p.id != "impatient-executive"]

    scenario = next(
        t
        for t in compile_experiment(profile, EXPERIMENT_ID)["scenarios"]
        if t["id"] == "S-1"
    )

    assert scenario["persona_refs"] == ["cooperative-delegator"]


def test_personas_are_inline() -> None:
    """One output file, one schema — there is no separate personas file."""
    document = compiled()

    assert [p["id"] for p in document["personas"]] == [
        "cooperative-delegator",
        "impatient-executive",
    ]


def test_the_yaml_parses_back_to_the_same_document() -> None:
    document = compiled()

    assert yaml.safe_load(to_yaml(document)) == document


# ── the review document ────────────────────────────────────────────────────


def test_review_keeps_behaviours_that_were_never_ticked() -> None:
    """The record of what was considered and deliberately not measured."""
    review = render_review(research_assistant(), EXPERIMENT_ID)

    assert "Considered, not measured" in review
    assert "EB-2" in review
    assert "Keeps answers under a page" in review


def test_review_marks_why_each_behaviour_is_there() -> None:
    review = render_review(research_assistant(), EXPERIMENT_ID)

    assert "_(measured)_" in review
    assert "_(considered, not measured)_" in review


def test_review_trial_count_matches_the_profile() -> None:
    """The document and the interview footer read from the same calculation."""
    profile = research_assistant()

    review = render_review(profile, EXPERIMENT_ID)
    assert f"{profile.trial_count()} trials" in review
    assert "## Trials" in review
    assert "scenario–persona pairs" not in review
    assert "## Who we simulate" not in review
    assert "## How we check it" not in review
    assert "## Personas" in review
    assert "## Scenarios" in review


def test_review_needs_no_interview() -> None:
    """A hand-written profile renders — no step, no history, no interview id."""
    assert render_review(research_assistant(), EXPERIMENT_ID).startswith(
        "# Research assistant"
    )


def test_review_and_experiment_use_the_same_persona_ids() -> None:
    """The readable id is both the human label and the compiled reference key."""
    review = render_review(research_assistant(), EXPERIMENT_ID)

    assert "**Cooperative delegator**" in review
    assert "**Impatient executive**" in review
    assert [p["id"] for p in compiled()["personas"]] == [
        "cooperative-delegator",
        "impatient-executive",
    ]


def test_the_product_detail_is_kept_in_review_but_not_compiled() -> None:
    profile = research_assistant()

    review = render_review(profile, EXPERIMENT_ID)
    experiment = to_yaml(compile_experiment(profile, EXPERIMENT_ID))

    assert profile.product.detail in review
    assert profile.product.detail not in experiment
    assert yaml.safe_load(experiment)["description"] == profile.product.description
