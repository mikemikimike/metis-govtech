"""REST-based runner — drives simulations against HTTP API targets (future)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...runner import Runner

if TYPE_CHECKING:
    from ...types import ChosenAction, Observation, RunConfig


class RestRunner(Runner):
    """Runner implementation for REST API targets.

    Minimal implementation: POST messages to a chat endpoint, parse responses.
    """

    async def setup(self, config: RunConfig) -> None:
        raise NotImplementedError("REST runner not yet implemented")

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        raise NotImplementedError("REST runner not yet implemented")

    async def teardown(self) -> None:
        pass

    async def get_session_id(self) -> str | None:
        return None
