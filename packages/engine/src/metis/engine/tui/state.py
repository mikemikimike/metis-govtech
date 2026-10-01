"""Pure data model tracking experiment progress for the TUI dashboard."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

SimulationRunPhase = Literal["pending", "simulating", "completed", "failed"]


@dataclass
class SimulationRunState:
    scenario_id: str
    persona_id: str
    trial_index: int  # 1-based: first trial is 1, up to num_trials
    num_trials: int
    phase: SimulationRunPhase
    current_turn: int | None
    max_turns: int
    turn_detail: str
    duration_seconds: float | None
    stop_reason: str | None
    worker_id: int | None = None


@dataclass
class SimulationScenarioState:
    scenario_id: str
    runs: list[SimulationRunState]
    phase: Literal["pending", "active", "completed"]


class SimulationState:
    def __init__(
        self,
        experiment_id: str,
        scenarios: list[SimulationScenarioState],
        total_runs: int,
    ) -> None:
        self.experiment_id = experiment_id
        self.scenarios = scenarios
        self.total_runs = total_runs
        self._start_time = time.monotonic()

    def _find_run(
        self, scenario_id: str, persona_id: str, trial_index: int
    ) -> tuple[SimulationScenarioState, SimulationRunState]:
        for sc in self.scenarios:
            if sc.scenario_id == scenario_id:
                for run in sc.runs:
                    if run.persona_id == persona_id and run.trial_index == trial_index:
                        return sc, run
        raise KeyError(
            f"Run not found: {scenario_id} x {persona_id} trial {trial_index}"
        )

    def mark_run_started(
        self,
        scenario_id: str,
        persona_id: str,
        trial_index: int,  # 1-based
        worker_id: int | None = None,
    ) -> None:
        sc, run = self._find_run(scenario_id, persona_id, trial_index)
        run.phase = "simulating"
        run.worker_id = worker_id
        if sc.phase == "pending":
            sc.phase = "active"

    def mark_run_turn(
        self,
        scenario_id: str,
        persona_id: str,
        trial_index: int,  # 1-based
        turn: int,
        max_turns: int,
        detail: str,
    ) -> None:
        _, run = self._find_run(scenario_id, persona_id, trial_index)
        run.current_turn = turn
        run.max_turns = max_turns
        run.turn_detail = detail

    def mark_run_completed(
        self,
        scenario_id: str,
        persona_id: str,
        trial_index: int,  # 1-based
        stop_reason: str,
        duration_seconds: float,
    ) -> None:
        sc, run = self._find_run(scenario_id, persona_id, trial_index)
        run.phase = "completed"
        run.stop_reason = stop_reason
        run.duration_seconds = duration_seconds
        self._check_scenario_complete(sc)

    def mark_run_failed(
        self,
        scenario_id: str,
        persona_id: str,
        trial_index: int,  # 1-based
        reason: str,
        duration_seconds: float,
    ) -> None:
        sc, run = self._find_run(scenario_id, persona_id, trial_index)
        run.phase = "failed"
        run.stop_reason = reason
        run.duration_seconds = duration_seconds
        self._check_scenario_complete(sc)

    def _check_scenario_complete(self, sc: SimulationScenarioState) -> None:
        if all(r.phase in ("completed", "failed") for r in sc.runs):
            sc.phase = "completed"

    @property
    def completed_runs(self) -> int:
        return sum(
            1
            for sc in self.scenarios
            for r in sc.runs
            if r.phase in ("completed", "failed")
        )

    @property
    def completed_scenarios(self) -> int:
        return sum(1 for sc in self.scenarios if sc.phase == "completed")

    @property
    def active_scenario(self) -> SimulationScenarioState | None:
        for sc in self.scenarios:
            if sc.phase == "active":
                return sc
        return None

    @property
    def pending_scenario_count(self) -> int:
        return sum(1 for sc in self.scenarios if sc.phase == "pending")

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start_time
