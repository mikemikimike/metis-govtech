"""CLI input for the interview opening fields."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from metis.wizard.application.config import load_config
from metis.wizard.contracts.interview_state import CapabilityConfidence

if TYPE_CHECKING:
    from metis.wizard.contracts.capabilities import CapabilityId

Printer = Callable[[str], None]
Reader = Callable[[str], str]


def read_description(*, out: Printer, read: Reader = input) -> str:
    """Ask the package opening question until the user gives a description."""
    question = load_config().opening_question
    while True:
        description = read(f"\n{question}\n> ").strip()
        if description:
            return description
        out("  Enter a description of the target.")


def read_capability_evidence(
    *, out: Printer, read: Reader = input
) -> tuple[list[CapabilityId], CapabilityConfidence]:
    """Show the capability catalogue and read the required opening evidence."""
    categories = load_config().capability_categories
    choices: list[tuple[CapabilityId, str]] = []
    out("\nKnown capabilities (select any that you know the target has):")
    for category in categories:
        out(f"\n{category.name}")
        out("─" * len(category.name))
        for capability in category.capabilities:
            choices.append((capability.id, capability.name))
            out(
                f"  {len(choices)}. {capability.name} ({capability.id.value})"
                f" — {capability.description}"
            )

    by_number = {
        str(index): capability_id for index, (capability_id, _) in enumerate(choices, 1)
    }
    by_name = {name.casefold(): capability_id for capability_id, name in choices}
    by_id = {
        capability_id.value.casefold(): capability_id for capability_id, _ in choices
    }
    while True:
        raw = read(
            "\nKnown capabilities (comma-separated numbers or names; blank for none): "
        ).strip()
        if not raw:
            selected: list[CapabilityId] = []
            break
        selected = []
        unknown: list[str] = []
        for token in (part.strip() for part in raw.split(",")):
            if not token:
                continue
            capability_id = (
                by_number.get(token)
                or by_name.get(token.casefold())
                or by_id.get(token.casefold())
            )
            if capability_id is None:
                unknown.append(token)
            elif capability_id not in selected:
                selected.append(capability_id)
        if unknown:
            out("  Choose only the numbered, named, or id values shown above.")
            continue
        break

    while True:
        raw = (
            read(
                "How confident are you that this selection covers all capabilities? "
                "(low/medium/high): "
            )
            .strip()
            .casefold()
        )
        try:
            confidence = CapabilityConfidence(raw)
        except ValueError:
            out("  Enter low, medium, or high.")
            continue
        return selected, confidence
