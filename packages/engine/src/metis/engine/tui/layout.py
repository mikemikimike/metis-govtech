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
    """Renderable for a single worker's tail buffer."""

    def __init__(self, tail_buffer: TailBuffer) -> None:
        self._buf = tail_buffer

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        entries = self._buf.get_entries()
        max_lines = max(1, (options.height or 10) - 1)
        entries = entries[-max_lines:]

        if not entries:
            yield Text("(waiting for output)", style="dim")
            return

        output = Text()
        for i, entry in enumerate(entries):
            if i > 0:
                output.append("\n")
            if isinstance(entry.content, Text):
                output.append_text(entry.content)
            else:
                output.append(entry.content)
        yield output


_active: bool = False


def is_tui_active() -> bool:
    return _active


def _create_live(layout: Layout, console: Console) -> Live:
    return Live(layout, console=console, refresh_per_second=1, screen=True)


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

    def __init__(
        self, state: SimulationState, tail_buffers: dict[str, TailBuffer]
    ) -> None:
        self._state = state
        self._tail_buffers = tail_buffers
        self._console = Console(stderr=True)

        self._layout = Layout()

        # Build tail section: one panel per worker, stacked vertically
        sorted_keys = sorted(tail_buffers.keys())
        tail_panels = [Layout(name=f"tail-{k}") for k in sorted_keys]

        if len(tail_panels) == 1:
            tail_section = Layout(name="tail", ratio=3)
            tail_section.update(
                Panel(
                    _LiveTailRenderable(tail_buffers[sorted_keys[0]]),
                    title="Log Tail",
                    border_style="dim",
                )
            )
        else:
            tail_section = Layout(name="tail", ratio=3)
            tail_section.split_column(*tail_panels)
            for key, panel_layout in zip(sorted_keys, tail_panels, strict=True):
                panel_layout.update(
                    Panel(
                        _LiveTailRenderable(tail_buffers[key]),
                        title=key,
                        border_style="dim",
                    )
                )

        self._layout.split_column(
            Layout(name="dashboard", ratio=2),
            tail_section,
        )
        self._layout["dashboard"].update(
            Panel(
                _LiveDashboardRenderable(state),
                title="Dashboard",
                border_style="blue",
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
