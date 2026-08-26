"""
Langfuse trace fetching and DeepEval adapter.

Merges trace-fetching (``langfuse_fetch``) and the Langfuse→DeepEval adapter
(``langfuse_adapter``) into a single module.

High-level entry point:

- :func:`fetch_by_session_id` — fetch all traces for a specific session

Lower-level extraction helpers are also re-exported for use by metrics.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    Turn,
)
from deepeval.test_case.llm_test_case import ToolCall
from langfuse import Langfuse
from langfuse.api import ObservationsView, TraceWithDetails

from metis.engine.extractor.types import (
    ChatMessage,
    Delegation,
    ObservationSummary,
    PriorTurn,
    SessionContext,
    ToolCallSummary,
)
from metis.engine.simulation.types import CollectedArtifact, Persona, Scenario
from metis.library.metrics._types import (
    ClarificationRequest,
    OrcaChatMetadata,
    TraceMetadata,
)

# ---------------------------------------------------------------------------
# Span classification helpers
# ---------------------------------------------------------------------------

# Span name prefixes that signal a direct workflow delegation
# (no delegate_task_to_member tool call).
# Maps span name prefix → canonical agent target string.
_WORKFLOW_SPAN_TO_AGENT = {
    "orca-data-analysis": "data-analyst",
    "orca-slide": "slide-maker",
    "orca-text-analysis": "text-analyst",
}

# AGENT span name fragments that are utility/infrastructure, not the real subagent work.
# Sorted longest-first so more specific patterns are checked before shorter ones.
_UTILITY_AGENT_FRAGMENTS = sorted(
    [
        "workflow_notify_summary",
        "workflow_notify",
        "notify_summary",
        "workflow_summary",
    ],
    key=len,
    reverse=True,
)

# Known real-subagent name fragments, used to prefer them over anything else.
_SUBAGENT_FRAGMENTS = [
    "data_analysis_agent",
    "data_analyst",
    "slide_maker",
    "slide_reviewer",
    "text_analyst",
]


def _is_utility_agent(name: str) -> bool:
    n = name.lower()
    return any(frag in n for frag in _UTILITY_AGENT_FRAGMENTS)


def _is_known_subagent(name: str) -> bool:
    n = name.lower()
    return any(frag in n for frag in _SUBAGENT_FRAGMENTS)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def get_langfuse_client() -> Langfuse:
    """Return a configured Langfuse client (never None)."""
    import os

    if os.environ.get("LANGFUSE_BASE_URL") and not os.environ.get("LANGFUSE_HOST"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]
    return Langfuse()


# ---------------------------------------------------------------------------
# Observation extractors
# ---------------------------------------------------------------------------


def _extract_tool_calls(observations: list[ObservationsView]) -> list[ObservationsView]:
    """Extract tool/function calls from observations.

    :param observations: List of Langfuse observation objects.
    :returns: Observations whose ``type`` is ``"TOOL"``.
    """
    return [obs for obs in observations if obs.type == "TOOL"]


def _extract_delegation(observations: list[ObservationsView]) -> Delegation | None:
    """Find the subagent delegation from observations.

    Returns a dict with:

    - ``target``: subagent name (e.g. ``"data-analyst"``, ``"slide-maker"``)
    - ``task``: the delegation message/instruction

    Or ``None`` if no delegation occurred (direct handle).

    The subagent's response is available separately via
    ``_extract_subagent_output`` / ``LLMTestCase.context``.

    :param observations: List of Langfuse observation objects.
    :returns: Delegation dict, or ``None`` if the trace was handled directly.
    """
    # Primary: delegate_task_to_member TOOL observation (explicit tool-call delegation)
    for obs in observations:
        if obs.name == "delegate_task_to_member" and obs.type == "TOOL":
            inp = obs.input or {}
            return Delegation(
                target=inp.get("member_id", "") if isinstance(inp, dict) else "",
                task=inp.get("task", "") if isinstance(inp, dict) else "",
            )

    # Fallback 1: orca-chat span metadata (older routing pattern)
    for obs in observations:
        if obs.name == "orca-chat":
            meta = obs.metadata or {}
            routed = meta.get("routed_to_agents", []) if isinstance(meta, dict) else []
            if routed:
                target = routed[0] if isinstance(routed, list) else str(routed)
                return Delegation(target=target, task="")

    # Fallback 2: orca-data-analysis / orca-slide SPAN (direct workflow delegation).
    for obs in observations:
        span_name = obs.name or ""
        for prefix, agent_target in _WORKFLOW_SPAN_TO_AGENT.items():
            if span_name.startswith(prefix) and obs.type == "SPAN":
                return Delegation(target=agent_target, task="")

    return None


def _extract_spoke_context(
    observations: list[ObservationsView],
) -> dict[str, Any] | None:
    """Extract spoke_context from the trace (cached parameters from prior turns).

    Looks for save_spoke_context tool calls or session_state in agent input.

    :param observations: List of Langfuse observation objects.
    :returns: The spoke context dict, or ``None`` if not found.
    """
    for obs in observations:
        if obs.name == "save_spoke_context" and obs.input:
            return obs.input

    # Parse from subagent input which includes <session_state>
    for obs in observations:
        if obs.type == "AGENT" and (obs.name or "").endswith(".arun"):
            inp = obs.input or ""
            if isinstance(inp, str) and "spoke_context" in inp:
                import re

                match = re.search(r"'spoke_context':\s*(\{[^}]*\})", inp)
                if match:
                    try:
                        import ast

                        return ast.literal_eval(match.group(1))
                    except (ValueError, SyntaxError):
                        pass

    return None


def _extract_assistant_messages(
    observations: list[ObservationsView],
) -> list[ChatMessage]:
    """Extract assistant GENERATION outputs from the trace (LLM responses).

    :param observations: List of Langfuse observation objects.
    :returns: List of message dicts with ``role`` and ``content`` keys.
    """
    messages = []
    for obs in sorted(observations, key=lambda o: o.start_time or datetime.min):
        if obs.type == "GENERATION" and obs.output:
            output = obs.output
            if isinstance(output, dict):
                out_messages = output.get("messages", [])
                for msg in out_messages:
                    if msg.get("role") == "assistant":
                        messages.append(
                            ChatMessage(
                                role="assistant", content=msg.get("content", "")
                            )
                        )
            elif isinstance(output, str):
                messages.append(ChatMessage(role="assistant", content=output))
    return messages


def _extract_subagent_output(observations: list[ObservationsView]) -> str | None:
    """Extract the subagent's response (before Orca synthesis).

    Priority order:

    1. delegate_task_to_member TOOL output (explicit delegation tool call)
    2. orca-data-analysis / orca-slide SPAN output (direct workflow delegation)
    3. Known subagent AGENT spans (e.g. Data_Analysis_Agent.arun)
    4. Any non-Orca, non-utility AGENT span — pick the one with the longest output

    :param observations: List of Langfuse observation objects.
    :returns: Subagent response text, or ``None`` if not found.
    """
    # 1. Explicit delegation tool call
    for obs in observations:
        if obs.name == "delegate_task_to_member" and obs.output:
            return obs.output if isinstance(obs.output, str) else str(obs.output)

    # 2. Workflow delegation spans (orca-data-analysis, orca-slide, etc.)
    for obs in observations:
        span_name = obs.name or ""
        for prefix in _WORKFLOW_SPAN_TO_AGENT:
            if span_name.startswith(prefix) and obs.type == "SPAN" and obs.output:
                return obs.output if isinstance(obs.output, str) else str(obs.output)

    # 3. Known subagent AGENT spans — prefer these over generic .arun spans
    known_candidates = []
    for obs in observations:
        if obs.type == "AGENT" and obs.output and _is_known_subagent(obs.name or ""):
            text = obs.output if isinstance(obs.output, str) else str(obs.output)
            known_candidates.append(text)
    if known_candidates:
        return max(known_candidates, key=len)

    # 4. Any non-Orca, non-utility AGENT span ending in .arun
    generic_candidates = []
    for obs in observations:
        name = obs.name or ""
        if (
            obs.type == "AGENT"
            and name.endswith(".arun")
            and name.lower() != "orca.arun"
            and not _is_utility_agent(name)
            and obs.output
        ):
            text = obs.output if isinstance(obs.output, str) else str(obs.output)
            generic_candidates.append(text)
    if generic_candidates:
        return max(generic_candidates, key=len)

    return None


def _extract_clarification_requests(
    observations: list[ObservationsView],
) -> list[ClarificationRequest]:
    """Extract request_user_input tool calls (clarification questions).

    :param observations: List of Langfuse observation objects.
    :returns: List of :class:`ClarificationRequest` objects.
    """
    return [
        ClarificationRequest(
            name=obs.name, type=obs.type, input=obs.input, output=obs.output
        )
        for obs in observations
        if obs.name == "request_user_input" and obs.type == "TOOL"
    ]


def _extract_orca_chat_metadata(
    observations: list[ObservationsView],
) -> OrcaChatMetadata:
    """Extract metadata from the ``orca-chat`` observation span.

    Looks for the first observation named ``"orca-chat"`` and reads its
    ``metadata`` dict (populated by the Orca orchestrator backend).
    Returns a default-valued :class:`OrcaChatMetadata` when no such span
    exists or the metadata is malformed.

    :param observations: List of Langfuse observation objects.
    :returns: Populated :class:`OrcaChatMetadata` instance.
    """
    for obs in observations:
        if obs.name == "orca-chat":
            meta = obs.metadata or {}
            if not isinstance(meta, dict):
                return OrcaChatMetadata()

            def unwrap(v: object) -> int:
                if isinstance(v, dict) and "intValue" in v:
                    return int(v["intValue"])
                return int(v)  # type: ignore[arg-type]

            return OrcaChatMetadata(
                routed_to_agents=meta.get("routed_to_agents", []),
                num_agents_used=unwrap(meta.get("num_agents_used", 0)),
                num_tool_calls=unwrap(meta.get("num_tool_calls", 0)),
                num_history_messages=unwrap(meta.get("num_history_messages", 0)),
                mode=meta.get("mode", ""),
                had_error=meta.get("had_error", False),
                was_cancelled=meta.get("was_cancelled", False),
                prompt_version=meta.get("prompt_version", ""),
            )
    return OrcaChatMetadata()


# ---------------------------------------------------------------------------
# Bundled extraction intermediate
# ---------------------------------------------------------------------------


@dataclass
class _TraceExtraction:
    """Pre-extracted data from a single trace's observations.

    Built once per trace in fetch_by_session_id, then reused by both
    _trace_to_test_case and _session_to_conversational_test_case to
    avoid redundant extraction and API calls.
    """

    trace: TraceWithDetails
    observations: list[ObservationsView]
    tool_calls: list[ObservationsView]
    delegation: Delegation | None
    subagent_output: str | None
    spoke_context: dict[str, Any] | None
    assistant_messages: list[ChatMessage]
    clarification_requests: list[ClarificationRequest]
    chat_metadata: OrcaChatMetadata


def _extract_all(
    trace: TraceWithDetails, observations: list[ObservationsView]
) -> _TraceExtraction:
    """Run all extraction helpers once and return a bundled result."""
    return _TraceExtraction(
        trace=trace,
        observations=observations,
        tool_calls=_extract_tool_calls(observations),
        delegation=_extract_delegation(observations),
        subagent_output=_extract_subagent_output(observations),
        spoke_context=_extract_spoke_context(observations),
        assistant_messages=_extract_assistant_messages(observations),
        clarification_requests=_extract_clarification_requests(observations),
        chat_metadata=_extract_orca_chat_metadata(observations),
    )


# ---------------------------------------------------------------------------
# Test case construction
# ---------------------------------------------------------------------------


def _trace_to_test_case(
    ext: _TraceExtraction,
    session_context: SessionContext,
) -> LLMTestCase:
    """Convert pre-extracted trace data into a DeepEval LLMTestCase.

    This conversion is lossy. Per-observation fields NOT carried over:
    model identity, model_parameters, token usage/cost, latency,
    time_to_first_token, level/status_message, completion_start_time,
    prompt_id/name/version, and environment. Trace-level metadata, tags,
    user_id, and total_cost are also dropped. Expand the serialization
    below if a new metric needs any of these.

    :param ext: Pre-extracted data bundle for this trace.
    :param session_context: Session-level positioning info.
    :returns: A :class:`~deepeval.test_case.LLMTestCase` ready for metric evaluation.
    """
    trace = ext.trace
    trace_input = trace.input if isinstance(trace.input, str) else str(trace.input)
    trace_output = trace.output if isinstance(trace.output, str) else str(trace.output)

    context = [ext.subagent_output] if ext.subagent_output else None

    meta = TraceMetadata(
        trace_id=trace.id,
        session_id=session_context.session_id,
        turn_index=session_context.turn_index,
        total_turns=session_context.total_turns,
        prior_turns=session_context.prior_turns,
        observations=[
            ObservationSummary(
                id=obs.id,
                name=obs.name,
                type=obs.type,
                input=obs.input,
                output=obs.output,
                metadata=obs.metadata,
                start_time=obs.start_time,
                end_time=obs.end_time,
                parent_observation_id=obs.parent_observation_id,
            )
            for obs in ext.observations
        ],
        tool_calls=[
            ToolCallSummary(
                name=obs.name,
                type=obs.type,
                input=obs.input,
                output=obs.output,
            )
            for obs in ext.tool_calls
        ],
        delegation=ext.delegation,
        spoke_context=ext.spoke_context,
        assistant_messages=ext.assistant_messages,
        clarification_requests=ext.clarification_requests,
        chat_metadata=ext.chat_metadata,
    )

    return LLMTestCase(
        input=trace_input,
        actual_output=trace_output,
        context=context,
        metadata=meta,  # type: ignore[reportArgumentType]
    )


def _session_to_conversational_test_case(
    extractions: list[_TraceExtraction],
) -> ConversationalTestCase | None:
    """Convert pre-extracted trace data into a ConversationalTestCase.

    Each trace becomes a user turn + assistant turn pair.
    The assistant turn carries all tool calls from that trace's observations.

    Returns ``None`` if no extractions are provided.

    :param extractions: Pre-extracted data bundles (chronological, output-bearing only).
    :returns: A :class:`~deepeval.test_case.conversational_test_case\
        .ConversationalTestCase`, or ``None`` if no evaluable traces exist.
    """
    if not extractions:
        return None

    turns = []
    session_metadata: dict = {
        "session_id": extractions[0].trace.session_id,
        "trace_ids": [],
    }

    for ext in extractions:
        trace = ext.trace
        trace_input = trace.input if isinstance(trace.input, str) else str(trace.input)
        trace_output = (
            trace.output if isinstance(trace.output, str) else str(trace.output)
        )

        # Build ToolCall objects from pre-extracted tool observations
        tool_calls = []
        for obs in ext.tool_calls:
            inp = obs.input
            if isinstance(inp, dict):
                params = inp
            elif inp:
                params = {"raw": str(inp)[:500]}
            else:
                params = None
            tool_calls.append(
                ToolCall(
                    name=obs.name or "",
                    input_parameters=params,
                    output=str(obs.output)[:1000] if obs.output else None,
                )
            )

        # User turn
        turns.append(
            Turn(
                role="user",
                content=trace_input,
                metadata={"trace_id": trace.id},
            )
        )

        # Assistant turn with tool calls
        routed_to = ext.delegation.get("target", "") if ext.delegation else ""
        if not routed_to and ext.chat_metadata.routed_to_agents:
            routed_to = ext.chat_metadata.routed_to_agents[0]

        turns.append(
            Turn(
                role="assistant",
                content=trace_output,
                tools_called=tool_calls if tool_calls else None,
                metadata={
                    "trace_id": trace.id,
                    "routed_to": routed_to,
                    "num_tool_calls": len(tool_calls),
                },
            )
        )

        session_metadata["trace_ids"].append(trace.id)

    if not turns:
        return None

    return ConversationalTestCase(
        turns=turns,
        metadata=session_metadata,
    )


# ---------------------------------------------------------------------------
# High-level fetch entry points (from langfuse_fetch)
# ---------------------------------------------------------------------------


@dataclass
class FetchLangfuseResult:
    """Result of a Langfuse fetch operation, ready for evaluation.

    :param test_cases: Per-trace LLMTestCase objects (one per evaluable trace).
    :param session_test_cases: Per-session ConversationalTestCase objects.
    :param sessions: Raw traces grouped by session ID.
    :param skipped: Number of traces skipped (no output).
    """

    test_cases: list[LLMTestCase] = field(default_factory=list)
    session_test_cases: list[ConversationalTestCase] = field(default_factory=list)
    sessions: dict[str, list[TraceWithDetails]] = field(default_factory=dict)
    skipped: int = 0


def fetch_by_session_id(
    session_id: str,
    langfuse: Langfuse,
    *,
    limit: int = 50,
    retry_timeout: int = 0,
    artifacts: list[CollectedArtifact] | None = None,
    scenario: Scenario | None = None,
    persona: Persona | None = None,
    stop_reason: str | None = None,
    cancellation_available: bool | None = None,
) -> FetchLangfuseResult:
    """Fetch traces for a specific session and build test cases.

    :param session_id: Langfuse session ID.
    :param langfuse: Initialized Langfuse client.
    :param limit: Max traces to fetch.
    :param retry_timeout: Seconds to poll if no traces found (0 = no retry).
    :param artifacts: Collected artifacts from the session record, injected into
        each test case's metadata.
    :param scenario: Scenario object from experiment.yaml (passed through to
        metric metadata).
    :param persona: Persona object from experiment.yaml (passed through to
        metric metadata).
    :param stop_reason: Why the session stopped (passed through to metric
        metadata as observable execution state).
    :param cancellation_available: Whether the user could cancel the run
        (passed through to metric metadata as observable execution state).
    :returns: :class:`FetchLangfuseResult` with test cases ready for evaluation.
    """
    deadline = time.time() + retry_timeout
    traces: list[TraceWithDetails] = []

    while True:
        traces = langfuse.api.trace.list(session_id=session_id, limit=limit).data
        if traces or time.time() >= deadline:
            break
        time.sleep(10)

    if not traces:
        return FetchLangfuseResult()

    # Sort traces chronologically within the session
    traces.sort(key=lambda t: t.timestamp or "")

    session_artifacts: list[CollectedArtifact] = artifacts or []
    # Collect slide/image artifact paths in turn order for multimodal metrics.
    _IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    slide_images = sorted(
        [
            a
            for a in session_artifacts
            if a.path and a.filename.lower().endswith(_IMAGE_EXTS)
        ],
        key=lambda a: (a.collected_at_turn, a.filename),
    )
    slide_image_refs: list[str] | None = (
        [a.path for a in slide_images] if slide_images else None
    )
    test_cases: list[LLMTestCase] = []
    skipped: int = 0
    prior_turns: list[PriorTurn] = []
    extractions: list[_TraceExtraction] = []

    for turn_idx, trace in enumerate(traces):
        if not trace.output:
            skipped += 1
            continue

        observations: list[ObservationsView] = langfuse.api.observations.get_many(
            trace_id=trace.id
        ).data
        ext = _extract_all(trace, observations)
        extractions.append(ext)

        session_ctx = SessionContext(
            session_id=session_id,
            turn_index=turn_idx,
            total_turns=len(traces),
            prior_turns=list(prior_turns),
        )

        tc: LLMTestCase = _trace_to_test_case(ext, session_ctx)

        if session_artifacts and tc.metadata is not None:
            tc.metadata["artifacts"] = [a.model_dump() for a in session_artifacts]
        if scenario is not None and tc.metadata is not None:
            tc.metadata["scenario"] = scenario
            tc.metadata["scenario_id"] = scenario.id
        if persona is not None and tc.metadata is not None:
            tc.metadata["persona"] = persona
        if tc.metadata is not None:
            tc.metadata["stop_reason"] = stop_reason
            tc.metadata["cancellation_available"] = cancellation_available
            tc.metadata["slide_image_refs"] = slide_image_refs

        test_cases.append(tc)

        routed_to: str = ext.delegation.get("target", "") if ext.delegation else ""
        if not routed_to and ext.chat_metadata.routed_to_agents:
            routed_to = ext.chat_metadata.routed_to_agents[0]

        prior_turns.append(
            PriorTurn(
                input=(
                    trace.input
                    if isinstance(trace.input, str)
                    else str(trace.input or "")
                )[:500],
                output=(
                    trace.output
                    if isinstance(trace.output, str)
                    else str(trace.output or "")
                )[:500],
                routed_to=routed_to,
            )
        )

    session_test_cases: list[ConversationalTestCase] = []
    ctc: ConversationalTestCase | None = _session_to_conversational_test_case(
        extractions
    )
    if ctc:
        if scenario is not None and ctc.metadata is not None:
            ctc.metadata["scenario"] = scenario
        if persona is not None and ctc.metadata is not None:
            ctc.metadata["persona"] = persona
        if ctc.metadata is not None:
            ctc.metadata["stop_reason"] = stop_reason
            ctc.metadata["cancellation_available"] = cancellation_available
            ctc.metadata["slide_image_refs"] = slide_image_refs
        session_test_cases.append(ctc)

    return FetchLangfuseResult(
        test_cases=test_cases,
        session_test_cases=session_test_cases,
        sessions={session_id: traces},
        skipped=skipped,
    )
