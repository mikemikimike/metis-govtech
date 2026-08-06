"""Ring buffer for the TUI log tail panel."""

from __future__ import annotations

import logging
from collections import deque

from rich.text import Text


class TailBuffer:
    """Fixed-capacity ring buffer that filters log lines by level."""

    def __init__(self, max_lines: int = 15, min_level: int = logging.WARNING) -> None:
        self._max_lines = max_lines
        self._min_level = min_level
        self._lines: deque[Text | str] = deque(maxlen=max_lines)

    def append(self, line: Text | str, level: int = logging.INFO) -> None:
        if level >= self._min_level:
            self._lines.append(line)

    def set_min_level(self, level: int) -> None:
        self._min_level = level

    def get_lines(self) -> list[str]:
        """Return lines as plain strings (for non-TUI consumers and tests)."""
        return [line.plain if isinstance(line, Text) else line for line in self._lines]

    def get_entries(self) -> list[Text | str]:
        """Return entries (Text or str) for rendering."""
        return list(self._lines)

    def clear(self) -> None:
        self._lines.clear()
