"""
Type definitions for the Langfuse trace extractor.

Contains all TypedDicts and dataclasses used to represent structured data
extracted from Langfuse observations and passed to DeepEval metrics.
"""

from dataclasses import dataclass, field
from typing import NotRequired

from typing_extensions import TypedDict

from metis.engine.simulation.types import ExperimentTask, Persona


@dataclass
class ClarificationRequest:
    """A single request_user_input tool call extracted from observations."""

    name: str
    type: str
    input: object | None = None
    output: object | None = None


@dataclass
class OrcaChatMetadata:
    """Structured metadata extracted from the ``orca-chat`` Langfuse span.

    Fields mirror the keys written by the Orca orchestrator backend into
    the span's ``metadata`` dict at request completion.  Integer fields may
    arrive wrapped as ``{"intValue": N}`` — the extraction helper unwraps
    them automatically.
    """

    routed_to_agents: list = field(default_factory=list)
    num_agents_used: int = 0
    num_tool_calls: int = 0
    num_history_messages: int = 0
    mode: str = ""
    had_error: bool = False
    was_cancelled: bool = False
    prompt_version: str = ""


class RoutingSummary(TypedDict):
    """Aggregate routing statistics for an evaluation run.

    Summarises how traces were classified and routed to subagents
    during the three-phase evaluation pipeline.

    TypedDict rather than dataclass because this is serialized directly
    to JSON via :func:`json.dumps` in :mod:`report` and consumed
    with ``["key"]`` access throughout the report rendering code.
    """

    total_traces: int
    total_sessions: int
    direct_handle: int
    routing_failed: int
    subagent_counts: dict


class SessionToolCallData(TypedDict):
    """Shape of a tool-call entry inside :class:`SessionTurnData`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON via :func:`json.dumps` in :mod:`report` and consumed with
    ``["key"]`` access throughout the report rendering code.
    """

    name: str
    input: str
    output: str


class SessionTurnData(TypedDict):
    """Shape of a single turn entry inside :class:`SessionMetricsEntry`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON and consumed with ``["key"]`` access in :mod:`report`.
    """

    role: str
    content: str
    tools: NotRequired[list]


class SessionMetricResult(TypedDict):
    """Shape of a single metric result inside :class:`SessionMetricsEntry`.

    TypedDict rather than dataclass because these are serialized directly to
    JSON and consumed with ``["key"]`` access in :mod:`report`.
    """

    name: str
    score: float | None
    reason: str
    success: bool
    skipped: bool


class SessionMetricsEntry(TypedDict):
    """Shape of one session's metrics data passed to
    :func:`report_from_evaluate_result`.

    TypedDict rather than dataclass because the report layer serializes these
    with :func:`json.dumps` (no ``dataclasses.asdict`` needed) and reads fields
    with dict subscript access throughout :mod:`report`.
    """

    session_id: str
    num_turns: int
    turns: list
    metrics: list


class TraceMetadata(TypedDict):
    """Shape of the metadata dict attached to each LLMTestCase.

    Populated by :func:`trace_to_test_case`.  Metrics should read fields
    from this dict via ``test_case.metadata``.
    """

    trace_id: str
    session_id: str
    turn_index: int
    total_turns: int
    prior_turns: list
    observations: list
    tool_calls: list
    delegation: dict | None
    spoke_context: dict | None
    assistant_messages: list
    retry_counts: dict
    clarification_requests: list
    chat_metadata: OrcaChatMetadata
    # Added at runtime by run_langfuse_eval when available:
    artifacts: NotRequired[dict]
    # Reserved for future ground-truth annotation source:
    annotations: NotRequired[dict]
    # Injected from experiment.yaml at fetch time:
    task: NotRequired[ExperimentTask]
    persona: NotRequired[Persona]
    task_id: NotRequired[str]


@dataclass
class SessionContext:
    """Session-level context for a trace within a multi-turn conversation."""

    session_id: str
    turn_index: int
    total_turns: int
    prior_turns: list = field(default_factory=list)
