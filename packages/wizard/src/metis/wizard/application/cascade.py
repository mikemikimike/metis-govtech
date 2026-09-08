"""What an edit costs the work derived from it.

**Nothing is discarded silently. The wizard asks** — and it offers no opinion on whether the
derived content still holds. Judging that reliably is exactly the kind of call a model gets
quietly wrong, and a wrong silent judgement leaves criteria measuring wording that no longer
exists.

The critical property is *timing*. The question is asked and answered in the same turn, before
the next screen is composed. Nothing carries an "out of date" badge around the interface
afterwards and there is no state to track between turns — if the question could be deferred,
this would be staleness tracking, which is the thing the whole design avoids.

The rule underneath: **ask before discarding work a person could have shaped; redo the model's
own choices freely.**
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from metis.wizard.contracts.conversation import ChoiceRequest, Option, OptionId
from metis.wizard.domain.cascade import (
    Impact,
    impacts_for,
)
from metis.wizard.domain.cascade import (
    clear_for_regeneration as clear_impact,
)

if TYPE_CHECKING:
    from metis.wizard.domain.patch import Patch
    from metis.wizard.domain.profile import ProductProfile


@dataclass
class Question:
    """One thing to ask before moving on, and what to do with each answer."""

    text: str
    subject: str  # the node whose derived work is in question
    kind: str  # "criteria" | "scenario" | "tree"

    def to_request(self) -> ChoiceRequest:
        keep, redo, mine = {
            "criteria": ("They're fine", "Regenerate", "I'll edit them myself"),
            "scenario": ("It's fine", "Regenerate", "I'll edit it myself"),
            "tree": (
                "Keep the current draft",
                "Redraft from the new description",
                "Review the current draft",
            ),
        }[self.kind]
        mine_action = "review" if self.kind == "tree" else "edit"

        return ChoiceRequest(
            prompt=self.text,
            multi=False,
            options=[
                Option(
                    id=OptionId(action="keep", target=self.subject),
                    label=keep,
                    primary=True,
                ),
                Option(
                    id=OptionId(action="regenerate", target=self.subject), label=redo
                ),
                Option(
                    id=OptionId(action=mine_action, target=self.subject), label=mine
                ),
            ],
        )


# The three actions a cascade question always offers. `edit` and `review` are the two "I'll look
# myself" answers — a criteria/scenario question edits, a tree question reviews — so either marks
# the shape. `keep` and `regenerate` are always both present.
_CASCADE_ACTIONS = frozenset({"keep", "regenerate", "edit", "review"})


def question_from_request(request: object, profile: ProductProfile) -> Question | None:
    """Rebuild the cascade question a pending request represents, or None if it is not one.

    A cascade question is composed on one turn and answered on the next, but the driver is built
    fresh each turn and no longer holds the `pending_questions` list it used to route the answer
    through. So a turn reconstructs the question from the request the client sends back — the same
    three options `Question.to_request` emits — and reseeds the driver with it. Detection is by
    shape: a single-select choice whose options are exactly the cascade actions, with `keep` and
    `regenerate` both present. The kind follows the subject — a tree question carries `review`; a
    criteria question names a behaviour; a scenario question names a scenario.
    """
    if not isinstance(request, ChoiceRequest) or request.multi:
        return None
    actions = {option.id.action for option in request.options}
    if not ({"keep", "regenerate"} <= actions <= _CASCADE_ACTIONS):
        return None

    subject = next(
        (option.id.target for option in request.options if option.id.target), None
    )
    if subject is None:
        return None

    if "review" in actions:
        kind = "tree"
    elif profile.behaviour(subject) is not None:
        kind = "criteria"
    elif profile.scenario(subject) is not None:
        kind = "scenario"
    else:
        return None

    return Question(text=request.prompt, subject=subject, kind=kind)


def questions_for(profile: ProductProfile, patches: list[Patch]) -> list[Question]:
    """What to ask, in order, given what was just edited.

    `profile` is the document from before the patches. A product field written while the
    first tree is being drafted cannot invalidate that same draft — there was no older tree.

    Sequenced deliberately: criteria first, then each scenario covering the behaviour. The user
    answers about the thing nearest the edit before being asked about the thing further away.
    """
    asked: list[Question] = []
    for impact in impacts_for(profile, patches):
        if impact.kind == "tree":
            text = (
                "That changes the product description. The current draft came "
                "from the previous version — what should I do with that draft?"
            )
        elif impact.kind == "criteria":
            text = f"Done. Regenerate {impact.subject}'s acceptance criteria?"
        else:
            text = f"{impact.subject} covers {impact.related_to}. Regenerate that scenario?"
        asked.append(Question(text=text, subject=impact.subject, kind=impact.kind))
    return asked


def clear_for_regeneration(
    profile: ProductProfile, question: Question, user_typed: set[str] | None = None
) -> None:
    """Answering "Regenerate" lands in a state the screens already draw.

    A measured behaviour with no criteria is what the Behaviour step's Continue fills in; a
    behaviour no scenario covers is what the scenarios gate catches. Both were built for the forward
    pass and happen to be the landing pad for coming back.

    **Text the user typed survives.** IDs recorded in the interview's `user_typed` set came in
    through a form and are used as-is, so regenerating criteria rewrites model nodes and keeps
    those nodes.
    """
    clear_impact(
        profile,
        Impact(subject=question.subject, kind=question.kind),
        user_typed,
    )
