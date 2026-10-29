"""Tests for the runner contract's data model — ActionResult and Observation."""

import pytest
from pydantic import ValidationError

from metis.engine.simulation.gen_1.types import ActionResult, Observation


class TestActionResultVerdict:
    """I2: succeeded is mandatory; failure needs a detail; retryable is failure-only."""

    def test_success_needs_no_detail(self) -> None:
        row = ActionResult(action_index=0, succeeded=True)
        assert row.detail == ""
        assert row.retryable is None
        assert row.withheld is False

    def test_failure_without_detail_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            ActionResult(action_index=0, succeeded=False)

    def test_failure_with_whitespace_only_detail_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            ActionResult(action_index=0, succeeded=False, detail="   \n ")

    def test_success_with_retryable_true_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="MUST be None"):
            ActionResult(action_index=0, succeeded=True, retryable=True)

    def test_success_with_retryable_false_is_also_rejected(self) -> None:
        # Not a typo: False is an opinion about retrying a delivery that never
        # failed, which is exactly as meaningless as True.
        with pytest.raises(ValidationError, match="MUST be None"):
            ActionResult(action_index=0, succeeded=True, retryable=False)

    @pytest.mark.parametrize("hint", [None, True, False])
    def test_failure_may_carry_any_retryable_value(self, hint: bool | None) -> None:
        row = ActionResult(
            action_index=0, succeeded=False, detail="rejected", retryable=hint
        )
        assert row.retryable is hint

    def test_withheld_row_is_a_failure_row_with_a_detail(self) -> None:
        row = ActionResult(
            action_index=2,
            succeeded=False,
            detail="Turn not submitted: file 'x.csv' is not a fixture for this scenario",
            withheld=True,
        )
        assert row.withheld and not row.succeeded


class TestObservationChannels:
    def test_available_actions_defaults_to_none_not_empty_list(self) -> None:
        # Three-state: None means nobody looked, [] means looked and none offered.
        assert Observation().available_actions is None

    def test_observed_but_empty_is_distinguishable_from_unobserved(self) -> None:
        assert Observation(available_actions=[]).available_actions == []

    def test_new_channels_default_empty(self) -> None:
        obs = Observation()
        assert obs.response_notices == []
        assert obs.action_results == []

    def test_delivered_defaults_to_true(self) -> None:
        # I5: the common case is that nothing about the turn is in question.
        assert Observation().delivered is True
