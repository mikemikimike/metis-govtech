"""Tests for observable execution metadata written by the Langfuse extractor.

The extractor writes ``stop_reason`` and ``cancellation_available`` into the
grader-visible metadata of every test case. These tests use a mocked Langfuse
client (no network) and assert that the fields reach both the per-trace
``LLMTestCase`` metadata and the session ``ConversationalTestCase`` metadata,
and that they are marked unavailable (never invented) when the caller does
not supply them.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from metis.core import Artifact
from metis.engine.extractor.langfuse import fetch_by_session_id


def _make_observation(
    trace_id: str,
    session_id: str,
    *,
    obs_id: str | None = None,
    parent_observation_id: str | None = None,
    name: str = "orca-chat",
    obs_type: str = "AGENT",
    input: object = "user question",
    output: object = "assistant answer",
    start_time: str | None = "2026-01-01T00:00:00Z",
) -> dict[str, object]:
    """Build a raw camelCase v2-observation dict, as the Langfuse API returns it.

    Defaults produce a root observation (no parent) for a one-turn trace.
    """
    return {
        "id": obs_id or f"root-{trace_id}",
        "traceId": trace_id,
        "sessionId": session_id,
        "name": name,
        "type": obs_type,
        "input": input,
        "output": output,
        "metadata": None,
        "startTime": start_time,
        "endTime": None,
        "parentObservationId": parent_observation_id,
    }


def _make_v2_langfuse(raw_observations: list[dict[str, object]]) -> MagicMock:
    """Build a mocked Langfuse client whose v2 endpoint returns the given observations in one page."""
    lf = MagicMock()
    lf.api.observations_v_2.get_many.return_value = SimpleNamespace(
        data=raw_observations, meta=SimpleNamespace(cursor=None)
    )
    return lf


def _filter_column(call_kwargs: dict[str, object]) -> str:
    """Return the ``column`` of the structured filter a get_many call used."""
    raw_filter = call_kwargs["filter"]
    assert isinstance(raw_filter, str)
    (condition,) = json.loads(raw_filter)
    return condition["column"]


def _make_v2_langfuse_with_filtered_responses(
    *,
    session_filtered: list[dict[str, object]],
    trace_filtered: list[dict[str, object]],
) -> MagicMock:
    """Build a mocked Langfuse client whose response depends on the filter column.

    Regression harness for issue #435: a real nprd ``sessionId`` filter
    silently drops Orca's agent-run spans (and any observation with no
    session id at all), while a ``traceId`` filter always returns the
    complete tree. Every other mock in this file returns identical data
    regardless of filter, so it cannot tell a correct two-step fetch apart
    from one that (incorrectly) treats the session-filtered list as a
    trace's full observation set. This helper can.
    """
    lf = MagicMock()

    def _get_many(**kwargs: object) -> SimpleNamespace:
        column = _filter_column(kwargs)
        if column == "sessionId":
            return SimpleNamespace(
                data=session_filtered, meta=SimpleNamespace(cursor=None)
            )
        if column == "traceId":
            return SimpleNamespace(
                data=trace_filtered, meta=SimpleNamespace(cursor=None)
            )
        raise AssertionError(f"unexpected filter column: {column}")

    lf.api.observations_v_2.get_many.side_effect = _get_many
    return lf


def test_missing_execution_metadata_is_marked_unavailable(tmp_path: Path) -> None:
    """When the caller supplies nothing, fields are None (never fabricated)."""
    lf = _make_v2_langfuse([_make_observation("t1", "s1")])

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
    lf = _make_v2_langfuse([_make_observation("t1", "s1")])
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
    observations = [
        _make_observation("t0", "s1", start_time="2026-01-01T00:00:00Z"),
        _make_observation("t1", "s1", start_time="2026-01-01T00:01:00Z"),
        _make_observation("t2", "s1", start_time="2026-01-01T00:02:00Z"),
    ]
    lf = _make_v2_langfuse(observations)
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


def test_builds_test_case_from_root_observation_input_output(tmp_path: Path) -> None:
    """A trace with a root (parentless) observation plus children builds one test case
    from the root's input/output, not from any child's.
    """
    lf = _make_v2_langfuse(
        [
            {
                "id": "root-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "orca-chat",
                "type": "AGENT",
                "input": "user question",
                "output": "assistant answer",
                "metadata": None,
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": None,
                "parentObservationId": None,
            },
            {
                "id": "child-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "tool-call",
                "type": "TOOL",
                "input": "tool in",
                "output": "tool out",
                "metadata": None,
                "startTime": "2026-01-01T00:00:01Z",
                "endTime": None,
                "parentObservationId": "root-1",
            },
        ]
    )

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    assert len(result.test_cases) == 1
    tc = result.test_cases[0]
    assert tc.input == "user question"
    assert tc.actual_output == "assistant answer"


def test_multi_trace_session_orders_by_root_start_time(tmp_path: Path) -> None:
    """Two traces' roots, inserted out of order, come back sorted by start_time."""
    lf = _make_v2_langfuse(
        [
            {
                "id": "root-2",
                "traceId": "t2",
                "sessionId": "s1",
                "name": "orca-chat",
                "type": "AGENT",
                "input": "second question",
                "output": "second answer",
                "metadata": None,
                "startTime": "2026-01-01T00:01:00Z",
                "endTime": None,
                "parentObservationId": None,
            },
            {
                "id": "root-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "orca-chat",
                "type": "AGENT",
                "input": "first question",
                "output": "first answer",
                "metadata": None,
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": None,
                "parentObservationId": None,
            },
        ]
    )

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    assert [tc.input for tc in result.test_cases] == [
        "first question",
        "second question",
    ]


def test_root_with_no_output_is_skipped_not_emptied(tmp_path: Path) -> None:
    """A root observation with no output (turn never completed) is skipped, matching the
    pre-migration ``if not trace.output: skipped += 1; continue`` rule — it must not produce
    a test case with an empty-string ``actual_output``.
    """
    lf = _make_v2_langfuse(
        [
            {
                "id": "root-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "orca-chat",
                "type": "AGENT",
                "input": "question",
                "output": None,
                "metadata": None,
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": None,
                "parentObservationId": None,
            },
        ]
    )

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    assert result.test_cases == []
    assert result.skipped == 1


def test_nprd_string_shaped_io_matches_already_parsed_dict_shape(
    tmp_path: Path,
) -> None:
    """nprd returns input/output as raw strings (parse_io_as_json is rejected). A
    delegate_task_to_member TOOL input and a GENERATION output, both stringified JSON
    exactly as nprd returns them, must extract the same delegation target/task and
    assistant message as if the server had sent already-parsed dicts.
    """
    lf = _make_v2_langfuse(
        [
            {
                "id": "root-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "orca-chat",
                "type": "AGENT",
                "input": "user question",
                "output": "assistant answer",
                "metadata": None,
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": None,
                "parentObservationId": None,
            },
            {
                "id": "delegate-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "delegate_task_to_member",
                "type": "TOOL",
                "input": '{"member_id": "data-analyst", "task": "summarize sales"}',
                "output": "done",
                "metadata": None,
                "startTime": "2026-01-01T00:00:01Z",
                "endTime": None,
                "parentObservationId": "root-1",
            },
            {
                "id": "gen-1",
                "traceId": "t1",
                "sessionId": "s1",
                "name": "Claude.ainvoke",
                "type": "GENERATION",
                "input": "irrelevant",
                "output": '{"messages": [{"role": "assistant", "content": "final answer"}]}',
                "metadata": None,
                "startTime": "2026-01-01T00:00:02Z",
                "endTime": None,
                "parentObservationId": "root-1",
            },
        ]
    )

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    assert len(result.test_cases) == 1
    meta = result.test_cases[0].metadata
    assert meta is not None
    assert meta["delegation"] == {"target": "data-analyst", "task": "summarize sales"}
    assert meta["assistant_messages"] == [
        {"role": "assistant", "content": "final answer"}
    ]


def test_two_step_fetch_survives_issue_435_session_id_mismatch(tmp_path: Path) -> None:
    """Regression test for issue #435.

    nprd found that Orca's agent-run spans (``*.arun``) carry a different
    session id than their turn's root — Agno's own instrumentation writes
    its session id to the same ``session.id`` attribute Langfuse's
    ``propagate_attributes`` uses, so the agent-run span's write wins — and
    that a trailing GENERATION in a delegated run can carry no session id
    at all. A ``sessionId``-filtered fetch silently drops both, with no
    error. The fix (the two-step fetch: discover trace ids by ``sessionId``,
    then re-fetch each trace in full by ``traceId``) must still see them.

    This mock answers differently depending on which column the request's
    `filter` targets, so it is the one test in this file that would fail if
    the extractor used the session-filtered list as a trace's observation
    set instead of re-fetching by ``traceId``.
    """
    root = {
        "id": "root-1",
        "traceId": "t1",
        "sessionId": "s1",
        "name": "orca-chat",
        "type": "AGENT",
        "input": "user question",
        "output": "assistant answer",
        "metadata": None,
        "startTime": "2026-01-01T00:00:00Z",
        "endTime": None,
        "parentObservationId": None,
    }
    # Failure mode 1 (#435 section 1): an agent-run span carrying Agno's own
    # session id, not the Langfuse one — dropped by a sessionId filter.
    agent_span = {
        "id": "agent-1",
        "traceId": "t1",
        "sessionId": "agno-session-uuid-mismatch",
        "name": "Data_Analysis_Agent.arun",
        "type": "AGENT",
        "input": "do the analysis",
        "output": "subagent synthesis output",
        "metadata": None,
        "startTime": "2026-01-01T00:00:01Z",
        "endTime": None,
        "parentObservationId": "root-1",
    }
    # Failure mode 2 (#435 section 1): an observation with no session id at
    # all — also dropped by a sessionId filter.
    generation_without_session_id = {
        "id": "gen-1",
        "traceId": "t1",
        "sessionId": None,
        "name": "Claude.ainvoke_stream",
        "type": "GENERATION",
        "input": "irrelevant",
        "output": '{"messages": [{"role": "assistant", "content": "deep generation text"}]}',
        "metadata": None,
        "startTime": "2026-01-01T00:00:02Z",
        "endTime": None,
        "parentObservationId": "agent-1",
    }

    lf = _make_v2_langfuse_with_filtered_responses(
        # A real sessionId filter would return only the root here — both
        # the mismatched-id AGENT span and the no-session-id generation are
        # silently dropped (this is the exact #435 failure, reproduced).
        session_filtered=[root],
        # A traceId filter always returns the complete, unbroken tree.
        trace_filtered=[root, agent_span, generation_without_session_id],
    )

    result = fetch_by_session_id("s1", lf, experiment_root=tmp_path)

    assert len(result.test_cases) == 1
    tc = result.test_cases[0]
    meta = tc.metadata
    assert meta is not None

    # The full 3-observation tree reached the test case, not just the root —
    # proof the extractor fetched by traceId rather than trusting the
    # session-filtered list from trace discovery.
    assert len(meta["observations"]) == 3

    # Failure mode 1: the dropped AGENT span's output still reaches context
    # via _extract_subagent_output's known-subagent fallback.
    assert tc.context == ["subagent synthesis output"]

    # Failure mode 2: the no-session-id generation's content still reaches
    # assistant_messages via _extract_assistant_messages.
    assert meta["assistant_messages"] == [
        {"role": "assistant", "content": "deep generation text"}
    ]
