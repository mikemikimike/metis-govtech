"""RunnerFactory protocol — the lifecycle every generation's factory shares."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class RunnerFactory(Protocol):
    """Factory that manages shared resources and creates Runner instances.

    Implementations own the lifecycle of expensive shared state (e.g., a
    browser process) and produce fresh Runner instances per attempt.

    A factory may set a class attribute ``generation`` naming the simulator
    generation its runners belong to. A factory without one is ``"gen_1"``.
    The attribute is optional, so it is not declared here.

    Each generation narrows ``create`` to its own ``Runner`` type (for
    ``gen_1``, ``gen_1.runner.Gen1RunnerFactory``).
    """

    async def start(self) -> None:
        """Acquire shared resources (launch browser, open connection pool)."""
        ...

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> object:
        """Create a fresh Runner for one attempt."""
        ...

    async def close(self) -> None:
        """Release shared resources."""
        ...
