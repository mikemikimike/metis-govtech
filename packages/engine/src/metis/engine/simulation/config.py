"""Simulation-level configuration shared by every transport."""

from __future__ import annotations

from pydantic import BaseModel


class RunRetryConfig(BaseModel):
    """Run-level retry budget consumed by the experiment runner.

    A run that fails with a RunRecoverableError is torn down and retried
    from scratch up to run_max_retries times, pausing run_retry_delay_seconds
    between attempts.
    """

    run_max_retries: int = 2
    run_retry_delay_seconds: float = 5.0
