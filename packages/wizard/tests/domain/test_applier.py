"""Patches, permissions, and the two things the model can never write."""

import pytest
from fixtures.profiles import research_assistant

from metis.wizard.contracts import Patch, PatchOp, PatchOrigin
from metis.wizard.domain import paths
from metis.wizard.domain.applier import apply, sanitise
from metis.wizard.domain.permissions import SessionStep, StepPermissions, owner_of

EB1_PRIORITY = "epics[EP-1].behaviours[EB-1].priority"
EB1_STATEMENT = "epics[EP-1].behaviours[EB-1].statement"
AC1_METRIC = "epics[EP-1].behaviours[EB-1].criteria[AC-1-1].metric_fqn"


def patch(path: str, value=None, *, op=PatchOp.SET, origin=PatchOrigin.MODEL) -> Patch:
    return Patch(op=op, path=path, value=value, origin=origin)


# ── origin is checked before address ───────────────────────────────────────


def test_the_users_tick_is_applied_and_the_models_is_not() -> None:
    """The two patches are byte-identical. Only origin tells them apart."""
    profile = research_assistant()
    profile.behaviour("EB-1").priority = False  # type: ignore[union-attr]

    from_model = patch(EB1_PRIORITY, True, origin=PatchOrigin.MODEL)
    from_wizard = patch(EB1_PRIORITY, True, origin=PatchOrigin.WIZARD)
    assert from_model.op == from_wizard.op and from_model.path == from_wizard.path

    rejected = apply(profile, [from_model])
    assert rejected.applied == []
    assert len(rejected.rejected) == 1
    assert profile.behaviour("EB-1").priority is False  # type: ignore[union-attr]

    accepted = apply(profile, [from_wizard])
    assert len(accepted.applied) == 1
    assert profile.behaviour("EB-1").priority is True  # type: ignore[union-attr]


def test_rejecting_a_tick_says_whose_call_it_is() -> None:
    """The one message where the wizard must say *I chose not to*."""
    profile = research_assistant()

    result = apply(profile, [patch(EB1_PRIORITY, True)])

    message = result.rejected[0].message
    assert "your call" in message
    assert "wrong" not in message.lower()  # not the user's fault
    assert "error" not in message.lower()  # not an outage


def test_the_model_cannot_claim_wizard_origin() -> None:
    """Origin is stamped by the code that builds a patch, never carried in model output."""
    claimed = [patch(EB1_PRIORITY, True, origin=PatchOrigin.WIZARD)]

    cleaned = sanitise(claimed)

    assert cleaned[0].origin is PatchOrigin.MODEL
    profile = research_assistant()
    profile.behaviour("EB-1").priority = False  # type: ignore[union-attr]
    assert apply(profile, cleaned).applied == []


def test_priority_is_owned_by_no_step() -> None:
    """The path appears in no entry — that is the structural half of the rule."""
    assert owner_of(EB1_PRIORITY) is None
    for globs in StepPermissions.values():
        assert not any("priority" in g for g in globs)


# ── the metric is the matcher's, not the model's ────────────────────────────


def test_metric_fqn_is_owned_by_no_step() -> None:
    """Like priority, it appears in no entry — the matcher resolves it, never the model."""
    assert owner_of(AC1_METRIC) is None
    for globs in StepPermissions.values():
        assert not any("metric_fqn" in g for g in globs)


def test_rejecting_a_metric_write_points_at_rewording() -> None:
    """A stray model write is refused with wording help, not the raw internal path."""
    profile = research_assistant()

    result = apply(profile, [patch(AC1_METRIC, "some.other.Metric")])

    assert result.applied == []
    message = result.rejected[0].message
    assert "reword" in message.lower()
    assert "metric_fqn" not in message  # the raw field name never surfaces
    assert AC1_METRIC not in message  # nor the raw path
    assert profile.behaviour("EB-1").criteria[0].metric_fqn != "some.other.Metric"  # type: ignore[union-attr]


def test_an_unowned_address_is_refused_without_leaking_its_path() -> None:
    """The generic refusal names 'part of that change', never the bookkeeping address."""
    result = apply(research_assistant(), [patch("product.invented_field", "x")])

    message = result.rejected[0].message
    assert "invented_field" not in message
    assert "isn't mine to write" in message


# ── permission follows the address, not the step ───────────────────────────


def test_a_behaviour_edit_from_the_criteria_step_is_applied() -> None:
    """ "Reword EB-4" typed at the criteria step should simply work."""
    profile = research_assistant()
    step = SessionStep.CRITERIA

    result = apply(profile, [patch(EB1_STATEMENT, "Cites a source, accurately")])

    assert len(result.applied) == 1
    assert profile.behaviour("EB-1").statement == "Cites a source, accurately"  # type: ignore[union-attr]
    assert owner_of(EB1_STATEMENT) is SessionStep.BEHAVIOURS  # a different step owns it
    assert step is SessionStep.CRITERIA  # and the current step never changed


def test_an_address_no_step_owns_is_writable_nowhere() -> None:
    profile = research_assistant()

    result = apply(profile, [patch("product.invented_field", "x")])

    assert result.applied == []
    assert owner_of("product.invented_field") is None


def test_clarify_and_prioritise_grant_nothing() -> None:
    """Both steps exist and the model may write nothing during either."""
    assert SessionStep.CLARIFY not in StepPermissions
    assert SessionStep.PRIORITISE not in StepPermissions


# ── the mechanics ──────────────────────────────────────────────────────────


def test_add_remove_and_set() -> None:
    profile = research_assistant()

    apply(
        profile,
        [
            patch(
                "personas",
                {"id": "P-9", "description": "A new archetype"},
                op=PatchOp.ADD,
                origin=PatchOrigin.WIZARD,
            )
        ],
    )
    assert profile.persona("P-9") is not None

    apply(
        profile,
        [patch("personas[P-9]", op=PatchOp.REMOVE, origin=PatchOrigin.WIZARD)],
    )
    assert profile.persona("P-9") is None


def test_a_patch_at_a_missing_node_is_reported_not_raised() -> None:
    profile = research_assistant()

    result = apply(profile, [patch("epics[EP-404].behaviours[EB-1].statement", "x")])

    assert result.applied == []
    assert result.any_rejected


def test_a_malformed_value_is_reported_not_raised() -> None:
    """A model can send an ADD whose value won't build the object its list holds — a bad
    enum, or behaviours as bare id strings instead of objects. That is a patch that didn't
    happen, not a crash four answers into an interview. The module's contract is that a
    rejected patch is never silent; a value that won't validate is one of them.
    """
    profile = research_assistant()

    result = apply(
        profile,
        [
            patch(
                "epics",
                {"id": "EP-9", "behaviours": ["EB-1", "EB-2"]},
                op=PatchOp.ADD,
                origin=PatchOrigin.WIZARD,  # even a trusted patch must not crash on a bad value
            )
        ],
    )

    assert result.applied == []
    assert result.any_rejected
    assert not any(e.id == "EP-9" for e in profile.epics)


def test_paths_address_by_id_not_index() -> None:
    profile = research_assistant()

    node = paths.resolve(profile, "epics[EP-1].behaviours[EB-1].criteria[AC-1-1]")

    assert node.id == "AC-1-1"


@pytest.mark.parametrize(
    ("bracket", "expected_id", "raises"),
    [
        ("EB-1", "EB-1", False),  # an id that matches always wins
        ("0", "EB-1", False),  # a bare integer falls back to a positional index
        ("99", None, True),  # out of range is still an error, not a silent miss
    ],
)
def test_a_list_is_addressed_by_id_first_then_by_numeric_index(
    bracket, expected_id, raises
) -> None:
    """A model is told to address by id and mostly does, but it sometimes falls back to
    `behaviours[0]`. A bare integer resolves positionally — no id in the scheme is an integer,
    so it cannot shadow a real id — which stops a whole behaviour's freshly drafted criteria
    from being silently dropped. Id addressing stays first and preferred.
    """
    profile = research_assistant()
    path = f"epics[EP-1].behaviours[{bracket}]"

    if raises:
        with pytest.raises(paths.PathError):
            paths.resolve(profile, path)
    else:
        assert paths.resolve(profile, path).id == expected_id


def test_criteria_added_by_positional_index_actually_land() -> None:
    """The end-to-end shape of the live failure: a criteria ADD addressed by index applies
    rather than being rejected, so the criteria the model drafted are not lost."""
    profile = research_assistant()
    profile.behaviour("EB-1").criteria = []  # type: ignore[union-attr]

    result = apply(
        profile,
        [
            patch(
                "epics[EP-1].behaviours[0].criteria",
                {
                    "id": "AC-1-1",
                    "given": "a question",
                    "when": "answered",
                    "then": "it cites a source",
                },
                op=PatchOp.ADD,
                origin=PatchOrigin.WIZARD,
            )
        ],
    )

    assert len(result.applied) == 1
    assert profile.behaviour("EB-1").criteria[0].id == "AC-1-1"  # type: ignore[union-attr]


def test_a_glob_does_not_span_a_dot() -> None:
    """`epics[*].behaviours[*]` must not match something nested deeper under it."""
    assert owner_of("epics[EP-1].behaviours[EB-1]") is SessionStep.BEHAVIOURS
    assert (
        owner_of("epics[EP-1].behaviours[EB-1].criteria[AC-1-1]")
        is SessionStep.CRITERIA
    )
