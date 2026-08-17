"""
Type definitions for the shared metric catalog.

Contains the TypedDicts and dataclasses used to represent structured data
passed to DeepEval metrics. These are standalone copies of the types from
metis.engine.extractor.types, adapted so that metis-library has no dependency
on metis-engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NotRequired

from typing_extensions import TypedDict


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


class ObservationSummary(TypedDict):
    """Serialised subset of a Langfuse observation carried in TraceMetadata."""

    id: str
    name: str | None
    type: str | None
    input: Any
    output: Any
    metadata: Any
    start_time: datetime | None
    end_time: datetime | None
    parent_observation_id: str | None


class ToolCallSummary(TypedDict):
    """Serialised subset of a TOOL observation carried in TraceMetadata."""

    name: str | None
    type: str | None
    input: Any
    output: Any


class ChatMessage(TypedDict):
    """A chat message with role and content."""

    role: str
    content: str


class Delegation(TypedDict):
    """A subagent delegation extracted from trace observations."""

    target: str
    task: str


class PriorTurn(TypedDict):
    """A summarised prior conversation turn for session context."""

    input: str
    output: str
    routed_to: str


class TraceMetadata(TypedDict):
    """Shape of the metadata dict attached to each LLMTestCase.

    Populated by trace-to-test-case adapters.  Metrics should read fields
    from this dict via ``test_case.metadata``.

    TypedDict (not BaseModel) because DeepEval's ``LLMTestCase.metadata``
    is typed as a plain dict — a TypedDict IS a dict at runtime so it
    passes through without ``.model_dump()`` while still providing static
    type checking on keys and values.
    """

    trace_id: str
    session_id: str
    turn_index: int
    total_turns: int
    prior_turns: list[PriorTurn]
    observations: list[ObservationSummary]
    tool_calls: list[ToolCallSummary]
    delegation: Delegation | None
    spoke_context: dict[str, Any] | None
    assistant_messages: list[ChatMessage]
    clarification_requests: list[ClarificationRequest]
    chat_metadata: OrcaChatMetadata
    # Added at runtime when available:
    artifacts: NotRequired[list[dict[str, Any]]]
    # Reserved for future ground-truth annotation source:
    annotations: NotRequired[dict]
    # Injected from experiment configuration at fetch time:
    persona: NotRequired[object]
    scenario: NotRequired[object]
    scenario_id: NotRequired[str]
    task: NotRequired[object]  # deprecated alias for scenario
    task_id: NotRequired[str]  # deprecated alias for scenario_id
