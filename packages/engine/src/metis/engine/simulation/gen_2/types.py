"""gen_2's interface types: what the user agent says, and what comes back."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class UserAgentOutput(BaseModel):
    """One turn's decision, as the user agent's LLM returns it."""

    reasoning: str = Field(
        description=(
            "What you observed and why you chose this action. It is not shown to the "
            "assistant."
        )
    )
    """Why the user chose this. Kept in the log, never shown to the target or the runner."""
    action: str = Field(
        description=(
            "One plain-language action. Anything you send to the assistant, the whole "
            "message, goes between ⟦ and ⟧, written the way your persona would type it, "
            "for example: ⟦How many leave days do I get?⟧. An action with no ⟦ ⟧ "
            "quoted message means nothing is sent."
        )
    )
    """One plain-language action. Text for the target sits between ``⟦`` and ``⟧``."""
    decision: Literal["continue", "goal_achieved", "giving_up"] = Field(
        description=(
            '"goal_achieved" when you have what you asked for; "giving_up" when the '
            "assistant keeps failing to make progress or your persona would give up; "
            '"continue" otherwise.'
        )
    )
    """Whether the user carries on, has what they wanted, or gives up."""

    @model_validator(mode="after")
    def _continue_needs_an_action(self) -> Self:
        if self.decision == "continue" and not self.action.strip():
            raise ValueError("a 'continue' decision needs an action")
        return self


class Reading(BaseModel):
    """The runner's own account of what its action did.

    An interpretation, not a fact: the user agent is told so. Whatever code can copy
    or measure belongs on :class:`Observation` instead.
    """

    outcome: str
    why: str
    next_options: str = ""
    """What the runner thinks the user could do next, if it has a view."""


class Observation(BaseModel):
    """What one ``Runner.act`` hands back, with facts kept apart from the reading."""

    reply: str | None
    """The target's reply, copied by code. ``None`` when no reply was shown."""
    reading: Reading
    promised: list[str] = Field(default_factory=list)
    """Names of files the reply promised, copied by code from it."""
    observed: bool = True
    """``False`` when nobody could check the target's state after the action."""
    notice: str | None = None
    """A problem METIS itself found with the turn, such as a timeout. Not the runner's."""
    submission_unresolved: bool = False
    """``True`` when a submission never settled, so the target cannot take another."""
    sent_nothing: bool = False
    """``True`` when the action tried to send a message but quoted none, so the runner
    refused the submission and none reached the target. The turn is not counted."""


class Promise(BaseModel, frozen=True):
    """A file the target said it would deliver."""

    name: str
    turn: int
    """The turn whose reply promised it."""
