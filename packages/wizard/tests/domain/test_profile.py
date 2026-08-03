"""The document model: round-tripping, the tick, and walking the tree."""

from pathlib import Path

from fixtures.profiles import research_assistant

from metis.wizard.contracts import EpicScope, InteractionType, ProductProfile


def test_round_trips_through_json_unchanged() -> None:
    """Every id, enum value and reference list survives a serialise/parse cycle."""
    original = research_assistant()
    parsed = ProductProfile.model_validate_json(original.model_dump_json())

    assert parsed == original
    # spot-check the things a loose serialiser would quietly flatten
    assert parsed.universal_epic() is not None
    assert parsed.universal_epic().scope is EpicScope.UNIVERSAL  # type: ignore[union-attr]
    assert parsed.behaviour("EB-3").interaction_type is InteractionType.FORM  # type: ignore[union-attr]
    assert parsed.task("T-1").behaviour_refs == ["EB-1", "EB-2"]  # type: ignore[union-attr]


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


def test_ticked_excludes_universal_behaviours() -> None:
    """Universals are always on and ride along on every task — never the user's decision."""
    profile = research_assistant()
    ticked = {b.id for b in profile.ticked()}

    assert ticked == {"EB-1", "EB-3"}
    assert "EB-U1" not in ticked
    # but they are still reachable, and still in the one epics list
    assert [b.id for b in profile.universal_behaviours()] == ["EB-U1"]


def test_universal_epic_appears_in_a_plain_iteration() -> None:
    """Renderers and the compiler walk one list — no special-casing to find universals."""
    profile = research_assistant()

    assert "EP-UNI" in [e.id for e in profile.epics]
    assert "EB-U1" in [b.id for b in profile.behaviours()]


def test_scope_is_derived_from_the_parent_epic() -> None:
    """`Behaviour` carries no scope field — it would be redundant with position."""
    profile = research_assistant()

    assert profile.epic_of("EB-U1").is_universal  # type: ignore[union-attr]
    assert not profile.epic_of("EB-1").is_universal  # type: ignore[union-attr]


def test_criterion_ids_are_scoped_to_their_behaviour() -> None:
    profile = research_assistant()
    behaviour = profile.behaviour("EB-1")

    assert behaviour is not None
    assert [c.id for c in behaviour.criteria] == ["AC-1-1", "AC-1-2"]


def test_coverage_and_session_count() -> None:
    profile = research_assistant()

    assert profile.uncovered() == []
    assert [t.id for t in profile.tasks_covering("EB-1")] == ["T-1"]
    # T-1: 2 personas × 3 trials = 6; T-2: 1 × 3 = 3
    assert profile.session_count() == 9


def test_uncovered_reports_ticked_behaviours_with_no_task() -> None:
    profile = research_assistant()
    profile.tasks = [t for t in profile.tasks if t.id != "T-2"]

    assert [b.id for b in profile.uncovered()] == ["EB-3"]
