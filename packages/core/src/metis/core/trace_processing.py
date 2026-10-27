"""The trace processor: the one place graders go to read a session, select what to judge, and
render it for the judge.

A grader judges a session in pieces: each turn, a run of turns, the whole session, or one file.
It calls the select function for its scope, which returns each piece under the label of its
result, then renders each piece with a render function and sends that to its judge. Nothing
outside this module reads an observation's ``input``, ``output`` or ``metadata``; those hold
whatever the application sent.

============================================  ===================================================
What a grader needs                           Use
============================================  ===================================================
**1. Read the session**
The turns: messages, tool calls, reply        ``turns(input.traces)``
The files the target produced                 ``find_artifacts(input, name)``
**2. Select what to judge**
Each turn on its own (trace scope)            ``select_by_turn(turns, last_only=...)``
A turn and turns before it (subsession)       ``select_by_window(turns, size, last_only=...)``
The whole session (session scope)             ``select_session(turns)``
Each file with a name (artifact scope)        ``select_by_artifact(input, name)``
**3. Render it for the judge**
Turns: user, tool calls, reply, errors        ``render_session(turns, tool_results=...)``
Turns: only what the user reads               ``render_dialogue(turns, assistant_only=...)``
A file                                        ``render_artifact(path)``
**4. Read one payload in detail**
A message's text for a role                   ``text_of(value, role)``
Every chat message in a payload               ``messages_of(value)``
A tool call's arguments or result             ``tool_arguments(call)``, ``tool_result(call)``
============================================  ===================================================

Each select function returns a ``dict`` from label to what the judge reads. The label becomes
``GraderResult.scope``:

======================  ====================  ===============================  ==================
Scope                   Select                One entry, label: value          Render
======================  ====================  ===============================  ==================
trace                   ``select_by_turn``    ``"turn:3"``: that one turn      ``render_session``
subsession              ``select_by_window``  ``"turns:2-4"``: those turns     ``render_session``
session                 ``select_session``    ``"session"``: every turn        ``render_session``
artifact                ``select_by_artifact``  ``"artifact:a.pdf:0"``: a path  ``render_artifact``
======================  ====================  ===============================  ==================

A grader that judges one turn with every turn before it as context uses
``select_by_window(turns, size=None)``. A grader that needs another view of the same turns, such
as ``render_dialogue``, calls that render function itself.

**Problems.** A function returns a ``Problem`` when METIS could not read or find something. It is
never the target's fault, so a grader records it as ``errored`` with the detail, never as a low
score. What the target itself reported as an error is a ``TargetError`` on the turn, which is
evidence to grade.

**Supported payloads.** The readers in section 4 support these shapes. Anything else is an
``unsupported`` problem. Adding a shape means one row here and one reader change.

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

A reply that is a JSON object or array, and not a chat message, is the target's answer in a
structured format, so ``Turn.reply`` holds it as JSON text. Langfuse replaces media an
application uploaded (images, files) with a reference token,
``@@@langfuseMedia:type=…|id=…|source=…@@@``. METIS does not fetch the media, so a judge given
the token would grade without the image, and any text holding one is ``unsupported``. A string
that looks like a dict but is not JSON (for example a tool output in Python syntax) is a string.

Everything here is frozen and every collection a tuple, because one ``GradingInput`` is shared
by concurrent grader runs.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

# Pydantic field types (Turn.trace, ToolCall.observation), so runtime imports.
from metis.core.traces import Observation, Trace  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Sequence

    from metis.core.artifacts import Artifact
    from metis.core.traces import GradingInput

ProblemKind = Literal["missing", "unsupported", "no_match", "artifact_unavailable"]
Field = Literal["input", "output", "metadata"]


# ---------------------------------------------------------------------------
# Types: a turn, its tool calls and errors, and a problem
# ---------------------------------------------------------------------------


class Problem(BaseModel, frozen=True):
    """Something METIS could not read or find. Never a failure of the target."""

    kind: ProblemKind
    detail: str
    trace_id: str | None = None
    observation_id: str | None = None
    field: Field | None = None


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
    """``trace.root.output`` as assistant text, or as JSON text when it is a JSON object or array
    that is not a chat message."""
    tool_calls: tuple[ToolCall, ...]
    """Every ``TOOL`` observation in the trace, at any depth, oldest first."""
    target_errors: tuple[TargetError, ...]

    @property
    def trace_id(self) -> str:
        return self.trace.id


class ToolCallPart(BaseModel, frozen=True):
    """A tool call the model asked for inside a message."""

    name: str
    arguments: dict[str, Any] | str | None = None


class Message(BaseModel, frozen=True):
    """One chat message, whatever format it arrived in."""

    role: str
    text: str
    tool_calls: tuple[ToolCallPart, ...] = ()


# ---------------------------------------------------------------------------
# 1. Read the session
# ---------------------------------------------------------------------------


def turns(traces: Sequence[Trace]) -> tuple[Turn, ...]:
    """Every turn in the session, oldest first, including turns where the target failed.

    One trace is one turn. Each ``Turn`` holds the user's message, every tool call, the reply,
    and each error the target reported.
    """
    return tuple(_turn(index, trace) for index, trace in enumerate(traces))


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


# ---------------------------------------------------------------------------
# 2. Select what a grader judges
# ---------------------------------------------------------------------------


_NO_TURNS = Problem(kind="no_match", detail="The session has no turns.")


def select_by_turn(
    turns: tuple[Turn, ...], *, last_only: bool = False
) -> dict[str, tuple[Turn, ...] | Problem] | Problem:
    """Trace scope: each turn on its own, or only the last turn, labelled ``turn:N``.

    The value is a one-turn tuple, so it renders like any other run of turns. A turn whose
    reply cannot be read is a ``Problem`` in place of the turn, unless the target reported an
    error on it: a missing reply is then the target failing, so the turn is judged. A session
    with no turns is a ``Problem``.
    """
    if not turns:
        return _NO_TURNS
    selected: dict[str, tuple[Turn, ...] | Problem] = {}
    for turn in turns[-1:] if last_only else turns:
        label = f"turn:{turn.index + 1}"
        if isinstance(turn.reply, Problem) and not turn.target_errors:
            selected[label] = turn.reply.model_copy(
                update={
                    "detail": f"The reply in turn {turn.index + 1} cannot be read: "
                    f"{turn.reply.detail}."
                }
            )
        else:
            selected[label] = (turn,)
    return selected


def select_by_window(
    turns: tuple[Turn, ...], size: int | None = None, *, last_only: bool = False
) -> dict[str, tuple[Turn, ...]] | Problem:
    """Subsession scope: for each turn, or only the last turn, that turn and up to
    ``size - 1`` turns just before it, labelled ``turns:A-B``.

    ``size=None`` holds every turn before it, so the judge has the whole conversation so far.
    A window near the start of the session is shorter, because fewer turns come before it.
    A session with no turns is a ``Problem``.
    """
    if not turns:
        return _NO_TURNS
    selected: dict[str, tuple[Turn, ...]] = {}
    for end in turns[-1:] if last_only else turns:
        start = 0 if size is None else max(end.index + 1 - size, 0)
        selected[f"turns:{start + 1}-{end.index + 1}"] = turns[start : end.index + 1]
    return selected


def select_session(turns: tuple[Turn, ...]) -> dict[str, tuple[Turn, ...]] | Problem:
    """Session scope: every turn, labelled ``session``. A session with no turns is a
    ``Problem``."""
    if not turns:
        return _NO_TURNS
    return {"session": turns}


def select_by_artifact(
    input: GradingInput, name: str | None
) -> dict[str, Path] | Problem:
    """Artifact scope: each received target file called ``name``, labelled
    ``artifact:<name>:<n>``.

    A revised file keeps its name, so each revision is its own entry. No file with the name,
    or no name, is a ``Problem``.
    """
    if name is None:
        return Problem(kind="no_match", detail="No artifact name is set.")
    found = find_artifacts(input, name)
    if isinstance(found, Problem):
        return found.model_copy(
            update={"detail": f"No received target file named {name!r}."}
        )
    return {
        f"artifact:{name}:{index}": Path(artifact.path)
        for index, artifact in enumerate(found)
        if artifact.path is not None
    }


# ---------------------------------------------------------------------------
# 3. Render what was selected for the judge
# ---------------------------------------------------------------------------


def render_session(
    turns: tuple[Turn, ...] | Problem,
    *,
    tool_results: bool = False,
    max_chars: int | None = None,
) -> str | Problem:
    """Turns as one plain-text transcript: one turn, a window, or the whole session.

    Each turn is ``## Turn N``, then ``User:``, one ``Tool name (agent): arguments`` line per
    tool call, ``Assistant:``, and a ``[target error: …]`` line per target error. Anything
    unreadable is shown as ``[unreadable: kind: detail]`` rather than dropped, so the judge sees
    the gap.

    With ``tool_results``, each tool call line is followed by ``Tool result [status]: result``.
    The status is ``error`` when Langfuse recorded the call's level as ``ERROR`` or ``WARNING``,
    with the status message when there is one, else ``ok``. With ``max_chars``, an argument or
    result longer than that ends in ``…[cut off]``. ``None`` cuts nothing, and the judge's
    ``max_input_tokens`` limits the size. A ``Problem`` passes through unchanged, so a grader's
    loop needs no branch for a turn that cannot be judged.
    """
    if isinstance(turns, Problem):
        return turns
    blocks: list[str] = []
    for turn in turns:
        lines = [f"## Turn {turn.index + 1}", f"User: {_shown(turn.user)}"]
        for call in turn.tool_calls:
            agent = f" ({call.agent})" if call.agent else ""
            arguments = _shown_payload(tool_arguments(call.observation), max_chars)
            lines.append(f"Tool {call.name}{agent}: {arguments}")
            if tool_results:
                result = _shown_payload(tool_result(call.observation), max_chars)
                lines.append(f"Tool result [{_call_status(call)}]: {result}")
        lines.append(f"Assistant: {_shown(turn.reply)}")
        lines.extend(f"[target error: {error.message}]" for error in turn.target_errors)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_dialogue(
    turns: tuple[Turn, ...] | Problem, *, assistant_only: bool = False
) -> str | Problem:
    """The ``User:`` and ``Assistant:`` lines of ``render_session``, without tool calls.

    For a judge of what the user reads. With ``assistant_only``, only the ``Assistant:`` lines,
    for a judge of the replies' own wording. A ``Problem`` passes through unchanged.
    """
    if isinstance(turns, Problem):
        return turns
    blocks: list[str] = []
    for turn in turns:
        lines = [f"## Turn {turn.index + 1}"]
        if not assistant_only:
            lines.append(f"User: {_shown(turn.user)}")
        lines.append(f"Assistant: {_shown(turn.reply)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


MAX_FILE_BYTES = 50 * 1024 * 1024
"""The largest file the judge accepts."""


class FileInput(BaseModel, frozen=True):
    """A file as the judge receives it: its name and its bytes as a base64 data URL."""

    filename: str
    data_url: str


def render_artifact(path: Path | Problem) -> FileInput | Problem:
    """A file as the judge receives it. The judge reads the file itself, so METIS does not
    extract its text. A file that cannot be read, or that is larger than ``MAX_FILE_BYTES``,
    is a ``Problem``. A ``Problem`` passes through unchanged.
    """
    if isinstance(path, Problem):
        return path
    try:
        data = path.read_bytes()
    except OSError as exc:
        return Problem(
            kind="missing", detail=f"The file {path.name} cannot be read: {exc}"
        )
    if len(data) > MAX_FILE_BYTES:
        return Problem(
            kind="unsupported",
            detail=f"The file {path.name} is larger than {MAX_FILE_BYTES:,} bytes.",
        )
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(data).decode("ascii")
    return FileInput(filename=path.name, data_url=f"data:{mime};base64,{encoded}")


# ---------------------------------------------------------------------------
# 4. Read one payload in detail
# ---------------------------------------------------------------------------


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
# Internal
# ---------------------------------------------------------------------------


_ERROR_LEVELS = ("ERROR", "WARNING")


_MEDIA_REFERENCE = re.compile(
    r"@@@langfuseMedia:type=([^|@]*)\|id=([^|@]*)\|source=[^@]*@@@"
)


def _turn(index: int, trace: Trace) -> Turn:
    by_id = {observation.id: observation for observation in trace.observations}
    root = trace.root
    return Turn(
        index=index,
        trace=trace,
        user=_locate_value(text_of(root.input, role="user"), root, "input"),
        reply=_locate_value(_reply_of(root.output), root, "output"),
        tool_calls=tuple(
            ToolCall(turn_index=index, observation=o, agent=_agent_of(o, by_id))
            for o in trace.observations
            if o.type == "TOOL"
        ),
        target_errors=_target_errors(trace),
    )


def _reply_of(value: object) -> str | Problem:
    # A reply in a structured format, such as a JSON object, is the target's answer, so it is
    # shown as JSON text. Only a chat message payload is read for its assistant text.
    if isinstance(value, (dict, list)) and isinstance(messages_of(value), Problem):
        text = json.dumps(value, ensure_ascii=False)
        return _media_problem(text) or text
    return text_of(value, role="assistant")


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


def _locate(problem: Problem, observation: Observation, field: Field) -> Problem:
    return problem.model_copy(
        update={
            "trace_id": observation.trace_id,
            "observation_id": observation.id,
            "field": field,
        }
    )


def _locate_value(
    value: str | Problem, observation: Observation, field: Field
) -> str | Problem:
    return _locate(value, observation, field) if isinstance(value, Problem) else value


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


def _shown(value: str | Problem) -> str:
    return (
        f"[unreadable: {value.kind}: {value.detail}]"
        if isinstance(value, Problem)
        else value
    )


def _shown_payload(value: object, max_chars: int | None) -> str:
    if isinstance(value, Problem):
        return _shown(value)
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    )
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[:max_chars] + " …[cut off]"


def _call_status(call: ToolCall) -> str:
    if call.observation.level not in _ERROR_LEVELS:
        return "ok"
    message = call.observation.status_message
    return f"error: {message}" if message else "error"
