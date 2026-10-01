"""The shared Profile-readiness rules.

Stage derivation, the Scenario screen gate, best-effort finish and compile preflight all ask about
the same Profile. The complete collector owns the objective gaps; the Scenario helper owns the
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
    from metis.wizard.domain.profile import ProductProfile

# The engine schema bounds a scenario's trial count; the Scenario screen's stepper enforces the
# same range door-side. Kept here so the screen and the readiness check cannot disagree on it.
TRIALS_MIN = 1
TRIALS_MAX = 20


def scenario_readiness(profile: ProductProfile) -> list[MissingData]:
    """Every reason the Scenario list is not yet runnable, in user-facing order.

    Order mirrors how a person reads the screen: the behaviours left uncovered first, then each
    scenario's own faults. An empty list means the Profile passes the Scenario gate.
    """
    gaps: list[MissingData] = []

    if not profile.scenarios:
        gaps.append(
            _gap(
                MissingDataCode.NO_SCENARIOS,
                None,
                "There are no scenarios yet.",
            )
        )
        return gaps

    measured = {behaviour.id for behaviour in profile.measured_behaviours()}
    persona_ids = {persona.id for persona in profile.personas}

    # A measured behaviour no scenario exercises is measured on nothing.
    for behaviour in profile.uncovered():
        gaps.append(
            _gap(
                MissingDataCode.BEHAVIOUR_UNCOVERED,
                behaviour.id,
                f"{behaviour.id} is covered by no scenario.",
            )
        )

    for scenario in profile.scenarios:
        if not set(scenario.behaviour_refs) & measured:
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_NO_SELECTED_BEHAVIOUR,
                    scenario.id,
                    f"{scenario.id} covers no selected behaviour.",
                )
            )

        # The schema declares persona_refs with minItems 1, so an empty run list is a file the
        # engine refuses to load.
        if not scenario.persona_refs:
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_NO_PERSONA,
                    scenario.id,
                    f"{scenario.id} has nobody to run it.",
                )
            )

        # A client-held state could carry a reference the Profile no longer has; the screen
        # never composes one, but preflight must not trust that.
        unknown = [
            ref for ref in scenario.behaviour_refs if profile.behaviour(ref) is None
        ] + [ref for ref in scenario.persona_refs if ref not in persona_ids]
        if unknown:
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_UNKNOWN_REFERENCE,
                    scenario.id,
                    f"{scenario.id} refers to something that no longer exists.",
                )
            )

        if not TRIALS_MIN <= scenario.num_trials <= TRIALS_MAX:
            gaps.append(
                _gap(
                    MissingDataCode.SCENARIO_INVALID_TRIALS,
                    scenario.id,
                    f"{scenario.id} needs between {TRIALS_MIN} and {TRIALS_MAX} trials.",
                )
            )

    return gaps


def profile_readiness(profile: ProductProfile) -> list[MissingData]:
    """Return all objective gaps before a Profile can produce a runnable experiment."""
    gaps: list[MissingData] = []
    if not profile.product.name or not profile.product.description:
        gaps.append(
            MissingData(
                code=MissingDataCode.PRODUCT_INCOMPLETE,
                stage=InterviewStep.CLARIFY,
                message="The product name and description are required.",
            )
        )

    if not profile.features or not profile.behaviours():
        gaps.append(
            MissingData(
                code=MissingDataCode.BEHAVIOURS_INCOMPLETE,
                stage=InterviewStep.BEHAVIOURS,
                message="At least one Feature and Behaviour are required.",
            )
        )
    elif not profile.measured_behaviours():
        gaps.append(
            MissingData(
                code=MissingDataCode.NO_MEASURED_BEHAVIOUR,
                stage=InterviewStep.BEHAVIOURS,
                message="At least one Behaviour must be measured.",
            )
        )

    for behaviour in profile.measured_behaviours():
        if not behaviour.criteria:
            gaps.append(
                MissingData(
                    code=MissingDataCode.CRITERIA_INCOMPLETE,
                    stage=InterviewStep.CRITERIA,
                    subject=behaviour.id,
                    message=f"{behaviour.id} needs at least one Criterion.",
                )
            )

    if not profile.personas:
        gaps.append(
            MissingData(
                code=MissingDataCode.NO_PERSONAS,
                stage=InterviewStep.PERSONAS,
                message="At least one Persona is required.",
            )
        )

    gaps.extend(scenario_readiness(profile))
    return gaps


def _gap(code: MissingDataCode, subject: str | None, message: str) -> MissingData:
    return MissingData(
        code=code,
        stage=InterviewStep.SCENARIOS,
        subject=subject,
        message=message,
    )
