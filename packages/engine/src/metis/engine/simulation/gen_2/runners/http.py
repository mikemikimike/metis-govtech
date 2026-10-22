"""The generic HTTP runner: a skeleton, so far, tested on fakes only.

``HttpRunnerFactory`` loads the specification's target binding. Its runner does nothing
yet: the evidence pointers (#508), the tools and the rules code enforces (#509), and the
runner-agent loop (#481) arrive in later steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ...config import TrialRetryConfig
from ..binding import TargetBindingError, load_target_binding
from ..runner import Runner

if TYPE_CHECKING:
    from pathlib import Path

    from metis.core.specification import Specification
    from metis.core.trials import TrialConfig

    from ..binding import LoadedBinding
    from ..types import Observation, Promise


class HttpRunner(Runner):
    """Will carry out the user's action on an HTTP target; does nothing yet."""

    def __init__(self, binding: LoadedBinding) -> None:
        self._binding = binding

    @property
    def session_id(self) -> str | None:
        return None

    async def setup(self, config: TrialConfig) -> None:
        pass

    async def act(self, action: str, promised: list[Promise]) -> Observation:
        """Not implemented until #481.

        It raises rather than returning an empty ``Observation``, which would record a
        reply the target never sent.
        """
        raise NotImplementedError("HttpRunner.act is not implemented until #481")

    async def end_chat(self, promised: list[Promise]) -> None:
        pass

    async def teardown(self) -> None:
        pass


class HttpRunnerFactory:
    """Builds :class:`HttpRunner`s for the app the specification's target binding names."""

    generation: ClassVar[str] = "gen_2"

    def __init__(self, binding: LoadedBinding) -> None:
        self._binding = binding

    @property
    def binding(self) -> LoadedBinding:
        return self._binding

    @classmethod
    def from_specification(
        cls, specification: Specification, inputs_dir: Path
    ) -> HttpRunnerFactory:
        """Load ``specification.target_binding`` from the experiment's ``inputs_dir``.

        :raises TargetBindingError: When the specification names no binding, or the
            binding cannot be loaded.
        """
        if specification.target_binding is None:
            raise TargetBindingError(
                "HttpRunnerFactory needs the specification's target_binding, "
                "which is not set"
            )
        return cls(load_target_binding(inputs_dir, specification.target_binding))

    @property
    def retry_defaults(self) -> tuple[int, float]:
        defaults = TrialRetryConfig()
        return defaults.trial_max_retries, defaults.trial_retry_delay_seconds

    async def start(self) -> None:
        """Nothing to acquire yet; #509 opens the HTTP client here."""

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> HttpRunner:
        return HttpRunner(self._binding)

    async def close(self) -> None:
        """Nothing to release yet; #509 closes the HTTP client here."""
