"""Tests for the v2 observation model and root-observation selection.

Covers the camelCase-to-snake_case mapping the v2 endpoint requires, the
input/output JSON-string normalization METIS now does itself (nprd rejects
``parse_io_as_json=true`` as of 2026-10-14, so the server always returns raw
strings), and the two-tier root-selection logic: prefer the server's
``isRootObservation`` flag when present, fall back to a null
``parent_observation_id`` when the flag is absent entirely, and under either
method fall back to earliest ``start_time`` on zero or multiple matches
(issue #432 edge cases).
"""

from datetime import UTC, datetime

from metis.engine.extractor.observation_v2 import (
    ObservationV2,
    group_by_trace,
    select_root,
)


def test_parses_camel_case_fields_to_snake_case() -> None:
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "orca-chat",
        "type": "AGENT",
        "input": "hello",
        "output": "hi there",
        "metadata": {"k": "v"},
        "startTime": "2026-01-01T00:00:00.000Z",
        "endTime": "2026-01-01T00:00:01.000Z",
        "parentObservationId": None,
        "isRootObservation": True,
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.id == "obs-1"
    assert obs.trace_id == "trace-1"
    assert obs.session_id == "sess-1"
    assert obs.input == "hello"
    assert obs.output == "hi there"
    assert obs.start_time == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert obs.parent_observation_id is None
    assert obs.is_root_observation is True


def test_is_root_observation_defaults_to_none_when_absent() -> None:
    """A server that omits isRootObservation (older Langfuse) must not fail validation."""
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "root-span",
        "type": "SPAN",
        "input": "in",
        "output": "out",
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": None,
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.is_root_observation is None


def test_plain_text_io_is_kept_as_a_string() -> None:
    """nprd always returns input/output as raw strings now. A plain-text answer like "42"
    or "true" must stay a string, not become an int/bool/other type.
    """
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "root-span",
        "type": "SPAN",
        "input": "42",
        "output": "true",
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": None,
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.input == "42"
    assert obs.output == "true"


def test_json_object_string_output_is_parsed_into_a_dict() -> None:
    """The nprd shape for a GENERATION's output: a stringified {"messages": [...]} blob.
    Must come back as a dict so _extract_assistant_messages's isinstance check fires.
    """
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "Claude.ainvoke",
        "type": "GENERATION",
        "input": "irrelevant",
        "output": '{"messages": [{"role": "assistant", "content": "hi"}]}',
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": "root-1",
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.output == {"messages": [{"role": "assistant", "content": "hi"}]}


def test_json_array_string_is_parsed_into_a_list() -> None:
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "tool-call",
        "type": "TOOL",
        "input": "[1, 2, 3]",
        "output": "out",
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": "root-1",
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.input == [1, 2, 3]


def test_malformed_json_looking_string_is_kept_as_a_string() -> None:
    """A string that starts with "{" but isn't valid JSON must not raise or get dropped."""
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "root-span",
        "type": "SPAN",
        "input": "{not valid json",
        "output": "out",
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": None,
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.input == "{not valid json"


def test_dict_and_list_io_pass_through_unchanged() -> None:
    """If a future server build does send already-parsed dicts/lists, don't double-encode them."""
    raw = {
        "id": "obs-1",
        "traceId": "trace-1",
        "sessionId": "sess-1",
        "name": "root-span",
        "type": "SPAN",
        "input": {"a": 1},
        "output": [1, 2],
        "metadata": None,
        "startTime": None,
        "endTime": None,
        "parentObservationId": None,
    }

    obs = ObservationV2.model_validate(raw)

    assert obs.input == {"a": 1}
    assert obs.output == [1, 2]


def _obs(
    obs_id: str,
    trace_id: str,
    *,
    parent: str | None,
    is_root: bool | None = None,
    start_time: datetime | None = None,
) -> ObservationV2:
    return ObservationV2(
        id=obs_id,
        trace_id=trace_id,
        session_id="sess-1",
        name=obs_id,
        type="SPAN",
        input=None,
        output=None,
        metadata=None,
        start_time=start_time,
        end_time=None,
        parent_observation_id=parent,
        is_root_observation=is_root,
    )


def test_group_by_trace_preserves_order() -> None:
    observations = [
        _obs("o1", "t1", parent=None),
        _obs("o2", "t2", parent=None),
        _obs("o3", "t1", parent="o1"),
    ]

    grouped = group_by_trace(observations)

    assert list(grouped.keys()) == ["t1", "t2"]
    assert [o.id for o in grouped["t1"]] == ["o1", "o3"]
    assert [o.id for o in grouped["t2"]] == ["o2"]


def test_select_root_prefers_is_root_observation_flag() -> None:
    """When the flag is present, it wins even if parent_observation_id disagrees."""
    observations = [
        _obs("o1", "t1", parent=None, is_root=False),
        _obs("o2", "t1", parent="o1", is_root=True),
    ]

    root = select_root("t1", observations)

    assert root.id == "o2"


def test_select_root_falls_back_to_null_parent_when_flag_absent_on_every_row() -> None:
    """No observation in the group has is_root_observation set — the server omitted the
    flag entirely, so root detection falls back to parent_observation_id is None.
    """
    observations = [
        _obs("o1", "t1", parent=None, is_root=None),
        _obs("o2", "t1", parent="o1", is_root=None),
    ]

    root = select_root("t1", observations)

    assert root.id == "o1"


def test_select_root_finds_single_parentless_observation() -> None:
    observations = [
        _obs("o1", "t1", parent=None),
        _obs("o2", "t1", parent="o1"),
    ]

    root = select_root("t1", observations)

    assert root.id == "o1"


def test_select_root_falls_back_to_earliest_start_time_on_zero_roots() -> None:
    """No observation has parent_observation_id is None, and the flag is absent — pick
    earliest start_time, don't crash.
    """
    observations = [
        _obs(
            "o1",
            "t1",
            parent="missing-parent",
            start_time=datetime(2026, 1, 1, 0, 0, 5),
        ),
        _obs(
            "o2",
            "t1",
            parent="missing-parent",
            start_time=datetime(2026, 1, 1, 0, 0, 1),
        ),
    ]

    root = select_root("t1", observations)

    assert root.id == "o2"


def test_select_root_falls_back_to_earliest_start_time_on_multiple_roots() -> None:
    """Two observations both have is_root_observation=True — deterministic tiebreak."""
    observations = [
        _obs(
            "o1",
            "t1",
            parent=None,
            is_root=True,
            start_time=datetime(2026, 1, 1, 0, 0, 5),
        ),
        _obs(
            "o2",
            "t1",
            parent=None,
            is_root=True,
            start_time=datetime(2026, 1, 1, 0, 0, 1),
        ),
    ]

    root = select_root("t1", observations)

    assert root.id == "o2"


def test_select_root_treats_missing_start_time_as_earliest() -> None:
    """A None start_time sorts as datetime.min, matching _extract_assistant_messages's convention."""
    observations = [
        _obs(
            "o1",
            "t1",
            parent=None,
            is_root=True,
            start_time=datetime(2026, 1, 1, 0, 0, 5),
        ),
        _obs("o2", "t1", parent=None, is_root=True, start_time=None),
    ]

    root = select_root("t1", observations)

    assert root.id == "o2"
