"""Shared wording for the evaluation run count."""

from __future__ import annotations


def format_runs(count: int) -> str:
    """State a run count with the correct singular or plural unit."""
    return f"{count} run" if count == 1 else f"{count} runs"
