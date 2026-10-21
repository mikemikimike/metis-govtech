"""Composing the screen for each step.

This is the package's answer to *"draw this screen"*, not *"here is my document"*. Every
function here walks the specification, decides each card's state, composes its components and
notes, runs the completeness check, and emits a finished request.

Nothing here calls a model. Screens are composed from the specification as it stands, which is why
document warnings clear themselves: they are recomputed every time a screen is built, so
there is never a stale flag to track.

All user-facing wording lives here. That is the accepted cost of the door contract — a door
wanting different phrasing changes this file, rather than two doors quietly disagreeing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metis.wizard.application.readiness import specification_readiness
from metis.wizard.application.trials import format_trials
from metis.wizard.contracts.conversation import (
    AnyCardComponent,
    BehaviourCard,
    CardDisclosure,
    CardDivider,
    CardNumberField,
    CardOptionGroup,
    CardText,
    CardUploadField,
    ChoiceRequest,
    FormField,
    FormRequest,
    Option,
    OptionId,
    ScenarioCard,
    Warning,
    WarningSource,
    WizardRequest,
)
from metis.wizard.domain.patch import Patch, PatchOp, PatchOrigin
from metis.wizard.domain.permissions import InterviewStep

if TYPE_CHECKING:
    from metis.wizard.domain.specification import Behaviour, Feature, Specification

TRIALS_MIN = 1
TRIALS_MAX = 20
FEEDBACK_INSTRUCTION = (
    'To leave comments, choose "Chat about it" first; the next prompt accepts text.'
)


# ── step headers ─────────────────────────────────────────────────────────────

# The interview's steps, in order, each with the header title it shows. Position and total
# are *derived* from this list, so no screen builder ever writes a number — the one drift the
# design names out loud. CLARIFY is step one even though the model, not a screen builder,
# composes its chat; DONE is terminal and carries no header.
_STEP_TITLES: dict[InterviewStep, str] = {
    InterviewStep.CLARIFY: "Understanding your target",
    InterviewStep.BEHAVIOURS: "Behaviours",
    InterviewStep.CRITERIA: "Acceptance criteria",
    InterviewStep.PERSONAS: "Personas",
    InterviewStep.SCENARIOS: "Scenarios",
}
_INTERVIEW_STEPS: list[InterviewStep] = list(_STEP_TITLES)


def _ready_through(specification: Specification, step: InterviewStep) -> bool:
    """True when the Specification has no missing content at or before this review."""
    position = _INTERVIEW_STEPS.index(step)
    return not any(
        _INTERVIEW_STEPS.index(gap.stage) <= position
        for gap in specification_readiness(specification)
    )


def stamp_step(request: WizardRequest, step: InterviewStep) -> None:
    """Write the step's header onto a request: title, one-based position and total.

    One place turns a step into a position, so the five screens cannot drift into disagreeing
    about which of five they are. A step off the list — only DONE — leaves the fields at their
    `None` defaults, so a door draws no header rather than a wrong one.

    A mid-step form or chat is stamped with whatever step the interview is on when it is
    raised, which is the parent step — so "I'll add one" keeps the header anchored rather than
    looking like the interview jumped.
    """
    if step not in _STEP_TITLES:
        return
    request.title = _STEP_TITLES[step]
    request.step = _INTERVIEW_STEPS.index(step) + 1
    request.steps = len(_INTERVIEW_STEPS)


def _wizard_patch(path: str, value: object, op: PatchOp = PatchOp.SET) -> Patch:
    """A patch the package composed, and knows it composed.

    Everything on a tick, a chip or a stepper goes through here — which is what lets the
    applier trust it without an address check.
    """
    return Patch(op=op, path=path, value=value, origin=PatchOrigin.WIZARD)


def _behaviour_path(specification: Specification, behaviour_id: str, field: str) -> str:
    feature = specification.feature_of(behaviour_id)
    feature_id = feature.id if feature else "?"
    return f"features[{feature_id}].behaviours[{behaviour_id}].{field}"


def _section(feature: Feature) -> str:
    # The name alone. "Feature 1 ·" would be ordinal noise — the grouping is already visible, and
    # the number matches nothing the user could refer to.
    return feature.name


# ── the three replies ──────────────────────────────────────────────────────


def _three_replies(
    accept_label: str, add_label: str, *, accept_enabled: bool = True
) -> list[Option]:
    """Screen-level replies, for a flat list reviewed as a whole.

    Single-select: each carries a model-composed patch or triggers a model call, and two of
    those can contradict each other.
    """
    return [
        Option(
            id=OptionId(action="accept"),
            label=accept_label,
            primary=True,
            enabled=accept_enabled,
        ),
        Option(id=OptionId(action="chat"), label="Chat about it"),
        Option(id=OptionId(action="add"), label=add_label),
    ]


# ── step 1 · behaviours ────────────────────────────────────────────────────

BEHAVIOUR_INSTRUCTION = (
    "Every behaviour starts selected for measurement. Clear any you don't want to measure. "
    'To leave comments, choose "Chat about it" first; the next prompt accepts text.'
)


def target_completion_form(specification: Specification) -> FormRequest | None:
    """Ask for required Target fields that the model did not supply."""
    fields: list[FormField] = []
    if not specification.target.name.strip():
        fields.append(FormField(id="target.name", label="Target name", multiline=False))
    if not specification.target.description.strip():
        fields.append(FormField(id="target.description", label="Target description"))
    if not fields:
        return None
    return FormRequest(
        prompt="Enter the missing target details to continue to the behaviour review.",
        fields=fields,
    )


def behaviours_screen(specification: Specification, message: str) -> ChoiceRequest:
    """Review and measurement selection in one screen.

    Each card shows a behaviour and carries its own measurement tick — the "which of these do
    we measure" decision, the only real decision in the interview. `multi=True`: every tick was
    composed by the package and writes one independent flag on a different behaviour, so nothing
    can invalidate anything else, and several ticks can travel together.

    `selected` reflects `measured`, so both doors draw a checkbox (drafted and form behaviours
    start measured). Continue is disabled while nothing is measured: with no measured behaviour
    there is nothing to write criteria for.
    """
    cards: list[BehaviourCard] = []
    for feature in specification.features:
        for behaviour in feature.behaviours:
            cards.append(
                BehaviourCard(
                    id=behaviour.id,
                    section=_section(feature),
                    title=behaviour.name,
                    selected=behaviour.measured,
                    components=[CardText(text=behaviour.description)],
                    options=[
                        Option(
                            id=OptionId(action="tick", target=behaviour.id),
                            label="Measure this",
                            selected=behaviour.measured,
                            patch=_wizard_patch(
                                _behaviour_path(
                                    specification, behaviour.id, "measured"
                                ),
                                not behaviour.measured,
                            ),
                        )
                    ],
                )
            )

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=True,
        options=[
            Option(id=OptionId(action="chat"), label="Chat about it"),
            *[
                Option(
                    id=OptionId(action="add", target=feature.id),
                    label=f"Add to {feature.name}",
                )
                for feature in specification.features
            ],
            Option(
                id=OptionId(action="continue"),
                label="Continue",
                primary=True,
                # A disabled Continue is still shown, marked unavailable. Readiness through this
                # review requires a complete Target and at least one measured Behaviour.
                enabled=_ready_through(specification, InterviewStep.BEHAVIOURS),
            ),
        ],
        instruction=BEHAVIOUR_INSTRUCTION,
    )


# ── step 2 · criteria ──────────────────────────────────────────────────────


def _criterion_components(behaviour: Behaviour) -> list[AnyCardComponent]:
    components: list[AnyCardComponent] = []
    for criterion in behaviour.criteria:
        if components:
            components.append(CardDivider())
        components.append(CardText(text=criterion.description))
        from metis.wizard.application.matching.matcher import default_grader_args

        settings = {**default_grader_args(criterion), **criterion.grader_args}
        components.append(
            CardDisclosure(
                label="Grader details",
                items=[
                    CardText(label="Name", text=criterion.name),
                    CardText(
                        label="Grader", text=criterion.grader_fqn or "Not selected"
                    ),
                    *[
                        CardText(label=name, text=json.dumps(value, ensure_ascii=False))
                        for name, value in settings.items()
                    ],
                ],
            )
        )
        components.append(
            CardOptionGroup(
                options=[
                    Option(
                        id=OptionId(action="parameters", target=criterion.id),
                        label="Edit assessment",
                    )
                ]
            )
        )
    return components


def criteria_screen(specification: Specification, message: str) -> ChoiceRequest:
    """The only per-card screen, and it earns it.

    Criteria are the one thing scoped to a single behaviour, so "chat about it" has to say
    *which* it. Everywhere else the model drafts a list and the user reviews it whole.
    """
    cards: list[BehaviourCard] = []

    for feature in specification.features:
        for behaviour in feature.behaviours:
            if behaviour.measured:
                cards.append(
                    BehaviourCard(
                        id=behaviour.id,
                        section=_section(feature),
                        title=behaviour.name,
                        selected=True,
                        components=[
                            CardText(text=behaviour.description),
                            *_criterion_components(behaviour),
                        ],
                        # Three distinct, behaviour-scoped operations, each carrying this
                        # card's id. Their labels name the authorship they perform: a
                        # model-assisted discussion of these criteria, one model-authored
                        # suggestion, or one criterion the user writes verbatim. The driver
                        # splits on the action and passes the target through, so "these
                        # criteria" is enforced, not merely prompted.
                        options=[
                            Option(
                                id=OptionId(action="chat", target=behaviour.id),
                                label="Chat about these criteria",
                            ),
                            Option(
                                id=OptionId(action="another", target=behaviour.id),
                                label="Suggest one for me",
                            ),
                            Option(
                                id=OptionId(action="type", target=behaviour.id),
                                label="Write one myself",
                            ),
                        ],
                    )
                )
            else:
                # Drawn greyed, with no actions — visible so you can see what you left out,
                # dormant so it costs nothing.
                cards.append(
                    BehaviourCard(
                        id=behaviour.id,
                        section=_section(feature),
                        title=behaviour.name,
                        components=[
                            CardText(text=behaviour.description),
                            *_criterion_components(behaviour),
                        ],
                        selected=False,
                        note="Not selected. Tasks cannot use these Criteria.",
                    )
                )

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=False,
        instruction=(
            'To leave comments, choose "Chat about it" under the relevant item first; '
            "the next prompt accepts text."
        ),
        options=[
            Option(id=OptionId(action="back"), label="← Back"),
            Option(
                id=OptionId(action="continue"),
                label="Continue",
                primary=True,
                enabled=_ready_through(specification, InterviewStep.CRITERIA),
            ),
        ],
    )


# ── step 3 · personas ──────────────────────────────────────────────────────


def personas_screen(specification: Specification, message: str) -> ChoiceRequest:
    cards = [
        BehaviourCard(
            id=persona.id,
            title=persona.name,
            selected=True,
            components=[CardText(text=persona.description)],
        )
        for persona in specification.personas
    ]

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=False,
        options=_three_replies(
            "Looks right",
            "Add one",
            accept_enabled=_ready_through(specification, InterviewStep.PERSONAS),
        ),
        instruction=FEEDBACK_INSTRUCTION,
    )


# ── step 4 · scenarios ───────────────────────────────────────────────────────


def scenarios_screen(
    specification: Specification,
    message: str,
    available_fixture_names: list[str] | None = None,
) -> ChoiceRequest:
    gaps = specification_readiness(specification)
    cards = []
    for task in specification.tasks:
        scenario = specification.scenario(task.scenario_ref)
        cards.append(
            ScenarioCard(
                id=task.id,
                title=task.id,
                trials=task.num_trials,
                components=[
                    CardText(
                        text=scenario.description if scenario else "Select a Scenario."
                    ),
                    CardOptionGroup(
                        label="Scenario",
                        options=[
                            Option(
                                id=OptionId(
                                    action="scenario", target=task.id, via=item.id
                                ),
                                label=item.name,
                                selected=item.id == task.scenario_ref,
                                patch=_wizard_patch(
                                    f"tasks[{task.id}].scenario_ref", item.id
                                ),
                            )
                            for item in specification.scenarios
                        ],
                    ),
                    CardOptionGroup(
                        label="Persona",
                        options=[
                            Option(
                                id=OptionId(action="run", target=task.id, via=item.id),
                                label=item.name,
                                selected=item.id == task.persona_ref,
                                patch=_wizard_patch(
                                    f"tasks[{task.id}].persona_ref", item.id
                                ),
                            )
                            for item in specification.personas
                        ],
                    ),
                    CardOptionGroup(
                        label="Behaviours",
                        options=[
                            Option(
                                id=OptionId(action="cover", target=task.id, via=b.id),
                                label=b.name
                                if b.measured
                                else f"{b.name} (not measured)",
                                selected=b.id in task.behaviour_refs,
                                patch=_wizard_patch(
                                    f"tasks[{task.id}].behaviour_refs",
                                    sorted(set(task.behaviour_refs) ^ {b.id}),
                                ),
                            )
                            for b in specification.behaviours()
                            if b.measured or b.id in task.behaviour_refs
                        ]
                        + [
                            Option(
                                id=OptionId(action="cover", target=task.id, via=ref),
                                label=f"{ref} (missing; remove this reference)",
                                selected=True,
                                patch=_wizard_patch(
                                    f"tasks[{task.id}].behaviour_refs",
                                    [bid for bid in task.behaviour_refs if bid != ref],
                                ),
                            )
                            for ref in task.behaviour_refs
                            if specification.behaviour(ref) is None
                        ],
                    ),
                    CardNumberField(
                        label="Trials",
                        id=OptionId(action="trials", target=task.id),
                        value=task.num_trials,
                        min=TRIALS_MIN,
                        max=TRIALS_MAX,
                    ),
                    CardUploadField(
                        label="Files sent to your target",
                        id=OptionId(action="files", target=task.id),
                        value=list(task.fixtures),
                        available=list(available_fixture_names or []),
                    ),
                ],
                options=[
                    Option(
                        id=OptionId(action="copy-task", target=task.id),
                        label="Copy Test Case",
                    ),
                    Option(
                        id=OptionId(action="remove-task", target=task.id),
                        label="Remove Test Case",
                    ),
                ],
            )
        )
    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=True,
        warnings=[
            Warning(text=g.message, source=WarningSource.DOCUMENT, blocking=True)
            for g in gaps
        ],
        footer=f"Total: {len(specification.tasks)} Test Cases · {format_trials(specification.trial_count())}",
        instruction=FEEDBACK_INSTRUCTION,
        options=[
            Option(id=OptionId(action="back"), label="← Back"),
            Option(id=OptionId(action="chat"), label="Chat about it"),
            Option(id=OptionId(action="add"), label="Add Scenario"),
            *[
                Option(
                    id=OptionId(action="add-task", target=scenario.id),
                    label=f"Add Test Case: {scenario.name}",
                )
                for scenario in specification.scenarios
            ],
            Option(
                id=OptionId(action="continue"),
                label="Continue",
                primary=True,
                enabled=not gaps,
            ),
        ],
    )
