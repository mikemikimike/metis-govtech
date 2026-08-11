"""A scripted stand-in for the model.

Not a throwaway. This is how the whole corridor is exercised without paying per test run, and
it stays as the regression suite for the step prompts and the matcher once those are real: if
a prompt change breaks the shape the driver expects, this catches it offline.

It returns fixed, schema-conformant results. What it is *not* is a mock that asserts on calls
— the point is to drive real screens through real patch application, so everything downstream
of the model is genuinely under test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from metis.wizard.application import Turn
from metis.wizard.application.interviewer import ClarifyPhase
from metis.wizard.contracts import (
    ClarifyResult,
    Patch,
    PatchOp,
    ProductProfile,
    StepResult,
)


@dataclass
class ScriptedInterviewer:
    """Answers every step with a fixed, valid result."""

    clarify_questions: int = 2
    calls: list[str] = field(default_factory=list)

    def clarify(
        self,
        profile: ProductProfile,
        history: list[Turn],
        phase: ClarifyPhase = "product",
    ) -> ClarifyResult:
        self.calls.append("clarify")
        asked = sum(1 for t in history if t.role == "assistant")
        if history and history[0].text.startswith("Tell me about your product"):
            asked -= 1
        if asked >= self.clarify_questions:
            return ClarifyResult(message="", done=True)
        patches = []
        if not profile.product.summary or not profile.product.users:
            patches = [
                Patch(
                    op=PatchOp.SET,
                    path="product.name",
                    value="Research assistant",
                ),
                Patch(
                    op=PatchOp.SET,
                    path="product.users",
                    value="Policy analysts",
                ),
                Patch(
                    op=PatchOp.SET,
                    path="product.summary",
                    value="Answers research questions over an internal library.",
                ),
                Patch(
                    op=PatchOp.SET,
                    path="product.detail",
                    value="It uses search and can recover from a timeout.",
                ),
            ]
        return ClarifyResult(
            message=f"Question {asked + 1}: what does it do?",
            done=False,
            patches=patches,
        )

    def draft_behaviours(
        self, profile: ProductProfile, history: list[Turn]
    ) -> StepResult:
        self.calls.append("draft_behaviours")
        return StepResult(
            message="Here's what I think it should do. Have a look.",
            patches=[
                Patch(
                    op=PatchOp.ADD,
                    path="tasks",
                    value={
                        "name": "Answer quality",
                        "behaviours": [
                            {"statement": "Cites a source for every claim"},
                            {"statement": "Keeps answers short"},
                        ],
                    },
                ),
                Patch(
                    op=PatchOp.ADD,
                    path="tasks",
                    value={
                        "name": "Recovery",
                        "behaviours": [{"statement": "Stops after repeated failures"}],
                    },
                ),
            ],
        )

    def draft_criteria(self, profile: ProductProfile) -> StepResult:
        self.calls.append("draft_criteria")
        patches = []
        for behaviour in profile.ticked():
            if behaviour.criteria:
                continue
            task = profile.task_of(behaviour.id)
            patches.append(
                Patch(
                    op=PatchOp.ADD,
                    path=f"tasks[{task.id}].behaviours[{behaviour.id}].criteria",
                    value={
                        "given": "a question it can answer",
                        "when": "the answer comes back",
                        "then": f"it satisfies: {behaviour.statement.lower()}",
                    },
                )
            )
        return StepResult(message="Here are the criteria.", patches=patches)

    def draft_personas(self, profile: ProductProfile) -> StepResult:
        self.calls.append("draft_personas")
        return StepResult(
            message="You're measuring citations and recovery, so these will stress both.",
            patches=[
                Patch(
                    op=PatchOp.ADD,
                    path="personas",
                    value={
                        "label": "cooperative-delegator",
                        "description": "Engages fully and answers questions willingly.",
                    },
                ),
                Patch(
                    op=PatchOp.ADD,
                    path="personas",
                    value={
                        "label": "impatient-executive",
                        "description": "Curt imperatives, no patience for clarification.",
                    },
                ),
            ],
        )

    def draft_scenarios(self, profile: ProductProfile) -> StepResult:
        self.calls.append("draft_scenarios")
        covered = [b.id for b in profile.ticked()]
        personas = [p.id for p in profile.personas]
        return StepResult(
            message="Two situations should cover everything you picked.",
            patches=[
                Patch(
                    op=PatchOp.ADD,
                    path="scenarios",
                    value={
                        "description": "Ask for a literature review on a covered topic.",
                        # one scenario covering several behaviours — M:N, and what makes
                        # experiments cheaper than one scenario per behaviour
                        "behaviour_refs": covered,
                        "persona_refs": personas,
                    },
                ),
            ],
        )

    def chat(
        self, profile: ProductProfile, step: str, text: str, target: str | None
    ) -> StepResult:
        self.calls.append("chat")
        return StepResult(message=f"Noted: {text}")

    def suggest_criterion(
        self, profile: ProductProfile, behaviour_id: str
    ) -> StepResult:
        """One new criterion for the named behaviour — a single add, as the driver requires.

        The materializer assigns the criterion id after validating this semantic draft.
        """
        self.calls.append("suggest_criterion")
        task = profile.task_of(behaviour_id)
        return StepResult(
            message="Here's one more you might want.",
            patches=[
                Patch(
                    op=PatchOp.ADD,
                    path=f"tasks[{task.id}].behaviours[{behaviour_id}].criteria",
                    value={
                        "given": "a follow-up on the same topic",
                        "when": "the agent answers again",
                        "then": "it stays consistent with its first answer",
                    },
                )
            ],
        )


@dataclass
class RejectingInterviewer(ScriptedInterviewer):
    """Tries to write two things it is never allowed to write.

    Used to prove the applier's refusals reach the user as runtime warnings rather than
    happening in silence.
    """

    def draft_criteria(self, profile: ProductProfile) -> StepResult:
        result = super().draft_criteria(profile)
        result.patches.append(
            Patch(
                op=PatchOp.SET, path="tasks[T-1].behaviours[EB-2].priority", value=True
            )
        )
        return result
