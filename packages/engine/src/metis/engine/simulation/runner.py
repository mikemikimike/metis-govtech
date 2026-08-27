"""Runner ABC — transport layer connecting the simulation to a target system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ChosenAction, Observation, RunConfig


class Runner(ABC):
    """Transport layer — connects the simulation to a target system.

    Implementations translate (message, actions) pairs into transport-specific
    operations (browser DOM, REST API, RPC) and return an Observation.

    The runner does not know about personas, scenarios, or the UserAgent.
    It does not manage the turn loop or stopping conditions.
    """

    @abstractmethod
    async def setup(self, config: RunConfig) -> None:
        """Prepare the connection (launch browser, authenticate, open session)."""

    @abstractmethod
    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Deliver user message + chosen actions to the target, return observation."""

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up (close browser, end HTTP session)."""

    @abstractmethod
    async def get_session_id(self) -> str | None:
        """Return the target system's session identifier, if available."""

    async def recover(self) -> None:  # noqa: B027
        """Attempt lightweight recovery (e.g., page refresh). Default: no-op."""
