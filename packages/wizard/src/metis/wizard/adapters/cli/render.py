"""The CLI door.

Nothing in this file names a behaviour, a criterion, a task, a persona or a step. It
branches on request type and on `CardComponentType` — a stepper is not a chip row — and on
nothing else. A web door replaces the prints with components and is otherwise the same
function.

Every string displayed here arrived as finished text. The door adds punctuation and layout;
it never composes a sentence about the domain.
"""

from __future__ import annotations

from collections.abc import Callable

from metis.wizard.application.trials import format_trials
from metis.wizard.contracts.conversation import (
    AnyRequest,
    AnyResponse,
    Card,
    CardComponentType,
    CardNumberField,
    CardUploadField,
    ChatRequest,
    ChatResponse,
    ChoiceRequest,
    ChoiceResponse,
    FormRequest,
    FormResponse,
    Option,
)

Printer = Callable[[str], None]
Reader = Callable[[str], str]


def _header(request: AnyRequest, out: Printer) -> None:
    """Draw the step header, if the request carries one.

    The title and position are finished values the package stamped — the door formats them
    into a panel and composes no sentence about the domain. A request with no metadata (an
    older session, or any unstamped request) draws nothing, so the body renders exactly as it
    did before this change.

    The panel is rendered to text through `out` rather than printed straight to a terminal,
    so a test that injects `out` still captures it and a redirected run degrades cleanly:
    a captured Rich console detects it is not a terminal and emits no control sequences. The
    console sizes the panel to the terminal rather than a fixed width.
    """
    if request.title is None and request.step is None:
        return

    from rich.console import Console
    from rich.panel import Panel

    position = (
        f"step {request.step} of {request.steps}"
        if request.step is not None and request.steps is not None
        else None
    )

    console = Console()
    with console.capture() as capture:
        console.print(Panel(request.title or "", subtitle=position))
    out(capture.get().rstrip("\n"))


def _divider(out: Printer) -> None:
    """Separate the per-card choices above from the interview choices below.

    Drawn only when a screen has cards — a screen that is nothing but replies has no two
    regions to hold apart.
    """
    from rich.console import Console
    from rich.rule import Rule

    console = Console()
    with console.capture() as capture:
        console.print(Rule())
    out(capture.get().rstrip("\n"))


def _checkbox(selected: bool | None) -> str:
    if selected is None:
        return ""
    return "[x] " if selected else "[ ] "


def _ref(option: Option) -> str:
    """The item a choice applies to, without the action verb.

    Displayed beside a choice so a user can see *which* behaviour or scenario a repeated label
    ("Chat about it") belongs to. The verb (`chat`, `tick`, `cover`) is machinery the user
    never types — the number selects — so it is dropped from the display. Selection still
    keys on the full `str(option.id)`, so a typed key like `chat:EB-6` keeps working.
    A screen-level reply (`accept`, `continue`, `back`) has no target and shows nothing.
    """
    return ":".join(p for p in (option.id.target, option.id.via) if p)


def _choice_line(
    option: Option,
    selectable: dict[str, Option],
    *,
    indent: str,
    mark: str = "",
) -> str:
    """Register an enabled choice and draw its stable number plus the item it applies to."""
    key = str(option.id)
    suffix = "" if option.enabled else "   (unavailable)"
    if not option.enabled:
        return f"{indent}— {mark}{option.label}{suffix}"

    if key not in selectable:
        selectable[key] = option
    number = list(selectable).index(key) + 1
    ref = _ref(option)
    tag = f"  ({ref})" if ref else ""
    return f"{indent}{number}. {mark}{option.label}{tag}{suffix}"


def _draw_card(
    card: Card,
    out: Printer,
    selectable: dict[str, Option],
    editable: dict[str, CardNumberField | CardUploadField] | None = None,
    field_numbers: dict[str, int] | None = None,
) -> None:
    # Indented one level under its section heading, so the cards read as a list rather than a
    # wall of sentences. A card with a checkbox (`[x]`/`[ ]`) already reads as an item; one
    # without gets a bullet so it still does.
    box = _checkbox(card.selected)
    bullet = "" if box else "• "
    out(f"\n  {box}{bullet}{card.title}")

    for component in card.components:
        if component.label:
            out(f"    {component.label}")

        match component.type:
            case CardComponentType.DIVIDER:
                # A blank line between two component groups — the terminal's rule between a
                # behaviour's acceptance criteria, so a run of them does not read as one block.
                out("")
            case CardComponentType.TEXT:
                out(f"    - {component.text}")
            case CardComponentType.OPTIONS:
                for option in component.options:
                    mark = "[x] " if option.selected else "[ ] "
                    out(_choice_line(option, selectable, indent="      ", mark=mark))
            case CardComponentType.NUMBER:
                key = str(component.id)
                if editable is not None:
                    editable[key] = component
                number = (
                    f"{field_numbers[key]}. "
                    if field_numbers is not None and key in field_numbers
                    else ""
                )
                out(
                    f"      {number}({component.id}) {component.value}   "
                    f"[{component.min}–{component.max}]"
                )
                card_trials = getattr(card, "trials", None)
                if isinstance(card_trials, int):
                    out(f"      {format_trials(card_trials)}")
            case CardComponentType.UPLOAD:
                key = str(component.id)
                if editable is not None:
                    editable[key] = component
                number = (
                    f"{field_numbers[key]}. "
                    if field_numbers is not None and key in field_numbers
                    else ""
                )
                out(
                    f"      {number}({component.id}) {', '.join(component.value) or '—'}"
                )

    if card.note:
        out(f"    {card.note}")
    for option in card.options:
        out(_choice_line(option, selectable, indent="    "))


def _option_keys(request: ChoiceRequest) -> list[str]:
    """Return enabled option keys in the same order the screen numbers them."""
    keys: list[str] = []

    def add(option: Option) -> None:
        key = str(option.id)
        if option.enabled and key not in keys:
            keys.append(key)

    for card in request.cards:
        for component in card.components:
            for option in getattr(component, "options", []) or []:
                add(option)
        for option in card.options:
            add(option)
    for warning in request.warnings:
        for option in warning.options:
            add(option)
    for option in request.options:
        add(option)
    return keys


def _field_keys(request: ChoiceRequest) -> list[str]:
    keys: list[str] = []
    for card in request.cards:
        for component in card.components:
            # Only the value-bearing components carry an id; isinstance narrows to those so the
            # id access is type-safe as the component union grows (a divider, for one, has none).
            if isinstance(component, (CardNumberField, CardUploadField)):
                key = str(component.id)
                if key not in keys:
                    keys.append(key)
    return keys


def _draw(
    request: ChoiceRequest,
    out: Printer,
    editable: dict[str, CardNumberField | CardUploadField] | None = None,
) -> dict[str, Option]:
    """Draw a choice screen and return what may be selected."""
    selectable: dict[str, Option] = {}
    field_numbers = None
    if editable is not None:
        field_numbers = {
            key: len(_option_keys(request)) + index
            for index, key in enumerate(_field_keys(request), start=1)
        }

    section = None
    for card in request.cards:
        if card.section != section:  # a heading, whatever it happens to mean
            section = card.section
            if section:
                # Underlined with the section's own width so tasks stand apart from the
                # behaviours under them. Plain characters, so a redirected run stays readable.
                out(f"\n{section}")
                out("─" * len(section))
        _draw_card(card, out, selectable, editable, field_numbers)

    for warning in request.warnings:
        out(f"\n{'STOP' if warning.blocking else 'note'}  {warning.text}")
        for option in warning.options:
            out(_choice_line(option, selectable, indent="      "))

    if request.footer:
        out(f"\n{request.footer}")
    if request.instruction:
        out(f"\n{request.instruction}")

    # A divider holds the per-card choices apart from the replies that advance the interview —
    # but only when there are cards to hold apart.
    if request.cards and request.options:
        _divider(out)

    if request.options:
        out("")
    for option in request.options:
        # A disabled option is still shown, marked unavailable — hiding it would leave the
        # user wondering where Continue went.
        out(_choice_line(option, selectable, indent="  "))

    return selectable


def _read_nonblank(read: Reader, out: Printer, prompt: str) -> str:
    """Keep the current text prompt active until the user supplies an answer."""
    while True:
        value = read(prompt).strip()
        if value:
            return value
        out("  Please enter a response.")


def _read_multiline(read: Reader, out: Printer) -> str:
    """Read comment lines until an explicit marker ends the response.

    The `.done` marker is this reader's own input mechanic — blank lines are content here, so
    Enter cannot submit — so the reader states it, not the package. A door with a Send button
    (the web door) never sees this line and shows only the package's neutral prompt.
    """
    out("  Enter or paste as many lines as you need, then type .done on a new line.")
    lines: list[str] = []
    while True:
        value = read("> " if not lines else "| ").rstrip()
        if value.strip().casefold() == ".done":
            if any(line.strip() for line in lines):
                return "\n".join(lines).strip()
            out("  Please enter a response.")
            continue
        # Blank lines are content here: pasted lists and YAML commonly use them between
        # entries, which is why submission needs an explicit marker rather than Enter.
        lines.append(value)


def _read_number_field(
    field: CardNumberField, key: str, read: Reader, out: Printer
) -> ChoiceResponse:
    while True:
        raw = read(f"{field.label or 'Value'} ({field.min}–{field.max})\n> ").strip()
        try:
            value = int(raw)
        except ValueError:
            out(f"  Enter an integer from {field.min} to {field.max}.")
            continue
        if not number_within(value, field.min, field.max):
            out(f"  Enter an integer from {field.min} to {field.max}.")
            continue
        return ChoiceResponse(values={key: value})


def _read_file_field(field: CardUploadField, key: str, read: Reader) -> ChoiceResponse:
    raw = read(f"{field.label or 'Names'} (comma-separated; blank clears)\n> ")
    if not raw.strip():
        values: list[str] = []
    else:
        values = []
        for item in raw.split(","):
            name = item.strip()
            if name not in values:
                values.append(name)
    return ChoiceResponse(values={key: values})


def _discard_buffered_input(read: Reader) -> None:
    """Drop the rest of a mistaken multiline paste before showing the menu again."""
    if read is not input:
        return
    try:
        import sys
        import termios

        if sys.stdin.isatty():
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (ImportError, AttributeError, OSError):
        # Non-POSIX and redirected input have no terminal queue to clear.
        return


def render(
    request: AnyRequest,
    *,
    out: Printer = print,
    read: Reader = input,
    show_header: bool = True,
) -> AnyResponse:
    """Draw a request, collect input, return the matching response.

    `show_header` lets the caller suppress the panel when this request is a further screen of
    the step already on the terminal — several clarify questions, or a mid-step form, all sit
    under one step and repeating "step 1 of 6" above each adds noise. The default is to draw
    it, so a web door or a test that renders one request in isolation is unaffected.
    """
    # The header is drawn once, above the prompt. The choice loop below re-prompts on a bad
    # entry without coming back through here, so a correction never redraws the panel.
    if show_header:
        _header(request, out)
    out(f"\n{request.prompt}")

    if isinstance(request, ChatRequest):
        text = (
            _read_multiline(read, out)
            if request.multiline
            else _read_nonblank(read, out, "> ")
        )
        return ChatResponse(text=text)

    if isinstance(request, FormRequest):
        values = {}
        for field in request.fields:
            prompt = f"{field.label}"
            if field.placeholder:
                prompt += f" ({field.placeholder})"
            values[field.id] = read(f"{prompt}\n> ").strip()
        return FormResponse(values=values)

    editable: dict[str, CardNumberField | CardUploadField] = {}
    selectable = _draw(request, out, editable)
    ordered_keys = [*selectable, *editable]
    numbers = {str(index): key for index, key in enumerate(ordered_keys, start=1)}

    while True:
        prompt = (
            "\nChoose one or more (comma-separated numbers or names): "
            if request.multi
            else "\nChoose one (number or name): "
        )
        raw = read(prompt).strip()
        entered = [k for k in (part.strip() for part in raw.split(",")) if k]
        keys = list(dict.fromkeys(numbers.get(key, key) for key in entered))

        known = set(ordered_keys)
        unknown = [key for key in entered if numbers.get(key, key) not in known]
        if unknown:
            out("  This screen only accepts one of the menu choices above.")
            if request.instruction:
                out(f"  {request.instruction}")
            _discard_buffered_input(read)
            continue
        # Enforced door-side because the package said so on the wire: options composed by
        # the model can contradict each other, so only one may be sent.
        if not request.multi and len(keys) > 1:
            out("  Just one of those, please.")
            continue
        if not keys:
            out("  Pick one.")
            continue

        field_keys = [key for key in keys if key in editable]
        if field_keys:
            if len(keys) != 1:
                out(
                    "  Edit one field at a time; do not combine it with another choice."
                )
                continue
            key = field_keys[0]
            field = editable[key]
            if isinstance(field, CardNumberField):
                return _read_number_field(field, key, read, out)
            return _read_file_field(field, key, read)

        return ChoiceResponse(selected=keys)


def number_within(value: int, low: int, high: int) -> bool:
    """Stepper bounds, checked without contacting the package."""
    return low <= value <= high
