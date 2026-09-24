"""Runner ABC — transport layer connecting the simulation to a target system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from .types import ChosenAction, Observation, RunConfig


class Runner(ABC):
    """Transport layer — connects the simulation to a target system.

    Implementations translate (message, actions) pairs into transport-specific
    operations (browser DOM, REST API, RPC) and return an Observation.

    The runner does not know about personas, scenarios, or the UserAgent.
    It does not manage the turn loop or stopping conditions.

    Implementations MUST satisfy the runner contract in
    ``docs/runner-contract.md``, which is normative for every runner in this
    repository or outside it.
    """

    @abstractmethod
    async def setup(self, config: RunConfig) -> None:
        """Prepare the connection (launch browser, authenticate, open session)."""

    @abstractmethod
    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Deliver user message + chosen actions to the target, return observation.

        Contract obligations (``docs/runner-contract.md``):

        - **I1** — the returned ``Observation.action_results`` MUST hold exactly
          one ``ActionResult`` per action in ``actions``, ordered so that
          ``action_results[i].action_index == i``. Never drop an action silently.
        - **I3** — after this returns, the target session MUST be usable next
          turn. A runner that knows its session is dead MUST raise instead,
          even when it holds a good account of the turn.
        - **I4** — this MAY be assumed to be called at most once per persona
          turn, so an implementation need not tolerate or detect a re-send.
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up (close browser, end HTTP session)."""

    @abstractmethod
    async def get_session_id(self) -> str | None:
        """Return the target system's session identifier, if available."""


class RunnerFactory(Protocol):
    """Factory that manages shared resources and creates Runner instances.

    Implementations own the lifecycle of expensive shared state (e.g., a
    browser process) and produce fresh Runner instances per attempt.
    """

    async def start(self) -> None:
        """Acquire shared resources (launch browser, open connection pool)."""
        ...

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Runner:
        """Create a fresh Runner for one attempt."""
        ...

    async def close(self) -> None:
        """Release shared resources."""
        ...
