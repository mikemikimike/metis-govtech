"""What the driver needs from a model, as an interface.

Two implementations exist: the real one over the gateway, and a scripted stand-in used by the
tests. The stand-in is not a throwaway — it is how the whole corridor is exercised without
paying per test run, and it stays as the regression suite for the prompts and the matcher.

Every method returns structured output. Nothing here returns prose the caller has to parse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from metis.wizard.contracts.interview_state import InterviewContext, Turn
    from metis.wizard.contracts.output import (
        ClarifyResult,
        CriterionConfiguration,
        StepResult,
    )
    from metis.wizard.domain.specification import Criterion, Specification


class InterviewerUnavailable(RuntimeError):
    """The configured interviewer cannot be constructed (usually missing credentials)."""


class InterviewerOutputError(RuntimeError):
    """An interviewer could not return a valid structured result after its retries."""


class InterviewContextBudgetError(InterviewerOutputError):
    """The full request does not fit the configured model context budget."""


class Interviewer(Protocol):
    """The model, from the driver's point of view."""

    def configure_criterion(
        self,
        criterion: Criterion,
        previous: Criterion | None,
        specification: Specification,
        request: str,
        context: InterviewContext | None = None,
    ) -> CriterionConfiguration:
        """Configure the matched assessment from its full requirement and current settings."""
        ...

    def clarify(
        self,
        specification: Specification,
        history: list[Turn],
        context: InterviewContext | None = None,
    ) -> ClarifyResult:
        """One open question, or done. The only step the model may end on its own."""
        ...

    def draft_behaviours(
        self,
        specification: Specification,
        history: list[Turn],
        context: InterviewContext | None = None,
    ) -> StepResult:
        """Features and behaviours. No criteria yet."""
        ...

    def draft_criteria(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        """Criteria for every ticked behaviour that lacks them, in one call."""
        ...

    def draft_personas(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        """Archetypes, justified by what the user chose to measure."""
        ...

    def draft_scenarios(
        self,
        specification: Specification,
        context: InterviewContext | None = None,
    ) -> StepResult:
        """The whole covering set, in one call."""
        ...

    def chat(
        self,
        specification: Specification,
        step: str,
        text: str,
        target: str | None,
        context: InterviewContext | None = None,
    ) -> StepResult:
        """A free-text exchange, answered with suggested edits as chips."""
        ...

    def suggest_criterion(
        self,
        specification: Specification,
        behaviour_id: str,
        context: InterviewContext | None = None,
    ) -> StepResult:
        """Exactly one new criterion for the named behaviour, as a single add patch.

        The bounded "Suggest one for me" op. `behaviour_id` names which behaviour to extend —
        the driver refuses a result that is anything other than one add under that behaviour's
        own criteria, so this is a suggestion, not an open licence to edit the tree.
        """
        ...
