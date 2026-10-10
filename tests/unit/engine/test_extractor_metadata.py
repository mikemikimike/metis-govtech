"""Tests for observable execution metadata written by the Langfuse extractor.

The extractor writes ``stop_reason`` and ``cancellation_available`` into the
grader-visible metadata of every test case. These tests use a mocked Langfuse
client (no network) and assert that the fields reach both the per-trace
``LLMTestCase`` metadata and the session ``ConversationalTestCase`` metadata,
and that they are marked unavailable (never invented) when the caller does
not supply them.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from metis.core import Artifact
from metis.engine.extractor.langfuse import fetch_by_session_id


def _make_trace(
    trace_id: str, session_id: str, *, timestamp: str = "2026-01-01T00:00:00Z"
) -> SimpleNamespace:
    """Build a minimal trace object the extractor can convert."""
    return SimpleNamespace(
        id=trace_id,
        session_id=session_id,
        input="user question",
        output="assistant answer",
        timestamp=timestamp,
    )


def _make_langfuse(traces: list[SimpleNamespace]) -> MagicMock:
    """Build a mocked Langfuse client returning the given traces, no observations."""
    lf = MagicMock()
    lf.api.trace.list.return_value = SimpleNamespace(data=traces)
    lf.api.observations.get_many.return_value = SimpleNamespace(data=[])
    return lf


def test_missing_execution_metadata_is_marked_unavailable(tmp_path: Path) -> None:
    """When the caller supplies nothing, fields are None (never fabricated)."""
    lf = _make_langfuse([_make_trace("t1", "s1")])

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    tc = result.test_cases[0]
    assert tc.metadata is not None
    assert tc.metadata["stop_reason"] is None
    assert tc.metadata["cancellation_available"] is None

    ctc = result.session_test_cases[0]
    assert ctc.metadata is not None
    assert ctc.metadata["stop_reason"] is None
    assert ctc.metadata["cancellation_available"] is None


def test_metadata_artifacts_carry_absolute_resolved_path(tmp_path: Path) -> None:
    """Artifacts embedded in test-case metadata carry an absolute resolved path.

    ``metis-library`` depends only on ``metis-core`` (never on ``metis-engine``),
    so it has no access to ``experiment_root``. Resolving here, before artifacts
    are embedded in ``LLMTestCase.metadata``, means library's own code just reads
    an already-absolute path string.
    """
    lf = _make_langfuse([_make_trace("t1", "s1")])
    artifacts = [
        Artifact(name="deck.pptx", path="out/deck.pptx", at_turn=0, state="received"),
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


def test_metadata_artifacts_are_scoped_to_known_turns(tmp_path: Path) -> None:
    """A turn's metadata['artifacts'] must exclude artifacts from later turns.

    Regression test for issue #383: every turn used to see the full session
    artifact list, unfiltered by ``at_turn`` — a turn-0 test case could see a
    file the target hadn't produced until turn 2.
    """
    traces = [
        _make_trace("t0", "s1", timestamp="2026-01-01T00:00:00Z"),
        _make_trace("t1", "s1", timestamp="2026-01-01T00:01:00Z"),
        _make_trace("t2", "s1", timestamp="2026-01-01T00:02:00Z"),
    ]
    lf = _make_langfuse(traces)
    artifacts = [
        Artifact(name="turn0.txt", at_turn=0, path="out/turn0.txt", state="received"),
        Artifact(name="turn2.txt", at_turn=2, path="out/turn2.txt", state="received"),
        Artifact(
            name="session.txt", at_turn=None, path="out/session.txt", state="received"
        ),
    ]

    result = fetch_by_session_id(
        "s1", lf, experiment_root=tmp_path, artifacts=artifacts
    )

    names_by_turn: list[set[str]] = []
    for tc in result.test_cases:
        assert tc.metadata is not None
        names_by_turn.append({a["name"] for a in tc.metadata["artifacts"]})
    # Turn 0: the turn-0 artifact and the unattributed session artifact only.
    assert names_by_turn[0] == {"turn0.txt", "session.txt"}
    # Turn 1: still no turn-2 artifact — it hasn't happened yet.
    assert names_by_turn[1] == {"turn0.txt", "session.txt"}
    # Turn 2: the turn-2 artifact is now visible too. Superset of turn 1's set.
    assert names_by_turn[2] == {"turn0.txt", "turn2.txt", "session.txt"}
    assert names_by_turn[1] <= names_by_turn[2]
