"""Tests for observable execution metadata written by the Langfuse extractor.

The extractor writes ``stop_reason``, ``cancellation_available``, and
``slide_image_refs`` into the metric-visible metadata of every test case. These
tests use a mocked Langfuse client (no network) and assert that the fields reach
both the per-trace ``LLMTestCase`` metadata and the session
``ConversationalTestCase`` metadata, and that they are marked unavailable (never
invented) when the caller does not supply them.
"""

from pathlib import Path
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


def test_execution_metadata_reaches_metric_metadata(tmp_path: Path) -> None:
    """Stop reason, cancellation, and ordered image refs reach both metadata layers."""
    lf = _make_langfuse([_make_trace("t1", "s1")])
    artifacts = [
        # Out-of-order + mixed types: only images are kept, sorted by turn/name.
        Artifact(
            name="slide2.png",
            at_turn=1,
            path="out/slide2.png",
            state="received",
        ),
        Artifact(
            name="deck.pptx",
            at_turn=1,
            path="out/deck.pptx",
            state="received",
        ),
        Artifact(
            name="slide1.png",
            at_turn=0,
            path="out/slide1.png",
            state="received",
        ),
    ]

    result = fetch_by_session_id(
        "s1",
        lf,
        experiment_root=tmp_path,
        artifacts=artifacts,
        stop_reason="goal_achieved",
        cancellation_available=True,
    )

    expected_slide1 = str(tmp_path / "out/slide1.png")
    expected_slide2 = str(tmp_path / "out/slide2.png")

    tc = result.test_cases[0]
    assert tc.metadata is not None
    assert tc.metadata["stop_reason"] == "goal_achieved"
    assert tc.metadata["cancellation_available"] is True
    # PPTX excluded; images ordered by (at_turn, name).
    assert tc.metadata["slide_image_refs"] == [expected_slide1, expected_slide2]

    ctc = result.session_test_cases[0]
    assert ctc.metadata is not None
    assert ctc.metadata["stop_reason"] == "goal_achieved"
    assert ctc.metadata["cancellation_available"] is True
    assert ctc.metadata["slide_image_refs"] == [expected_slide1, expected_slide2]


def test_fixture_images_are_excluded_from_slide_refs(tmp_path: Path) -> None:
    """Persona-uploaded image fixtures must not reach multimodal metric inputs.

    Fixtures now live in ``record.artifacts`` alongside target outputs, so the
    slide-image filter must drop ``source="fixture"`` entries — otherwise the
    user's own uploaded PNG would be judged as an assistant deliverable.
    """
    lf = _make_langfuse([_make_trace("t1", "s1")])
    artifacts = [
        Artifact(
            name="uploaded.png",
            source="fixture",
            at_turn=1,
            path="fixtures/uploaded.png",
            state="received",
        ),
        Artifact(
            name="delivered.png",
            source="target",
            at_turn=2,
            path="out/delivered.png",
            state="received",
        ),
    ]

    result = fetch_by_session_id(
        "s1", lf, experiment_root=tmp_path, artifacts=artifacts
    )

    tc = result.test_cases[0]
    assert tc.metadata is not None
    # Only the delivered target image; the fixture upload is excluded.
    assert tc.metadata["slide_image_refs"] == [str(tmp_path / "out/delivered.png")]


def test_missing_execution_metadata_is_marked_unavailable(tmp_path: Path) -> None:
    """When the caller supplies nothing, fields are None (never fabricated)."""
    lf = _make_langfuse([_make_trace("t1", "s1")])

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

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


def test_metadata_artifacts_carry_absolute_resolved_path(tmp_path: Path) -> None:
    """Artifacts embedded in test-case metadata carry an absolute resolved path.

    ``metis-library`` depends only on ``metis-core`` (never on ``metis-engine``),
    so it has no access to ``experiment_root``. Resolving here, before artifacts
    are embedded in ``LLMTestCase.metadata``, means library's own code just reads
    an already-absolute path string.
    """
    lf = _make_langfuse([_make_trace("t1", "s1")])
    artifacts = [
        Artifact(name="deck.pptx", path="out/deck.pptx", at_turn=1, state="received"),
    ]
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "deck.pptx").write_bytes(b"PK\x03\x04")

    result = fetch_by_session_id(
        "s1", lf, experiment_root=tmp_path, artifacts=artifacts
    )

    tc = result.test_cases[0]
    assert tc.metadata is not None
    metadata_artifacts = tc.metadata["artifacts"]
    assert metadata_artifacts[0]["path"] == str(tmp_path / "out" / "deck.pptx")
