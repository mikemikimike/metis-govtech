"""Rich Live + Layout composition for the TUI control plane."""

from __future__ import annotations

from types import TracebackType

from rich.console import Console, ConsoleOptions, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .dashboard import render_dashboard
from .state import SimulationState
from .tail import TailBuffer


class _LiveTailRenderable:
    """Renderable that reads from the tail buffer at render time.

    The buffer stores pre-styled Rich Text objects (built by format_log_text
    with the same styling as core's _rich_console_renderer).
    """

    def __init__(self, tail_buffer: TailBuffer) -> None:
        self._tail_buffer = tail_buffer

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        entries = self._tail_buffer.get_entries()
        if not entries:
            yield Text("(no log output)", style="dim")
            return
        output = Text()
        for i, entry in enumerate(entries[-15:]):
            if i > 0:
                output.append("\n")
            if isinstance(entry, Text):
                output.append_text(entry)
            else:
                output.append(entry)
        yield output


_active: bool = False


def is_tui_active() -> bool:
    return _active


def _create_live(layout: Layout, console: Console) -> Live:
    return Live(layout, console=console, refresh_per_second=2, screen=False)


class _LiveDashboardRenderable:
    """Renderable that re-renders the dashboard from current state on every frame."""

    def __init__(self, state: SimulationState) -> None:
        self._state = state

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield render_dashboard(self._state)


class TUIContext:
    """Context manager that owns the Rich Live display."""

    def __init__(self, state: SimulationState, tail_buffer: TailBuffer) -> None:
        self._state = state
        self._tail_buffer = tail_buffer
        self._console = Console(stderr=True)
        self._layout = Layout()
        self._layout.split_column(
            Layout(name="dashboard", ratio=2),
            Layout(name="tail", ratio=3),
        )
        # Set panels to live renderables that read current state on every frame
        self._layout["dashboard"].update(
            Panel(
                _LiveDashboardRenderable(state),
                title="Dashboard",
                border_style="blue",
            )
        )
        self._layout["tail"].update(
            Panel(
                _LiveTailRenderable(tail_buffer),
                title="Log Tail",
                border_style="dim",
            )
        )
        self._live: Live | None = None

    def __enter__(self) -> TUIContext:
        global _active
        _active = True
        self._live = _create_live(self._layout, self._console)
        self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        global _active
        _active = False
        if self._live:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None

    def refresh(self) -> None:
        """Force an immediate refresh of the Live display."""
        if self._live:
            self._live.refresh()
