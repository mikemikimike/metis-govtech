"""
Type definitions for the shared metric catalog.

Contains the TypedDicts and dataclasses used to represent structured data
passed to DeepEval metrics. These are standalone copies of the types from
metis.engine.extractor.types, adapted so that metis-library has no dependency
on metis-engine.
"""

from dataclasses import dataclass, field
from typing import NotRequired

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


class TraceMetadata(TypedDict):
    """Shape of the metadata dict attached to each LLMTestCase.

    Populated by trace-to-test-case adapters.  Metrics should read fields
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
    clarification_requests: list
    chat_metadata: OrcaChatMetadata
    # Added at runtime when available:
    artifacts: NotRequired[dict]
    # Reserved for future ground-truth annotation source:
    annotations: NotRequired[dict]
    # Injected from experiment configuration at fetch time:
    task: NotRequired[object]
    persona: NotRequired[object]
    task_id: NotRequired[str]
