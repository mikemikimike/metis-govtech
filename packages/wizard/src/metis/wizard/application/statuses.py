"""Package-owned copy for work that takes long enough to acknowledge."""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources

import yaml

from metis.wizard.domain.permissions import SessionStep

STATUS_FILE = "statuses.yaml"


def status_for(step: SessionStep) -> str:
    """Return finished status copy for a phase of the interview.

    This deliberately reads the tiny file on each call. Status wording is presentation
    configuration, so an operator can tune it between turns without rebuilding either door.
    """
    document = yaml.safe_load(
        resources.files("metis.wizard")
        .joinpath(STATUS_FILE)
        .read_text(encoding="utf-8")
    )
    if not isinstance(document, Mapping) or not isinstance(
        document.get("statuses"), Mapping
    ):
        raise RuntimeError(f"{STATUS_FILE} must contain a 'statuses' mapping.")

    statuses = document["statuses"]
    value = statuses.get(step.value)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            f"{STATUS_FILE} must define a non-empty status for '{step.value}'."
        )
    return value


__all__ = ["STATUS_FILE", "status_for"]
