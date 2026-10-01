"""The document model: round-tripping, the tick, and walking the tree."""

import json
from pathlib import Path

import jsonschema

import metis.wizard
from metis.wizard.contracts import ProductProfile
from tests.fixtures.wizard.profiles import research_assistant

# The schema ships beside the wizard package (packages/wizard/schemas), not inside its source, so
# anchor to the installed package rather than to this test file's location.
SCHEMA_PATH = (
    Path(metis.wizard.__file__).resolve().parents[3] / "schemas" / "profile.schema.json"
)


def test_round_trips_through_json_unchanged() -> None:
    """Every id, enum value and reference list survives a serialise/parse cycle."""
    original = research_assistant()
    parsed = ProductProfile.model_validate_json(original.model_dump_json())

    assert parsed == original
    # spot-check the structured criterion description and stable references
    assert parsed.behaviour("EB-3").criteria[0].description.then.startswith("it stops")  # type: ignore[union-attr]
    assert parsed.scenario("S-1").behaviour_refs == ["EB-1", "EB-2"]  # type: ignore[union-attr]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    original = research_assistant()
    path = tmp_path / "profile.yaml"
    original.save(path)

    assert ProductProfile.load(path) == original


def test_unmeasuring_keeps_criteria() -> None:
    """`measured` is scope, not content — the criteria are never derived from it.

    This is what lets the tick stay live without any staleness tracking.
    """
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")
    assert behaviour is not None
    before = [c.model_copy(deep=True) for c in behaviour.criteria]

    behaviour.measured = False

    assert behaviour.criteria == before
    assert len(behaviour.criteria) == 2


def test_dormant_criteria_survive_on_unmeasured_behaviours() -> None:
    """The fixture's EB-2 is unmeasured but keeps its criterion."""
    profile = research_assistant()
    behaviour = profile.behaviour("EB-2")

    assert behaviour is not None
    assert behaviour.measured is False
    assert len(behaviour.criteria) == 1


def test_measured_behaviours_are_the_behaviours_the_user_chose() -> None:
    """The measurement choice is the user's only real decision."""
    profile = research_assistant()

    assert {b.id for b in profile.measured_behaviours()} == {"EB-1", "EB-3"}
    # EB-2 is unmeasured: still in the document, still carrying criteria
    assert "EB-2" in {b.id for b in profile.behaviours()}


def test_a_behaviour_resolves_to_its_owning_feature() -> None:
    """`Behaviour` carries no feature id — position in the tree is the only link."""
    profile = research_assistant()

    assert profile.feature_of("EB-1").id == "F-1"  # type: ignore[union-attr]
    assert profile.feature_of("EB-3").id == "F-2"  # type: ignore[union-attr]
    assert profile.feature_of("EB-nope") is None


def test_criterion_ids_are_scoped_to_their_behaviour() -> None:
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")

    assert behaviour is not None
    assert [c.id for c in behaviour.criteria] == ["AC-1-1", "AC-1-2"]


def test_coverage_and_trial_count() -> None:
    profile = research_assistant()

    assert profile.uncovered() == []
    assert [t.id for t in profile.scenarios_covering("EB-1")] == ["S-1"]
    # S-1: 2 personas × 3 trials = 6; S-2: 1 × 3 = 3
    assert profile.trial_count() == 9

    profile.scenarios[1].num_trials = 1
    assert profile.trial_count() == 7

    profile.scenarios[0].persona_refs = []
    assert profile.trial_count() == 1


def test_uncovered_reports_ticked_behaviours_with_no_scenario() -> None:
    profile = research_assistant()
    profile.scenarios = [t for t in profile.scenarios if t.id != "S-2"]

    assert [b.id for b in profile.uncovered()] == ["EB-3"]


def test_full_profile_validates_against_committed_schema() -> None:
    """A profile exercising every shape conforms to the shipped profile.schema.json."""
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(
        instance=research_assistant().model_dump(mode="json"), schema=schema
    )
