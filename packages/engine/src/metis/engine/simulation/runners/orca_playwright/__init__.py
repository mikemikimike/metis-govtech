"""Old import path, kept for ``runner_factory_ref``; re-exports ``metis.engine.simulation.gen_1.runners.orca_playwright``."""

from metis.engine.simulation.gen_1.runners.orca_playwright import (
    OrcaPlaywrightRunner,
    OrcaPlaywrightRunnerFactory,
)

__all__ = ["OrcaPlaywrightRunner", "OrcaPlaywrightRunnerFactory"]
