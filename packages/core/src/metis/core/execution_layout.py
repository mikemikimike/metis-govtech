"""Relative paths shared by execution writers and report readers."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

EXECUTIONS = PurePosixPath("experiments/execute")
INPUTS = PurePosixPath("inputs")
SPECIFICATION = INPUTS / "specification.yaml"
FIXTURES = INPUTS / "fixtures"
TRIALS = PurePosixPath("outputs/trials")
TRIAL_RECORD = "record.json"
"""File name of a trial's ``TrialRecord``, inside its folder under ``TRIALS``."""
REPORTS = PurePosixPath("outputs/reports")
RESULTS = REPORTS / "results.json"
LOGS = PurePosixPath("logs")


def experiment_root_from_results(results_file: Path) -> Path:
    """Find the execution root for a results file in outputs/reports/."""
    root = results_file.parent
    for part in reversed(REPORTS.parts):
        if root.name != part:
            raise ValueError("The results file must be in outputs/reports/.")
        root = root.parent
    return root
