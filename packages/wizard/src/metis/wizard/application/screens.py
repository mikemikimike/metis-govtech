"""Composing the screen for each step.

This is the package's answer to *"draw this screen"*, not *"here is my document"*. Every
function here walks the profile, decides each card's state, composes its components and
notes, runs the completeness check, and emits a finished request.

Nothing here calls a model. Screens are composed from the profile as it stands, which is why
document warnings clear themselves: they are recomputed every time a screen is built, so
there is never a stale flag to track.

All user-facing wording lives here. That is the accepted cost of the door contract — a door
wanting different phrasing changes this file, rather than two doors quietly disagreeing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.wizard.application.trials import format_trials
from metis.wizard.contracts.conversation import (
    AnyCardComponent,
    BehaviourCard,
    CardDivider,
    CardNumberField,
    CardOptionGroup,
    CardText,
    CardUploadField,
    ChoiceRequest,
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
    from metis.wizard.domain.profile import Behaviour, ProductProfile, Scenario, Task

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
    InterviewStep.CLARIFY: "Understanding your product",
    InterviewStep.BEHAVIOURS: "Behaviours",
    InterviewStep.PRIORITISE: "What to measure",
    InterviewStep.CRITERIA: "Acceptance criteria",
    InterviewStep.PERSONAS: "Personas",
    InterviewStep.SCENARIOS: "Scenarios",
}
_INTERVIEW_STEPS: list[InterviewStep] = list(_STEP_TITLES)


def stamp_step(request: WizardRequest, step: InterviewStep) -> None:
    """Write the step's header onto a request: title, one-based position and total.

    One place turns a step into a position, so the six screens cannot drift into disagreeing
    about which of six they are. A step off the list — only DONE — leaves the fields at their
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


def _behaviour_path(profile: ProductProfile, behaviour_id: str, field: str) -> str:
    task = profile.task_of(behaviour_id)
    task_id = task.id if task else "?"
    return f"tasks[{task_id}].behaviours[{behaviour_id}].{field}"


def _section(task: Task) -> str:
    # The name alone. "Task 1 ·" would be ordinal noise — the grouping is already visible, and
    # the number matches nothing the user could refer to.
    return task.name


# ── the three replies ──────────────────────────────────────────────────────


def _three_replies(accept_label: str, add_label: str) -> list[Option]:
    """Screen-level replies, for a flat list reviewed as a whole.

    Single-select: each carries a model-composed patch or triggers a model call, and two of
    those can contradict each other.
    """
    return [
        Option(id=OptionId(action="accept"), label=accept_label, primary=True),
        Option(id=OptionId(action="chat"), label="Chat about it"),
        Option(id=OptionId(action="add"), label=add_label),
    ]


# ── step 1 · behaviours ────────────────────────────────────────────────────


def behaviours_screen(profile: ProductProfile, message: str) -> ChoiceRequest:
    """A flat list reviewed whole — so the replies belong to the screen, not to each card.

    No card carries a `selected` here (`selected=None`): this screen only shows the drafted
    behaviours and asks for a nod to continue. The tick — the "which of these do we measure"
    decision — is made one screen later, on prioritise. A checkbox drawn here would imply the
    user must choose something before they have been asked to; both doors draw no box for a
    `None` selected (the CLI's `_checkbox` returns "", the web door renders the plain row).
    """
    cards = []
    for task in profile.tasks:
        for behaviour in task.behaviours:
            cards.append(
                BehaviourCard(
                    id=behaviour.id,
                    section=_section(task),
                    title=behaviour.name,
                    selected=None,
                    components=[CardText(text=behaviour.description)],
                )
            )

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=False,
        options=[
            Option(id=OptionId(action="accept"), label="Looks right", primary=True),
            Option(id=OptionId(action="chat"), label="Chat about it"),
            *[
                Option(
                    id=OptionId(action="add", target=task.id),
                    label=f"Add to {task.name}",
                )
                for task in profile.tasks
            ],
        ],
        instruction=FEEDBACK_INSTRUCTION,
    )


# ── step 2 · prioritise ────────────────────────────────────────────────────


def prioritise_screen(profile: ProductProfile) -> ChoiceRequest:
    """One question, on its own screen. The tick is the user's only real decision.

    `multi=True`: every option here was composed by the package and writes one independent
    flag on a different behaviour, so nothing can invalidate anything else.
    """
    cards: list[BehaviourCard] = []

    for task in profile.tasks:
        for behaviour in task.behaviours:
            cards.append(
                BehaviourCard(
                    id=behaviour.id,
                    section=_section(task),
                    title=behaviour.name,
                    selected=behaviour.measured,
                    components=[CardText(text=behaviour.description)],
                    options=[
                        Option(
                            id=OptionId(action="tick", target=behaviour.id),
                            label="Measure this",
                            selected=behaviour.measured,
                            patch=_wizard_patch(
                                _behaviour_path(profile, behaviour.id, "measured"),
                                not behaviour.measured,
                            ),
                        )
                    ],
                )
            )

    # No empty-task warning: leaving a task unticked is a legitimate choice, not a mistake to
    # flag. "Continue" is what generates criteria for whatever is ticked, so ticked-but-empty
    # cannot arise, and there is nothing here that needs blocking either.
    return ChoiceRequest(
        prompt=(
            "I've selected all behaviours as a starting point. Clear any you don't want "
            "to measure, then I'll write acceptance criteria for the rest."
        ),
        cards=cards,
        multi=True,
        options=[
            Option(id=OptionId(action="back"), label="← Back"),
            Option(id=OptionId(action="continue"), label="Continue", primary=True),
        ],
    )


# ── step 3 · criteria ──────────────────────────────────────────────────────


def _criterion_components(behaviour: Behaviour) -> list[AnyCardComponent]:
    # Each clause is its own labelled component rather than one run-on sentence. A labelled
    # component is a form row in both doors — the web aligns the label in a left column and the
    # CLI prints it above the value — so "Given / When / Then" reads as three aligned rows,
    # matching how the criterion is drawn in the document pane. The door stays shape-only: it
    # renders whatever labels arrive and never learns these three are a criterion.
    #
    # A divider sits *between* criteria, never before the first or after the last, so a behaviour
    # with several acceptance criteria does not read as one undifferentiated run of Given/When/Then
    # rows. The divider is shape, not domain — the door draws a rule where one arrives and never
    # learns it marks a criterion boundary.
    components: list[AnyCardComponent] = []
    for criterion in behaviour.criteria:
        if components:
            components.append(CardDivider())
        components.append(CardText(label="Name", text=criterion.name))
        components.append(CardText(label="Given", text=criterion.description.given))
        components.append(CardText(label="When", text=criterion.description.when))
        components.append(CardText(label="Then", text=criterion.description.then))
    return components


def criteria_screen(profile: ProductProfile, message: str) -> ChoiceRequest:
    """The only per-card screen, and it earns it.

    Criteria are the one thing scoped to a single behaviour, so "chat about it" has to say
    *which* it. Everywhere else the model drafts a list and the user reviews it whole.
    """
    cards: list[BehaviourCard] = []

    for task in profile.tasks:
        for behaviour in task.behaviours:
            if behaviour.measured:
                cards.append(
                    BehaviourCard(
                        id=behaviour.id,
                        section=_section(task),
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
                        section=_section(task),
                        title=behaviour.name,
                        components=[
                            CardText(text=behaviour.description),
                            *_criterion_components(behaviour),
                        ],
                        selected=False,
                        note="not selected — no criteria will be written",
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
            Option(id=OptionId(action="continue"), label="Continue", primary=True),
        ],
    )


# ── step 4 · personas ──────────────────────────────────────────────────────


def personas_screen(profile: ProductProfile, message: str) -> ChoiceRequest:
    cards = [
        BehaviourCard(
            id=persona.id,
            title=persona.name,
            selected=True,
            components=[CardText(text=persona.description)],
        )
        for persona in profile.personas
    ]

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=False,
        options=_three_replies("Looks right", "Add one"),
        instruction=FEEDBACK_INSTRUCTION,
    )


# ── step 5 · scenarios ───────────────────────────────────────────────────────


def _coverage_group(profile: ProductProfile, scenario_id: str) -> CardOptionGroup:
    scenario = profile.scenario(scenario_id)
    covered = set(scenario.behaviour_refs) if scenario else set()
    return CardOptionGroup(
        label="Covers",
        options=[
            Option(
                id=OptionId(action="cover", target=scenario_id, via=behaviour.id),
                label=behaviour.name,
                selected=behaviour.id in covered,
                patch=_wizard_patch(
                    f"scenarios[{scenario_id}].behaviour_refs",
                    sorted(covered ^ {behaviour.id}),
                ),
            )
            for behaviour in profile.measured_behaviours()
        ],
    )


def _persona_group(profile: ProductProfile, scenario_id: str) -> CardOptionGroup:
    scenario = profile.scenario(scenario_id)
    running = set(scenario.persona_refs) if scenario else set()
    return CardOptionGroup(
        label="Run as",
        options=[
            Option(
                id=OptionId(action="run", target=scenario_id, via=persona.id),
                label=persona.name,
                selected=persona.id in running,
                patch=_wizard_patch(
                    f"scenarios[{scenario_id}].persona_refs",
                    sorted(running ^ {persona.id}),
                ),
            )
            for persona in profile.personas
        ],
    )


def _covers_a_selection(profile: ProductProfile, scenario: Scenario) -> bool:
    """Does the scenario reference at least one currently selected behaviour?

    `measured_behaviours()` is exactly that set. A scenario whose refs are all empty, unknown or unmeasured
    covers nothing the experiment will measure — nothing rides along to make up the
    difference — so it fails this test and the gate below stops the step.
    """
    return bool(
        set(scenario.behaviour_refs) & {b.id for b in profile.measured_behaviours()}
    )


def _scenario_warnings(profile: ProductProfile) -> list[Warning]:
    """The blocking gates. Each carries its own fixes where it can."""
    warnings: list[Warning] = []

    for behaviour in profile.uncovered():
        fixes = [
            Option(
                id=OptionId(action="generate-scenario", via=behaviour.id),
                label="Generate one",
            )
        ]
        fixes += [
            Option(
                id=OptionId(action="cover", target=scenario.id, via=behaviour.id),
                label=f"add to {scenario.id}",
                patch=_wizard_patch(
                    f"scenarios[{scenario.id}].behaviour_refs",
                    sorted({*scenario.behaviour_refs, behaviour.id}),
                ),
            )
            for scenario in profile.scenarios
        ]
        warnings.append(
            Warning(
                text=f"{behaviour.id} is covered by no scenario.",
                source=WarningSource.DOCUMENT,
                blocking=True,
                options=fixes,
            )
        )

    for scenario in profile.scenarios:
        if not _covers_a_selection(profile, scenario):
            # A scenario that measures no selected behaviour is a trial spent proving
            # nothing. The fix is a click on the card's own "Covers" group already on screen,
            # so no options.
            warnings.append(
                Warning(
                    text=f"{scenario.id} covers no selected behaviour.",
                    source=WarningSource.DOCUMENT,
                    blocking=True,
                )
            )

        if not scenario.persona_refs:
            # The experiment schema declares persona_refs with minItems 1, so a scenario with
            # every chip off produces a file the engine refuses to load.
            warnings.append(
                Warning(
                    text=f"{scenario.id} has nobody to run it.",
                    source=WarningSource.DOCUMENT,
                    blocking=True,
                )
            )

    return warnings


def scenarios_screen(profile: ProductProfile, message: str) -> ChoiceRequest:
    warnings = _scenario_warnings(profile)
    blocked = any(w.blocking for w in warnings)
    blocking_ids = (
        {s.id for s in profile.scenarios if not s.persona_refs}
        | {s.id for s in profile.scenarios if not _covers_a_selection(profile, s)}
        | {s.id for b in profile.uncovered() for s in profile.scenarios_covering(b.id)}
    )

    cards = [
        ScenarioCard(
            id=scenario.id,
            title=scenario.name,
            blocking=scenario.id in blocking_ids,
            trials=len(scenario.persona_refs) * scenario.num_trials,
            components=[
                CardText(text=scenario.description),
                _coverage_group(profile, scenario.id),
                _persona_group(profile, scenario.id),
                CardNumberField(
                    label="Trials",
                    id=OptionId(action="trials", target=scenario.id),
                    value=scenario.num_trials,
                    min=TRIALS_MIN,
                    max=TRIALS_MAX,
                ),
                CardUploadField(
                    label="Files",
                    id=OptionId(action="files", target=scenario.id),
                    value=list(scenario.fixtures),
                ),
            ],
        )
        for scenario in profile.scenarios
    ]

    footer = f"Total: {format_trials(profile.trial_count())}"

    return ChoiceRequest(
        prompt=message,
        cards=cards,
        multi=True,
        warnings=warnings,
        footer=footer,
        instruction=FEEDBACK_INSTRUCTION,
        options=[
            Option(id=OptionId(action="back"), label="← Back"),
            Option(id=OptionId(action="chat"), label="Chat about it"),
            Option(id=OptionId(action="add"), label="I'll add one"),
            Option(
                id=OptionId(action="continue"),
                label="Continue",
                primary=True,
                # A disabled Continue is still shown. `enabled` carries the distinction that
                # a blocking warning alone could not: which control the gate is holding.
                enabled=not blocked,
            ),
        ],
    )
