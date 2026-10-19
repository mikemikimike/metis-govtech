"""render_transcript and find_artifacts (#431).

The transcript is the one text view every LLM judge sees, so its layout is pinned exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from metis.core import Artifact
from metis.core.trace_processing import (
    Problem,
    find_artifacts,
    render_transcript,
    turns,
)
from metis.core.traces import GradingInput, Observation, Trace


def _t(second: int) -> datetime:
    return datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)


def _session(*, reply: object = "a") -> GradingInput:
    t = "t1"
    observations = (
        Observation(
            id="root",
            trace_id=t,
            type="SPAN",
            input="q",
            output=reply,
            start_time=_t(0),
        ),
        Observation(
            id="agent",
            trace_id=t,
            type="AGENT",
            name="A",
            parent_observation_id="root",
            start_time=_t(1),
        ),
        Observation(
            id="tool",
            trace_id=t,
            type="TOOL",
            name="search",
            input={"q": "x"},
            parent_observation_id="agent",
            start_time=_t(2),
        ),
    )
    return GradingInput(
        traces=(Trace(id=t, session_id="s", observations=observations),)
    )


def test_transcript_tags_each_part_in_order() -> None:
    assert render_transcript(turns(_session())) == (
        '## Turn 1\nUser: q\nTool search (A): {"q": "x"}\nAssistant: a'
    )


def test_transcript_marks_unreadable_and_target_errors() -> None:
    text = render_transcript(turns(_session(reply=None)))
    assert "Assistant: [unreadable: missing: no value]" in text
    assert text.endswith("[target error: the target returned no reply]")


def test_turns_are_separated_by_a_blank_line() -> None:
    gi = _session()
    two = GradingInput(traces=gi.traces * 2)
    assert render_transcript(turns(two)).count("\n\n## Turn ") == 1


def _artifact(name: str, **fields: object) -> Artifact:
    defaults: dict[str, object] = {
        "source": "target",
        "state": "received",
        "path": f"/tmp/{name}",
    }
    defaults.update(fields)
    return Artifact(name=name, **defaults)  # type: ignore[arg-type]


def test_find_artifacts_returns_every_received_target_match() -> None:
    first = _artifact("deck.pptx", path="/tmp/1/deck.pptx")
    second = _artifact("deck.pptx", path="/tmp/2/deck.pptx")
    gi = GradingInput(
        traces=(),
        artifacts=(
            first,
            _artifact("deck.pptx", source="fixture"),
            _artifact("deck.pptx", state="unavailable", path=None),
            _artifact("other.docx"),
            second,
        ),
    )
    assert find_artifacts(gi, "deck.pptx") == (first, second)


def test_find_artifacts_with_no_match_is_artifact_unavailable() -> None:
    problem = find_artifacts(GradingInput(traces=()), "deck.pptx")
    assert isinstance(problem, Problem)
    assert problem.kind == "artifact_unavailable"
    assert "deck.pptx" in problem.detail
