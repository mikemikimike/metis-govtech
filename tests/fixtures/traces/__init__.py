"""A real Orca session, scrubbed, for trace-processor and demo-grader tests (#431).

``orca_session.json`` holds the raw Langfuse Observations API v2 rows of
``sess-261019165653-ed52``, recorded after nprd's v4 upgrade. ``load_orca_session`` builds it
into a ``GradingInput`` the way ``metis.engine.extractor.fetch_session`` does. Refresh it with
``uv run python -m tests.fixtures.traces.refresh``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from metis.core.traces import GradingInput, Observation, Trace

SESSION_ID = "sess-261019165653-ed52"
FIXTURE = Path(__file__).with_name("orca_session.json")


def _root_start(trace: Trace) -> tuple[bool, float]:
    start = trace.root.start_time
    return (start is None, start.timestamp() if start else 0.0)


def load_orca_session() -> GradingInput:
    """The case-study session as graders receive it. It has no artifacts: none were recorded."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_trace: dict[str, list[Observation]] = defaultdict(list)
    for row in data["rows"]:
        observation = Observation.model_validate(row)
        by_trace[observation.trace_id].append(observation)
    traces = [
        Trace.from_observations(trace_id, data["session_id"], observations)
        for trace_id, observations in by_trace.items()
    ]
    return GradingInput(traces=tuple(sorted(traces, key=_root_start)))
