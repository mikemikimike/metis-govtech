"""Tests for observable execution metadata written by the Langfuse extractor.

The extractor writes ``stop_reason``, ``cancellation_available``, and
``slide_image_refs`` into the metric-visible metadata of every test case. These
tests use a mocked Langfuse client (no network) and assert that the fields reach
both the per-trace ``LLMTestCase`` metadata and the session
``ConversationalTestCase`` metadata, and that they are marked unavailable (never
invented) when the caller does not supply them.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from metis.core import Artifact
from metis.engine.extractor.langfuse import fetch_by_session_id


def _make_trace(trace_id: str, session_id: str) -> SimpleNamespace:
    """Build a minimal trace object the extractor can convert."""
    return SimpleNamespace(
        id=trace_id,
        session_id=session_id,
        input="user question",
        output="assistant answer",
        timestamp="2026-01-01T00:00:00Z",
    )


def _make_langfuse(traces: list[SimpleNamespace]) -> MagicMock:
    """Build a mocked Langfuse client returning the given traces, no observations."""
    lf = MagicMock()
    lf.api.trace.list.return_value = SimpleNamespace(data=traces)
    lf.api.observations.get_many.return_value = SimpleNamespace(data=[])
    return lf


def test_execution_metadata_reaches_metric_metadata() -> None:
    """Stop reason, cancellation, and ordered image refs reach both metadata layers."""
    lf = _make_langfuse([_make_trace("t1", "s1")])
    artifacts = [
        # Out-of-order + mixed types: only images are kept, sorted by turn/name.
        Artifact(
            name="slide2.png",
            type="download",
            collected_at_turn=1,
            uri="file:///out/slide2.png",
        ),
        Artifact(
            name="deck.pptx",
            type="download",
            collected_at_turn=1,
            uri="file:///out/deck.pptx",
        ),
        Artifact(
            name="slide1.png",
            type="download",
            collected_at_turn=0,
            uri="file:///out/slide1.png",
        ),
    ]

    result = fetch_by_session_id(
        "s1",
        lf,
        artifacts=artifacts,
        stop_reason="goal_achieved",
        cancellation_available=True,
    )

    tc = result.test_cases[0]
    assert tc.metadata is not None
    assert tc.metadata["stop_reason"] == "goal_achieved"
    assert tc.metadata["cancellation_available"] is True
    # PPTX excluded; images ordered by (collected_at_turn, name).
    assert tc.metadata["slide_image_refs"] == ["/out/slide1.png", "/out/slide2.png"]

    ctc = result.session_test_cases[0]
    assert ctc.metadata is not None
    assert ctc.metadata["stop_reason"] == "goal_achieved"
    assert ctc.metadata["cancellation_available"] is True
    assert ctc.metadata["slide_image_refs"] == ["/out/slide1.png", "/out/slide2.png"]


def test_missing_execution_metadata_is_marked_unavailable() -> None:
    """When the caller supplies nothing, fields are None (never fabricated)."""
    lf = _make_langfuse([_make_trace("t1", "s1")])

    result = fetch_by_session_id("s1", lf)

    tc = result.test_cases[0]
    assert tc.metadata is not None
    assert tc.metadata["stop_reason"] is None
    assert tc.metadata["cancellation_available"] is None
    assert tc.metadata["slide_image_refs"] is None

    ctc = result.session_test_cases[0]
    assert ctc.metadata is not None
    assert ctc.metadata["stop_reason"] is None
    assert ctc.metadata["cancellation_available"] is None
    assert ctc.metadata["slide_image_refs"] is None
