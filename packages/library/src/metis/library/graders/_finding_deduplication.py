"""Finding Deduplication grader (M-ORCA-*)."""

from typing import Any, ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from ._base import (
    EVIDENCE_INSTRUCTION,
    MetisTurnGrader,
    _ContextAwareGEval,
    mark_skipped,
)
from ._judge import _get_judge_model
from ._types import LlmTestCaseMetadata, OrcaChatMetadata

# Canonical agent type fragments and the key they map to.
_AGENT_TYPE_MAP = [
    ("data_analysis_agent", "data_analyst"),
    ("data_analyst", "data_analyst"),
    ("slide_maker", "slide_maker"),
    ("slide_reviewer", "slide_reviewer"),
    ("text_analyst", "text_analyst"),
]


def _canonical_agent_type(span_name: str) -> str | None:
    """Return a canonical agent key for a span name.

    Returns None if it's not a known subagent.
    """
    n = span_name.lower()
    for fragment, key in _AGENT_TYPE_MAP:
        if fragment in n:
            return key
    return None


def _is_multi_agent_trace(test_case: LLMTestCase) -> bool:
    """Return True only when the trace involved 2+ distinct subagent *types*.

    Checks three independent signals:
    1. orca-chat metadata num_agents_used > 1
    2. routed_to_agents list has > 1 distinct entry
    3. More than one distinct canonical agent type in AGENT spans
       (Data_Analysis_Agent.arun + Data_Analyst.arun = one type, not two)
    """
    metadata = cast("LlmTestCaseMetadata", test_case.metadata)
    chat_meta: OrcaChatMetadata = metadata.get("chat_metadata") or OrcaChatMetadata()

    # Signal 1: explicit count from orca-chat span
    if chat_meta.num_agents_used > 1:
        return True

    # Signal 2: routed_to_agents list
    routed = chat_meta.routed_to_agents
    if len(set(str(a).lower() for a in routed)) > 1:
        return True

    # Signal 3: count distinct canonical agent types across AGENT spans
    observations = metadata.get("observations", [])
    seen_types = set()
    for obs in observations:
        if obs.get("type") != "AGENT":
            continue
        agent_type = _canonical_agent_type(obs.get("name", ""))
        if agent_type:
            seen_types.add(agent_type)
    return len(seen_types) > 1


class FindingDeduplicationGrader(MetisTurnGrader):
    """No finding redundantly stated across multi-agent synthesis?

    Extract+judge: checks whether the final response contains redundant
    restatements of the same finding. Skips short responses and single-agent traces.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "orchestration",
        "per-turn",
        "judge-graded",
    )

    MIN_OUTPUT_LENGTH = 400

    def __init__(self, threshold: float = 0.6) -> None:
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _should_skip(self, test_case: LLMTestCase) -> str | None:
        output_len = len(test_case.actual_output or "")
        if not _is_multi_agent_trace(test_case):
            return "Single-agent or direct response (dedup N/A)"
        if output_len < self.MIN_OUTPUT_LENGTH:
            return f"Response too short ({output_len} chars) for meaningful dedup check"
        return None

    def _get_geval(self) -> _ContextAwareGEval:
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Finding Deduplication",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator's "
                    "response contains REDUNDANT findings — "
                    "the same factual point stated multiple "
                    "times in different words.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "synthesized response.\n\n"
                    "IMPORTANT DISTINCTIONS:\n"
                    "- A summary at the end that recaps key "
                    "points from detailed sections is "
                    "NORMAL STRUCTURE, not redundancy.\n"
                    "- Mentioning a finding once in a table and "
                    "once in prose explanation is "
                    "NORMAL, not redundancy.\n"
                    "- TRUE redundancy is when the exact same "
                    "analytical point appears multiple "
                    "times with no structural reason (e.g. "
                    "same insight in intro AND body AND "
                    "conclusion with identical phrasing).\n\n"
                    "Score 1.0 if no redundancy or only normal "
                    "structural recapping. "
                    "Score 0.5 if some unnecessary repetition "
                    "but not egregious. "
                    "Score 0.0 ONLY if the same finding is "
                    "clearly copy-pasted or restated "
                    "verbatim 3+ times with no structural "
                    "justification." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    async def a_measure(
        self, test_case: LLMTestCase, *args: Any, **kwargs: Any
    ) -> float:
        skip_reason = self._should_skip(test_case)
        if skip_reason:
            return mark_skipped(self, skip_reason)

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._accrue_cost(geval.evaluation_cost)
        self._accrue_tokens(geval.input_tokens, geval.output_tokens)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Finding Deduplication"

    def is_successful(self) -> bool:
        return self.success is True
