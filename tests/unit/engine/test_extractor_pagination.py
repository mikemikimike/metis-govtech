"""Tests for paginated fetching from Langfuse's v2 observations endpoint.

A session's observations can span more than one page once pagination is
cursor-driven rather than trace-count-driven (issue #432). These tests mock
`observations_v_2.get_many` to return two pages and assert every observation
across both pages is collected, and that the request parameters match the
contract in issue #432 (fields and the sessionId filter — NOT
parse_io_as_json, which nprd now rejects with an HTTP 400 as of 2026-10-14;
the request must omit it entirely).

`_fetch_trace_observations` shares its pagination loop with
`_fetch_session_observations` (both call `_page_through_observations`), but
is covered separately here because it must build a `traceId` filter, not a
`sessionId` one — that distinction is exactly what issue #435's two-step
fetch depends on (see the module note in `langfuse.py`).
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from metis.engine.extractor.langfuse import (
    _fetch_session_observations,
    _fetch_trace_observations,
)


def _page(data: list[dict[str, object]], cursor: str | None) -> SimpleNamespace:
    return SimpleNamespace(data=data, meta=SimpleNamespace(cursor=cursor))


def _make_observation(obs_id: str, trace_id: str) -> dict[str, object]:
    return {
        "id": obs_id,
        "traceId": trace_id,
        "sessionId": "sess-1",
        "name": "root-span",
        "type": "SPAN",
        "input": "in",
        "output": "out",
        "metadata": None,
        "startTime": "2026-01-01T00:00:00.000Z",
        "endTime": None,
        "parentObservationId": None,
    }


def test_follows_cursor_across_pages() -> None:
    page1 = _page([_make_observation("o1", "t1")], cursor="cursor-abc")
    page2 = _page([_make_observation("o2", "t2")], cursor=None)
    lf = MagicMock()
    lf.api.observations_v_2.get_many.side_effect = [page1, page2]

    observations = _fetch_session_observations(lf, "sess-1")

    assert [o.id for o in observations] == ["o1", "o2"]
    assert lf.api.observations_v_2.get_many.call_count == 2


def test_stops_when_cursor_is_absent() -> None:
    page1 = _page([_make_observation("o1", "t1")], cursor=None)
    lf = MagicMock()
    lf.api.observations_v_2.get_many.return_value = page1

    observations = _fetch_session_observations(lf, "sess-1")

    assert [o.id for o in observations] == ["o1"]
    assert lf.api.observations_v_2.get_many.call_count == 1


def test_request_uses_session_filter_and_required_fields() -> None:
    lf = MagicMock()
    lf.api.observations_v_2.get_many.return_value = _page([], cursor=None)

    _fetch_session_observations(lf, "sess-1")

    _, kwargs = lf.api.observations_v_2.get_many.call_args
    assert kwargs["fields"] == "core,basic,io,metadata"
    parsed_filter = json.loads(kwargs["filter"])
    assert parsed_filter == [
        {"type": "string", "column": "sessionId", "operator": "=", "value": "sess-1"}
    ]
    assert kwargs["limit"] == 1000


def test_request_omits_parse_io_as_json() -> None:
    """nprd rejects parse_io_as_json=true with an HTTP 400 as of 2026-10-14 ("no longer
    supported on the v2 observations endpoint"). The kwarg must not be sent at all —
    not even as False — so a stricter future server that rejects the key outright
    still works.
    """
    lf = MagicMock()
    lf.api.observations_v_2.get_many.return_value = _page([], cursor=None)

    _fetch_session_observations(lf, "sess-1")

    _, kwargs = lf.api.observations_v_2.get_many.call_args
    assert "parse_io_as_json" not in kwargs


def test_trace_fetch_follows_cursor_across_pages() -> None:
    """_fetch_trace_observations shares its pagination loop with the
    session-scoped fetch, so cursor-following must work the same way here.
    """
    page1 = _page([_make_observation("o1", "t1")], cursor="cursor-abc")
    page2 = _page([_make_observation("o2", "t1")], cursor=None)
    lf = MagicMock()
    lf.api.observations_v_2.get_many.side_effect = [page1, page2]

    observations = _fetch_trace_observations(lf, "t1")

    assert [o.id for o in observations] == ["o1", "o2"]
    assert lf.api.observations_v_2.get_many.call_count == 2


def test_trace_fetch_uses_trace_id_filter_not_session_id() -> None:
    """This is the distinction issue #435's two-step fetch depends on: a
    traceId filter, never a sessionId one, so agent-run spans and other
    observations missing their session id are never silently dropped.
    """
    lf = MagicMock()
    lf.api.observations_v_2.get_many.return_value = _page([], cursor=None)

    _fetch_trace_observations(lf, "t1")

    _, kwargs = lf.api.observations_v_2.get_many.call_args
    parsed_filter = json.loads(kwargs["filter"])
    assert parsed_filter == [
        {"type": "string", "column": "traceId", "operator": "=", "value": "t1"}
    ]
