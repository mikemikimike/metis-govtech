"""Routes structlog events to per-run log files and the TUI tail buffer.

When the TUI is active, the LogRouter replaces core's _rich_console_renderer
as the final processor in structlog's chain. It renders each event to:
1. Per-run log files (plain text or JSON — always at DEBUG)
2. The TUI tail buffer (styled Rich Text, same format as core's renderer)
3. Returns "" so structlog's PrintLogger writes nothing to stderr
   (Rich Live owns the terminal)
"""

from __future__ import annotations

import json as json_mod
import logging
import time
from pathlib import Path
from typing import IO, Any, Literal

import structlog
from rich.text import Text
from structlog.types import EventDict

from metis.engine.tui.tail import TailBuffer

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_LEVEL_STYLES = {
    "debug": "dim",
    "info": "green",
    "warning": "yellow",
    "error": "bold red",
    "critical": "bold white on red",
}


def _run_log_filename(
    scenario_id: str, persona_id: str, trial: int, num_trials: int
) -> str:
    pad = max(2, len(str(num_trials)))
    return f"simulate-{scenario_id}_{persona_id}-{trial:0{pad}}.log"


class LogRouter:
    """Final structlog processor that replaces the default renderer.

    Routes every event to per-run files and the tail buffer. When TUI is
    active, returns "" to suppress stderr (Rich Live owns the terminal).
    When no TUI, falls through to the original renderer for stderr output.
    """

    def __init__(
        self,
        log_dir: Path,
        log_format: Literal["text", "json"] = "text",
        tail_buffers: dict[str, TailBuffer] | None = None,
        fallback_renderer: Any = None,
    ) -> None:
        self._log_dir = log_dir
        self._log_format = log_format
        self._tail_buffers = tail_buffers or {}
        self._fallback_renderer = fallback_renderer
        self._handles: dict[str, IO[str]] = {}
        self._start_time = time.monotonic()
        log_dir.mkdir(parents=True, exist_ok=True)

    def _run_key(self, scenario_id: str, persona_id: str, trial: int) -> str:
        return f"{scenario_id}:{persona_id}:{trial}"

    def open_run(
        self, scenario_id: str, persona_id: str, trial: int, num_trials: int
    ) -> None:
        key = self._run_key(scenario_id, persona_id, trial)
        filename = _run_log_filename(scenario_id, persona_id, trial, num_trials)
        path = self._log_dir / filename
        self._handles[key] = open(path, "w", encoding="utf-8")  # noqa: SIM115

    def close_run(self, scenario_id: str, persona_id: str, trial: int) -> None:
        key = self._run_key(scenario_id, persona_id, trial)
        handle = self._handles.pop(key, None)
        if handle:
            handle.flush()
            handle.close()

    def close_all(self) -> None:
        for handle in self._handles.values():
            handle.flush()
            handle.close()
        self._handles.clear()

    def process(self, logger: Any, method_name: str, event_dict: EventDict) -> str:
        """Structlog renderer: routes to files + tail, optionally to stderr."""
        scenario_id = event_dict.get("scenario_id")
        persona_id = event_dict.get("persona_id")
        trial = event_dict.get("trial")

        # Route to per-run file (always at DEBUG — all events)
        if scenario_id and persona_id and trial is not None:
            key = self._run_key(scenario_id, persona_id, trial)
            handle = self._handles.get(key)
            if handle:
                handle.write(self._format_file_line(event_dict) + "\n")

        # Route to per-worker tail buffer (or broadcast if no worker key)
        if self._tail_buffers:
            level_name = event_dict.get("level", "debug")
            level_num = _LEVEL_MAP.get(level_name, logging.DEBUG)
            styled = self._render_styled(event_dict)
            worker = event_dict.get("worker")
            if worker and worker in self._tail_buffers:
                self._tail_buffers[worker].append(styled, level=level_num)
            else:
                for buf in self._tail_buffers.values():
                    buf.append(styled, level=level_num)

        # When no TUI, fall through to the original renderer for stderr output
        if self._fallback_renderer is not None:
            return self._fallback_renderer(logger, method_name, event_dict)

        # TUI mode: suppress stderr output entirely (Live owns the terminal)
        raise structlog.DropEvent()

    def _elapsed_str(self) -> str:
        """Format elapsed time since router creation as HH:MM:SS."""
        elapsed = time.monotonic() - self._start_time
        h = int(elapsed) // 3600
        m = (int(elapsed) % 3600) // 60
        s = int(elapsed) % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _render_styled(self, event_dict: EventDict) -> Text:
        """Build a styled Rich Text for the TUI tail panel."""
        event = event_dict.get("event", "")
        scenario_id = event_dict.get("scenario_id")
        persona_id = event_dict.get("persona_id")

        output = Text()
        output.append(f"{self._elapsed_str()} ", style="dim")
        if scenario_id and persona_id:
            output.append(f"[{scenario_id}:{persona_id}] ", style="dim cyan")
        output.append(event)
        return output

    def _format_file_line(self, event_dict: EventDict) -> str:
        """Format a line for per-run log files (plain text or JSON)."""
        if self._log_format == "json":
            return json_mod.dumps(
                {k: v for k, v in event_dict.items() if k != "_record"},
                default=str,
            )
        timestamp = event_dict.get("timestamp", "")
        level = event_dict.get("level", "info").upper()
        event = event_dict.get("event", "")
        return f"[{timestamp}] [{level:<8}] {event}"


def setup_engine_logging(
    log_dir: Path,
    log_format: Literal["text", "json"] = "text",
    tail_buffers: dict[str, TailBuffer] | None = None,
    use_tui: bool = True,
) -> LogRouter:
    """Create a LogRouter and install it as structlog's renderer.

    Replaces the last processor (core's _rich_console_renderer) with the
    router, which handles both file output and TUI tail rendering.
    When use_tui=False, core's renderer is kept as fallback so events
    still appear on stderr.
    Must be called AFTER configure_logging().
    """
    config = structlog.get_config()
    current_processors = list(config.get("processors", []))

    # Capture the current renderer to use as fallback when no TUI
    fallback = None
    if not use_tui and current_processors:
        fallback = current_processors[-1]

    router = LogRouter(
        log_dir=log_dir,
        log_format=log_format,
        tail_buffers=tail_buffers,
        fallback_renderer=fallback,
    )

    # Replace the last processor (the renderer) with our router
    if current_processors:
        current_processors[-1] = router.process
    else:
        current_processors.append(router.process)

    structlog.configure(
        processors=current_processors,
        wrapper_class=config.get("wrapper_class"),
        context_class=config.get("context_class"),
        logger_factory=config.get("logger_factory"),
        cache_logger_on_first_use=False,
    )

    # In TUI mode, suppress the stdlib root handler's stderr output.
    # Third-party libraries (Playwright, httpx) use stdlib logging which
    # writes to stderr via the StreamHandler installed by configure_logging().
    # These writes corrupt the alternate screen that Rich Live owns.
    if use_tui:
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(logging.CRITICAL + 1)

    return router


def teardown_engine_logging(router: LogRouter) -> None:
    """Close all file handles and restore the default structlog renderer."""
    from metis.core.logging import configure_logging

    router.close_all()

    # Re-run core's configure_logging to restore the original renderer
    configure_logging(level="WARNING")
