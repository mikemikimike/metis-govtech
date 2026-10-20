"""The shared trace processor: how graders and the report read a session's traces (#431).

An observation's structure is reliable (id, trace id, parent, type, name, start time), but its
``input``, ``output`` and ``metadata`` hold whatever the application sent, so they are typed
``Any``. This module is the only code in METIS that reads those three fields. It works in
three layers:

1. **Views** (``Turn``, ``ToolCall``), built only from structural fields.
2. **Readers** (``text_of``, ``messages_of``, ``tool_arguments``, ``tool_result``), each
   answering one question about a payload and returning either the value or a ``Problem``.
3. **``Problem``**: METIS could not read or find something. It is never the target's fault, so
   a grader maps it to ``skipped`` or ``errored``, never to a low score. What the target itself
   reported as an error is a ``TargetError`` on the turn instead, which is evidence to grade.

Readers support exactly these payload shapes. Anything else is an ``unsupported`` problem.
Adding a shape means one row here and one reader change.

=====================================================  ============================================
Shape                                                  Read by
=====================================================  ============================================
plain string                                           ``text_of`` (for any role), ``tool_result``
``{"role", "content"}``, a list of these, or           ``messages_of``; ``text_of`` takes the last
``{"messages": [...]}`` of these (OpenAI-style;        message with the requested role. ``content``
``content`` a string or a list of text blocks)         blocks of type ``text`` are joined
``{"role", "parts": [...]}`` or a list of these        ``messages_of``; ``text_of`` joins the text
(OpenTelemetry GenAI ``gen_ai.*.messages``)            parts
a dict                                                 ``tool_arguments``, ``tool_result``
=====================================================  ============================================

Langfuse replaces media an application uploaded (images, files) with a reference token,
``@@@langfuseMedia:type=…|id=…|source=…@@@``. METIS does not fetch the media, so a judge given
the token would grade without the image. Any text holding one is ``unsupported`` instead.

A string that looks like a dict but is not JSON (for example a tool output in Python syntax) is
a string: ``tool_result`` returns it as ``str`` and nothing tries to parse it. The supported
shapes come from Langfuse's documented OpenTelemetry property mapping and from captured
sessions. OpenTelemetry GenAI's file and image parts are not supported.

Everything here is frozen and every collection a tuple, because one ``GradingInput`` is shared
by concurrent grader runs.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from pydantic import BaseModel

# Pydantic field types (Turn.trace, ToolCall.observation), so runtime imports.
from metis.core.traces import Observation, Trace  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Callable

    from metis.core.artifacts import Artifact
    from metis.core.traces import GradingInput

T = TypeVar("T")

ProblemKind = Literal["missing", "unsupported", "no_match", "artifact_unavailable"]
Field = Literal["input", "output", "metadata"]


_MEDIA_REFERENCE = re.compile(
    r"@@@langfuseMedia:type=([^|@]*)\|id=([^|@]*)\|source=[^@]*@@@"
)


def _media_problem(text: str) -> Problem | None:
    """An ``unsupported`` problem naming the first Langfuse media reference in ``text``."""
    match = _MEDIA_REFERENCE.search(text)
    if match is None:
        return None
    return Problem(
        kind="unsupported",
        detail=f"holds a Langfuse media reference ({match.group(1)}, id {match.group(2)}) "
        "that METIS does not fetch",
    )


class Problem(BaseModel, frozen=True):
    """Something METIS could not read or find. Never a failure of the target."""

    kind: ProblemKind
    detail: str
    trace_id: str | None = None
    observation_id: str | None = None
    field: Field | None = None


class ToolCallPart(BaseModel, frozen=True):
    """A tool call the model asked for inside a message."""

    name: str
    arguments: dict[str, Any] | str | None = None


class Message(BaseModel, frozen=True):
    """One chat message, whatever format it arrived in."""

    role: str
    text: str
    tool_calls: tuple[ToolCallPart, ...] = ()


def _describe(value: object) -> str:
    """A short name for an unexpected value, for a ``Problem``'s detail."""
    if isinstance(value, dict):
        keys = ", ".join(sorted(str(k) for k in value)[:6])
        return f"dict with keys {keys}" if keys else "empty dict"
    if isinstance(value, list):
        return f"list of {len(value)}"
    return type(value).__name__


def _content_text(content: object) -> str | None:
    """The text of an OpenAI-style ``content``: a string, or a list of text blocks.

    ``None`` when a block list holds no text block at all (only images or files, say), so the
    message is reported as unsupported rather than read as an empty reply.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(texts) if texts or not content else None
    return None


def _openai_tool_calls(raw: object) -> tuple[ToolCallPart, ...]:
    calls: list[ToolCallPart] = []
    for entry in raw if isinstance(raw, list) else []:
        function = entry.get("function") if isinstance(entry, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            arguments = function.get("arguments")
            calls.append(
                ToolCallPart(
                    name=function["name"],
                    arguments=arguments if isinstance(arguments, (dict, str)) else None,
                )
            )
    return tuple(calls)


def _message(raw: object) -> Message | None:
    """One message in either supported format, or ``None`` if it is neither."""
    if not isinstance(raw, dict) or not isinstance(raw.get("role"), str):
        return None
    role = raw["role"]
    if "parts" in raw:
        parts = raw["parts"]
        if not isinstance(parts, list):
            return None
        texts: list[str] = []
        calls: list[ToolCallPart] = []
        known = False
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_call_response":
                known = True
            if part.get("type") == "text" and isinstance(part.get("content"), str):
                known = True
                texts.append(part["content"])
            elif part.get("type") == "tool_call" and isinstance(part.get("name"), str):
                arguments = part.get("arguments")
                known = True
                calls.append(
                    ToolCallPart(
                        name=part["name"],
                        arguments=arguments
                        if isinstance(arguments, (dict, str))
                        else None,
                    )
                )
        if parts and not known:
            return None  # only unsupported parts (images, files): not an empty message
        return Message(role=role, text="\n".join(texts), tool_calls=tuple(calls))
    if "content" in raw or "tool_calls" in raw:
        text = _content_text(raw.get("content"))
        if text is None:
            return None
        return Message(
            role=role, text=text, tool_calls=_openai_tool_calls(raw.get("tool_calls"))
        )
    return None


def messages_of(value: object) -> tuple[Message, ...] | Problem:
    """The chat messages in a payload, in order."""
    if value is None:
        return Problem(kind="missing", detail="no value")
    if isinstance(value, dict) and "messages" in value:
        value = value["messages"]
    items = value if isinstance(value, list) else [value]
    messages = tuple(_message(item) for item in items)
    if not items or any(m is None for m in messages):
        return Problem(
            kind="unsupported",
            detail=f"not a list of chat messages: {_describe(value)}",
        )
    return tuple(m for m in messages if m is not None)


def text_of(value: object, role: str) -> str | Problem:
    """The text a payload holds for ``role``: a plain string, or its last ``role`` message."""
    if value is None:
        return Problem(kind="missing", detail="no value")
    if isinstance(value, str):
        return _media_problem(value) or value
    messages = messages_of(value)
    if isinstance(messages, Problem):
        return messages
    for message in reversed(messages):
        if message.role == role:
            return _media_problem(message.text) or message.text
    return Problem(kind="missing", detail=f"no {role} message")


def _locate(problem: Problem, observation: Observation, field: Field) -> Problem:
    return problem.model_copy(
        update={
            "trace_id": observation.trace_id,
            "observation_id": observation.id,
            "field": field,
        }
    )


def tool_arguments(observation: Observation) -> dict[str, Any] | Problem:
    """A tool call's arguments, which must be a dict."""
    value = observation.input
    if value is None:
        problem = Problem(kind="missing", detail="the tool call has no arguments")
    elif isinstance(value, dict):
        return value
    else:
        problem = Problem(
            kind="unsupported", detail=f"arguments are a {_describe(value)}"
        )
    return _locate(problem, observation, "input")


def tool_result(observation: Observation) -> str | dict[str, Any] | Problem:
    """A tool call's result: text, or a dict when the application recorded one."""
    value = observation.output
    if value is None:
        problem = Problem(kind="missing", detail="the tool call has no result")
    elif isinstance(value, (str, dict)):
        media = _media_problem(value if isinstance(value, str) else json.dumps(value))
        if media is None:
            return value
        problem = media
    else:
        problem = Problem(kind="unsupported", detail=f"result is a {_describe(value)}")
    return _locate(problem, observation, "output")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class TargetError(BaseModel, frozen=True):
    """Something the target itself reported as wrong: evidence about the target, to be graded."""

    message: str
    trace_id: str
    observation_id: str


class ToolCall(BaseModel, frozen=True):
    """One ``TOOL`` observation, wherever it sits in its trace."""

    turn_index: int
    observation: Observation
    agent: str | None
    """The name of the nearest enclosing ``AGENT`` observation, or ``None`` if there is none."""

    @property
    def name(self) -> str:
        return self.observation.name or ""

    @property
    def observation_id(self) -> str:
        return self.observation.id


class Turn(BaseModel, frozen=True):
    """One exchange: one trace, read the way Langfuse documents a trace's input and output."""

    index: int
    trace: Trace
    user: str | Problem
    """``trace.root.input`` as user text."""
    reply: str | Problem
    """``trace.root.output`` as assistant text."""
    tool_calls: tuple[ToolCall, ...]
    """Every ``TOOL`` observation in the trace, at any depth, oldest first."""
    target_errors: tuple[TargetError, ...]

    @property
    def trace_id(self) -> str:
        return self.trace.id


_ERROR_LEVELS = ("ERROR", "WARNING")


def _agent_of(observation: Observation, by_id: dict[str, Observation]) -> str | None:
    seen: set[str] = set()
    parent_id = observation.parent_observation_id
    while parent_id and parent_id in by_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id[parent_id]
        if parent.type == "AGENT":
            return parent.name
        parent_id = parent.parent_observation_id
    return None


def _target_errors(trace: Trace) -> tuple[TargetError, ...]:
    errors: list[TargetError] = []
    root = trace.root
    if root.output is None:
        errors.append(
            TargetError(
                message="the target returned no reply",
                trace_id=trace.id,
                observation_id=root.id,
            )
        )
    for observation in trace.observations:
        if observation.level in _ERROR_LEVELS:
            errors.append(
                TargetError(
                    message=observation.status_message
                    or f"{observation.level} on {observation.name}",
                    trace_id=trace.id,
                    observation_id=observation.id,
                )
            )
    return tuple(errors)


def _turn(index: int, trace: Trace) -> Turn:
    by_id = {observation.id: observation for observation in trace.observations}
    root = trace.root
    return Turn(
        index=index,
        trace=trace,
        user=_locate_value(text_of(root.input, role="user"), root, "input"),
        reply=_locate_value(text_of(root.output, role="assistant"), root, "output"),
        tool_calls=tuple(
            ToolCall(turn_index=index, observation=o, agent=_agent_of(o, by_id))
            for o in trace.observations
            if o.type == "TOOL"
        ),
        target_errors=_target_errors(trace),
    )


def _locate_value(
    value: str | Problem, observation: Observation, field: Field
) -> str | Problem:
    return _locate(value, observation, field) if isinstance(value, Problem) else value


def turns(input: GradingInput) -> tuple[Turn, ...]:
    """Every turn in the session, oldest first, including turns where the target failed."""
    return tuple(_turn(index, trace) for index, trace in enumerate(input.traces))


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_all(units: tuple[T, ...]) -> tuple[T, ...] | Problem:
    """Every unit, or ``no_match`` when there are none."""
    return units or Problem(kind="no_match", detail="there is nothing to select")


def select_final(units: tuple[T, ...]) -> tuple[T, ...] | Problem:
    """The last unit, or ``no_match`` when there are none."""
    return units[-1:] or Problem(kind="no_match", detail="there is no final unit")


def select_where(
    units: tuple[T, ...], predicate: Callable[[T], bool]
) -> tuple[T, ...] | Problem:
    """The units ``predicate`` accepts, in order, or ``no_match`` when it accepts none."""
    selected = tuple(unit for unit in units if predicate(unit))
    return selected or Problem(kind="no_match", detail="no unit met the condition")


# ---------------------------------------------------------------------------
# Transcript and artifacts
# ---------------------------------------------------------------------------


def _shown(value: str | Problem) -> str:
    return (
        f"[unreadable: {value.kind}: {value.detail}]"
        if isinstance(value, Problem)
        else value
    )


def _shown_arguments(call: ToolCall) -> str:
    arguments = tool_arguments(call.observation)
    if isinstance(arguments, Problem):
        return _shown(arguments)
    return json.dumps(arguments, ensure_ascii=False, default=str)


def render_transcript(turns: tuple[Turn, ...]) -> str:
    """One plain-text view of a run of turns, the same for every LLM judge.

    Each turn is ``## Turn N``, then ``User:``, one ``Tool name (agent):`` line per tool call,
    ``Assistant:``, and a ``[target error: …]`` line per target error. Anything unreadable is
    shown as ``[unreadable: kind: detail]`` rather than dropped, so the judge sees the gap.
    """
    blocks: list[str] = []
    for turn in turns:
        lines = [f"## Turn {turn.index + 1}", f"User: {_shown(turn.user)}"]
        for call in turn.tool_calls:
            agent = f" ({call.agent})" if call.agent else ""
            lines.append(f"Tool {call.name}{agent}: {_shown_arguments(call)}")
        lines.append(f"Assistant: {_shown(turn.reply)}")
        lines.extend(f"[target error: {error.message}]" for error in turn.target_errors)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def find_artifacts(input: GradingInput, name: str) -> tuple[Artifact, ...] | Problem:
    """Every received target file called ``name``, in the run's order.

    Names are not unique (a revised file keeps its name), so all matches are returned and the
    grader decides which to use. Which turn produced a file is not known here (see #427).
    """
    found = tuple(
        artifact
        for artifact in input.artifacts
        if artifact.name == name
        and artifact.source == "target"
        and artifact.state == "received"
        and artifact.path is not None
    )
    return found or Problem(
        kind="artifact_unavailable", detail=f"no received target file named {name!r}"
    )
