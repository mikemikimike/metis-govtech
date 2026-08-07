"""Tests for TUI layout composition."""

from unittest.mock import patch

from metis.engine.tui.layout import TUIContext, is_tui_active
from metis.engine.tui.state import RunState, ScenarioState, SimulationState
from metis.engine.tui.tail import TailBuffer


def _make_state() -> SimulationState:
    scenarios = [
        ScenarioState(
            scenario_id="test-scn",
            runs=[
                RunState(
                    scenario_id="test-scn",
                    persona_id="test-per",
                    trial=1,
                    num_trials=1,
                    phase="pending",
                    current_turn=None,
                    max_turns=20,
                    turn_detail="",
                    duration_seconds=None,
                    stop_reason=None,
                ),
            ],
            phase="pending",
        ),
    ]
    return SimulationState(experiment_id="test-exp", scenarios=scenarios, total_runs=1)


class TestTUIContext:
    def test_context_manager_enters_and_exits(self) -> None:
        state = _make_state()
        tail = TailBuffer(max_lines=10)
        # Use a non-TTY console to avoid actual terminal manipulation
        with patch("metis.engine.tui.layout._create_live") as mock_live:
            mock_live.return_value.__enter__ = lambda s: s
            mock_live.return_value.__exit__ = lambda s, *a: None
            mock_live.return_value.update = lambda *a: None
            ctx = TUIContext(state=state, tail_buffers={"w0": tail})
            with ctx:
                assert is_tui_active()
            assert not is_tui_active()

    def test_refresh_does_not_raise(self) -> None:
        state = _make_state()
        tail = TailBuffer(max_lines=10)
        with patch("metis.engine.tui.layout._create_live") as mock_live:
            mock_live.return_value.__enter__ = lambda s: s
            mock_live.return_value.__exit__ = lambda s, *a: None
            mock_live.return_value.update = lambda *a: None
            ctx = TUIContext(state=state, tail_buffers={"w0": tail})
            with ctx:
                ctx.refresh()  # should not raise
