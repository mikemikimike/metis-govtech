"""The resumable control data of one interview — client-held, not package-owned.

`InterviewState` is a plain value. `handle_interview` (in the application layer) takes one
operation, applies it, and returns the next value. Nothing here reads or writes a file: a client
that wants to keep the interview between requests serializes this model to JSON and sends it back
on the next operation, so a CLI and a stateless HTTP server rehydrate mid-conversation the same way.

It carries only what the next operation needs: the Profile being built, the two explicit user
decisions (`behaviours_confirmed`, `confirmed`), the bounded clarification history, the authorship
bookkeeping, and at most one pending request. Where the interview *is* — its stage — is not stored:
it is derived from this evidence, or read from the pending request's own `stage`. See
`application.turn.derive_stage`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from metis.wizard.contracts.conversation import AnyRequest

# `profile` is a Pydantic field, so `ProductProfile` must be a runtime import — Pydantic
# resolves the annotation at runtime and a TYPE_CHECKING-only import leaves InterviewState
# "not fully defined". See CLAUDE.md — Coding Conventions.
from metis.wizard.domain.profile import ProductProfile

# The most recent clarification turns kept for model context. Older turns are trimmed after each
# accepted operation: they are prose the model no longer needs, not a display transcript a door
# must keep. A door that wants the full transcript keeps its own record outside this state.
HISTORY_LIMIT = 12


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class InterviewState(BaseModel):
    """One client-held value, serialized to JSON between turns.

    There is no `id`, `step`, resolved-request transcript, or file method. The pending request is
    the only structured request, and it carries its own stage; the stage is not duplicated here.
    """

    model_config = ConfigDict(extra="forbid")

    profile: ProductProfile
    # The measurement-scope lock. The combined Behaviour screen asks the user to pick the
    # behaviours worth measuring; its Continue sets this true. It is not a "the user saw the
    # screen" receipt — Criteria generation reads the measured subset it locks in, and any later
    # change to the Behaviour list or its measured selection clears it. There is deliberately no
    # `criteria_confirmed` or `personas_confirmed`; only the measured scope needs an explicit lock.
    behaviours_confirmed: bool = False
    # The final lock, set only by Continue on a ready Scenario screen or a successful finish. Any
    # accepted Profile mutation clears it, so an earlier approval can never sign off new content.
    confirmed: bool = False
    history: list[Turn] = Field(default_factory=list, max_length=HISTORY_LIMIT)
    # These sets belong to the interview, not to the portable ProductProfile artifact.
    user_typed: set[str] = Field(default_factory=set)
    issued_ids: set[str] = Field(default_factory=set)
    # The one live screen, or None between the finish and a fresh start. It carries its own
    # `request_id` and `stage`; the state stores neither separately.
    pending: AnyRequest | None = None

    @model_validator(mode="after")
    def _pending_has_turn_metadata(self) -> InterviewState:
        """Reject a client state that cannot bind its next response safely."""
        if self.pending is not None:
            if not self.pending.request_id:
                raise ValueError("pending.request_id is required")
            if self.pending.stage is None:
                raise ValueError("pending.stage is required")
        return self
