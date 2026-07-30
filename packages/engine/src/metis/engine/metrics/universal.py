"""
Universal metrics (M-UNI-*) — apply to all agents.

Code-graded: M-UNI-1, 2, 3, 4, 6
Model-graded (GEval): M-UNI-5, 7, 8, 9, 10, 11
"""

from typing import cast

from deepeval.metrics import BaseMetric, ConversationalGEval, GEval
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from metis.engine.extractor.types import OrcaChatMetadata, TraceMetadata

from ._judge import _get_judge_model


class SyncBaseMetric(BaseMetric):
    """BaseMetric subclass that implements a_measure.

    Calls measure synchronously.

    Adds a `skipped` flag so reporters can distinguish "passed"
    from "not evaluated due to missing data." Skipped metrics
    still return success=True (so assert_test doesn't fail), but
    reporters should exclude them from pass-rate aggregation.

    Exposes evaluation_cost/input_tokens/output_tokens from inner
    GEval so DeepEval's framework can pick them up.
    """

    async_mode = False
    skipped: bool = False

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


class SinglePromptClarificationMetric(SyncBaseMetric):
    """All clarifications should be asked in a single message.

    Uses request_user_input TOOL observations from the span tree.
    If the agent asks for user input more than once, that's multiple
    clarification rounds — it should batch them into one form/message.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])

        clarification_count = len(clarifications)

        if clarification_count == 0:
            self.score = 1.0
            self.reason = "No clarification requests (proceeded directly)"
            self.success = True
            return self.score or 0.0

        self.score = 1.0 if clarification_count <= 1 else 0.0
        status = (
            "OK, single prompt"
            if clarification_count <= 1
            else "FAIL: should batch into one"
        )
        self.reason = f"{clarification_count} request_user_input call(s) — {status}"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Single-Prompt Clarification"

    def is_successful(self) -> bool:
        return self.success is True


class TurnsToTaskStartMetric(SyncBaseMetric):
    """How many turns before work begins?

    Uses the num_history_messages from orca-chat span and counts
    request_user_input calls. Each request_user_input is a round-trip
    back to the user before work starts. Gate: ≤2 turns.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0, max_turns: int = 2):
        self.threshold = threshold
        self.max_turns = max_turns
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )

        # Each request_user_input is a turn back to the user
        turns_before_action = len(clarifications)
        num_history = chat_meta.num_history_messages

        self.score = 1.0 if turns_before_action <= self.max_turns else 0.0
        self.reason = (
            f"{turns_before_action} clarification "
            f"round-trip(s) before task execution "
            f"(max: {self.max_turns}, "
            f"history_msgs: {num_history})"
        )
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Turns to Task Start"

    def is_successful(self) -> bool:
        return self.success is True


class StepEfficiencyMetric(SyncBaseMetric):
    """Task completed in near-minimum tool calls?

    Uses actual TOOL observations from the span tree. Without annotations,
    reports the count from both orca-chat metadata and observation tree
    (informational pass). With annotations, compares to expected minimum.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0, max_ratio: float = 1.3):
        self.threshold = threshold
        self.max_ratio = max_ratio
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        tool_calls = metadata.get("tool_calls", [])
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        annotations = metadata.get("annotations", {})

        actual_count = len(tool_calls)
        reported_count = chat_meta.num_tool_calls
        expected_minimum = annotations.get("expected_minimum_steps")

        if expected_minimum is None:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                f"{actual_count} tool call(s) in "
                f"observation tree (orca-chat reports "
                f"{reported_count}), no minimum "
                f"annotated — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        if expected_minimum == 0:
            self.score = 1.0 if actual_count == 0 else 0.0
            self.reason = f"{actual_count} tool call(s), expected 0"
            self.success = (self.score or 0) >= self.threshold
            return self.score or 0.0

        ratio = actual_count / expected_minimum
        self.score = 1.0 if ratio <= self.max_ratio else 0.0
        self.reason = f"{actual_count} tool call(s) vs {expected_minimum} minimum (ratio: {ratio:.2f}, max: {self.max_ratio})"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Step Efficiency"

    def is_successful(self) -> bool:
        return self.success is True


class ContextReuseMetric(SyncBaseMetric):
    """Uses cached context instead of re-asking?

    Detects request_user_input calls that ask for information already present
    in spoke_context. Passes if no redundant re-asks are found.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        observations = metadata.get("observations", [])
        spoke_context = metadata.get("spoke_context") or {}

        if not spoke_context:
            self.score = 1.0
            self.skipped = True
            self.reason = "No spoke_context present (first interaction) — SKIPPED"
            self.success = True
            return self.score or 0.0

        cached_keys = set(spoke_context.keys())
        redundant_asks = 0

        for obs in observations:
            if obs.get("name") == "request_user_input":
                output = obs.get("output") or {}
                question_text = str(output).lower()
                for key in cached_keys:
                    if key.lower() in question_text:
                        redundant_asks += 1
                        break

        self.score = 1.0 if redundant_asks == 0 else 0.0
        self.reason = f"{redundant_asks} redundant re-ask(s) for info already in spoke_context (cached keys: {list(cached_keys)})"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Context Reuse"

    def is_successful(self) -> bool:
        return self.success is True


class BoundedTroubleshootingMetric(SyncBaseMetric):
    """Stops retrying after N attempts?

    Counts repeated calls to the same tool name in TOOL observations.
    For example, execute_python called 7 times suggests the agent kept
    retrying failed code. Passes if no single tool exceeds max_retries.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0, max_retries: int = 5):
        self.threshold = threshold
        self.max_retries = max_retries
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        retry_counts = metadata.get("retry_counts", {})
        tool_calls = metadata.get("tool_calls", [])

        # Also count from raw tool calls for completeness
        if not retry_counts and tool_calls:
            from collections import Counter

            counts = Counter(tc.get("name", "") for tc in tool_calls)
            retry_counts = {name: c for name, c in counts.items() if c > 1}

        violations = {
            name: count
            for name, count in retry_counts.items()
            if count > self.max_retries
        }

        if not retry_counts:
            self.score = 1.0
            self.reason = "No repeated tool calls detected"
        elif not violations:
            self.score = 1.0
            max_name = max(retry_counts, key=lambda k: retry_counts[k])
            self.reason = f"Repeated tools within bounds (max: {max_name}={retry_counts[max_name]}, limit: {self.max_retries})"
        else:
            self.score = 0.0
            self.reason = (
                f"Retry limit exceeded: {violations} (limit: {self.max_retries})"
            )

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Bounded Troubleshooting"

    def is_successful(self) -> bool:
        return self.success is True


# --- Model-graded metrics (GEval) ---


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


class DiagnosisQualityMetric(SyncBaseMetric):
    """Root cause identified before fix attempted?

    Extract+judge: extracts error observations and the agent's response,
    then judges whether the agent diagnosed the root cause before attempting a fix.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Diagnosis Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent correctly "
                    "diagnosed the root cause of a "
                    "failure "
                    "before attempting a fix.\n\n"
                    "The 'input' is the user's request "
                    "that triggered an error.\n"
                    "The 'actual_output' is the agent's "
                    "response including its diagnosis "
                    "and actions.\n\n"
                    "Check:\n"
                    "1. Does the agent identify what went "
                    "wrong (the root cause), not just "
                    "the symptom?\n"
                    "2. Does the diagnosis appear BEFORE "
                    "the fix attempt in the response?\n"
                    "3. Is the stated root cause "
                    "plausible given the error?\n\n"
                    "Score 1.0 if root cause correctly "
                    "identified before fix. "
                    "Score 0.5 if diagnosis is present "
                    "but superficial or after the fix "
                    "attempt. "
                    "Score 0.0 if no diagnosis — agent "
                    "jumps straight to retrying or "
                    "guessing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _has_error(self, test_case: LLMTestCase) -> bool:
        metadata = cast(TraceMetadata, test_case.metadata)
        if metadata.get("had_error"):
            return True
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        if chat_meta.had_error:
            return True
        observations = metadata.get("observations", [])
        for obs in observations:
            if obs.get("type") != "TOOL":
                continue
            obs_meta = obs.get("metadata") or {}
            if obs_meta.get("error"):
                return True
            level = obs.get("level") or ""
            if level.upper() == "ERROR":
                return True
        return False

    def measure(self, test_case: LLMTestCase) -> float:
        if not self._has_error(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No error observed in trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self._absorb_geval_cost(geval)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        if not self._has_error(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No error observed in trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self._absorb_geval_cost(geval)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Diagnosis Quality"

    def is_successful(self) -> bool:
        return self.success is True


class OpenEndedScopeQualityMetric(SyncBaseMetric):
    """Agent-chosen scope appropriate when user doesn't specify?

    Full judge: evaluates whether the agent's chosen scope is comprehensive,
    relevant, and proportionate for an open-ended request.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Open-Ended Scope Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the scope the agent chose "
                    "when the user gave an open-ended "
                    "request "
                    "(e.g. 'explore this dataset', "
                    "'scan this document', "
                    "'what's interesting here').\n\n"
                    "The 'input' is the user's "
                    "open-ended request.\n"
                    "The 'actual_output' is the agent's "
                    "response showing what it chose to "
                    "cover.\n\n"
                    "Rate on three dimensions:\n"
                    "1. Comprehensive: Does it cover the "
                    "major topics/patterns a competent "
                    "analyst would?\n"
                    "2. Relevant: Is everything it "
                    "covers actually pertinent (no "
                    "filler or tangents)?\n"
                    "3. Proportionate: Is the depth "
                    "appropriate — not too shallow, not "
                    "obsessively detailed?\n\n"
                    "Score 1.0 if scope is excellent on "
                    "all dimensions. "
                    "Score 0.5 if adequate but missing a "
                    "major topic or including filler. "
                    "Score 0.0 if scope is clearly wrong "
                    "(trivial coverage of a rich "
                    "source, or "
                    "overwhelmingly irrelevant "
                    "tangents)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Open-Ended Scope Quality"

    def is_successful(self) -> bool:
        return self.success is True


class ClarificationPrecisionMetric(SyncBaseMetric):
    """All questions necessary and no needed question omitted?

    Extract+judge: extracts clarification questions from the trace and judges
    whether they are precisely calibrated — necessary and complete.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Clarification Precision",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the quality of clarification "
                    "questions the agent asked.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' contains the "
                    "clarification question(s) the agent "
                    "asked.\n\n"
                    "Check:\n"
                    "1. Necessity: Is every question "
                    "required to proceed? (no "
                    "superfluous questions)\n"
                    "2. Completeness: Are there obvious "
                    "missing questions the agent should "
                    "have asked?\n"
                    "3. Specificity: Are questions "
                    "precise enough to get actionable "
                    "answers?\n\n"
                    "Score 1.0 if all questions are "
                    "necessary, none are missing, and "
                    "they're specific. "
                    "Score 0.5 if mostly right but one "
                    "superfluous or one missing "
                    "question. "
                    "Score 0.0 if asks irrelevant things "
                    "or misses critical information "
                    "needs." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])

        if not clarifications:
            self.score = 1.0
            self.skipped = True
            self.reason = "No clarification questions asked — SKIPPED"
            self.success = True
            return self.score or 0.0

        questions_text = "\n".join(
            str(c.output or c.input or c) for c in clarifications
        )
        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=questions_text,
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        geval.measure(judge_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        clarifications = metadata.get("clarification_requests", [])

        if not clarifications:
            self.score = 1.0
            self.skipped = True
            self.reason = "No clarification questions asked — SKIPPED"
            self.success = True
            return self.score or 0.0

        questions_text = "\n".join(
            str(c.output or c.input or c) for c in clarifications
        )
        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=questions_text,
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(judge_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Clarification Precision"

    def is_successful(self) -> bool:
        return self.success is True


class FailureReportQualityMetric(SyncBaseMetric):
    """Report includes what failed, what was attempted, and next steps?

    Full judge: evaluates the agent's failure report when it stops on an error.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Failure Report Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the quality of the agent's "
                    "failure report to the user.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the agent's "
                    "failure report.\n\n"
                    "A good failure report must include "
                    "ALL THREE:\n"
                    "1. What failed: Clear description "
                    "of the error or obstacle\n"
                    "2. What was attempted: What the "
                    "agent tried before giving up\n"
                    "3. Actionable next steps: At least "
                    "one concrete suggestion for the "
                    "user\n\n"
                    "Score 1.0 if all three present and clear. "
                    "Score 0.5 if two of three present. "
                    "Score 0.0 if only one or none — e.g. just says 'I couldn't do it'."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )

        if not chat_meta.had_error:
            self.score = 1.0
            self.skipped = True
            self.reason = "No error in this trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )

        if not chat_meta.had_error:
            self.score = 1.0
            self.skipped = True
            self.reason = "No error in this trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Failure Report Quality"

    def is_successful(self) -> bool:
        return self.success is True


class AssumptionTransparencyMetric(SyncBaseMetric):
    """Assumptions explicitly stated to user?

    Full judge: evaluates whether the agent makes its assumptions visible.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Assumption Transparency",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent explicitly "
                    "states assumptions it made.\n\n"
                    "SYSTEM CONTEXT: This agent is an "
                    "orchestrator that delegates tasks "
                    "to "
                    "specialised subagents (Data "
                    "Analyst, Slide Maker, Text "
                    "Analyst, etc.). "
                    "Delegating a task to the correct "
                    "subagent is STANDARD BEHAVIOUR, "
                    "not an "
                    "assumption. Routing decisions, "
                    "tool usage, and reading file "
                    "contents are "
                    "normal operations — do NOT count "
                    "these as 'unstated "
                    "assumptions.'\n\n"
                    "The 'input' is the user's request "
                    "(which may be ambiguous or "
                    "underspecified).\n"
                    "The 'actual_output' is the agent's "
                    "response.\n\n"
                    "Only flag these as unstated "
                    "assumptions:\n"
                    "- Interpreting an ambiguous user "
                    "request one way without saying so\n"
                    "- Choosing a scope/format/timeframe "
                    "the user didn't specify\n"
                    "- Making analytical choices "
                    "(grouping, filtering, method) "
                    "without explaining\n\n"
                    "Do NOT flag as unstated "
                    "assumptions:\n"
                    "- Delegating to a subagent (this is "
                    "the system's normal workflow)\n"
                    "- Reading a file the user "
                    "uploaded\n"
                    "- Using available tools to "
                    "accomplish the task\n"
                    "- Identifying column names from a "
                    "CSV (this is observation, not "
                    "assumption)\n\n"
                    "Score 1.0 if all assumptions are "
                    "transparently stated, or no "
                    "assumptions needed. "
                    "Score 0.5 if some assumptions "
                    "stated but others implicit. "
                    "Score 0.0 if the agent clearly made "
                    "scope/interpretation "
                    "assumptions but never mentioned "
                    "them. "
                    "If the task required no assumptions "
                    "(fully specified), score 1.0." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Assumption Transparency"

    def is_successful(self) -> bool:
        return self.success is True


class ConstraintAdherenceMetric(SyncBaseMetric):
    """All explicit constraints and negative instructions respected?

    Extract+judge: checks whether user-specified constraints are honored.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Constraint Adherence",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the agent respected "
                    "all explicit constraints and "
                    "negative instructions from the "
                    "user.\n\n"
                    "SYSTEM CONTEXT: This agent is an "
                    "orchestrator that delegates tasks "
                    "to "
                    "specialised subagents. When the "
                    "user says 'analyse this file' or "
                    "'cluster "
                    "this data', the orchestrator's job "
                    "is to delegate to the right "
                    "subagent — "
                    "this IS completing the task. "
                    "Presenting a configuration form "
                    "before execution "
                    "is NORMAL WORKFLOW, not a failure "
                    "to perform the task.\n\n"
                    "IMPORTANT: Only evaluate EXPLICIT "
                    "constraints — things the user said "
                    "with "
                    "words like 'do not', 'must', "
                    "'only', 'no more than', 'without', "
                    "'exclude'. "
                    "Do NOT treat the user's task "
                    "request itself as a 'constraint.' "
                    "The task "
                    "is being delegated and executed — "
                    "evaluate whether explicit "
                    "restrictions "
                    "within that task are honoured.\n\n"
                    "The 'input' is the user's "
                    "request.\n"
                    "The 'actual_output' is the agent's "
                    "response.\n\n"
                    "Check:\n"
                    "1. Identify all explicit "
                    "constraints in the input (format "
                    "restrictions, "
                    "exclusions, limits, negative "
                    "instructions)\n"
                    "2. Verify each constraint is satisfied in the output\n"
                    "3. If no explicit constraints exist, score 1.0\n\n"
                    "Score 1.0 if all constraints respected or no constraints present. "
                    "Score 0.5 if minor violation of a soft constraint. "
                    "Score 0.0 if a hard constraint is clearly violated."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Constraint Adherence"

    def is_successful(self) -> bool:
        return self.success is True


class TurnBudgetMetric(SyncBaseMetric):
    """Session completed within the allowed turn budget.

    Checks that the total number of conversation turns did not exceed
    max_turns. Passes if turns <= max_turns, fails otherwise.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0, max_turns: int = 10):
        self.threshold = threshold
        self.max_turns = max_turns
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata or {})
        total_turns = metadata.get("total_turns")
        if total_turns is None:
            self.skipped = True
            self.score = 1.0
            self.reason = "total_turns not present in metadata — skipped"
            self.success = True
            return self.score

        self.score = 1.0 if total_turns <= self.max_turns else 0.0
        self.reason = f"Session used {total_turns} turn(s) (budget: {self.max_turns})"
        self.success = self.score >= self.threshold
        return self.score

    @property
    def __name__(self):
        return "Turn Budget"

    def is_successful(self) -> bool:
        return self.success


def get_judge_metrics():
    """Return all UNI judge metrics. Call only when you have API keys configured."""
    return (
        DiagnosisQualityMetric(),
        OpenEndedScopeQualityMetric(),
        ClarificationPrecisionMetric(),
        FailureReportQualityMetric(),
        AssumptionTransparencyMetric(),
        ConstraintAdherenceMetric(),
    )
