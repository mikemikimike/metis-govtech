"""Tests for the action validation layer."""

from unittest.mock import patch

import pytest

from metis.engine.simulation.harness._action_filter import (
    ActionIntent,
    SkipReason,
    filter_actions,
)
from metis.engine.simulation.types import (
    ButtonClickAction,
    FileUploadAction,
    FormFillAction,
)


@pytest.fixture(autouse=True)
def _suppress_structlog():
    """Patch logger to avoid closed-file errors from test ordering."""
    with patch("metis.engine.simulation.harness._action_filter.logger"):
        yield


@pytest.fixture
def available_files() -> list[str]:
    return ["data.csv", "report.xlsx", "config.json"]


class TestButtonFiltering:
    """Non-actionable buttons are filtered; actionable ones pass through."""

    def test_non_actionable_reasoning_filtered(self, available_files):
        actions = [ButtonClickAction(selector="Reasoning (1 step)")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0].reason == SkipReason.non_actionable

    def test_non_actionable_sources_filtered(self, available_files):
        actions = [ButtonClickAction(selector="View sources")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0
        assert result.skipped[0].reason == SkipReason.non_actionable

    def test_non_actionable_collapse_filtered(self, available_files):
        actions = [ButtonClickAction(selector="Collapse all")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0

    def test_non_actionable_show_more_filtered(self, available_files):
        actions = [ButtonClickAction(selector="Show more")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0

    def test_non_actionable_citation_filtered(self, available_files):
        actions = [ButtonClickAction(selector="citation [3]")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0

    def test_non_actionable_step_count_filtered(self, available_files):
        actions = [ButtonClickAction(selector="3 steps")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0

    def test_actionable_button_passes(self, available_files):
        actions = [ButtonClickAction(selector="Download all")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 1
        assert result.actions[0].intent == ActionIntent.click

    def test_submit_button_classified_as_submit(self, available_files):
        actions = [ButtonClickAction(selector="Generate report")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 1
        assert result.actions[0].intent == ActionIntent.submit

    def test_confirm_button_classified_as_submit(self, available_files):
        actions = [ButtonClickAction(selector="Confirm")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 1
        assert result.actions[0].intent == ActionIntent.submit


class TestUploadFiltering:
    """Duplicate and missing-file uploads are filtered."""

    def test_duplicate_upload_filtered(self, available_files):
        actions = [FileUploadAction(file="data.csv")]
        result = filter_actions(
            actions, uploaded_files={"data.csv"}, available_files=available_files
        )
        assert len(result.actions) == 0
        assert result.skipped[0].reason == SkipReason.duplicate_upload

    def test_missing_file_filtered(self, available_files):
        actions = [FileUploadAction(file="nonexistent.txt")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0
        assert result.skipped[0].reason == SkipReason.file_not_found
        assert "data.csv" in result.skipped[0].detail

    def test_valid_upload_passes(self, available_files):
        actions = [FileUploadAction(file="data.csv")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 1
        assert result.actions[0].intent == ActionIntent.upload


class TestFormFillFiltering:
    """Form fills always pass through."""

    def test_form_fill_passes(self, available_files):
        actions = [FormFillAction(selector="select#model", value="GPT-4")]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 1
        assert result.actions[0].intent == ActionIntent.fill


class TestMixedActions:
    """Filter handles a realistic mix of actions."""

    def test_mixed_actions_correctly_classified(self, available_files):
        actions = [
            FileUploadAction(file="data.csv"),
            FileUploadAction(file="data.csv"),  # duplicate
            ButtonClickAction(selector="Reasoning (1 step)"),  # non-actionable
            ButtonClickAction(selector="Submit"),  # submit
            FormFillAction(selector="input#name", value="test"),
            ButtonClickAction(selector="Download all"),  # click
        ]
        result = filter_actions(
            actions, uploaded_files=set(), available_files=available_files
        )
        # First upload passes, second is duplicate (first one added to uploaded_files? No — filter doesn't mutate)
        # Actually filter doesn't track uploads within the batch — both "data.csv" are new
        # Wait, the second one: uploaded_files is empty, and file exists, so it passes too
        # The filter is stateless within a call — dedup is session-level
        assert len(result.actions) == 5  # both uploads + submit + fill + click
        assert len(result.skipped) == 1  # only the Reasoning button

    def test_empty_actions_returns_empty(self, available_files):
        result = filter_actions(
            [], uploaded_files=set(), available_files=available_files
        )
        assert len(result.actions) == 0
        assert len(result.skipped) == 0
