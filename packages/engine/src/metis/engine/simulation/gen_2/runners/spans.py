"""The user's own words, kept verbatim.

The user agent puts text meant for the target between ``⟦`` and ``⟧``. Before the runner
agent sees the action, code numbers each span ``{{1}}``, ``{{2}}``, ...; the agent writes
those placeholders where the user's text goes, and code substitutes the exact span. The
agent can place the user's words but never write them, which is what lets the record say
they reached the target word for word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .rules import ToolRefused

OPEN, CLOSE = "⟦", "⟧"
_SPAN = re.compile(re.escape(OPEN) + r"(.*?)" + re.escape(CLOSE), re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")


@dataclass
class Spans:
    """The quoted spans of one action, and which of them reached the target."""

    action: str
    texts: list[str]
    sent: set[int] = field(default_factory=set)
    """1-based numbers of the spans substituted into a request."""

    @classmethod
    def of(cls, action: str) -> Spans:
        return cls(action, [m.group(1) for m in _SPAN.finditer(action)])

    @property
    def masked(self) -> str:
        """The action as the runner agent sees it, each span replaced by its number."""
        numbers = iter(range(1, len(self.texts) + 1))
        return _SPAN.sub(lambda _: f"{{{{{next(numbers)}}}}}", self.action)

    def substitute_text(self, text: str) -> str:
        """``text`` with each placeholder replaced by its span.

        :raises ToolRefused: When a placeholder names no span.
        """
        for found in _PLACEHOLDER.findall(text):
            if not 1 <= int(found) <= len(self.texts):
                raise ToolRefused(
                    f"{{{{{found}}}}} names no quoted span; "
                    f"the action has {len(self.texts)}"
                )
        self.sent |= {int(n) for n in _PLACEHOLDER.findall(text)}
        return _PLACEHOLDER.sub(lambda m: self.texts[int(m.group(1)) - 1], text)

    def substitute(self, value: Any) -> Any:
        """Substitute every placeholder in a JSON-like value."""
        if isinstance(value, str):
            return self.substitute_text(value)
        if isinstance(value, list):
            return [self.substitute(v) for v in value]
        if isinstance(value, dict):
            return {k: self.substitute(v) for k, v in value.items()}
        return value
