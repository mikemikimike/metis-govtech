"""The object a door talks to.

    while (request := session.next()) is not None:
        session.respond(render(request))

`.next()` composes the screen for wherever the interview is, or hands back the one already
pending. `.respond()` applies what came back and moves on. `.profile()` exists for a door
that wants to draw the read-only document pane — no door needs it to render a request.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Self

from metis.wizard.contracts.conversation import (
    AnyRequest,
    AnyResponse,
    ChatRequest,
    ChatResponse,
    ChoiceRequest,
    FormRequest,
    FormResponse,
    options_of,
)
from metis.wizard.contracts.session_state import SessionState, Turn
from metis.wizard.domain.permissions import SessionStep
from metis.wizard.domain.profile import collect_profile_ids

if TYPE_CHECKING:
    from metis.wizard.application.driver import StepDriver
    from metis.wizard.domain.profile import ProductProfile


class Session:
    def __init__(
        self,
        state: SessionState,
        *,
        path: Path | None = None,
        driver: StepDriver | None = None,
    ) -> None:
        self.state = state
        self.path = path
        self._driver = driver

    # ── lifecycle ──────────────────────────────────────────────────────────

    @classmethod
    def start(
        cls,
        profile: ProductProfile,
        *,
        path: Path | None = None,
        driver: StepDriver | None = None,
        session_id: str | None = None,
    ) -> Self:
        state = SessionState(
            id=session_id or f"wizard-{uuid.uuid4().hex[:8]}",
            profile=profile,
            step=SessionStep.CLARIFY,
            issued_ids=collect_profile_ids(profile),
        )
        return cls(state, path=path, driver=driver)

    @classmethod
    def resume(cls, path: Path, *, driver: StepDriver | None = None) -> Self:
        """Pick up where it left off. No model call already paid for is re-paid."""
        return cls(SessionState.load(path), path=Path(path), driver=driver)

    # ── the corridor ───────────────────────────────────────────────────────

    def next(self) -> AnyRequest | None:
        """The screen to draw, or None when the interview is finished."""
        if self.state.step is SessionStep.DONE:
            return None

        # A pending request is one already asked and not yet answered. Handing it back rather
        # than recomposing is what makes resume free: the screen the user was looking at is
        # the screen they come back to, and no model call is repeated to rebuild it.
        if self.state.pending is not None:
            return self.state.pending

        request = self._compose()
        self.state.pending = request
        self._record("assistant", request.prompt)
        self.save()
        return request

    def respond(self, response: AnyResponse) -> None:
        """Apply a response, then persist. The save is the last thing that happens."""
        request = self.state.pending
        if request is None:
            raise RuntimeError("respond() called with nothing pending.")

        self._record("user", _describe(response))
        _mark_chosen(request, response)
        _record_answer(request, response)

        step_before = self.state.step
        self.state.resolve_pending()

        if self._driver is not None:
            self._driver.handle(self.state, request, response)

        # A screen is answered when it is left, not when it is replied to. If the step did
        # not move and the driver composed nothing, the user toggled something on the screen
        # they are still looking at — so drop the receipt and let `next()` rebuild that same
        # screen with the toggle showing. Keeping it would put two copies of one screen in
        # the conversation, the first of them greyed out for no reason the user can see.
        #
        # This is for *choice* screens only, where "toggle then recompose in place" is the
        # mechanism. A chat or form turn is a real exchange, not a toggle — and clarify holds
        # the step still on purpose (the answer goes to history and the next question is
        # composed), so a chat receipt looks identical to a tick here. Popping it would
        # discard the whole turn, which is exactly why the clarify conversation was never
        # shown. Those receipts stay.
        if (
            isinstance(request, ChoiceRequest)
            and self.state.step is step_before
            and self.state.pending is None
        ):
            self.state.requests.pop()

        self.save()

    def back(self, step: SessionStep) -> None:
        """`← Back` is an assignment, not a mechanism.

        Nothing is truncated and nothing is replayed. What happens to work written against
        an older version of a node is decided separately, by the edit cascade — not here.

        The screen being left stays in the conversation as a receipt. Removing it would be a
        second mechanism, and it would make the transcript claim the user never went there.
        """
        self.state.step = step
        self.state.pending = None
        self.save()

    # ── what a door may read ───────────────────────────────────────────────

    def profile(self) -> ProductProfile:
        """For drawing the read-only document pane. Not needed to render a request."""
        return self.state.profile

    def busy_message(self) -> str:
        """Finished package copy for work started from the current phase."""
        from metis.wizard.application.interview import status_for

        return status_for(self.state.step)

    # ── internals ──────────────────────────────────────────────────────────

    def _compose(self) -> AnyRequest:
        if self._driver is None:
            raise RuntimeError(
                "This session has no driver, so it cannot compose a screen. "
                "Pass one to Session.start() or Session.resume()."
            )
        return self._driver.compose(self.state)

    def _record(self, role: str, text: str) -> None:
        if text:
            self.state.history.append(Turn(role=role, text=text))  # type: ignore[arg-type]

    def save(self) -> None:
        if self.path is not None:
            self.state.save(self.path)


def _mark_chosen(request: AnyRequest, response: AnyResponse) -> None:
    """Record what was picked, on the request itself.

    A receipt has to say what was chosen, or a greyed screen reading "Looks right · Chat
    about it · I'll add one" tells the reader nothing. The alternative is persisting the
    response beside the request, which is a second record of one fact. `Option.selected`
    already exists and already means "this one", so the request answers for itself.
    """
    selected = set(getattr(response, "selected", None) or [])
    if not selected:
        return

    for key, option in options_of(request).items():
        if key in selected:
            option.selected = True


def _record_answer(request: AnyRequest, response: AnyResponse) -> None:
    """Stamp the user's own words onto the request they answered.

    A choice marks the chosen `Option.selected` and so describes itself when redrawn; a chat
    and a form have no option to mark, so the reply is recorded on the request instead. Without
    this, a resolved chat block shows the question with nothing beneath it — the whole clarify
    exchange reads as one-sided, because the transcript is drawn from the requests alone and a
    `ChatRequest` carries only its prompt.
    """
    if isinstance(request, ChatRequest) and isinstance(response, ChatResponse):
        request.answer = response.text
    elif isinstance(request, FormRequest) and isinstance(response, FormResponse):
        request.answer = dict(response.values)


def _describe(response: AnyResponse) -> str:
    """The transcript line for a response.

    A choice is an event rather than a message, so it gets the option ids it carried —
    enough to reconstruct what the user did without pretending they typed a sentence.
    """
    text = getattr(response, "text", None)
    if text is not None:
        return str(text)
    values = getattr(response, "values", None)
    if values:
        return "; ".join(f"{k}: {v}" for k, v in values.items())
    selected = getattr(response, "selected", None)
    if selected is not None:
        return ", ".join(selected)
    return ""
