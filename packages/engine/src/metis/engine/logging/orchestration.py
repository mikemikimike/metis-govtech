"""Writes the orchestration index log (simulate.log)."""

from __future__ import annotations

import json as json_mod
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Literal

from .router import _run_log_filename


class OrchestrationLogger:
    """Writes simulate.log — the experiment-level timeline index.

    Records scenario/run start and completion events with timestamps
    and pointers to per-run detail logs. Intended for quick post-hoc
    triage: scan this file to find the run you care about, then follow
    the log path to full DEBUG output.
    """

    def __init__(
        self, log_dir: Path, log_format: Literal["text", "json"] = "text"
    ) -> None:
        self._log_dir = log_dir
        self._log_format = log_format
        log_dir.mkdir(parents=True, exist_ok=True)
        self._handle: IO[str] = open(  # noqa: SIM115
            log_dir / "simulate.log", "w", encoding="utf-8"
        )

    def _timestamp(self) -> str:
        return datetime.now(tz=UTC).strftime("%H:%M:%S")

    def _write_text(self, line: str) -> None:
        self._handle.write(f"[{self._timestamp()}] {line}\n")
        self._handle.flush()

    def _write_json(self, data: dict) -> None:
        data["timestamp"] = self._timestamp()
        self._handle.write(json_mod.dumps(data, default=str) + "\n")
        self._handle.flush()

    def scenario_started(self, scenario_id: str) -> None:
        if self._log_format == "json":
            self._write_json(
                {"event_type": "SCENARIO_STARTED", "scenario_id": scenario_id}
            )
        else:
            self._write_text(f"SCENARIO {scenario_id} STARTED")

    def run_started(
        self, scenario_id: str, persona_id: str, trial: int, num_trials: int
    ) -> None:
        log_filename = _run_log_filename(scenario_id, persona_id, trial, num_trials)
        pointer = f"logs/{log_filename}"
        if self._log_format == "json":
            self._write_json(
                {
                    "event_type": "RUN_STARTED",
                    "scenario_id": scenario_id,
                    "persona_id": persona_id,
                    "trial": trial,
                    "num_trials": num_trials,
                    "log_file": pointer,
                }
            )
        else:
            self._write_text(
                f"RUN {scenario_id} x {persona_id} [trial {trial}/{num_trials}] "
                f"STARTED → {pointer}"
            )

    def run_completed(
        self,
        scenario_id: str,
        persona_id: str,
        trial: int,
        num_trials: int,
        stop_reason: str,
        total_turns: int,
        duration_seconds: float,
    ) -> None:
        duration_str = f"{duration_seconds:.0f}s"
        if self._log_format == "json":
            self._write_json(
                {
                    "event_type": "RUN_COMPLETED",
                    "scenario_id": scenario_id,
                    "persona_id": persona_id,
                    "trial": trial,
                    "num_trials": num_trials,
                    "stop_reason": stop_reason,
                    "total_turns": total_turns,
                    "duration_seconds": duration_seconds,
                }
            )
        else:
            self._write_text(
                f"RUN {scenario_id} x {persona_id} [trial {trial}/{num_trials}] "
                f"COMPLETED ({stop_reason}, {total_turns} turns, {duration_str})"
            )

    def scenario_completed(
        self, scenario_id: str, runs_passed: int, runs_total: int
    ) -> None:
        if self._log_format == "json":
            self._write_json(
                {
                    "event_type": "SCENARIO_COMPLETED",
                    "scenario_id": scenario_id,
                    "runs_passed": runs_passed,
                    "runs_total": runs_total,
                }
            )
        else:
            self._write_text(
                f"SCENARIO {scenario_id} COMPLETED ({runs_passed}/{runs_total} runs passed)"
            )

    def close(self) -> None:
        self._handle.flush()
        self._handle.close()
