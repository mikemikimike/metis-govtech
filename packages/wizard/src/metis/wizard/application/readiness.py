"""The shared Specification-readiness rules.

Stage derivation, the Scenario screen gate, best-effort finish and compile preflight all ask about
the same Specification. The complete collector owns the objective gaps; the Scenario helper owns the
engine-facing Scenario rules. Keeping both here stops the application from growing several
slightly different definitions of "ready".

The result is a list of `MissingData` — the same structured shape a turn returns to a caller —
so a door can render the gaps and finish can report them without re-deriving anything. An empty
list means ready.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.wizard.contracts.turn import MissingData, MissingDataCode
from metis.wizard.domain.permissions import InterviewStep

if TYPE_CHECKING:
    from metis.wizard.domain.specification import Specification

# The engine schema bounds a scenario's trial count; the Scenario screen's stepper enforces the
# same range door-side. Kept here so the screen and the readiness check cannot disagree on it.
TRIALS_MIN = 1
TRIALS_MAX = 20


def scenario_readiness(specification: Specification) -> list[MissingData]:
    """Every reason the Scenario list is not yet runnable, in user-facing order.

    Order mirrors how a person reads the screen: the behaviours left uncovered first, then each
    scenario's own faults. An empty list means the Specification passes the Scenario gate.
    """
    gaps: list[MissingData] = []

    if not specification.scenarios:
        gaps.append(
            _gap(
                MissingDataCode.NO_SCENARIOS,
                None,
                "There are no scenarios yet.",
            )
        )
        return gaps

    persona_ids = {persona.id for persona in specification.personas}

    # A measured behaviour no scenario exercises is measured on nothing.
    for behaviour in specification.uncovered():
        gaps.append(
            _gap(
                MissingDataCode.BEHAVIOUR_UNCOVERED,
                behaviour.id,
                f"{behaviour.id} is covered by no scenario.",
            )
        )

    for scenario in specification.scenarios:
        if not any(t.scenario_ref == scenario.id for t in specification.tasks):
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_NO_PERSONA,
                    scenario.id,
                    f"{scenario.id} needs a Task.",
                )
            )
    for task in specification.tasks:
        if not task.behaviour_refs or not all(
            any(b.id == ref for b in specification.measured_behaviours())
            for ref in task.behaviour_refs
        ):
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_NO_SELECTED_BEHAVIOUR,
                    task.id,
                    f"{task.id} needs measured Behaviours.",
                )
            )
        if (
            task.persona_ref not in persona_ids
            or not specification.scenario(task.scenario_ref)
            or any(specification.behaviour(ref) is None for ref in task.behaviour_refs)
        ):
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_UNKNOWN_REFERENCE,
                    task.id,
                    f"{task.id} has an unknown reference.",
                )
            )
        if not TRIALS_MIN <= task.num_trials <= TRIALS_MAX:
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_INVALID_TRIALS,
                    task.id,
                    f"{task.id} needs between 1 and 20 Trials.",
                )
            )

    return gaps


def specification_readiness(specification: Specification) -> list[MissingData]:
    """Return all objective gaps before a Specification can produce a runnable experiment."""
    gaps: list[MissingData] = []
    if not specification.product.name or not specification.product.description:
        gaps.append(
            MissingData(
                code=MissingDataCode.PRODUCT_INCOMPLETE,
                stage=InterviewStep.CLARIFY,
                message="The product name and description are required.",
            )
        )

    if not specification.features or not specification.behaviours():
        gaps.append(
            MissingData(
                code=MissingDataCode.BEHAVIOURS_INCOMPLETE,
                stage=InterviewStep.BEHAVIOURS,
                message="At least one Feature and Behaviour are required.",
            )
        )
    elif not specification.measured_behaviours():
        gaps.append(
            MissingData(
                code=MissingDataCode.NO_MEASURED_BEHAVIOUR,
                stage=InterviewStep.BEHAVIOURS,
                message="At least one Behaviour must be measured.",
            )
        )

    for behaviour in specification.measured_behaviours():
        if not behaviour.criteria:
            gaps.append(
                MissingData(
                    code=MissingDataCode.CRITERIA_INCOMPLETE,
                    stage=InterviewStep.CRITERIA,
                    subject=behaviour.id,
                    message=f"{behaviour.id} needs at least one Criterion.",
                )
            )

    if not specification.personas:
        gaps.append(
            MissingData(
                code=MissingDataCode.NO_PERSONAS,
                stage=InterviewStep.PERSONAS,
                message="At least one Persona is required.",
            )
        )

    gaps.extend(scenario_readiness(specification))
    return gaps


def _gap(code: MissingDataCode, subject: str | None, message: str) -> MissingData:
    return MissingData(
        code=code,
        stage=InterviewStep.SCENARIOS,
        subject=subject,
        message=message,
    )
