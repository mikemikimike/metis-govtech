"""
Orca orchestrator metrics (M-ORCA-*).

Code-graded: RoutingAccuracyMetric, DirectHandleRecognitionMetric
Model-graded: DELEGATION_QUALITY_METRIC, SYNTHESIS_QUALITY_METRIC (GEval)
"""

from typing import cast

from deepeval.metrics import (
    ArgumentCorrectnessMetric as _ArgumentCorrectnessMetric,
)
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall

from metis.library.metrics._types import OrcaChatMetadata, TraceMetadata

from ._judge import _get_judge_model
from .universal import (
    EVIDENCE_INSTRUCTION,
    SyncBaseMetric,
    _ContextAwareGEval,
    _with_eval_context,
)

# ---------------------------------------------------------------------------
# Agent grounding context (for judges that need to know what the system CAN do)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_SUMMARY = (
    "Orca is a multi-agent orchestrator that routes user "
    "requests to specialised subagents. "
    "It can also handle simple requests directly without "
    "delegation. "
    "It manages conversation context across turns and "
    "synthesises subagent outputs for the user."
)

TOOL_MANIFEST = (
    "AVAILABLE SUBAGENTS:\n"
    "- Data Analyst (data-analyst): Analyses data files "
    "(CSV, XLSX, etc.), produces charts, "
    "runs Python code, generates reports. "
    "Tools: execute_python, analyze_data, "
    "create_file, view.\n"
    "- Slide Maker (slide-maker): Creates PowerPoint "
    "presentations from source documents. "
    "Tools: make_ppt, list_ppt_themes.\n"
    "- Slide Reviewer (slide-reviewer): Reviews and "
    "critiques existing slide decks.\n"
    "- Text Analyst (text-analyst): Performs text "
    "clustering, topic modelling, NLP tasks.\n"
    "\n"
    "ORCA'S OWN TOOLS:\n"
    "- delegate_task_to_member: Routes a task to a "
    "subagent\n"
    "- request_user_input: Asks the user a clarifying "
    "question (via form)\n"
    "- read_source_file: Reads uploaded files\n"
    "- save_spoke_context: Persists context between "
    "turns\n"
    "- web_search: Searches the web for information\n"
)


class RoutingAccuracyMetric(SyncBaseMetric):
    """Right subagent chosen?

    LLM judge evaluates whether the chosen subagent (or direct handling) was
    appropriate for the user's request. No annotations needed.
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
                name="Routing Accuracy",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator routed the "
                    "user's request to the "
                    "correct subagent (or handled it directly when "
                    "appropriate).\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is what the orchestrator "
                    "did — its response shows "
                    "which agent handled the task (look for "
                    "mentions of 'Data Analyst', "
                    "'Slide Maker', or direct handling).\n\n"
                    "Available agents:\n"
                    "- Data Analyst: for data analysis, charts, "
                    "statistics, reports from data\n"
                    "- Slide Maker: for creating "
                    "presentations/slide decks\n"
                    "- Direct handling: for simple questions, "
                    "greetings, meta-questions about "
                    "capabilities\n\n"
                    "Score 1.0 if the routing was clearly correct. "
                    "Score 0.5 if the choice was defensible but "
                    "suboptimal. "
                    "Score 0.0 if clearly wrong (e.g. sent a data "
                    "question to Slide Maker)." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def _has_routing_decision(self, test_case: LLMTestCase) -> bool:
        """A routing decision occurred if delegation is present OR tool calls were made.

        A trace with no delegation and no tool calls (e.g. a greeting) had no
        routing decision to evaluate — the agent just responded directly without
        invoking anything.
        """
        metadata = cast(TraceMetadata, test_case.metadata)
        if metadata.get("delegation"):
            return True
        return bool(metadata.get("tool_calls"))

    def measure(self, test_case: LLMTestCase) -> float:
        if not self._has_routing_decision(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No routing decision in this trace (no delegation, no tool calls) — SKIPPED"
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
        if not self._has_routing_decision(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No routing decision in this trace (no delegation, no tool calls) — SKIPPED"
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
        return "Routing Accuracy"

    def is_successful(self) -> bool:
        return self.success is True


class DirectHandleRecognitionMetric(SyncBaseMetric):
    """Handles directly when no subagent fits?

    For queries annotated as direct-handle (expected_subagent=None),
    asserts that no delegation event occurred in the trace.
    Without annotations, skips.
    """

    async_mode = False

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        annotations = metadata.get("annotations", {})

        if "expected_subagent" not in annotations:
            self.score = 1.0
            self.skipped = True
            self.reason = "No expected_subagent annotated — SKIPPED"
            self.success = True
            return self.score or 0.0

        expected = annotations["expected_subagent"]

        if expected is not None:
            self.score = 1.0
            self.skipped = True
            self.reason = "Not a direct-handle case — SKIPPED"
            self.success = True
            return self.score or 0.0

        delegation = metadata.get("delegation")

        if delegation is None:
            self.score = 1.0
            self.reason = "Correctly handled directly without delegation"
        else:
            self.score = 0.0
            self.reason = f"Should have handled directly but delegated to '{delegation.get('target', '?')}'"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Direct Handle Recognition"

    def is_successful(self) -> bool:
        return self.success is True


# --- Model-graded metrics (GEval) ---
# Instantiated lazily via get_judge_metrics() to avoid requiring
# API keys at import time.


class DelegationQualityMetric(SyncBaseMetric):
    """Delegation Quality (span-aware wrapper for GEval).

    Extracts the delegation task message from the span tree and evaluates
    it with a GEval judge. If no delegation occurred, skips.
    """

    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Delegation Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the task description that the "
                    "orchestrator passes to its subagent.\n\n"
                    "The 'input' is the user's original request.\n"
                    "The 'actual_output' is the delegation "
                    "message/instruction sent to the "
                    "subagent.\n\n"
                    "Rate on four dimensions:\n"
                    "1. Clarity: Is the task description "
                    "unambiguous?\n"
                    "2. Comprehensiveness: Does it include all "
                    "necessary info (file names, "
                    "specific quantities, user constraints)?\n"
                    "3. Relevance: Does it faithfully represent "
                    "the user's request without "
                    "scope creep or narrowing?\n"
                    "4. Feasibility: Is the task achievable by "
                    "the target subagent?\n\n"
                    "Score 0.0 if critically deficient. "
                    "Score 0.5 if adequate. "
                    "Score 1.0 if excellent on all dimensions." + EVIDENCE_INSTRUCTION
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
        delegation = metadata.get("delegation")

        if not delegation or not delegation.get("task"):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation occurred or no task message found — SKIPPED"
            self.success = True
            return self.score or 0.0

        delegation_tc = LLMTestCase(
            input=test_case.input,
            actual_output=delegation["task"],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        geval.measure(delegation_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = f"[→ {delegation['target']}] {geval.reason}"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if not delegation or not delegation.get("task"):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation occurred or no task message found — SKIPPED"
            self.success = True
            return self.score or 0.0

        delegation_tc = LLMTestCase(
            input=test_case.input,
            actual_output=delegation["task"],
            metadata=test_case.metadata,
        )

        geval = self._get_geval()
        await geval.a_measure(delegation_tc)
        self.score = geval.score
        self.evaluation_cost = getattr(geval, "evaluation_cost", None)
        self.reason = f"[→ {delegation['target']}] {geval.reason}"
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Delegation Quality"

    def is_successful(self) -> bool:
        return self.success is True


class SynthesisFaithfulnessMetric(SyncBaseMetric):
    """Synthesis faithfulness — AC-ORCA-6.

    Does the orchestrator's response faithfully represent what the subagent
    returned? Uses test_case.context (subagent output) as retrieval_context
    for DeepEval's built-in FaithfulnessMetric.
    Skips if no subagent output is available.
    """

    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = FaithfulnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        subagent_output = test_case.context[0] if test_case.context else ""

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "No subagent output available for faithfulness check — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        if not test_case.actual_output or not test_case.actual_output.strip():
            self.score = 1.0
            self.skipped = True
            self.reason = "Empty actual_output — no Orca response to evaluate — SKIPPED"
            self.success = True
            return self.score or 0.0

        synthesis_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                retrieval_context=[subagent_output],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(synthesis_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Synthesis Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True


class ClarificationJudgementMetric(SyncBaseMetric):
    """Asks when ambiguous, skips when clear?

    Extract+judge: given annotation of whether the query is ambiguous or clear,
    checks whether Orca's behaviour matches (clarify for ambiguous, proceed for clear).
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
                name="Clarification Judgement",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator correctly "
                    "judged whether to ask for "
                    "clarification or proceed directly.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is what the orchestrator "
                    "did (asked a question or proceeded).\n\n"
                    "A good orchestrator:\n"
                    "- Asks for clarification when the request "
                    "has multiple valid interpretations\n"
                    "- Proceeds directly when intent is clear "
                    "and unambiguous\n"
                    "- Does NOT ask unnecessary clarifications "
                    "for clear requests\n"
                    "- Does NOT barrel ahead on genuinely "
                    "ambiguous requests\n\n"
                    "Score 1.0 if the clarification decision "
                    "was correct. "
                    "Score 0.5 if borderline (request was "
                    "somewhat ambiguous and agent's choice "
                    "was defensible). "
                    "Score 0.0 if clearly wrong (asked when "
                    "obvious, or proceeded when genuinely "
                    "ambiguous)." + EVIDENCE_INSTRUCTION
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
        return "Clarification Judgement"

    def is_successful(self) -> bool:
        return self.success is True


class RedelegationOnFailureMetric(SyncBaseMetric):
    """Re-delegates or tries different subagent after bad output?

    Extract+judge: checks whether Orca re-delegated when subagent output was poor.
    Skips if no delegation occurred or subagent output looks fine.
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
                name="Re-delegation on Failure",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "appropriately handled a subagent's "
                    "poor or incomplete output.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "final response.\n"
                    "The 'context' contains the subagent's raw "
                    "output.\n\n"
                    "Check:\n"
                    "1. Was the subagent output actually "
                    "deficient (off-topic, incomplete, "
                    "wrong)?\n"
                    "2. If yes, did the orchestrator detect the "
                    "problem?\n"
                    "3. Did it re-delegate, try a different "
                    "approach, or supplement the output?\n\n"
                    "Score 1.0 if subagent output was good (no "
                    "recovery needed), or if the "
                    "orchestrator correctly detected and "
                    "recovered from bad output. "
                    "Score 0.5 if it partially recovered "
                    "(noted issues but still passed through "
                    "flawed content). "
                    "Score 0.0 if it blindly relayed clearly "
                    "deficient subagent output." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        subagent_output = test_case.context[0] if test_case.context else ""

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = "No subagent output to evaluate recovery — SKIPPED"
            self.success = True
            return self.score or 0.0

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
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
        subagent_output = test_case.context[0] if test_case.context else ""

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = "No subagent output to evaluate recovery — SKIPPED"
            self.success = True
            return self.score or 0.0

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
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
        return "Re-delegation on Failure"

    def is_successful(self) -> bool:
        return self.success is True


class GapAcknowledgementMetric(SyncBaseMetric):
    """Gaps in subagent output explicitly noted?

    Extract+judge: checks whether Orca acknowledges gaps/uncertainties in
    the subagent's response rather than silently passing them through.
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
                name="Gap Acknowledgement",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "acknowledges gaps or uncertainties "
                    "in the subagent's output.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "final response.\n"
                    "The 'context' contains the subagent's raw "
                    "output.\n\n"
                    "Check:\n"
                    "1. Are there gaps in the subagent output "
                    "(missing data, unanswered parts, "
                    "hedged conclusions, caveats)?\n"
                    "2. If yes, does the orchestrator explicitly "
                    "acknowledge them to the user?\n"
                    "3. Does it avoid presenting incomplete "
                    "information as if it were complete?\n\n"
                    "Score 1.0 if no gaps exist or all gaps are "
                    "acknowledged. "
                    "When scoring 1.0, state ONLY: "
                    "'No unacknowledged gaps detected.' "
                    "Do not describe what the response "
                    "covered.\n"
                    "Score 0.5 if some gaps noted but others "
                    "silently ignored — "
                    "quote the ignored gap.\n"
                    "Score 0.0 if obvious gaps passed through "
                    "without mention — "
                    "quote the gap and the point where "
                    "acknowledgement was missing." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.CONTEXT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        subagent_output = test_case.context[0] if test_case.context else ""

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = "No subagent output to check for gaps — SKIPPED"
            self.success = True
            return self.score or 0.0

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
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
        subagent_output = test_case.context[0] if test_case.context else ""

        if not subagent_output:
            self.score = 1.0
            self.skipped = True
            self.reason = "No subagent output to check for gaps — SKIPPED"
            self.success = True
            return self.score or 0.0

        judge_tc = LLMTestCase(
            input=test_case.input,
            actual_output=test_case.actual_output,
            context=[subagent_output],
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
        return "Gap Acknowledgement"

    def is_successful(self) -> bool:
        return self.success is True


class ChatbotResponseQualityMetric(SyncBaseMetric):
    """Direct response helpful, appropriate tone, and concise?

    Full judge: evaluates Orca's quality when handling requests directly
    (no delegation). Skips if delegation occurred.
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
                name="Chatbot Response Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the orchestrator's direct response "
                    "(no subagent was used).\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "direct response.\n\n"
                    "Rate on three dimensions:\n"
                    "1. Helpful: Does it actually answer the "
                    "question or address the need?\n"
                    "2. Tone: Is the tone appropriate "
                    "(professional, friendly, matches "
                    "context)?\n"
                    "3. Concise: Is it appropriately brief "
                    "without being curt?\n\n"
                    "Score 1.0 if excellent on all dimensions. "
                    "Score 0.5 if helpful but verbose, or "
                    "concise but off-tone. "
                    "Score 0.0 if unhelpful, inappropriate, "
                    "or incomprehensible." + EVIDENCE_INSTRUCTION
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
        delegation = metadata.get("delegation")

        if delegation and delegation.get("target"):
            self.score = 1.0
            self.skipped = True
            self.reason = "Delegation occurred (not a direct-handle case) — SKIPPED"
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
        delegation = metadata.get("delegation")

        if delegation and delegation.get("target"):
            self.score = 1.0
            self.skipped = True
            self.reason = "Delegation occurred (not a direct-handle case) — SKIPPED"
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
        return "Chatbot Response Quality"

    def is_successful(self) -> bool:
        return self.success is True


class DecompositionQualityMetric(SyncBaseMetric):
    """Multi-intent request correctly decomposed into sub-tasks?

    Extract+judge: evaluates whether Orca correctly identifies and orders
    sub-tasks from a multi-intent request.
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
                name="Decomposition Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate how well the orchestrator "
                    "decomposed a multi-intent request.\n\n"
                    "The 'input' is the user's request "
                    "containing multiple intents.\n"
                    "The 'actual_output' is the orchestrator's "
                    "response showing how it handled the "
                    "request.\n\n"
                    "Check:\n"
                    "1. Were all distinct intents identified? "
                    "(no intent missed)\n"
                    "2. Were they ordered logically? "
                    "(dependencies respected — e.g. analyse "
                    "before present)\n"
                    "3. Were they executed appropriately? "
                    "(right subagent for each, or direct "
                    "handle)\n\n"
                    "Score 1.0 if all intents captured and "
                    "logically ordered. "
                    "Score 0.5 if intents captured but ordering "
                    "suboptimal. "
                    "Score 0.0 if an intent was missed entirely "
                    "or ordering is clearly wrong. "
                    "If the request has only one intent, "
                    "score 1.0." + EVIDENCE_INSTRUCTION
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
        return "Decomposition Quality"

    def is_successful(self) -> bool:
        return self.success is True


class AgentStatusCommunicationMetric(SyncBaseMetric):
    """User informed which agent is handling their request?

    Code grader: checks that when delegation occurs, the output mentions
    the agent name or type being used.
    """

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")
        metadata.get("chat_metadata") or OrcaChatMetadata()

        if not delegation or not delegation.get("target"):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation occurred — SKIPPED"
            self.success = True
            return self.score or 0.0

        target = delegation["target"]
        output_lower = (test_case.actual_output or "").lower()

        agent_names = [
            target.lower(),
            target.replace("_", " ").lower(),
            target.replace("-", " ").lower(),
        ]

        mentioned = any(name in output_lower for name in agent_names)

        if mentioned:
            self.score = 1.0
            self.reason = f"Agent '{target}' mentioned in response"
        else:
            self.score = 0.0
            self.reason = f"Agent '{target}' was used but not mentioned in the response"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Agent Status Communication"

    def is_successful(self) -> bool:
        return self.success is True


# Canonical agent type fragments and the key they map to — same taxonomy as the adapter.
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
    metadata = cast(TraceMetadata, test_case.metadata)
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


class FindingDeduplicationMetric(SyncBaseMetric):
    """No finding redundantly stated across multi-agent synthesis?

    Extract+judge: checks whether the final response contains redundant
    restatements of the same finding. Skips short responses and single-agent traces.
    """

    MIN_OUTPUT_LENGTH = 400

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _should_skip(self, test_case: LLMTestCase):
        output_len = len(test_case.actual_output or "")
        if not _is_multi_agent_trace(test_case):
            return "Single-agent or direct response (dedup N/A)"
        if output_len < self.MIN_OUTPUT_LENGTH:
            return f"Response too short ({output_len} chars) for meaningful dedup check"
        return None

    def _get_geval(self):
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

    def measure(self, test_case: LLMTestCase) -> float:
        skip_reason = self._should_skip(test_case)
        if skip_reason:
            self.score = 1.0
            self.skipped = True
            self.reason = f"{skip_reason} — SKIPPED"
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
        skip_reason = self._should_skip(test_case)
        if skip_reason:
            self.score = 1.0
            self.skipped = True
            self.reason = f"{skip_reason} — SKIPPED"
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
        return "Finding Deduplication"

    def is_successful(self) -> bool:
        return self.success is True


class FindingConsistencyMetric(SyncBaseMetric):
    """No contradictions in multi-agent synthesis?

    Extract+judge: checks whether the final response contains conflicting statements.
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
                name="Finding Consistency",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator's "
                    "response contains contradictions.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "synthesized response.\n\n"
                    "Check:\n"
                    "1. Are there any statements that "
                    "contradict each other?\n"
                    "2. If conflicting information exists, is "
                    "it explicitly flagged or resolved?\n"
                    "3. Are numbers, dates, or claims "
                    "consistent throughout?\n\n"
                    "Score 1.0 if fully consistent (no "
                    "contradictions). "
                    "Score 0.5 if a minor inconsistency exists "
                    "but is flagged. "
                    "Score 0.0 if clear contradictions are "
                    "present and unresolved." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if not _is_multi_agent_trace(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Single-agent or direct response (consistency N/A) — SKIPPED"
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
        metadata.get("chat_metadata") or OrcaChatMetadata()
        metadata.get("delegation")

        if not _is_multi_agent_trace(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Single-agent or direct response (consistency N/A) — SKIPPED"
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
        return "Finding Consistency"

    def is_successful(self) -> bool:
        return self.success is True


class CapabilityHonestyMetric(SyncBaseMetric):
    """Acknowledges limitations rather than fabricating capabilities?

    Full judge: checks that Orca doesn't claim it can do things beyond
    its available subagents.
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
                name="Capability Honesty",
                model=_get_judge_model(),
                criteria=(
                    "You are evaluating whether an AI agent "
                    "honestly represents its capabilities.\n\n"
                    "AGENT CONTEXT (what this agent can "
                    "actually do):\n"
                    "---\n"
                    f"{SYSTEM_PROMPT_SUMMARY}\n"
                    "---\n\n"
                    "AVAILABLE TOOLS AND SUBAGENTS:\n"
                    "---\n"
                    f"{TOOL_MANIFEST}\n"
                    "---\n\n"
                    "CRITICAL: The subagents listed above "
                    "(Data Analyst, Slide Maker, Slide "
                    "Reviewer, Text Analyst) are REAL and "
                    "EXIST. The agent referencing them, "
                    "delegating to them, or mentioning their "
                    "outputs is CORRECT BEHAVIOUR, not "
                    "fabrication. They may present forms to "
                    "gather configuration before executing. "
                    "This is normal workflow.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the agent's "
                    "response.\n\n"
                    "EVALUATION CRITERIA:\n"
                    "Only flag as dishonest if the agent:\n"
                    "1. Claims to have done something that NO "
                    "tool in the manifest could do "
                    "(e.g. claims to send an email when no "
                    "email tool exists)\n"
                    "2. Claims a specific file/artifact exists "
                    "that was never created by any "
                    "tool call (hallucinated output path)\n"
                    "3. Refuses something it clearly CAN do "
                    "per the manifest (false refusal)\n\n"
                    "Do NOT flag as dishonest:\n"
                    "- Mentioning Data Analyst, Slide Maker, "
                    "Slide Reviewer, or Text Analyst "
                    "(these are real subagents)\n"
                    "- Saying 'I'll hand this to the Data "
                    "Analyst' (this is delegation)\n"
                    "- Presenting a form for user input "
                    "(this is standard workflow)\n"
                    "- Describing what a subagent produced "
                    "(this is synthesis)\n\n"
                    "Score 1.0 if the agent's representation "
                    "of its capabilities is honest. "
                    "When scoring 1.0, state ONLY: "
                    "'No capability fabrication or false "
                    "refusal detected.' "
                    "Do NOT describe what the agent did well "
                    "— this metric only fires on "
                    "violations.\n"
                    "Score 0.0 ONLY if the agent fabricates a "
                    "capability that genuinely does not "
                    "exist in the manifest, or hallucinates "
                    "a specific artifact path. "
                    "When scoring 0.0, quote the specific "
                    "fabricated claim." + EVIDENCE_INSTRUCTION
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
        return "Capability Honesty"

    def is_successful(self) -> bool:
        return self.success is True


class CrossAgentContextRetentionMetric(SyncBaseMetric):
    """Context preserved across subagent invocations?

    Code grader: checks that multi-turn conversations maintain context
    by looking at whether spoke_context carries over and is not
    redundantly re-asked.
    """

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        chat_meta: OrcaChatMetadata = (
            metadata.get("chat_metadata") or OrcaChatMetadata()
        )
        spoke_context = metadata.get("spoke_context") or {}
        clarifications = metadata.get("clarification_requests", [])

        num_history = chat_meta.num_history_messages

        if num_history == 0:
            self.score = 1.0
            self.skipped = True
            self.reason = (
                "First message in session (no prior context to retain) — SKIPPED"
            )
            self.success = True
            return self.score or 0.0

        if spoke_context:
            cached_values = set(str(v).lower() for v in spoke_context.values() if v)
            redundant = 0
            for c in clarifications:
                q_text = str(c.output or c.input or "").lower()
                for val in cached_values:
                    if val and len(val) > 3 and val in q_text:
                        redundant += 1
                        break

            if redundant > 0:
                self.score = 0.0
                self.reason = f"{redundant} re-ask(s) for info already in spoke_context from prior turn"
            else:
                self.score = 1.0
                self.reason = f"Context retained across turns (spoke_context has {len(spoke_context)} keys, no re-asks)"
        else:
            self.score = 1.0
            self.reason = f"Multi-turn conversation (history={num_history}), no spoke_context but no redundant asks"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Cross-Agent Context Retention"

    def is_successful(self) -> bool:
        return self.success is True


class FollowUpRelevanceMetric(SyncBaseMetric):
    """Follow-up suggestions relevant and actionable?

    Full judge: evaluates the quality of follow-up suggestions offered
    at the end of a completed task. Skips mid-flow turns (form presentations,
    job submissions, status updates) where follow-ups are not expected.
    """

    MIDFLOW_SIGNALS = [
        "form",
        "fill in",
        "fill out",
        "please fill",
        "pick a",
        "is now running",
        "job submitted",
        "track progress",
    ]

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _is_midflow_response(self, test_case: LLMTestCase) -> bool:
        output_lower = (test_case.actual_output or "").lower()
        return any(signal in output_lower for signal in self.MIDFLOW_SIGNALS)

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Follow-Up Relevance",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the follow-up suggestions the "
                    "orchestrator offers after completing a "
                    "task.\n\n"
                    "The 'input' is the user's original "
                    "request.\n"
                    "The 'actual_output' is the orchestrator's "
                    "response (look for follow-up suggestions "
                    "at the end — questions, next steps, or "
                    "related actions offered to the user).\n\n"
                    "Check:\n"
                    "1. Are follow-up suggestions present?\n"
                    "2. Are they relevant to what was just "
                    "accomplished (not generic)?\n"
                    "3. Are they actionable (user could "
                    "actually do them as a next step)?\n\n"
                    "Score 1.0 if follow-ups are relevant and "
                    "actionable. "
                    "Score 0.7 if the task is clearly complete "
                    "and no follow-ups are needed "
                    "(simple confirmations, status updates). "
                    "Score 0.5 if present but generic ('let me "
                    "know if you need anything else'). "
                    "Score 0.0 ONLY if the response delivers "
                    "substantial results (analysis, report, "
                    "findings) but offers zero guidance on "
                    "what to do next, AND the user would "
                    "clearly benefit from suggestions." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        if self._is_midflow_response(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Mid-flow response (form/status/job submission) — follow-ups not expected — SKIPPED"
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
        if self._is_midflow_response(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "Mid-flow response (form/status/job submission) — follow-ups not expected — SKIPPED"
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
        return "Follow-Up Relevance"

    def is_successful(self) -> bool:
        return self.success is True


class DelegationArgumentCorrectnessMetric(SyncBaseMetric):
    """Delegation argument correctness — new metric.

    Uses DeepEval's built-in ArgumentCorrectnessMetric (referenceless LLM judge)
    to check whether the arguments Orca passed to delegate_task_to_member correctly
    reflect the user's intent. Skips if no delegation occurred.

    Constructs a synthetic ToolCall from delegation metadata so ArgumentCorrectness
    can evaluate the call without requiring @observe tracing.
    """

    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = _ArgumentCorrectnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(TraceMetadata, test_case.metadata)
        delegation = metadata.get("delegation")

        if not delegation or not delegation.get("task"):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation occurred — SKIPPED"
            self.success = True
            return self.score or 0.0

        tool_call = ToolCall(
            name="delegate_task_to_member",
            input_parameters={
                "target": delegation.get("target", ""),
                "task": delegation.get("task", ""),
            },
        )

        arg_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                tools_called=[tool_call],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(arg_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Delegation Argument Correctness"

    def is_successful(self) -> bool:
        return self.success is True


def get_judge_metrics():
    """Return all Orca metrics (code + judge).

    Call only when you have API keys configured.
    """
    return (
        DelegationQualityMetric(),
        SynthesisFaithfulnessMetric(),
        ClarificationJudgementMetric(),
        RedelegationOnFailureMetric(),
        GapAcknowledgementMetric(),
        ChatbotResponseQualityMetric(),
        DecompositionQualityMetric(),
        FindingDeduplicationMetric(),
        FindingConsistencyMetric(),
        CapabilityHonestyMetric(),
        FollowUpRelevanceMetric(),
    )
