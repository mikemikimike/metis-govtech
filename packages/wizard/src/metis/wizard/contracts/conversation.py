"""The contract between this package and whatever is driving it.

A CLI, an HTTP server and a pytest fixture all drive the same lifecycle: start with the user's
description, then send each typed answer in an `InterviewTurnRequest`.

`render` is the only thing a door implements, and a door never learns the domain. It does not
know what a behaviour, a criterion or a persona is — it draws rows, checkboxes, buttons and
text, and sends back what was clicked. Everything it renders arrives as *finished text*: the
package composes every sentence, including notes, warnings and totals. Two doors therefore
cannot drift, because neither knows enough to disagree.

The cost, named: the package owns wording. A door wanting different phrasing — or another
language — changes the package, not itself. One place to change beats two doors quietly
saying different things.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

# `Option.patch` and `WizardRequest.stage` are Pydantic fields, so `Patch` and `InterviewStep`
# must be runtime imports — Pydantic resolves the annotation at runtime and a TYPE_CHECKING-only
# import leaves the nesting models "not fully defined". See AGENTS.md — Coding Conventions.
from metis.wizard.domain.patch import Patch
from metis.wizard.domain.permissions import InterviewStep
from metis.wizard.domain.types import InteractionType

# ── what the user clicked ──────────────────────────────────────────────────


class OptionId(BaseModel):
    """What the user clicked, as an action and what it applies to.

    Opaque to the door, which sends back whatever it was handed. The package dispatches on
    `action` and is passed `target` — so a per-card action arrives as ("chat", "EB-1")
    rather than a string the package has to parse its own convention out of. `via` is the
    second reference the chip toggles need: ("cover", "S-1", via="EB-4") is "S-1 covers EB-4".
    """

    action: str  # "chat" · "tick" · "cover" · "continue"
    target: str | None = None  # "EB-1" · "S-1"
    via: str | None = None  # "EB-4" · "P-2"

    def __str__(self) -> str:  # doors use the action and references as the option key
        return ":".join(p for p in (self.action, self.target, self.via) if p)

    def __hash__(self) -> int:
        return hash((self.action, self.target, self.via))


class Option(BaseModel):
    """Shared — deliberately unprefixed.

    `Option` appears on `ChoiceRequest`, on `Card` and on `Warning`, so tying its name to any
    one of them would be misleading.
    """

    id: OptionId
    label: str
    patch: Patch | None = None  # chips and ticks carry their own patch — no model call
    selected: bool | None = None  # a toggleable chip when set, a plain button when None
    primary: bool = False  # a hint — the door decides what emphasis means
    enabled: bool = True  # a disabled Continue is still shown, marked unavailable


class FormField(BaseModel):
    """A typed control whose submitted value is transported as text."""

    id: str
    label: str
    placeholder: str = ""
    multiline: bool = True
    input_type: Literal["string", "integer", "number", "boolean"] = "string"
    value: str = ""
    required: bool = False
    choices: list[str] = Field(default_factory=list)
    help: str = ""
    group: str | None = None


# ── what a card is made of ─────────────────────────────────────────────────


class CardComponentType(StrEnum):
    TEXT = "text"
    OPTIONS = "options"
    NUMBER = "number"
    UPLOAD = "upload"
    DIVIDER = "divider"
    DISCLOSURE = "disclosure"


class CardComponent(BaseModel):
    """Everything inside a card is one ordered list, so the package controls what sits above
    what — "text, then chips, then more text" is expressible.

    The subclasses are discriminated by **shape, never by domain**: the door tells a stepper
    from a chip row, and cannot tell a behaviour from a persona. That distinction lives in
    `label`, which is finished text.
    """

    label: str | None = None  # "Covers" · "Run as" · "Trials" · "Files"


class CardText(CardComponent):
    type: Literal[CardComponentType.TEXT] = CardComponentType.TEXT
    text: str


class CardDisclosure(CardComponent):
    type: Literal[CardComponentType.DISCLOSURE] = CardComponentType.DISCLOSURE
    items: list[CardText] = Field(default_factory=list)


class CardOptionGroup(CardComponent):
    type: Literal[CardComponentType.OPTIONS] = CardComponentType.OPTIONS
    options: list[Option] = Field(default_factory=list)  # each with `selected` set


class CardNumberField(CardComponent):
    type: Literal[CardComponentType.NUMBER] = CardComponentType.NUMBER
    id: OptionId
    value: int
    min: int = 1  # validation is the package's business, enforced door-side too
    max: int = 20


class CardUploadField(CardComponent):
    type: Literal[CardComponentType.UPLOAD] = CardComponentType.UPLOAD
    id: OptionId
    value: list[str] = Field(default_factory=list)  # ["policy.pdf", "faq.md"]
    available: list[str] = Field(default_factory=list)

    @field_validator("value", mode="before")
    @classmethod
    def _load_legacy_value(cls, value: object) -> object:
        """Read the old comma-joined wire form while writing the structured form."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class CardDivider(CardComponent):
    """Separate adjacent groups in a card."""

    type: Literal[CardComponentType.DIVIDER] = CardComponentType.DIVIDER


CardFieldValue: TypeAlias = StrictInt | list[StrictStr]


AnyCardComponent: TypeAlias = Annotated[
    CardText
    | CardOptionGroup
    | CardNumberField
    | CardUploadField
    | CardDivider
    | CardDisclosure,
    Field(discriminator="type"),
]


# ── cards ──────────────────────────────────────────────────────────────────


class Card(BaseModel):
    """`Card` holds one hundred percent of the data.

    The subclasses pin their narrow fields and carry a stable wire discriminator. The door still
    renders both through one shape-driven path; the discriminator exists so Pydantic can preserve
    subtype-only fields such as a scenario's trial count across HTTP and interview persistence.
    """

    # The base remains useful to shape-only helpers. Concrete cards narrow this to a Literal so
    # `ChoiceRequest.cards` can use a discriminated union without making the renderer branch on it.
    kind: str = "standard"
    id: str  # package bookkeeping — never comes back in a response
    title: str
    section: str | None = (
        None  # "Answer quality" — a feature's bare name, a heading above this card
    )
    selected: bool | None = None  # a checkbox when set; none when None
    components: list[AnyCardComponent] = Field(default_factory=list)
    options: list[Option] = Field(default_factory=list)  # actions scoped to this card
    note: str | None = None  # an empty-state message — "not selected, no actions"
    blocking: bool = False  # this card is why Continue is disabled


class BehaviourCard(Card):
    """The behaviours and criteria steps. On behaviours it carries the measurement tick — review
    and the "which do we measure" ask are one screen — and at criteria its components are its
    criteria and its options are scoped to its behaviour.

    `selected` keeps the base's `bool | None`: a bool on both steps, reflecting the measured
    state a checkbox draws. A door draws no box only for `None`, which no live Behaviour card
    now sets."""

    kind: Literal["standard"] = "standard"  # pyright: ignore[reportIncompatibleVariableOverride]


class ScenarioCard(Card):
    """The scenarios step. Components start with description, then Covers, Run as, Trials, Files."""

    kind: Literal["scenario"] = "scenario"  # pyright: ignore[reportIncompatibleVariableOverride]
    # The value is carried as data so both doors can state the unit at the point they draw it.
    trials: int
    # Narrowed deliberately: a scenario never has a tick. See BehaviourCard for why the ignore.
    selected: None = None  # pyright: ignore[reportIncompatibleVariableOverride]


AnyCard: TypeAlias = Annotated[
    BehaviourCard | ScenarioCard,
    Field(discriminator="kind"),
]


# ── warnings ───────────────────────────────────────────────────────────────


class WarningSource(StrEnum):
    DOCUMENT = "document"  # a failed check over the Specification
    RUNTIME = "runtime"  # something the wizard or a service did


class Warning(BaseModel):
    """Something the user is told.

    DOCUMENT warnings are recomputed every time a screen is composed, so they clear
    themselves and nothing carries a stale flag. RUNTIME warnings are events — attached once,
    by whatever handled the event.

    `source` is what lets a door say "your document needs this" differently from "we had a
    problem", which matters: rendering an outage identically to a gate reads as blaming the
    user for it.
    """

    text: str  # finished text
    source: WarningSource = WarningSource.DOCUMENT
    blocking: bool = False  # stop, versus advisory note
    options: list[Option] = Field(default_factory=list)  # actionable fixes, if any


# ── outgoing ───────────────────────────────────────────────────────────────


class WizardRequestState(StrEnum):
    """Live, or already answered.

    A terminal never needed this: it draws a screen, the screen scrolls away, and what is on
    top is what you answer. A door that keeps the conversation on screen does need it — a
    resolved request is still visible, and must not be answerable twice.

    It is deliberately not a door concern. Both doors read the same flag, so neither can
    decide on its own that an answered screen is still live.
    """

    PENDING = "pending"
    RESOLVED = "resolved"


def _require_turn_metadata(schema: dict[str, object]) -> None:
    """Expose pending turn metadata as required and non-null in client schemas.

    Screen builders use the same models before the turn binder has the final stage and request
    identity. The pending-state boundary rejects that temporary form. The wire schema must describe
    the boundary form, not the internal draft form.
    """
    required = schema.setdefault("required", [])
    if isinstance(required, list):
        for name in ("request_id", "stage"):
            if name not in required:
                required.append(name)

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for name in ("request_id", "stage"):
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict):
            continue
        variants = property_schema.get("anyOf")
        if isinstance(variants, list):
            non_null = next(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, dict) and variant.get("type") != "null"
                ),
                None,
            )
            if isinstance(non_null, dict):
                property_schema.clear()
                property_schema.update(non_null)
        property_schema.pop("default", None)


class WizardRequest(BaseModel):
    """Base — what every request shares.

    `title`, `step` and `steps` are a one-directional projection of the driver's current stage.
    The package stamps where the interview is so a door can show it, and they never come back in
    a response. They live on the base, not on `ChoiceRequest`, so a chat question and an
    add-your-own form carry a header too. Screen builders may leave these unset until the request
    becomes pending.

    A door reads these; it does not derive them. Reading the interview stage door-side would
    mean the door learning that `BEHAVIOURS` exists and what to call it — the one thing the
    contract keeps it from knowing.

    `request_id` and `stage` are the turn contract's control fields, distinct from the three
    presentation fields above. `request_id` is opaque and fresh for every composed or recomposed
    request; an `InterviewTurnRequest` must carry the same one, which is what detects a late or
    duplicated answer. `stage` is the `InterviewStep` that owns the request and is authoritative
    while the request is pending — the client-held state stores the stage nowhere else. Both are
    stamped when a request becomes the pending one, so a screen builder never sets them.
    """

    prompt: str
    title: str | None = None  # "Behaviours" — finished text, for a header
    step: int | None = None  # 1-based position of this step in the interview
    steps: int | None = None  # how many steps the interview has
    state: WizardRequestState = WizardRequestState.PENDING
    request_id: str | None = None  # opaque, fresh per composition — "req-<uuid>"
    stage: InterviewStep | None = None  # the step that owns this pending request

    model_config = ConfigDict(json_schema_extra=_require_turn_metadata)


class ChatRequest(WizardRequest):
    type: Literal[InteractionType.CHAT] = InteractionType.CHAT
    multiline: bool = False
    # Which node this exchange is scoped to, when a per-card action raised it — a behaviour id
    # such as "EB-1". Application context, not a door concern: both doors transport it opaquely
    # and still branch only on request shape. The package reads it back to keep a targeted edit
    # scoped after an HTTP round trip or a resume, so a persisted follow-up cannot silently
    # widen. Optional with an empty default, so a screen-level chat carries nothing and an
    # older version-2 interview validates without a format bump.
    target: str | None = None
    # What the user typed, stamped on when the request resolves. A choice records what was
    # picked by marking the chosen `Option.selected`; a chat has no option to mark, so the
    # reply is recorded here instead — the same principle that the request answers for itself,
    # rather than a door reading a parallel transcript. Empty while pending; additive with a
    # default so an older persisted request validates and a door that ignores it is unchanged.
    answer: str = ""


class ChoiceRequest(WizardRequest):
    type: Literal[InteractionType.CHOICE] = InteractionType.CHOICE
    options: list[Option] = Field(default_factory=list)  # replies, Continue, Back
    multi: bool = False  # may several be sent together?
    cards: list[AnyCard] = Field(
        default_factory=list
    )  # when set, options grouped into rows
    warnings: list[Warning] = Field(default_factory=list)
    footer: str | None = None  # finished text — "Total: 9 trials"
    instruction: str | None = None  # finished text explaining how to answer this screen


class FormRequest(WizardRequest):
    type: Literal[InteractionType.FORM] = InteractionType.FORM
    fields: list[FormField]
    # Which parent this form writes into, when a per-card action raised it — an opaque id such
    # as "F-1" or "EB-1". Both doors carry it unchanged. The package reads it back so a manual
    # child stays under the parent whose card offered the action, including across a reload.
    # It is optional for screen-level forms.
    target: str | None = None
    # The values the user submitted, stamped on at resolve — the form's analogue of a chat's
    # `answer`, keyed by field id. Empty while pending; additive with a default.
    answer: dict[str, str] = Field(default_factory=dict)


# `Literal[InteractionType.CHAT]` rather than the bare enum is Pydantic machinery: for it to
# rebuild the right subclass when loading an interview file, each subclass's `type` must be a
# *distinct* type. Annotating all three as `InteractionType` makes them indistinguishable.
AnyRequest: TypeAlias = Annotated[
    ChatRequest | ChoiceRequest | FormRequest,
    Field(discriminator="type"),
]


def options_of(request: AnyRequest) -> dict[str, Option]:
    """Every option a screen offered, keyed the way a door sends it back.

    Options hide in four places — the screen, its warnings, each card, and the chip groups
    inside a card — and anything reasoning about what was clicked needs all four. Keeping the
    walk next to the models means it cannot fall behind them when a fifth place appears.
    """
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
            if isinstance(component, CardOptionGroup):
                for option in component.options:
                    add(option)
    return found


def editable_fields_of(
    request: AnyRequest,
) -> dict[str, CardNumberField | CardUploadField]:
    """Every value-bearing card component a choice request actually offered.

    This deliberately stays separate from :func:`options_of`: a field is an input, not a
    toggle or a navigation reply, even though both use the ``OptionId`` string form.
    """
    found: dict[str, CardNumberField | CardUploadField] = {}
    if not isinstance(request, ChoiceRequest):
        return found

    for card in request.cards:
        for component in card.components:
            if isinstance(component, (CardNumberField, CardUploadField)):
                found[str(component.id)] = component
    return found


# ── incoming ───────────────────────────────────────────────────────────────


class UserResponse(BaseModel):
    """Base. Named after who sends it — `UserRequest` would read as a request *from* the
    user, which is backwards."""


class ChatResponse(UserResponse):
    type: Literal[InteractionType.CHAT] = InteractionType.CHAT
    text: str


class ChoiceResponse(UserResponse):
    type: Literal[InteractionType.CHOICE] = InteractionType.CHOICE
    selected: list[str] = Field(default_factory=list)  # option ids, whatever they were
    values: dict[str, CardFieldValue] = Field(default_factory=dict)


class FormResponse(UserResponse):
    type: Literal[InteractionType.FORM] = InteractionType.FORM
    values: dict[str, str] = Field(default_factory=dict)  # field id → what was typed


AnyResponse: TypeAlias = Annotated[
    ChatResponse | ChoiceResponse | FormResponse,
    Field(discriminator="type"),
]

# Requests and responses pair by name and by value: ChatRequest ↔ ChatResponse,
# ChoiceRequest ↔ ChoiceResponse, FormRequest ↔ FormResponse. One enum value each, nothing
# left over — and nothing carries both `selected` and `text`, which is what forces a screen
# to offer either cards or a text box, never both.
