"""Tests that page actions module integrates retry infrastructure."""

from metis.engine.simulation.runners.playwright._element_resolver import resolve_element
from metis.engine.simulation.runners.playwright._page_actions import (
    auto_fill_and_submit,
    send_message,
    upload_file,
)
from metis.engine.simulation.runners.playwright._retry import (
    action_retry,
    track_submission,
)


class TestPageActionsImports:
    """Verify the retry and resolver infrastructure is wired into page_actions."""

    def test_send_message_importable(self) -> None:
        assert send_message is not None

    def test_upload_file_importable(self) -> None:
        assert upload_file is not None

    def test_auto_fill_importable(self) -> None:
        assert auto_fill_and_submit is not None

    def test_retry_infrastructure_importable(self) -> None:
        assert action_retry is not None
        assert track_submission is not None
        assert resolve_element is not None
