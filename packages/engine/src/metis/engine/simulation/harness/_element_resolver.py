"""Intent-based element resolution with fallback strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from metis.engine.simulation.exceptions import TransientDOMError

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


@dataclass(frozen=True)
class CSSStrategy:
    selector: str

    def locate(self, page: Page) -> Locator:
        return page.locator(self.selector)


@dataclass(frozen=True)
class AriaStrategy:
    role: str
    name: str

    def locate(self, page: Any) -> Any:
        return page.get_by_role(self.role, name=self.name)


@dataclass(frozen=True)
class TextStrategy:
    text: str

    def locate(self, page: Page) -> Locator:
        return page.get_by_text(self.text)


ElementStrategy: TypeAlias = CSSStrategy | AriaStrategy | TextStrategy


async def resolve_element(
    page: Page,
    *,
    intent: str,
    strategies: list[ElementStrategy],
    timeout_ms: int = 5000,
) -> Locator:
    """Try strategies in order, return the first visible+enabled locator.

    Raises TransientDOMError if no strategy finds a usable element.
    """
    for strategy in strategies:
        try:
            locator = strategy.locate(page).first
            if await locator.is_visible() and await locator.is_enabled():
                return locator
        except Exception:
            continue

    raise TransientDOMError(
        f"No strategy resolved a visible element for intent={intent!r}"
    )
