"""
Type definitions for the shared grader catalog.

Contains the TypedDicts and dataclasses used to represent structured data
passed to DeepEval graders. These are standalone copies of the serialized
shapes produced by metis.engine, adapted so that metis-library has no
dependency on metis-engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NotRequired, TypedDict

# ---------------------------------------------------------------------------
# Serialized shape TypedDicts (match what the engine writes)
# ---------------------------------------------------------------------------


class ObservationSummary(TypedDict):
    """Serialized Langfuse ObservationsView.

    Mirrors Langfuse's observation shape directly — input/output are
    untyped because the SDK returns arbitrary JSON per observation kind.
    If a second trace backend is added, define a METIS-native span model
    in metis-core and map from each backend into it.
    """

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
    """Subset of ObservationSummary for TOOL-type spans."""

    name: str | None
    type: str | None
    input: Any
    output: Any


class ChatMessage(TypedDict):
    """Assistant message extracted from generation outputs."""

    role: str
    content: str


class Delegation(TypedDict):
    """Subagent delegation info (target agent + task description)."""

    target: str
    task: str


class PriorTurn(TypedDict):
    """Truncated prior conversation turn for session context."""

    input: str
    output: str
    routed_to: str


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# LlmTestCaseMetadata
# ---------------------------------------------------------------------------


class LlmTestCaseMetadata(TypedDict):
    """Shape of the metadata dict attached to each LLMTestCase.

    This is a TypedDict (not a Pydantic model or dataclass) because
    DeepEval's ``LLMTestCase.metadata`` is typed as ``dict | None``.
    A TypedDict instance passes through without requiring ``.model_dump()``
    or ``dataclasses.asdict()``.

    Populated by trace-to-test-case adapters in metis-engine.
    Graders should read fields from this dict via ``test_case.metadata``.
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
    # Serialized metis.core.Artifact dicts; validated via get_artifacts().
    artifacts: NotRequired[list[dict[str, Any]]]
    # Reserved for future ground-truth annotation source:
    annotations: NotRequired[dict[str, Any]]
    # Observable execution metadata (engine-supplied):
    stop_reason: NotRequired[str | None]
    cancellation_available: NotRequired[bool | None]
    # Injected from experiment configuration at fetch time:
    persona: NotRequired[object]
    scenario: NotRequired[object]
    scenario_id: NotRequired[str]


# ---------------------------------------------------------------------------
# ConversationalTestCaseMetadata
# ---------------------------------------------------------------------------


class ConversationalTestCaseMetadata(TypedDict):
    """Shape of the metadata dict attached to each ConversationalTestCase.

    This is a TypedDict (not a Pydantic model or dataclass) because
    DeepEval's ``ConversationalTestCase.metadata`` is typed as
    ``dict | None``.  A TypedDict instance passes through without
    requiring ``.model_dump()`` or ``dataclasses.asdict()``.

    Populated by session-to-test-case adapters in metis-engine.
    Session graders should read fields from this dict via
    ``test_case.metadata``.
    """

    # --- Always present (set in _session_to_conversational_test_case) ---
    session_id: str
    trace_ids: list[str]

    # --- Observable execution state (set in fetch_by_session_id) ---
    stop_reason: str | None
    cancellation_available: bool | None

    # --- Injected from experiment configuration when available ---
    scenario: NotRequired[object]
    persona: NotRequired[object]

    # --- Grader annotations (injected at runtime) ---
    expected_minimum_steps: NotRequired[int]
