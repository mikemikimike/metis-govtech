"""The document model: round-tripping, the tick, and walking the tree."""

from pathlib import Path

from fixtures.profiles import research_assistant

from metis.wizard.contracts import InteractionType, ProductProfile


def test_round_trips_through_json_unchanged() -> None:
    """Every id, enum value and reference list survives a serialise/parse cycle."""
    original = research_assistant()
    parsed = ProductProfile.model_validate_json(original.model_dump_json())

    assert parsed == original
    # spot-check the things a loose serialiser would quietly flatten
    assert parsed.behaviour("EB-3").interaction_type is InteractionType.FORM  # type: ignore[union-attr]
    assert parsed.scenario("S-1").behaviour_refs == ["EB-1", "EB-2"]  # type: ignore[union-attr]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    original = research_assistant()
    path = tmp_path / "profile.json"
    original.save(path)

    assert ProductProfile.load(path) == original


def test_unticking_keeps_criteria() -> None:
    """`priority` is scope, not content — the criteria were never derived from it.

    This is what lets the tick stay live without any staleness tracking.
    """
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")
    assert behaviour is not None
    before = [c.model_copy(deep=True) for c in behaviour.criteria]

    behaviour.priority = False

    assert behaviour.criteria == before
    assert len(behaviour.criteria) == 2


def test_dormant_criteria_survive_on_unticked_behaviours() -> None:
    """The fixture's EB-2 is unticked but keeps its criterion, ready if it is ticked again."""
    profile = research_assistant()
    behaviour = profile.behaviour("EB-2")

    assert behaviour is not None
    assert behaviour.priority is False
    assert len(behaviour.criteria) == 1


def test_ticked_is_the_behaviours_the_user_chose() -> None:
    """The tick is the user's only real decision — nothing rides along beside it."""
    profile = research_assistant()

    assert {b.id for b in profile.ticked()} == {"EB-1", "EB-3"}
    # EB-2 is unticked: still in the document, still carrying criteria, just not measured
    assert "EB-2" in {b.id for b in profile.behaviours()}


def test_a_behaviour_resolves_to_its_owning_task() -> None:
    """`Behaviour` carries no task id — position in the tree is the only link."""
    profile = research_assistant()

    assert profile.task_of("EB-1").id == "T-1"  # type: ignore[union-attr]
    assert profile.task_of("EB-3").id == "T-2"  # type: ignore[union-attr]
    assert profile.task_of("EB-nope") is None


def test_criterion_ids_are_scoped_to_their_behaviour() -> None:
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")

    assert behaviour is not None
    assert [c.id for c in behaviour.criteria] == ["AC-1-1", "AC-1-2"]


def test_coverage_and_run_count() -> None:
    profile = research_assistant()

    assert profile.uncovered() == []
    assert [t.id for t in profile.scenarios_covering("EB-1")] == ["S-1"]
    # S-1: 2 personas × 3 trials = 6; S-2: 1 × 3 = 3
    assert profile.run_count() == 9

    profile.scenarios[1].num_trials = 1
    assert profile.run_count() == 7

    profile.scenarios[0].persona_refs = []
    assert profile.run_count() == 1


def test_uncovered_reports_ticked_behaviours_with_no_scenario() -> None:
    profile = research_assistant()
    profile.scenarios = [t for t in profile.scenarios if t.id != "S-2"]

    assert [b.id for b in profile.uncovered()] == ["EB-3"]
