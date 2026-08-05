"""Shared base classes and utilities for METIS metrics."""

from typing import ClassVar

from deepeval.metrics import BaseMetric, ConversationalGEval, GEval
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
    task = metadata.get("task")
    persona = metadata.get("persona")

    task_desc = getattr(task, "description", "") or ""
    persona_desc = getattr(persona, "description", "") or ""

    if not task_desc and not persona_desc:
        return ""

    parts = ["[EVALUATION CONTEXT]"]
    if task_desc:
        parts.append(f"Scenario: {task_desc.strip()}")
    if persona_desc:
        parts.append(f"User persona: {persona_desc.strip()}")
    parts.append("[END CONTEXT]")
    return "\n".join(parts)


def _with_eval_context(test_case: LLMTestCase) -> LLMTestCase:
    """Return a copy of test_case with task/persona context prepended to input.

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


class SyncBaseMetric(BaseMetric):
    """BaseMetric subclass that implements a_measure synchronously.

    Adds a `skipped` flag so reporters can distinguish "passed"
    from "not evaluated due to missing data." Skipped metrics
    still return success=True (so assert_test doesn't fail), but
    reporters should exclude them from pass-rate aggregation.

    Exposes evaluation_cost/input_tokens/output_tokens from inner
    GEval so DeepEval's framework can pick them up.

    All subclasses MUST define a `tags` ClassVar.
    """

    async_mode = False
    skipped: bool = False
    tags: ClassVar[tuple[str, ...]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "tags") or not isinstance(
            getattr(cls, "tags", None), tuple
        ):
            raise TypeError(
                f"{cls.__name__} must define a 'tags' ClassVar as a tuple of strings"
            )

    def _absorb_geval_cost(self, geval):
        """Copy cost/token info from an inner GEval after it evaluates."""
        if hasattr(geval, "evaluation_cost") and geval.evaluation_cost:
            self.evaluation_cost = (self.evaluation_cost or 0) + geval.evaluation_cost
        if hasattr(geval, "input_tokens") and geval.input_tokens:
            self.input_tokens = (self.input_tokens or 0) + geval.input_tokens
        if hasattr(geval, "output_tokens") and geval.output_tokens:
            self.output_tokens = (self.output_tokens or 0) + geval.output_tokens

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)
