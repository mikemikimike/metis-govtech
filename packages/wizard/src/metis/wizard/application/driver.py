"""The interview, as a state machine.

`compose(state)` builds the screen for wherever the interview is. `handle(state, req, resp)`
applies what came back and decides where to go next.

Most responses cost no model call: every tick, chip and stepper arrives carrying a patch the
package composed before the screen was ever drawn, so applying it is a dictionary lookup. The
model is called at five points only — clarify, and the four drafting steps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from metis.wizard.application import cascade, config, screens
from metis.wizard.application.interviewer import Interviewer, InterviewerOutputError
from metis.wizard.contracts.conversation import (
    AnyRequest,
    AnyResponse,
    CardFieldValue,
    CardNumberField,
    CardUploadField,
    ChatRequest,
    ChoiceRequest,
    FormField,
    FormRequest,
    Option,
    OptionId,
    Warning,
    WarningSource,
    editable_fields_of,
)
from metis.wizard.contracts.interview_state import InterviewState
from metis.wizard.contracts.output import (
    BehaviourDraft,
    CriterionDraft,
    PersonaDraft,
    ScenarioDraft,
    StepResult,
)
from metis.wizard.domain import materializer
from metis.wizard.domain.applier import apply, sanitise
from metis.wizard.domain.patch import Patch, PatchOp, PatchOrigin
from metis.wizard.domain.permissions import InterviewStep

if TYPE_CHECKING:
    from collections.abc import Callable

    from metis.wizard.contracts.interview_state import Turn
    from metis.wizard.domain.specification import Behaviour


class DriverState(InterviewState):
    """The client-held state, plus the one field the driver alone needs: where the interview is.

    `InterviewState` carries no stage — the stage is derived, so the client never stores it. But
    the state machine below reads and writes a stage on every turn, so a turn lifts the client
    value into this subclass, runs the driver on it, and projects the result back down without
    the stage. The driver therefore needs no knowledge of derivation, and the client contract
    keeps its single source of truth. See `application.turn`.
    """

    step: InterviewStep


_NEXT_STEP = {
    InterviewStep.CLARIFY: InterviewStep.BEHAVIOURS,
    InterviewStep.BEHAVIOURS: InterviewStep.CRITERIA,
    InterviewStep.CRITERIA: InterviewStep.PERSONAS,
    InterviewStep.PERSONAS: InterviewStep.SCENARIOS,
    InterviewStep.SCENARIOS: InterviewStep.DONE,
}

# Only these screens expose Back. Keeping the map explicit makes the door's visible
# navigation contract inspectable and avoids implying that hidden or terminal steps can go
# back through this handler.
_PREVIOUS_STEP = {
    InterviewStep.CRITERIA: InterviewStep.BEHAVIOURS,
    InterviewStep.SCENARIOS: InterviewStep.PERSONAS,
}

_DEFAULT_MESSAGES = {
    InterviewStep.BEHAVIOURS: "Here's the current draft.",
    InterviewStep.CRITERIA: "Here are the current acceptance criteria.",
    InterviewStep.PERSONAS: "Here are the current personas.",
    InterviewStep.SCENARIOS: "Here are the current scenarios.",
}

_CLARIFY_PRODUCT_PATHS = frozenset(
    {
        "product.name",
        "product.users",
        "product.description",
        "product.detail",
    }
)


def _clarify_questions_asked(history: list[Turn]) -> int:
    """Count only questions composed by the model, not the package opening line."""
    count = sum(1 for turn in history if turn.role == "assistant")
    if history and history[0].role == "assistant":
        try:
            opening = config.opening_question()
        except RuntimeError:
            opening = ""
        if opening and history[0].text == opening:
            count -= 1
    return max(0, count)


@dataclass
class StepDriver:
    """Composes screens and advances the interview.

    `pending_warnings` is where a RUNTIME warning waits between being raised and being drawn.
    It is the one piece of state that crosses a turn, and it is deliberately shown once: every
    runtime warning so far describes something that already happened rather than something
    still true.
    """

    interviewer: Interviewer
    matcher: object | None = None  # an EmbeddingMatcher; None leaves criteria unmatched
    pending_warnings: list[Warning] = field(default_factory=list)
    # Questions raised by an edit, waiting to be asked. They are drained before the next
    # screen is composed, in the same turn — which is what stops this being staleness
    # tracking. Nothing here survives to a later turn.
    pending_questions: list[cascade.Question] = field(default_factory=list)
    model_error: InterviewerOutputError | None = field(default=None, repr=False)
    # A later drafting call must not leak its introduction onto an earlier screen when the
    # user goes Back. These are presentation state only; a persisted pending request already
    # carries its prompt, and a recomposed screen after resume uses the neutral default.
    _step_messages: dict[InterviewStep, str] = field(default_factory=dict)

    # ── composing ──────────────────────────────────────────────────────────

    def compose(self, state: DriverState) -> AnyRequest:
        """Compose the next screen and stamp its step header.

        Stamping here rather than in each screen builder is deliberate: every request the
        interview produces — the clarify chat, the five review screens and any cascade
        question raised mid-step — leaves through this one method, so the header cannot go
        missing on one path or disagree with another. A cascade question raised while
        standing at criteria inherits the criteria header, which is what keeps it anchored.
        """
        request = self._compose(state)
        screens.stamp_step(request, state.step)
        return request

    def _compose(self, state: DriverState) -> AnyRequest:
        specification = state.specification
        step = state.step

        # An edit raised questions about work derived from it. Ask them before anything else,
        # in the same turn the edit happened — deferring is what would make this staleness
        # tracking rather than a question.
        if self.pending_questions:
            return self.pending_questions[0].to_request()

        if step is InterviewStep.CLARIFY:
            # The package-owned opening line is an assistant turn for context, but it is not a
            # question composed by the model and must not consume the clarify budget.
            if not any(t.role == "user" for t in state.history):
                return ChatRequest(prompt=config.opening_question())

            asked = _clarify_questions_asked(state.history)
            cap = config.clarify_turn_cap()
            if asked <= cap:
                result = self.interviewer.clarify(
                    specification,
                    state.history,
                    context=state.context,
                )
                self._run(
                    state,
                    result,
                    allowed_paths=_CLARIFY_PRODUCT_PATHS,
                )
                # The call at the bound is record-only. Its patches are required, but its
                # message must never become a sixth question or enter the transcript.
                if asked < cap and not result.done and result.message:
                    return ChatRequest(prompt=result.message)
            # Either the model is finished or the cap is reached. Draft regardless.
            state.step = InterviewStep.BEHAVIOURS
            step = InterviewStep.BEHAVIOURS

        if step is InterviewStep.BEHAVIOURS:
            # A model can finish clarification without filling required Product fields.
            # Collect them directly so the review cannot strand the user at Continue.
            completion = screens.product_completion_form(specification)
            if completion is not None:
                return completion
            if not specification.features:
                self._try(
                    lambda: self.interviewer.draft_behaviours(
                        specification,
                        state.history,
                        context=state.context,
                    ),
                    state,
                )
            return self._attach(
                screens.behaviours_screen(
                    specification, self._message(InterviewStep.BEHAVIOURS)
                )
            )

        if step is InterviewStep.CRITERIA:
            return self._attach(
                screens.criteria_screen(
                    specification, self._message(InterviewStep.CRITERIA)
                )
            )

        if step is InterviewStep.PERSONAS:
            if not specification.personas:
                self._try(
                    lambda: self.interviewer.draft_personas(
                        specification, context=state.context
                    ),
                    state,
                )
            return self._attach(
                screens.personas_screen(
                    specification, self._message(InterviewStep.PERSONAS)
                )
            )

        if step is InterviewStep.SCENARIOS:
            if not specification.scenarios:
                self._try(
                    lambda: self.interviewer.draft_scenarios(
                        specification, context=state.context
                    ),
                    state,
                )
            return self._attach(
                screens.scenarios_screen(
                    specification,
                    self._message(InterviewStep.SCENARIOS),
                    state.context.document_names,
                )
            )

        raise RuntimeError(f"Nothing to compose at step {step}.")

    def _message(self, step: InterviewStep) -> str:
        return self._step_messages.get(step, _DEFAULT_MESSAGES[step])

    def _attach(self, request: ChoiceRequest) -> ChoiceRequest:
        """Drain the runtime warnings onto the next screen drawn.

        Shown once: they are events, not conditions, so nothing recomputes them and nothing
        should carry them forward.
        """
        if self.pending_warnings:
            request.warnings = [*self.pending_warnings, *request.warnings]
            self.pending_warnings = []
        return request

    # ── handling ───────────────────────────────────────────────────────────

    def handle(
        self, state: DriverState, request: AnyRequest, response: AnyResponse
    ) -> None:
        if self.pending_questions:
            # `compose()` stamped the header onto the question the user is answering, so the
            # request that comes back carries one. Stamp the fresh copy the same way — with
            # the step it was raised on, which is still the current step — or the equality
            # check that routes the answer would miss on the header fields alone.
            expected = self.pending_questions[0].to_request()
            screens.stamp_step(expected, state.step)
            if request == expected:
                return self._answer_question(state, response)
        if isinstance(request, ChatRequest):
            return self._handle_chat(state, request, response)
        if isinstance(request, FormRequest):
            return self._handle_form(state, request, response)
        return self._handle_choice(state, request, response)

    def _handle_chat(
        self, state: DriverState, request: ChatRequest, response: AnyResponse
    ) -> None:
        text = getattr(response, "text", "")
        if state.step is InterviewStep.CLARIFY:
            return  # the answer is in history; the next compose() asks the next question

        # A chat raised from a criteria card carries that behaviour's id; a screen-level chat
        # carries None. The id both tells the model what the user is looking at and confines
        # the edit to that behaviour's own criteria — so "Chat about these criteria" cannot
        # reach across and rewrite a different card's.
        target = request.target
        before_texts = self._criterion_texts(state)
        try:
            result = self.interviewer.chat(
                state.specification,
                str(state.step),
                text,
                target,
                context=state.context,
            )
        except InterviewerOutputError as exc:
            self.model_error = exc
            # Keep the direct driver API's warning behavior. The turn transaction checks
            # `model_error` and converts this into a typed retryable failure.
            return self._refuse_chat()
        if target is not None:
            result = self._confine_to_behaviour(result, target)
        self._run(state, result)
        self._rematch_reworded(state, before_texts)

    def _refuse_chat(self) -> None:
        """Change nothing and say so, when a chat could not be answered by the model."""
        self.pending_warnings.append(
            Warning(
                text=(
                    "I couldn't work out a change from that just then, so I've left your "
                    "specification exactly as it is. Try saying it again."
                ),
                source=WarningSource.RUNTIME,
                blocking=False,
            )
        )

    def _confine_to_behaviour(
        self, result: StepResult, behaviour_id: str
    ) -> StepResult:
        """Drop any patch a scoped criteria chat produced that reaches outside this behaviour.

        The applier already enforces which *fields* the criteria step may write; this enforces
        which *behaviour*. A patch under `behaviours[<id>].criteria` stays; anything else — a
        sibling behaviour, the tree, a persona — is dropped and reported, because a chat the
        user opened on one card must not silently edit another.
        """
        prefix = f"behaviours[{behaviour_id}].criteria"
        kept = [p for p in result.patches if prefix in p.path]
        for dropped in result.patches:
            if prefix not in dropped.path:
                self.pending_warnings.append(
                    Warning(
                        text=(
                            "That change reached outside the criteria you were editing, so "
                            "I've left it out. Everything for this behaviour still applied."
                        ),
                        source=WarningSource.RUNTIME,
                        blocking=False,
                    )
                )
        return result.model_copy(update={"patches": kept})

    @staticmethod
    def _criterion_texts(state: DriverState) -> dict[str, str]:
        """Every criterion's wording, keyed by id — the input the matcher reads."""
        return {
            criterion.id: str(criterion.description)
            for behaviour in state.specification.behaviours()
            for criterion in behaviour.criteria
        }

    def _rematch_reworded(
        self, state: DriverState, before_texts: dict[str, str]
    ) -> None:
        """Re-resolve the grader for any criterion whose wording just changed.

        This is the other half of the "you may not write grader_fqn" rule: the model reweds
        the criterion instead, and the matcher — not the model — chooses the grader that new
        wording points at. Without this, `match_specification` would skip a criterion that already
        has a grader, so a reword would leave the old grader in place. Silent by design: the
        matcher only ever overwrites its own earlier choice.

        A criterion the chat *added* is absent from `before_texts`, so it counts as changed
        and is matched here too — the chat path has no other pass that would resolve it."""
        if self.matcher is None:
            return
        from metis.wizard.application.matching import rematch

        for behaviour in state.specification.behaviours():
            for criterion in behaviour.criteria:
                if str(criterion.description) != before_texts.get(criterion.id, ""):
                    rematch(criterion, self.matcher)  # type: ignore[arg-type]

    def _handle_form(
        self, state: DriverState, request: FormRequest, response: AnyResponse
    ) -> None:
        """Text typed into a form is used as-is — the model never sees it, so it cannot
        rewrite it. Everything created here is stamped FORM."""
        values = getattr(response, "values", {}) or {}
        specification = state.specification

        if state.step is InterviewStep.BEHAVIOURS and request.target is None:
            completion = screens.product_completion_form(specification)
            if completion is not None and request.fields == completion.fields:
                apply(
                    specification,
                    [
                        Patch(
                            op=PatchOp.SET,
                            path=field.id,
                            value=values[field.id],
                            origin=PatchOrigin.WIZARD,
                        )
                        for field in completion.fields
                        if isinstance(values.get(field.id), str)
                        and values[field.id].strip()
                    ],
                    issued_ids=state.issued_ids,
                    user_typed=state.user_typed,
                )
                return

        if request.target and any(
            field.id == "grader_args" for field in request.fields
        ):
            criterion = specification.criterion(request.target)
            if criterion is None:
                return self._refuse_form_target()
            from metis.wizard.application.matching.matcher import validate_grader_args

            try:
                args = json.loads(values.get("grader_args", "{}"))
                validate_grader_args(criterion.grader_fqn, args)
            except (ValueError, TypeError) as exc:
                return self._refuse_field_edit(f"Invalid Grader parameters: {exc}")
            criterion.grader_args = args
            return

        # A target keeps a manual child attached to the parent that offered the action. The
        # current step tells us which parent type the opaque id names.
        if request.target is not None:
            if state.step is InterviewStep.CRITERIA:
                return self._add_typed_criterion(state, request.target, values)
            if state.step is InterviewStep.BEHAVIOURS:
                return self._add_typed_behaviour(state, request.target, values)
            return self._refuse_form_target()

        # Scoped child forms must carry their parent id. A missing target is not a valid
        # screen-level Behaviour or Criterion form, and must never be guessed or widened.
        if state.step in (InterviewStep.BEHAVIOURS, InterviewStep.CRITERIA):
            return self._refuse_form_target()

        if state.step is InterviewStep.PERSONAS:
            materializer.add_persona(
                specification,
                PersonaDraft(
                    name=values.get("name", "Persona"),
                    description=values.get("description", ""),
                ),
                PatchOrigin.WIZARD,
                issued_ids=state.issued_ids,
                user_typed=state.user_typed,
            )
        elif state.step is InterviewStep.SCENARIOS:
            materializer.add_scenario(
                specification,
                ScenarioDraft(
                    name=values.get("name", "Scenario"),
                    description=values.get("description", ""),
                    tasks=[],
                ),
                PatchOrigin.WIZARD,
                issued_ids=state.issued_ids,
                user_typed=state.user_typed,
            )

    def _add_typed_behaviour(
        self, state: DriverState, feature_id: str, values: dict[str, Any]
    ) -> None:
        """Append one form-created Behaviour under the Feature that offered the action."""
        feature = state.specification.feature(feature_id)
        if feature is None:
            return self._refuse_form_target()

        feature.behaviours.append(
            materializer.add_behaviour(
                state.specification,
                BehaviourDraft(
                    name=values.get("name", "Behaviour"),
                    description=values.get("description", ""),
                ),
                PatchOrigin.WIZARD,
                issued_ids=state.issued_ids,
                user_typed=state.user_typed,
            )
        )

    def _add_typed_criterion(
        self, state: DriverState, behaviour_id: str, values: dict[str, Any]
    ) -> None:
        """Turn a submitted Given/When/Then form into one criterion under one behaviour.

        The clauses are used verbatim and stamped FORM, so a regeneration must keep them
        byte-identical. Refused with no mutation if the behaviour cannot be resolved — the same
        guard the form was raised behind, re-checked here because the id survived a round trip
        and the behaviour could in principle have gone away between raising and submitting.
        """
        behaviour = self._targeted_behaviour(state, behaviour_id)
        if behaviour is None:
            return self._refuse_unresolved_target()

        materializer.add_criterion(
            state.specification,
            behaviour,
            CriterionDraft(
                name=values.get("name", "Criterion"),
                given=values.get("given", ""),
                when=values.get("when", ""),
                then=values.get("then", ""),
            ),
            PatchOrigin.WIZARD,
            issued_ids=state.issued_ids,
            user_typed=state.user_typed,
        )
        # The new criterion has no grader yet; match it, and only it, if a matcher is wired.
        self._match_new(behaviour, {c.id for c in behaviour.criteria[:-1]})

    def _handle_choice(
        self, state: DriverState, request: AnyRequest, response: AnyResponse
    ) -> None:
        values = getattr(response, "values", {}) or {}
        selected = set(getattr(response, "selected", []) or [])

        if values:
            if selected or len(values) != 1:
                return self._refuse_field_edit(
                    "Edit one scenario field at a time; I left the specification unchanged."
                )
            key, value = next(iter(values.items()))
            return self._handle_field_value(state, request, key, value)

        if not selected:
            return

        options = _all_options(request)
        chosen = [options[key] for key in selected if key in options]
        actions = {option.id.action for option in chosen}

        if "parameters" in actions:
            cid = _target_of(chosen, "parameters")
            criterion = state.specification.criterion(cid or "")
            if criterion is None:
                return
            state.pending = FormRequest(
                prompt=f"Set parameters for {criterion.name}. Enter a JSON object. Current values: {json.dumps(criterion.grader_args)}",
                fields=[
                    FormField(
                        id="grader_args",
                        label="Grader parameters",
                        placeholder=json.dumps(criterion.grader_args),
                    )
                ],
                target=criterion.id,
            )
            screens.stamp_step(state.pending, state.step)
            return
        if actions & {"add-task", "copy-task", "remove-task"}:
            from metis.wizard.contracts.output import TaskDraft

            action = next(
                a for a in ("add-task", "copy-task", "remove-task") if a in actions
            )
            target = _target_of(chosen, action) or ""
            original = state.specification.task(target)
            if action == "remove-task":
                state.specification.tasks = [
                    t for t in state.specification.tasks if t.id != target
                ]
                return
            if not state.specification.personas:
                return
            scenario_id = original.scenario_ref if original else target
            scenario = state.specification.scenario(scenario_id)
            if scenario is None:
                return
            created = materializer.add_task(
                state.specification,
                TaskDraft(
                    scenario_ref=scenario_id,
                    persona_ref=original.persona_ref
                    if original
                    else state.specification.personas[0].id,
                    criterion_refs=list(original.criterion_refs)
                    if original
                    else [
                        c.id
                        for b in state.specification.measured_behaviours()
                        for c in b.criteria
                    ],
                    fixtures=list(original.fixtures) if original else [],
                ),
                PatchOrigin.WIZARD,
                issued_ids=state.issued_ids,
                user_typed=state.user_typed,
                allowed_fixture_names=set(state.context.document_names),
            )
            if original:
                created.num_trials = original.num_trials
                created.max_turns = original.max_turns
                created.timeout_minutes = original.timeout_minutes
                created.response_wait_ms = original.response_wait_ms
                created.max_run_retries = original.max_run_retries
            return

        # Toggles and ticks: apply the patches the package already composed.
        patches = [option.patch for option in chosen if option.patch]
        if patches:
            apply(
                state.specification,
                patches,
                issued_ids=state.issued_ids,
                user_typed=state.user_typed,
            )  # WIZARD origin — trusted by construction
            # Measurement changes are their own operation. Even if a multi-select caller also
            # sends Continue, return the recomposed Behaviour review first so the changed scope is
            # visible and must then be confirmed deliberately.
            if state.step is InterviewStep.BEHAVIOURS:
                return

        if "back" in actions:
            destination = _PREVIOUS_STEP.get(state.step, state.step)
            # Back to Behaviour review reopens the measurement-scope decision, so its earlier
            # confirmation no longer holds and must be earned again with Continue.
            if destination is InterviewStep.BEHAVIOURS:
                state.behaviours_confirmed = False
            state.step = destination
            return

        # The three criteria-card actions and the screen-level chat all dispatch on the action
        # the option carried, and each carries whatever behaviour id its card was scoped to in
        # its OptionId.target. Screen-level chat carries None and stays unscoped; the criteria
        # actions carry a behaviour id and are refused if it names no writable behaviour.
        if "chat" in actions:
            return self._open_chat(state, _target_of(chosen, "chat"))

        if "another" in actions:
            return self._suggest_one_criterion(state, _target_of(chosen, "another"))

        if "type" in actions:
            return self._open_criterion_form(state, _target_of(chosen, "type"))

        if "add" in actions:
            # Every repeated node has a short name and substantive content. The Behaviour
            # action also carries its Feature id so the submitted node cannot move to another
            # group during a door or save/resume round trip.
            fields = [
                FormField(id="name", label="Name"),
                FormField(id="description", label="Description", multiline=True),
            ]
            target = (
                _target_of(chosen, "add")
                if state.step is InterviewStep.BEHAVIOURS
                else None
            )
            form = FormRequest(
                prompt="Go ahead — I'll use exactly what you write.",
                fields=fields,
                target=target,
            )
            screens.stamp_step(form, state.step)
            state.pending = form
            return

        if "accept" in actions or "continue" in actions:
            self._advance(state)

    def _handle_field_value(
        self,
        state: DriverState,
        request: AnyRequest,
        key: str,
        value: CardFieldValue,
    ) -> None:
        """Validate one request-bound scenario field before composing its trusted patch."""
        field = editable_fields_of(request).get(key)
        if field is None:
            return self._refuse_field_edit(
                "That field is no longer available on this screen; I left the specification unchanged."
            )

        scenario_id = field.id.target
        scenario = state.specification.task(scenario_id) if scenario_id else None
        if scenario is None:
            return self._refuse_field_edit(
                "That scenario is no longer available; I left the specification unchanged."
            )

        if isinstance(field, CardNumberField):
            if field.id.action != "trials":
                return self._refuse_field_edit(
                    "That scenario field is not a supported trial editor; "
                    "I left the specification unchanged."
                )
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not field.min <= value <= field.max
            ):
                return self._refuse_field_edit(
                    f"Trials must be an integer from {field.min} to {field.max}; "
                    "I left the specification unchanged."
                )
            path = f"tasks[{scenario.id}].num_trials"
            patch_value: int | list[str] = value
        elif isinstance(field, CardUploadField):
            if field.id.action != "files":
                return self._refuse_field_edit(
                    "That scenario field is not a supported filename editor; "
                    "I left the specification unchanged."
                )
            normalized = _normalise_fixture_references(value)
            if normalized is None:
                return self._refuse_field_edit(
                    "Fixture references must be non-blank portable filenames; "
                    "I left the specification unchanged."
                )
            path = f"tasks[{scenario.id}].fixtures"
            patch_value = normalized
        else:  # pragma: no cover - editable_fields_of only returns the two field shapes
            return self._refuse_field_edit(
                "That scenario field is not editable; I left the specification unchanged."
            )

        outcome = apply(
            state.specification,
            [
                Patch(
                    op=PatchOp.SET,
                    path=path,
                    value=patch_value,
                    origin=PatchOrigin.WIZARD,
                )
            ],
            issued_ids=state.issued_ids,
            user_typed=state.user_typed,
        )
        if outcome.any_rejected:
            return self._refuse_field_edit(
                "That scenario field could not be updated; I left the specification unchanged."
            )

    def _refuse_field_edit(self, text: str) -> None:
        self.pending_warnings.append(
            Warning(text=text, source=WarningSource.RUNTIME, blocking=False)
        )

    # ── the three criteria-card workflows ────────────────────────────────────

    def _open_chat(self, state: DriverState, target: str | None) -> None:
        """Raise a chat request, scoped to a behaviour when one was named.

        `target` is the OptionId.target the clicked option carried — a behaviour id from a
        criteria card, or None from a screen-level "Chat about it". It rides on the request so
        the scope survives a save/resume or HTTP round trip, and `_handle_chat` reads it back.
        A mid-step chat inherits the header of the step it was raised on, so it does not read
        as the interview having jumped somewhere new.
        """
        chat = ChatRequest(
            prompt="What would you like to change?",
            multiline=True,
            target=target,
        )
        screens.stamp_step(chat, state.step)
        state.pending = chat

    def _open_criterion_form(self, state: DriverState, target: str | None) -> None:
        """Raise a Given/When/Then form that becomes one criterion under one behaviour.

        Three fields rather than one ambiguous description: manual entry is one structured
        criterion, and `_handle_form` uses each clause verbatim. Refused with no mutation when
        the behaviour cannot be resolved, so a stale or malformed target cannot land a criterion
        on the wrong behaviour.
        """
        if self._targeted_behaviour(state, target) is None:
            return self._refuse_unresolved_target()
        form = FormRequest(
            prompt="Write one yourself — I'll use exactly what you type.",
            target=target,
            fields=[
                FormField(id="name", label="Name", multiline=False),
                FormField(id="given", label="Given", multiline=False),
                FormField(id="when", label="When", multiline=False),
                FormField(id="then", label="Then", multiline=False),
            ],
        )
        screens.stamp_step(form, state.step)
        state.pending = form

    def _targeted_behaviour(
        self, state: DriverState, target: str | None
    ) -> Behaviour | None:
        """The behaviour a criteria action names, or None if it names nothing writable.

        A missing id, or an id no behaviour has, resolves to None — the two ways a criteria
        action could otherwise widen past the one card it was raised on.
        """
        if not target:
            return None
        return state.specification.behaviour(target)

    def _refuse_unresolved_target(self) -> None:
        """Change nothing and say so, when a criteria action names no writable behaviour."""
        self.pending_warnings.append(
            Warning(
                text=(
                    "I couldn't tell which behaviour that was for, so I've left everything "
                    "exactly as it is. Try that again from the behaviour's own card."
                ),
                source=WarningSource.RUNTIME,
                blocking=False,
            )
        )

    def _refuse_form_target(self) -> None:
        """Refuse a form whose parent no longer exists, without widening its scope."""
        self.pending_warnings.append(
            Warning(
                text=(
                    "I couldn't find where that item belongs, so I've left the specification "
                    "unchanged. Open the form again from its Feature."
                ),
                source=WarningSource.RUNTIME,
                blocking=False,
            )
        )

    def _suggest_one_criterion(self, state: DriverState, target: str | None) -> None:
        """Ask the model for exactly one new criterion under one behaviour, and match it.

        This is the "Suggest one for me" workflow: not a chat and not a form, but a bounded
        model op. The model returns a single add. Anything else — no addition, more than one,
        or an addition aimed anywhere but this behaviour's own criteria list — is refused
        whole, with nothing applied, because a suggestion the user asked for on one card must
        never edit a second one or overwrite what is already there.
        """
        behaviour = self._targeted_behaviour(state, target)
        if behaviour is None:
            return self._refuse_unresolved_target()

        try:
            result = self.interviewer.suggest_criterion(
                state.specification,
                behaviour.id,
                context=state.context,
            )
        except InterviewerOutputError as exc:
            self.model_error = exc
            return self._refuse_suggestion()

        before_ids = {c.id for c in behaviour.criteria}
        patches = sanitise(result.patches)
        if not self._is_one_criterion_add(patches, behaviour.id):
            return self._refuse_suggestion()

        outcome = apply(
            state.specification,
            patches,
            issued_ids=state.issued_ids,
            user_typed=state.user_typed,
            allowed_fixture_names=set(state.context.document_names),
        )
        if outcome.any_rejected or not outcome.applied:
            # The address passed the shape check but the applier still refused it, or the value
            # would not build a Criterion. Either way nothing landed cleanly, so say so rather
            # than leave a half-applied suggestion behind.
            return self._refuse_suggestion()

        # Match only what was just added — the criterion whose id is new to this behaviour.
        self._match_new(behaviour, before_ids)

    @staticmethod
    def _is_one_criterion_add(patches: list[Patch], behaviour_id: str) -> bool:
        """True only for a single add that lands inside this behaviour's own criteria list."""
        if len(patches) != 1:
            return False
        patch = patches[0]
        prefix = f"behaviours[{behaviour_id}].criteria"
        return patch.op is PatchOp.ADD and patch.path.endswith(prefix)

    def _match_new(self, behaviour: Behaviour, before_ids: set[str]) -> None:
        """Resolve a grader for any criterion the suggestion just added under this behaviour."""
        if self.matcher is None:
            return
        from metis.wizard.application.matching import rematch

        for criterion in behaviour.criteria:
            if criterion.id not in before_ids:
                rematch(criterion, self.matcher)  # type: ignore[arg-type]

    def _refuse_suggestion(self) -> None:
        """Change nothing and say so, when a suggestion did not come back as one clean add."""
        self.pending_warnings.append(
            Warning(
                text=(
                    "I couldn't get a single clean suggestion just then, so I've left your "
                    "criteria exactly as they are. Try that again."
                ),
                source=WarningSource.RUNTIME,
                blocking=False,
            )
        )

    def _advance(self, state: DriverState) -> None:
        """Move on, generating whatever the next screen needs and does not have."""
        current = state.step

        # Behaviour Continue is the measurement-scope lock. It needs at least one measured
        # behaviour — with none there is nothing to write criteria for — and it records that
        # the user has chosen the set to measure. A screen with the gate held stays put.
        if current is InterviewStep.BEHAVIOURS:
            if not state.specification.measured_behaviours():
                return
            state.behaviours_confirmed = True

        state.step = _NEXT_STEP.get(current, InterviewStep.DONE)

        # Continue at behaviours is what generates criteria — which is why measured-but-empty
        # cannot exist, and why nothing is generated for behaviours nobody picked.
        if state.step is InterviewStep.CRITERIA:
            allowed_paths = self._missing_measured_criteria_paths(state)
        else:
            allowed_paths = frozenset()
        if allowed_paths:
            self._try(
                lambda: self.interviewer.draft_criteria(
                    state.specification, context=state.context
                ),
                state,
                allowed_paths=allowed_paths,
                allowed_ops=frozenset({PatchOp.ADD}),
            )
            # A separate pass, after generation — never folded into it.
            self.match(state)

    # ── applying model output ──────────────────────────────────────────────

    @staticmethod
    def _missing_measured_criteria_paths(state: DriverState) -> frozenset[str]:
        """Return the exact Criteria collections that one draft can add to.

        The model receives the complete Specification for context. This allowlist prevents it from
        writing Criteria to an unmeasured Behaviour or replacing an existing Criteria set.
        """
        paths = set()
        for behaviour in state.specification.measured_behaviours():
            if behaviour.criteria:
                continue
            feature = state.specification.feature_of(behaviour.id)
            if (
                feature is None
            ):  # a Behaviour from this Specification must belong to one Feature
                continue
            paths.add(f"features[{feature.id}].behaviours[{behaviour.id}].criteria")
        return frozenset(paths)

    def _try(
        self,
        call: Callable[[], StepResult],
        state: DriverState,
        *,
        allowed_paths: frozenset[str] | None = None,
        allowed_ops: frozenset[PatchOp] | None = None,
    ) -> bool:
        """Run a model call, turning a total failure into a warning rather than a crash.

        Three attempts have already happened inside the client. Reaching here means all of
        them failed, so the user is told and the previous screen is redrawn — everything
        already decided is still in the specification, because nothing was applied.
        """
        try:
            self._run(
                state,
                call(),
                allowed_paths=allowed_paths,
                allowed_ops=allowed_ops,
            )
            return True
        except InterviewerOutputError as exc:
            self.model_error = exc
            self.pending_warnings.append(
                Warning(
                    text=(
                        "I couldn't get a usable answer from the model just then. "
                        "Nothing you've decided has been lost — try that again."
                    ),
                    source=WarningSource.RUNTIME,
                    blocking=False,
                )
            )
            return False

    def _run(
        self,
        state: DriverState,
        result: StepResult,
        *,
        allowed_paths: frozenset[str] | None = None,
        allowed_ops: frozenset[PatchOp] | None = None,
    ) -> None:
        """Apply a model result, reporting anything the applier refused.

        `sanitise` forces MODEL origin first: origin is stamped by the code that builds a
        patch, so a model claiming `wizard` is either confused or trying it on.
        """
        before = state.specification.model_copy(deep=True)
        if result.message:
            self._step_messages[state.step] = result.message
        patches = sanitise(result.patches)
        refused = [
            patch
            for patch in patches
            if (allowed_paths is not None and patch.path not in allowed_paths)
            or (allowed_ops is not None and patch.op not in allowed_ops)
        ]
        patches = [patch for patch in patches if patch not in refused]
        if refused:
            self.pending_warnings.append(
                Warning(
                    text=(
                        "I left out a model change that was outside this operation's "
                        "allowed scope. Your specification keeps the scope you selected."
                    ),
                    source=WarningSource.RUNTIME,
                    blocking=False,
                )
            )
        outcome = apply(
            state.specification,
            patches,
            issued_ids=state.issued_ids,
            user_typed=state.user_typed,
            allowed_fixture_names=set(state.context.document_names),
        )

        for rejection in outcome.rejected:
            self.pending_warnings.append(
                Warning(
                    text=rejection.message,
                    source=WarningSource.RUNTIME,
                    blocking=False,
                )
            )

        # Ask about anything derived from what just changed, before the next screen.
        self.pending_questions += cascade.questions_for(before, outcome.applied)

    def _answer_question(self, state: DriverState, response: AnyResponse) -> None:
        """Resolve one cascade question. Three answers, and only one changes anything."""
        question = self.pending_questions.pop(0)
        selected = set(getattr(response, "selected", []) or [])
        action = next((s.split(":", 1)[0] for s in selected), "keep")

        if action == "regenerate":
            if question.kind == "criteria":
                behaviour = state.specification.behaviour(question.subject)
                if behaviour is None or not behaviour.measured:
                    return
            cascade.clear_for_regeneration(
                state.specification, question, state.user_typed
            )
            # What is left is a state the forward pass already draws: a ticked behaviour
            # with no criteria, or a behaviour no scenario covers.
            if question.kind == "criteria":
                self._run(
                    state,
                    self.interviewer.draft_criteria(
                        state.specification, context=state.context
                    ),
                    allowed_paths=self._missing_measured_criteria_paths(state),
                    allowed_ops=frozenset({PatchOp.ADD}),
                )
                self.match(state)
            elif question.kind == "scenario":
                self._run(
                    state,
                    self.interviewer.draft_scenarios(
                        state.specification, context=state.context
                    ),
                )
            elif question.kind == "tree":
                state.step = InterviewStep.BEHAVIOURS
        elif action == "edit":
            form = FormRequest(
                prompt="Go ahead — I'll use exactly what you write.",
                fields=[
                    FormField(
                        id="description", label="In your own words", multiline=True
                    )
                ],
            )
            screens.stamp_step(form, state.step)
            state.pending = form
        elif action == "review" and question.kind == "tree":
            state.step = InterviewStep.BEHAVIOURS

    def match(self, state: DriverState) -> None:
        """Resolve graders for criteria that lack them.

        A separate pass, run after criteria generation rather than folded into it. If the
        provider is unreachable every criterion falls through to the generated judge, which is
        still a working experiment — so this warns and continues rather than blocking.
        """
        if self.matcher is None:
            return

        from metis.wizard.application.matching import match_specification

        match_specification(state.specification, self.matcher)  # type: ignore[arg-type]
        if getattr(self.matcher, "degraded", False):
            self.pending_warnings.append(
                Warning(
                    text=(
                        "I couldn't reach the service that picks graders, so I've written "
                        "a custom judge for each criterion instead. The evaluation still "
                        "runs."
                    ),
                    source=WarningSource.RUNTIME,
                    blocking=False,
                )
            )
            self.matcher.degraded = False  # type: ignore[attr-defined]  # shown once


def _target_of(chosen: list[Option], action: str) -> str | None:
    """The behaviour id the option carrying `action` was scoped to, or None.

    Reads it straight off `OptionId.target`, which the criteria screen set to the behaviour a
    card belongs to. Screen-level chat carries None here, which is exactly what keeps it
    unscoped; the criteria actions carry a behaviour id, which is what scopes them to one card.
    """
    return next((o.id.target for o in chosen if o.id.action == action), None)


def _normalise_fixture_references(value: object) -> list[str] | None:
    """Return safe, ordered filename references, or ``None`` when the value is invalid."""
    if not isinstance(value, list):
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return None
        name = item.strip()
        if (
            not name
            or name in {".", ".."}
            or "\x00" in name
            or "/" in name
            or "\\" in name
        ):
            return None
        if name not in seen:
            normalized.append(name)
            seen.add(name)
    return normalized


def _all_options(request: AnyRequest) -> dict[str, Option]:
    """Every option a screen offered, keyed the way the door sends them back."""
    found: dict[str, Option] = {}
    if not isinstance(request, ChoiceRequest):
        return found

    def add(option: Option) -> None:
        found[str(option.id)] = option

    for option in request.options:
        add(option)
    for warning in request.warnings:
        for option in warning.options:
            add(option)
    for card in request.cards:
        for option in card.options:
            add(option)
        for component in card.components:
            for option in getattr(component, "options", []) or []:
                add(option)
    return found


__all__ = ["DriverState", "OptionId", "StepDriver"]
