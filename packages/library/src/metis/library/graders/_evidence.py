"""Typed evidence selectors for graders.

Each selector is a Pydantic model used in grader_args to specify which evidence
to assess. The selector resolves against a ``GradingInput`` at grading time to
produce the subject text and supporting context.

Selector types:

- ``ResponseSelector``: selects an assistant response from the session.
  - ``last_response``: the last assistant reply in the session.
  - ``trace_id``: the root reply of a specific trace.
  - ``observation_id``: the output of a specific observation.

- ``ArtifactSelector``: selects an artifact by name and optional revision index.

- ``SessionSelector``: the entire session transcript (for whole-session assessments).

Selectors are explicit and unambiguous. When selection fails (no match, ambiguous
match, unreadable content), the result is an ``EvidenceError`` that maps to an
errored grader result — never a silent fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 — used at runtime in resolve_artifact
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from metis.core.artifacts import resolve_artifact_path
from metis.core.grading import GraderResult, GradingOutput
from metis.core.trace_processing import (
    Problem,
    ToolCall,
    Turn,
    render_transcript,
    select_all,
    select_final,
    text_of,
    tool_arguments,
    tool_result,
    turns,
)

from ._extraction import ExtractionError, extract_content

if TYPE_CHECKING:
    from metis.core.traces import GradingInput
    from metis.library.grader import JudgeArgs, LLMSettings


class EvidenceError:
    """Evidence selection or extraction failed. Maps to an errored GraderResult."""

    __slots__ = ("detail",)

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def to_result(self, *, scope: str | None = None) -> GraderResult:
        return GraderResult(status="errored", reason=self.detail, scope=scope)


@dataclass(frozen=True)
class SelectedEvidence:
    """Successfully selected evidence: the subject text and optional context."""

    subject: str
    context: str | None = None
    provenance: str | None = None


# ---------------------------------------------------------------------------
# Selector models
# ---------------------------------------------------------------------------


class LastResponseSelector(BaseModel):
    """Select the last assistant response in the session."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["last_response"] = "last_response"


class TraceResponseSelector(BaseModel):
    """Select the root response of a specific trace by ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["trace_id"] = "trace_id"
    trace_id: str = Field(min_length=1)


class ObservationResponseSelector(BaseModel):
    """Select the output of a specific observation by ID."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["observation_id"] = "observation_id"
    observation_id: str = Field(min_length=1)


class ArtifactSelector(BaseModel):
    """Select a target artifact by name, optionally specifying a revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["artifact"] = "artifact"
    name: str = Field(min_length=1)
    revision: int | None = Field(
        default=None,
        description="0-indexed revision when multiple artifacts share a name. "
        "None requires exactly one match.",
    )


class SessionSelector(BaseModel):
    """Select the entire session as the assessment subject."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["session"] = "session"


class AllArtifactsSelector(BaseModel):
    """Grade every revision of a named artifact independently."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["all_artifacts"] = "all_artifacts"
    name: str = Field(min_length=1)


class AllTurnsSelector(BaseModel):
    """Grade each turn in the session independently."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["all_turns"] = "all_turns"


class ToolCallsSelector(BaseModel):
    """Grade each tool call in the session independently.

    ``require_result`` controls whether a missing tool result makes that call
    ungradable.  When ``True`` (the default for criteria that judge outcomes),
    a call without a readable result is an evidence error.  When ``False``
    (for criteria that judge only the submitted arguments), a missing result
    does not block grading.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["tool_calls"] = "tool_calls"
    require_result: bool = Field(
        default=True,
        description="Whether a missing or unreadable tool result makes the call ungradable.",
    )


ResponseSelector = Annotated[
    LastResponseSelector | TraceResponseSelector | ObservationResponseSelector,
    Field(discriminator="kind"),
]

SingleEvidenceSelector = Annotated[
    LastResponseSelector
    | TraceResponseSelector
    | ObservationResponseSelector
    | ArtifactSelector
    | SessionSelector,
    Field(discriminator="kind"),
]
"""The five single-scope selectors.  Used by graders (such as checklist graders) whose
judgment requires exactly one evidence unit."""

EvidenceSelector = Annotated[
    LastResponseSelector
    | TraceResponseSelector
    | ObservationResponseSelector
    | ArtifactSelector
    | SessionSelector
    | AllArtifactsSelector
    | AllTurnsSelector
    | ToolCallsSelector,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_response(
    input: GradingInput,
    selector: (
        LastResponseSelector | TraceResponseSelector | ObservationResponseSelector
    ),
) -> SelectedEvidence | EvidenceError:
    """Resolve a response selector against the session's traces."""
    session = select_all(turns(input.traces))
    if isinstance(session, Problem):
        return EvidenceError(
            "The session has no turns; required evidence is unavailable."
        )

    if isinstance(selector, LastResponseSelector):
        final = select_final(session)
        if isinstance(final, Problem):
            return EvidenceError("No final turn to select.")
        reply = final[0].reply
        if isinstance(reply, Problem):
            return EvidenceError(f"The final response is unreadable: {reply.detail}")
        return SelectedEvidence(
            subject=reply,
            context=render_transcript(session[: final[0].index + 1]),
            provenance=f"last response (turn {final[0].index + 1}, trace {final[0].trace_id})",
        )

    if isinstance(selector, TraceResponseSelector):
        for turn in session:
            if turn.trace_id == selector.trace_id:
                if isinstance(turn.reply, Problem):
                    return EvidenceError(
                        f"Trace {selector.trace_id} root output is unreadable: {turn.reply.detail}"
                    )
                return SelectedEvidence(
                    subject=turn.reply,
                    context=render_transcript(session[: turn.index + 1]),
                    provenance=f"trace {selector.trace_id}",
                )
        return EvidenceError(f"No trace with id '{selector.trace_id}' in the session.")

    # ObservationResponseSelector
    for turn in session:
        for obs in turn.trace.observations:
            if obs.id == selector.observation_id:
                reply = text_of(obs.output, role="assistant")
                if isinstance(reply, Problem):
                    reply_str = obs.output
                    if isinstance(reply_str, str):
                        return SelectedEvidence(
                            subject=reply_str,
                            context=render_transcript(session[: turn.index + 1]),
                            provenance=f"observation {selector.observation_id} in trace {turn.trace_id}",
                        )
                    return EvidenceError(
                        f"Observation {selector.observation_id} output is unreadable: {reply.detail}"
                    )
                return SelectedEvidence(
                    subject=reply,
                    context=render_transcript(session[: turn.index + 1]),
                    provenance=f"observation {selector.observation_id} in trace {turn.trace_id}",
                )
    return EvidenceError(
        f"No observation with id '{selector.observation_id}' in the session."
    )


def resolve_artifact(
    input: GradingInput,
    selector: ArtifactSelector,
    experiment_root: Path | None = None,
) -> SelectedEvidence | EvidenceError:
    """Resolve an artifact selector and extract its content."""
    matches = [
        a
        for a in input.artifacts
        if a.name == selector.name
        and a.source == "target"
        and a.state == "received"
        and a.path is not None
    ]
    if not matches:
        return EvidenceError(f"No received target artifact named '{selector.name}'.")

    if selector.revision is not None:
        if selector.revision < 0 or selector.revision >= len(matches):
            return EvidenceError(
                f"Artifact '{selector.name}' has {len(matches)} revision(s); "
                f"revision {selector.revision} is out of range."
            )
        artifact = matches[selector.revision]
    elif len(matches) > 1:
        return EvidenceError(
            f"Artifact '{selector.name}' has {len(matches)} revisions. "
            f"Specify a revision index (0 to {len(matches) - 1}) to select one."
        )
    else:
        artifact = matches[0]

    assert artifact.path is not None
    if experiment_root is not None:
        file_path = resolve_artifact_path(experiment_root, artifact.path)
    else:
        file_path = Path(artifact.path)

    if file_path is None:
        return EvidenceError(f"Artifact '{selector.name}' has no resolvable path.")

    result = extract_content(file_path)
    if isinstance(result, ExtractionError):
        return EvidenceError(
            f"Cannot extract content from artifact '{selector.name}': {result.detail}"
        )

    session = select_all(turns(input.traces))
    context = render_transcript(session) if not isinstance(session, Problem) else None

    provenance = f"artifact '{selector.name}' ({result.format})"
    if selector.revision is not None:
        provenance += f" revision {selector.revision}"
    if result.warnings:
        provenance += f" [warnings: {'; '.join(result.warnings)}]"

    return SelectedEvidence(
        subject=result.text,
        context=context,
        provenance=provenance,
    )


def resolve_session(
    input: GradingInput,
    *,
    include_tool_results: bool = False,
) -> SelectedEvidence | EvidenceError:
    """Resolve a whole-session selector."""
    from ._judge_call import render_transcript_with_tool_results

    session = select_all(turns(input.traces))
    if isinstance(session, Problem):
        return EvidenceError(
            "The session has no turns; required evidence is unavailable."
        )

    if include_tool_results:
        transcript = render_transcript_with_tool_results(session)
    else:
        transcript = render_transcript(session)

    return SelectedEvidence(
        subject=transcript,
        provenance=f"full session ({len(session)} turns)",
    )


def resolve_evidence(
    input: GradingInput,
    selector: (
        LastResponseSelector
        | TraceResponseSelector
        | ObservationResponseSelector
        | ArtifactSelector
        | SessionSelector
    ),
    *,
    experiment_root: Path | None = None,
    include_tool_results: bool = False,
) -> SelectedEvidence | EvidenceError:
    """Resolve a single-scope evidence selector against the grading input.

    For multi-input selectors (``AllArtifactsSelector``, ``ToolCallsSelector``),
    use ``resolve_multi_evidence`` instead.
    """
    if isinstance(selector, SessionSelector):
        return resolve_session(input, include_tool_results=include_tool_results)
    if isinstance(selector, ArtifactSelector):
        return resolve_artifact(input, selector, experiment_root)
    return resolve_response(input, selector)


@dataclass(frozen=True)
class ScopedEvidence:
    """One resolved evidence unit with its scope label."""

    scope: str
    evidence: SelectedEvidence | EvidenceError


def resolve_multi_evidence(
    input: GradingInput,
    selector: AllArtifactsSelector | AllTurnsSelector | ToolCallsSelector,
    *,
    experiment_root: Path | None = None,
    include_tool_results: bool = False,
) -> list[ScopedEvidence]:
    """Resolve a multi-input selector into independently gradable evidence units.

    Each unit carries a ``scope`` label suitable for ``GraderResult.scope``.
    A failure on one unit does not suppress resolution of others.
    Returns an empty list only when the session has no matching units.
    """
    if isinstance(selector, AllArtifactsSelector):
        raw = resolve_all_artifacts(
            input,
            selector.name,
            experiment_root,
            include_tool_results=include_tool_results,
        )
        return [
            ScopedEvidence(
                scope=f"artifact:{selector.name}:{idx}",
                evidence=ev,
            )
            for idx, ev in raw
        ]

    if isinstance(selector, AllTurnsSelector):
        raw_turns = resolve_per_turn(input, include_tool_results=include_tool_results)
        return [
            ScopedEvidence(
                scope=f"turn:{turn.index + 1}",
                evidence=ev,
            )
            for turn, ev in raw_turns
        ]

    # ToolCallsSelector
    raw_calls = resolve_tool_calls(input, require_result=selector.require_result)
    return [
        ScopedEvidence(
            scope=f"tool_call:{call.observation_id}",
            evidence=ev,
        )
        for call, ev in raw_calls
    ]


def is_multi_selector(
    selector: EvidenceSelector,  # type: ignore[type-arg]
) -> bool:
    """Whether a selector produces multiple independent evidence units."""
    return isinstance(
        selector, (AllArtifactsSelector, AllTurnsSelector, ToolCallsSelector)
    )


# ---------------------------------------------------------------------------
# Unified grading helper
# ---------------------------------------------------------------------------


def _format_user_content(
    evidence: SelectedEvidence, context_label: str = "ADDITIONAL CONTEXT"
) -> str:
    parts = [f"ASSESSED EVIDENCE:\n{evidence.subject}"]
    if evidence.context and evidence.context != evidence.subject:
        parts.append(f"{context_label}:\n{evidence.context}")
    return "\n\n".join(parts)


async def grade_evidence(
    input: GradingInput,
    selector: EvidenceSelector,  # type: ignore[type-arg]
    llm: LLMSettings,
    args: JudgeArgs,
    system_prompt: str,
    response_model: type[BaseModel],
    schema_name: str,
    *,
    experiment_root: Path | None = None,
    include_tool_results: bool = False,
    single_scope: str = "session",
    context_label: str = "ADDITIONAL CONTEXT",
) -> GradingOutput:
    """Resolve evidence, grade it, and return scoped results.

    Handles both single-scope selectors (one judge call → one result) and
    multi-input selectors (one judge call per evidence unit → per-scope results
    with aggregate).  Evidence formatting, error handling, and scope assignment
    are done here so individual graders need only supply the system prompt.
    """
    from ._aggregation import grading_output_with_aggregate, results_from_multi_evidence
    from ._judge_call import judge_call

    if is_multi_selector(selector):
        scoped = resolve_multi_evidence(
            input,
            selector,
            experiment_root=experiment_root,  # type: ignore[arg-type]
            include_tool_results=include_tool_results,
        )
        if not scoped:
            return GradingOutput(
                results=[
                    GraderResult(
                        status="skipped",
                        reason="No matching evidence units.",
                    )
                ]
            )

        _label = context_label

        async def _grade_one(ev: SelectedEvidence, scope: str) -> GraderResult:
            result = await judge_call(
                llm,
                args,
                system_prompt,
                _format_user_content(ev, _label),
                response_model,
                schema_name,
                scope=scope,
            )
            if isinstance(result, GraderResult):
                return result
            return GraderResult(**result.model_dump(), scope=scope)

        per_scope = await results_from_multi_evidence(scoped, _grade_one)
        return grading_output_with_aggregate(per_scope)

    # Single-scope path
    evidence = resolve_evidence(
        input,
        selector,  # type: ignore[arg-type]
        experiment_root=experiment_root,
        include_tool_results=include_tool_results,
    )
    if isinstance(evidence, EvidenceError):
        return GradingOutput(results=[evidence.to_result(scope=single_scope)])

    result = await judge_call(
        llm,
        args,
        system_prompt,
        _format_user_content(evidence, context_label),
        response_model,
        schema_name,
        scope=single_scope,
    )
    if isinstance(result, GraderResult):
        return GradingOutput(results=[result])
    return GradingOutput(
        results=[GraderResult(**result.model_dump(), scope=single_scope)]
    )


# ---------------------------------------------------------------------------
# Multi-scope resolution
# ---------------------------------------------------------------------------


def _shown(value: str | Problem) -> str:
    if isinstance(value, Problem):
        return f"[unreadable: {value.kind}: {value.detail}]"
    return value


def resolve_per_turn(
    input: GradingInput,
    *,
    include_tool_results: bool = False,
) -> list[tuple[Turn, SelectedEvidence | EvidenceError]]:
    """Resolve each turn independently as an evidence unit.

    A turn with an unreadable reply and no target errors yields an ``EvidenceError``.
    Otherwise the turn is gradeable: the subject is the reply text (or an
    ``[unreadable: …]`` marker when the target failed to reply), and the context is
    the transcript through that turn.
    """
    from ._judge_call import render_transcript_with_tool_results

    session = turns(input.traces)
    if not session:
        return []

    results: list[tuple[Turn, SelectedEvidence | EvidenceError]] = []
    for turn in session:
        if isinstance(turn.reply, Problem) and not turn.target_errors:
            results.append(
                (
                    turn,
                    EvidenceError(
                        f"Turn {turn.index + 1} reply is unreadable: "
                        f"{turn.reply.detail}"
                    ),
                )
            )
            continue

        prefix = session[: turn.index + 1]
        if include_tool_results:
            context = render_transcript_with_tool_results(prefix)
        else:
            context = render_transcript(prefix)

        results.append(
            (
                turn,
                SelectedEvidence(
                    subject=_shown(turn.reply),
                    context=context,
                    provenance=f"turn {turn.index + 1} (trace {turn.trace_id})",
                ),
            )
        )
    return results


def resolve_all_artifacts(
    input: GradingInput,
    name: str,
    experiment_root: Path | None = None,
    *,
    include_tool_results: bool = False,
) -> list[tuple[int, SelectedEvidence | EvidenceError]]:
    """Resolve every revision of a named artifact independently.

    Includes *all* matching artifacts by name and source, not only those with
    ``state="received"``.  Unfetched or unavailable artifacts appear as errored
    results so the aggregate correctly reflects coverage.  A failure on one
    revision does not suppress extraction of others.
    """
    from ._judge_call import render_transcript_with_tool_results

    all_matching = [
        a for a in input.artifacts if a.name == name and a.source == "target"
    ]
    if not all_matching:
        return [(0, EvidenceError(f"No target artifact named '{name}'."))]

    session = select_all(turns(input.traces))
    if isinstance(session, Problem):
        context = None
    elif include_tool_results:
        context = render_transcript_with_tool_results(session)
    else:
        context = render_transcript(session)

    results: list[tuple[int, SelectedEvidence | EvidenceError]] = []
    for idx, artifact in enumerate(all_matching):
        if artifact.state != "received" or artifact.path is None:
            reason = (
                f"Artifact '{name}' revision {idx} is {artifact.state}"
                if artifact.state != "received"
                else f"Artifact '{name}' revision {idx} has no path"
            )
            results.append((idx, EvidenceError(reason)))
            continue

        if experiment_root is not None:
            file_path = resolve_artifact_path(experiment_root, artifact.path)
        else:
            file_path = Path(artifact.path)

        if file_path is None:
            results.append(
                (
                    idx,
                    EvidenceError(
                        f"Artifact '{name}' revision {idx} has no resolvable path."
                    ),
                )
            )
            continue

        extracted = extract_content(file_path)
        if isinstance(extracted, ExtractionError):
            results.append(
                (
                    idx,
                    EvidenceError(
                        f"Cannot extract content from artifact '{name}' revision {idx}: {extracted.detail}"
                    ),
                )
            )
            continue

        provenance = f"artifact '{name}' ({extracted.format}) revision {idx}"
        if extracted.warnings:
            provenance += f" [warnings: {'; '.join(extracted.warnings)}]"

        results.append(
            (
                idx,
                SelectedEvidence(
                    subject=extracted.text,
                    context=context,
                    provenance=provenance,
                ),
            )
        )
    return results


def resolve_tool_calls(
    input: GradingInput,
    *,
    require_result: bool = True,
) -> list[tuple[ToolCall, SelectedEvidence | EvidenceError]]:
    """Resolve each tool call in the session as an independent evidence unit.

    The subject contains the tool name, agent, and arguments.  The context is the
    transcript through the turn that contains the call.

    When ``require_result`` is ``True`` (default), a call whose result is unreadable
    is ungradable — the criterion needs the outcome.  When ``False``, the call is
    still gradeable with a placeholder result marker — the criterion only needs the
    submitted arguments.
    """
    import json as _json

    session = turns(input.traces)
    if not session:
        return []

    results: list[tuple[ToolCall, SelectedEvidence | EvidenceError]] = []
    for turn in session:
        context = render_transcript(session[: turn.index + 1])
        for call in turn.tool_calls:
            provenance = f"tool call {call.name} in turn {turn.index + 1} (trace {turn.trace_id})"

            args = tool_arguments(call.observation)
            res = tool_result(call.observation)

            if isinstance(args, Problem):
                results.append(
                    (
                        call,
                        EvidenceError(
                            f"{provenance}: arguments unreadable ({args.detail})"
                        ),
                    )
                )
                continue

            if require_result and isinstance(res, Problem):
                results.append(
                    (
                        call,
                        EvidenceError(
                            f"{provenance}: result unreadable ({res.detail})"
                        ),
                    )
                )
                continue

            args_text = _json.dumps(args, ensure_ascii=False, default=str)
            if isinstance(res, Problem):
                res_text = f"[no result: {res.detail}]"
            else:
                res_text = (
                    _json.dumps(res, ensure_ascii=False, default=str)
                    if isinstance(res, dict)
                    else res
                )

            agent = f" ({call.agent})" if call.agent else ""
            subject = (
                f"Tool: {call.name}{agent}\nArguments: {args_text}\nResult: {res_text}"
            )

            results.append(
                (
                    call,
                    SelectedEvidence(
                        subject=subject,
                        context=context,
                        provenance=provenance,
                    ),
                )
            )
    return results
