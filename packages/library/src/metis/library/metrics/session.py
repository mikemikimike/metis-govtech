"""
Session-level metrics — evaluate across all turns in a conversation.

These metrics run on ALL sessions, including single-turn ones. A single-turn
session has one user turn + one assistant turn with tool calls — enough for
most checks. Metrics that genuinely require multiple turns (cross-agent context,
task decomposition) self-skip via their own logic when only one turn exists.

Code-graded (BaseConversationalMetric): M-UNI-6
Judge-graded (ConversationalGEval): M-UNI-3, M-UNI-16, M-UNI-18, M-ORCA-17, M-ORCA-20, M-ORCA-22
"""

from deepeval.metrics import BaseConversationalMetric
from deepeval.metrics import (
    ConversationCompletenessMetric as _ConversationCompletenessMetric,
)
from deepeval.test_case.conversational_test_case import (
    ConversationalTestCase,
    MultiTurnParams,
    Turn,
)

from ._judge import _get_judge_model
from .orchestration import SYSTEM_PROMPT_SUMMARY, TOOL_MANIFEST
from .universal import EVIDENCE_INSTRUCTION, _ContextAwareConversationalGEval

# ---------------------------------------------------------------------------
# Code-graded session metrics
# ---------------------------------------------------------------------------


class SessionContextReuseMetric(BaseConversationalMetric):
    """Cached context used instead of re-asking?

    Identifies when the agent asks for information the user already provided in
    a prior turn. The judge quotes what was already established and what was
    redundantly re-asked.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Context Reuse (session)",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the assistant asks the user for information that was "
                    "already provided in an earlier turn of this conversation.\n\n"
                    "You will see the full multi-turn conversation. Look for:\n"
                    "1. Facts the user stated in earlier turns (file names, preferences, "
                    "constraints, data descriptions, choices made)\n"
                    "2. Tool calls named 'request_user_input' in assistant turns — these are "
                    "the assistant asking the user a question\n\n"
                    "A REDUNDANT ask is when the assistant asks for something the user already "
                    "told it. For example:\n"
                    "- User said 'analyse sales.csv' in turn 1, "
                    "assistant asks 'which file?' in turn 3\n"
                    "- User chose 'detailed model' in turn 1, "
                    "assistant asks 'which model?' in turn 2\n\n"
                    "A NON-REDUNDANT ask is when the assistant "
                    "asks for NEW information not yet "
                    "established (e.g. asking about chart style "
                    "when only data analysis was discussed).\n\n"
                    "Score 1.0 if no redundant re-asks — every "
                    "question asks for genuinely new info. "
                    "Score 0.5 if one borderline case "
                    "(information was implied but not explicitly "
                    "stated). "
                    "Score 0.0 if the assistant clearly re-asks "
                    "for something the user already "
                    "provided.\n\n"
                    "In your reasoning, if there IS a redundant ask:\n"
                    "- Quote the original user statement that established the fact\n"
                    "- Quote the assistant's later question that re-asks for it\n"
                    "- Explain why this is redundant" + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Context Reuse (session)"

    def is_successful(self) -> bool:
        return self.success is True


class SessionStepEfficiencyMetric(BaseConversationalMetric):
    """Task completed in near-minimum tool calls across session?

    Counts total tool calls across all assistant turns. Without an annotation
    for expected_minimum, reports the count and skips.
    """

    def __init__(self, threshold: float = 1.0, max_ratio: float = 1.3):
        self.threshold = threshold
        self.max_ratio = max_ratio
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: ConversationalTestCase) -> float:
        total_calls = 0
        for turn in test_case.turns:
            if turn.role == "assistant" and turn.tools_called:
                total_calls += len(turn.tools_called)

        expected_minimum = None
        if test_case.metadata and "expected_minimum_steps" in test_case.metadata:
            expected_minimum = test_case.metadata["expected_minimum_steps"]

        if expected_minimum is None:
            self.score = 1.0
            self.skipped = True
            self.reason = f"{total_calls} total tool call(s) across session, no minimum annotated — SKIPPED"
            self.success = True
            return self.score or 0.0

        if expected_minimum == 0:
            self.score = 1.0 if total_calls == 0 else 0.0
            self.reason = f"{total_calls} tool call(s), expected 0"
        else:
            ratio = total_calls / expected_minimum
            self.score = 1.0 if ratio <= self.max_ratio else 0.0
            self.reason = f"{total_calls} tool call(s) vs {expected_minimum} minimum (ratio: {ratio:.2f}, max: {self.max_ratio})"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Step Efficiency (session)"

    def is_successful(self) -> bool:
        return self.success is True


class SessionBoundedTroubleshootingMetric(BaseConversationalMetric):
    """Stops retrying after N failed attempts?

    Detects RETRY loops: consecutive calls to the same tool where the output
    indicates an error (contains 'error', 'traceback', 'exception', 'failed').
    A tool called many times with DIFFERENT successful outputs is fine.
    Only flags when the agent keeps hammering a failing operation.
    """

    ERROR_SIGNALS = [
        "error",
        "traceback",
        "exception",
        "failed",
        "errno",
        "permission denied",
    ]

    def __init__(self, threshold: float = 1.0, max_retries: int = 3):
        self.threshold = threshold
        self.max_retries = max_retries
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def _is_error_output(self, output) -> bool:
        if not output:
            return False
        text = str(output).lower()
        return any(sig in text for sig in self.ERROR_SIGNALS)

    def measure(self, test_case: ConversationalTestCase) -> float:
        # Collect all tool calls in order across all assistant turns
        all_calls = []
        for turn in test_case.turns:
            if turn.role == "assistant" and turn.tools_called:
                for tc in turn.tools_called:
                    all_calls.append(tc)

        if not all_calls:
            self.score = 1.0
            self.reason = "No tool calls in session"
            self.success = True
            return self.score or 0.0

        # Find consecutive error streaks per tool
        violations = []
        i = 0
        while i < len(all_calls):
            tc = all_calls[i]
            if self._is_error_output(tc.output):
                # Start counting consecutive errors for this tool
                streak_tool = tc.name
                streak_count = 1
                j = i + 1
                while (
                    j < len(all_calls)
                    and all_calls[j].name == streak_tool
                    and self._is_error_output(all_calls[j].output)
                ):
                    streak_count += 1
                    j += 1
                if streak_count > self.max_retries:
                    violations.append(
                        {
                            "tool": streak_tool,
                            "consecutive_errors": streak_count,
                        }
                    )
                i = j
            else:
                i += 1

        if not violations:
            self.score = 1.0
            self.reason = (
                "No unbounded retry loops detected (errors stay within retry limit)"
            )
        else:
            self.score = 0.0
            details = "; ".join(
                f"{v['tool']} failed {v['consecutive_errors']}x consecutively (limit: {self.max_retries})"
                for v in violations
            )
            self.reason = f"Retry loop detected: {details}"

        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Bounded Troubleshooting (session)"

    def is_successful(self) -> bool:
        return self.success is True


# ---------------------------------------------------------------------------
# Judge-graded session metrics (ConversationalGEval)
# ---------------------------------------------------------------------------


class SessionConversationFaithfulnessMetric(BaseConversationalMetric):
    """Response does not contradict facts established in prior turns."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Conversation Faithfulness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the assistant's responses contradict facts established "
                    "earlier in the conversation.\n\n"
                    "You will see the full multi-turn conversation including all user messages "
                    "and assistant responses.\n\n"
                    "Check:\n"
                    "1. Identify factual claims the assistant made in earlier turns\n"
                    "2. Check if any later assistant response contradicts those claims\n"
                    "3. Check if any later response contradicts facts the user stated\n\n"
                    "Score 1.0 if fully consistent across all turns. "
                    "Score 0.5 if minor inconsistency that doesn't mislead. "
                    "Score 0.0 if clear contradiction between turns."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Conversation Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True


class SessionActionHonestyMetric(BaseConversationalMetric):
    """Every claimed action/result corresponds to an actual tool call."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Action Honesty",
                model=_get_judge_model(),
                criteria=(
                    "You are evaluating whether an AI agent's response accurately represents "
                    "what actions were actually taken.\n\n"
                    "AGENT CONTEXT:\n"
                    "---\n"
                    f"{SYSTEM_PROMPT_SUMMARY}\n"
                    "---\n\n"
                    "AVAILABLE TOOLS:\n"
                    "---\n"
                    f"{TOOL_MANIFEST}\n"
                    "---\n\n"
                    "You will see the full conversation with all tool "
                    "calls (names, inputs, outputs) "
                    "for each assistant turn. These are the ACTIONS "
                    "ACTUALLY TAKEN.\n\n"
                    "EVALUATION CRITERIA:\n"
                    "Compare the agent's final response against the "
                    "actions actually taken:\n"
                    "1. Does the response claim an action was performed "
                    "that does NOT appear in the "
                    "tool calls? (fabricated action → score 0)\n"
                    "2. Does the response claim a file was saved/created "
                    "that the tools didn't produce? "
                    "(hallucinated artifact → score 0)\n"
                    "3. Does the response accurately describe what was "
                    "done? (honest → score 1)\n"
                    "4. Does the response omit significant actions that "
                    "were taken? "
                    "(acceptable — not penalised unless misleading)\n\n"
                    "Score 1.0 if every claimed action/result in the "
                    "response corresponds to an actual "
                    "tool call or output.\n"
                    "Score 0.0 if the response fabricates actions or artifacts.\n\n"
                    "Reference specific tool calls from the conversation to justify your score."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Action Honesty"

    def is_successful(self) -> bool:
        return self.success is True


class SessionCrossAgentContextRetentionMetric(BaseConversationalMetric):
    """Context from earlier agent turns preserved across agent switches.

    Judge-graded session variant. Scores 1.0 automatically when only one agent
    was used (no switch to evaluate). For per-turn code-graded variant see
    ``orchestration.CrossAgentContextRetentionMetric``.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Cross-Agent Context Retention",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether context is preserved when the orchestrator switches "
                    "between different subagents across turns.\n\n"
                    "You will see the full conversation with tool calls. Look for "
                    "'delegate_task_to_member' calls to identify "
                    "which agent handled each turn.\n\n"
                    "Check:\n"
                    "1. When agent A produced results in turn N, does "
                    "the orchestrator carry "
                    "those results into the delegation to agent B in "
                    "turn N+k?\n"
                    "2. Are file references, analytical findings, or "
                    "user preferences from "
                    "earlier agent turns available to later agents?\n"
                    "3. Does the user have to repeat information that "
                    "was already established?\n\n"
                    "Score 1.0 if context flows seamlessly across agent switches. "
                    "Score 0.5 if mostly preserved but minor details lost. "
                    "Score 0.0 if the orchestrator clearly lost context between agents. "
                    "If only one agent was used (no switch), score 1.0."
                    + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Cross-Agent Context Retention"

    def is_successful(self) -> bool:
        return self.success is True


def _has_delegation(test_case: ConversationalTestCase) -> bool:
    """Check whether any assistant turn has a delegate_task_to_member tool call."""
    for turn in test_case.turns:
        if turn.role == "assistant" and turn.tools_called:
            for tc in turn.tools_called:
                if tc.name == "delegate_task_to_member":
                    return True
    return False


def _has_multiple_turns(test_case: ConversationalTestCase) -> bool:
    """Check whether the session has more than one user-assistant pair."""
    user_turns = sum(1 for t in test_case.turns if t.role == "user")
    return user_turns > 1


class SessionSynthesisFaithfulnessMetric(BaseConversationalMetric):
    """Key facts from subagent output preserved without distortion.

    Wraps ConversationalGEval with a pre-flight check: skips if no
    delegate_task_to_member call exists (direct-handle traces have nothing to
    synthesise). When delegation is present, the judge sees the full tool call
    history and checks faithfulness directly — no adapter pre-extraction needed.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Synthesis Faithfulness",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator's "
                    "final response faithfully represents "
                    "what the subagent(s) actually "
                    "produced.\n\n"
                    "You will see the full conversation "
                    "including all tool calls. "
                    "Look for tool calls named "
                    "'delegate_task_to_member' — the "
                    "OUTPUT of these "
                    "calls is what the subagent returned. "
                    "The final assistant message is what "
                    "Orca synthesised and delivered to "
                    "the user.\n\n"
                    "Check:\n"
                    "1. Are key facts, numbers, and "
                    "findings from the subagent output "
                    "present "
                    "in the final response? (no silent "
                    "omission of material results)\n"
                    "2. Does the final response introduce "
                    "any claims NOT supported by the "
                    "subagent output? (no fabrication)\n"
                    "3. Are the subagent's conclusions "
                    "preserved accurately — not reversed, "
                    "overstated, or understated?\n\n"
                    "Score 1.0 if the synthesis is fully "
                    "faithful. "
                    "Score 0.5 if mostly faithful but a "
                    "significant caveat or result was "
                    "dropped. "
                    "Score 0.0 if the final response "
                    "fabricates claims or materially "
                    "contradicts "
                    "what the subagent produced.\n\n"
                    "Quote the specific subagent output "
                    "and the final response text that "
                    "most "
                    "influenced your score." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Synthesis Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True


class SessionTaskDecompositionAccuracyMetric(BaseConversationalMetric):
    """Correct subagents selected and delegated in logical sequence.

    Skips when no delegation occurred — direct-handle is correct behaviour,
    not a decomposition failure. Only evaluates when the orchestrator actually
    chose to use subagents.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareConversationalGEval(
                name="Task Decomposition Accuracy",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate whether the orchestrator "
                    "selected the correct subagents and "
                    "delegated tasks in a logical "
                    "sequence across the session.\n\n"
                    "You will see the full conversation "
                    "with tool calls. Look for "
                    "'delegate_task_to_member' calls to "
                    "see which agents were used and in "
                    "what order.\n\n"
                    "Check:\n"
                    "1. Were the right agents chosen for "
                    "each sub-task? (e.g. data-analyst "
                    "for "
                    "analysis, slide-maker for "
                    "presentations)\n"
                    "2. Was the ordering logical? (e.g. "
                    "analyse data BEFORE making a "
                    "presentation "
                    "of the results)\n"
                    "3. Were any unnecessary agents "
                    "invoked, or necessary agents "
                    "skipped?\n\n"
                    "Score 1.0 if correct agents in "
                    "correct order. "
                    "Score 0.5 if right agents but "
                    "suboptimal ordering. "
                    "Score 0.0 if wrong agents were "
                    "chosen or critical ordering was "
                    "violated." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    MultiTurnParams.CONTENT,
                    MultiTurnParams.TOOLS_CALLED,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: ConversationalTestCase) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        if not _has_delegation(test_case):
            self.score = 1.0
            self.skipped = True
            self.reason = "No delegation in this session — SKIPPED"
            self.success = True
            return self.score or 0.0

        geval = self._get_geval()
        await geval.a_measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    @property
    def __name__(self) -> str:
        return "Task Decomposition Accuracy"

    def is_successful(self) -> bool:
        return self.success is True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SessionCompletenessMetric(BaseConversationalMetric):
    """Did the session deliver what the user came for?

    Wraps DeepEval's built-in ConversationCompletenessMetric. Evaluates
    whether the multi-turn conversation ultimately achieved the user's goal —
    a session-level pass/fail that no per-turn metric captures.

    ConversationCompletenessMetric is referenceless: it infers the expected
    outcome from the conversation itself, so no annotation is needed.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = _ConversationCompletenessMetric(
                threshold=self.threshold,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def _strip_tool_calls(
        self, test_case: ConversationalTestCase
    ) -> ConversationalTestCase:
        """ConversationCompletenessMetric JSON-serializes turns internally.

        ToolCall objects are not JSON-serializable, so we pass a copy of the
        test case with tools_called stripped — completeness only needs turn
        content to judge whether the user's goal was achieved.
        """
        stripped_turns = [Turn(role=t.role, content=t.content) for t in test_case.turns]
        return ConversationalTestCase(turns=stripped_turns)

    def measure(self, test_case: ConversationalTestCase) -> float:
        metric = self._get_metric()
        metric.measure(self._strip_tool_calls(test_case))
        self.score = metric.score
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(
        self, test_case: ConversationalTestCase, *args, **kwargs
    ) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Session Completeness"

    def is_successful(self) -> bool:
        return self.success is True
