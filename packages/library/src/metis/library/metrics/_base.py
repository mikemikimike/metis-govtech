"""Shared base classes and utilities for METIS metrics."""

from typing import ClassVar

from deepeval.metrics import BaseConversationalMetric, BaseMetric, ConversationalGEval, GEval
from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase

EVIDENCE_INSTRUCTION = (
    "\n\nIMPORTANT: In your reasoning, quote the "
    "specific text, tool call, or output "
    "that most influenced your score. "
    "Use exact quotes from the input/output."
)


def _build_context_block(metadata: dict) -> str:
    """Build an [EVALUATION CONTEXT] block from metadata, or return empty string."""
    task = metadata.get("scenario") or metadata.get("task")
    persona = metadata.get("persona")

    scenario_desc = getattr(task, "description", "") or ""
    persona_desc = getattr(persona, "description", "") or ""

    if not scenario_desc and not persona_desc:
        return ""

    parts = ["[EVALUATION CONTEXT]"]
    if scenario_desc:
        parts.append(f"Scenario: {scenario_desc.strip()}")
    if persona_desc:
        parts.append(f"User persona: {persona_desc.strip()}")
    parts.append("[END CONTEXT]")
    return "\n".join(parts)


def _with_eval_context(test_case: LLMTestCase) -> LLMTestCase:
    """Return a copy of test_case with scenario/persona context prepended to input.

    Used for non-GEval metrics (e.g. FaithfulnessMetric) that don't have
    criteria we can inject into. GEval metrics use _ContextAwareGEval instead.
    """
    context_block = _build_context_block(test_case.metadata or {})
    if not context_block:
        return test_case

    return LLMTestCase(
        input=context_block + "\n\n" + test_case.input,
        actual_output=test_case.actual_output,
        expected_output=test_case.expected_output,
        context=test_case.context,
        retrieval_context=test_case.retrieval_context,
        tools_called=test_case.tools_called,
        metadata=test_case.metadata or {},
    )


class _ContextAwareGEval(GEval):
    """GEval subclass that injects eval context into criteria at measure time."""

    def _get_prompt(self, method, **kwargs):
        kwargs.setdefault("template_class", "GEval")
        return super()._get_prompt(method, **kwargs)

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        context_block = _build_context_block(test_case.metadata or {})
        if not context_block:
            return super().measure(test_case, *args, **kwargs)
        original_criteria = self.criteria
        self.criteria = "\n\n" + context_block + "\n\n" + original_criteria
        try:
            return super().measure(test_case, *args, **kwargs)
        finally:
            self.criteria = original_criteria

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        context_block = _build_context_block(test_case.metadata or {})
        if not context_block:
            return await super().a_measure(test_case, *args, **kwargs)
        original_criteria = self.criteria
        self.criteria = "\n\n" + context_block + "\n\n" + original_criteria
        try:
            return await super().a_measure(test_case, *args, **kwargs)
        finally:
            self.criteria = original_criteria


class _ContextAwareConversationalGEval(ConversationalGEval):
    """ConversationalGEval subclass that injects eval context into criteria."""

    def _get_prompt(self, method, **kwargs):
        kwargs.setdefault("template_class", "ConversationalGEval")
        return super()._get_prompt(method, **kwargs)

    def measure(self, test_case: ConversationalTestCase, *args, **kwargs) -> float:
        context_block = _build_context_block(test_case.metadata or {})
        if not context_block:
            return super().measure(test_case, *args, **kwargs)
        original_criteria = self.criteria
        self.criteria = "\n\n" + context_block + "\n\n" + original_criteria
        try:
            return super().measure(test_case, *args, **kwargs)
        finally:
            self.criteria = original_criteria

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        context_block = _build_context_block(test_case.metadata or {})
        if not context_block:
            return await super().a_measure(test_case, *args, **kwargs)
        original_criteria = self.criteria
        self.criteria = "\n\n" + context_block + "\n\n" + original_criteria
        try:
            return await super().a_measure(test_case, *args, **kwargs)
        finally:
            self.criteria = original_criteria


class MetisTurnMetric(BaseMetric):
    """Base class for per-turn METIS metrics (evaluated per LLMTestCase).

    Each per-turn metric is evaluated against a single trace/turn. The
    orchestrator routes metrics here when they are NOT subclasses of
    BaseConversationalMetric.

    Subclasses must:
    - Define ``tags: ClassVar[tuple[str, ...]]`` (enforced at class definition)
    - Implement either:
      - ``measure()`` + set ``async_mode = False`` (code-graded, synchronous)
      - ``async def a_measure()`` (judge-graded, async; async_mode defaults True)

    The orchestrator dispatches based on ``async_mode``:
    - False → ``measure()`` called via ``asyncio.to_thread``
    - True → ``await a_measure()``
    """

    tags: ClassVar[tuple[str, ...]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "tags") or not isinstance(
            getattr(cls, "tags", None), tuple
        ):
            raise TypeError(
                f"{cls.__name__} must define a 'tags' class variable as a tuple of strings"
            )

    def _accrue_cost(self, cost: float | None) -> None:
        """Override BaseMetric._accrue_cost to handle None initial state."""
        if cost is not None:
            self.evaluation_cost = (self.evaluation_cost or 0) + cost


class MetisSessionMetric(BaseConversationalMetric):
    """Base class for session-level METIS metrics.

    Subclasses must define a `tags` ClassVar. Session metrics evaluate
    full ConversationalTestCase objects (multi-turn conversations).
    """

    tags: ClassVar[tuple[str, ...]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "tags") or not isinstance(
            getattr(cls, "tags", None), tuple
        ):
            raise TypeError(
                f"{cls.__name__} must define a 'tags' class variable as a tuple of strings"
            )


def mark_skipped(metric: BaseMetric | BaseConversationalMetric, reason: str) -> float:
    """Mark a metric as skipped (not evaluated due to missing/irrelevant data).

    Sets metric.skipped = True so the orchestrator can read it directly.
    Sets score=1.0 and success=True so any DeepEval assert_test won't fail.
    """
    metric.skipped = True
    metric.score = 1.0
    metric.reason = reason
    metric.success = True
    return 1.0
