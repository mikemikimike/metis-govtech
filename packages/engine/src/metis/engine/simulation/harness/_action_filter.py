"""Action validation layer — single pre-filter before the state machine.

Classifies each action as actionable or non-actionable BEFORE the dispatch
loop touches the state machine. One place, one policy.

Two concerns separated:
1. SKIP: action should be silently dropped (non-actionable UI chrome)
2. RECLASSIFY: action needs SM routing metadata (e.g. submit detection)

The dispatch loop calls `filter_actions()` once per turn and iterates the
result — no inline regex checks, no ad-hoc `if/continue` patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from metis.core.logging import get_logger

from ..types import ButtonClickAction, FileUploadAction, FormFillAction, UIAction

logger = get_logger()

# ---------------------------------------------------------------------------
# Classification patterns
# ---------------------------------------------------------------------------

_NON_ACTIONABLE_PATTERN = re.compile(
    r"reasoning|sources|citation|\d+\s*step|collapse|expand|toggle"
    r"|show more|show less|show all|hide|copy|share|new chat"
    r"|thumbs up|thumbs down|feedback|like|dislike",
    re.IGNORECASE,
)

_SUBMIT_PATTERN = re.compile(
    r"submit|generate|run|start|create|analyze|confirm|proceed|continue|apply",
    re.IGNORECASE,
)


class ActionIntent(StrEnum):
    """Routing metadata attached to each validated action."""

    upload = "upload"
    click = "click"
    submit = "submit"
    fill = "fill"


class SkipReason(StrEnum):
    """Why an action was filtered out."""

    non_actionable = "non_actionable"
    duplicate_upload = "duplicate_upload"
    file_not_found = "file_not_found"


@dataclass
class ValidatedAction:
    """An action that passed validation, with routing metadata."""

    action: UIAction
    intent: ActionIntent


@dataclass
class SkippedAction:
    """An action that was filtered out, with reason."""

    action: UIAction
    reason: SkipReason
    detail: str = ""


@dataclass
class FilterResult:
    """Output of the filter: what to execute and what was dropped."""

    actions: list[ValidatedAction]
    skipped: list[SkippedAction]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_actions(
    actions: list[UIAction],
    *,
    uploaded_files: set[str],
    available_files: list[str],
) -> FilterResult:
    """Classify a turn's actions into actionable vs skipped.

    Args:
        actions: raw actions from the user agent
        uploaded_files: files already uploaded this session (for dedup)
        available_files: fixture filenames that exist on disk

    Returns:
        FilterResult with validated actions (execute these) and skipped
        actions (log these, don't execute).
    """
    validated: list[ValidatedAction] = []
    skipped: list[SkippedAction] = []

    for action in actions:
        if isinstance(action, FileUploadAction):
            if action.file in uploaded_files:
                skipped.append(
                    SkippedAction(
                        action, SkipReason.duplicate_upload, "already uploaded"
                    )
                )
            elif action.file not in available_files:
                skipped.append(
                    SkippedAction(
                        action,
                        SkipReason.file_not_found,
                        f"not in fixtures: {', '.join(available_files[:5]) or '(empty)'}",
                    )
                )
            else:
                validated.append(ValidatedAction(action, ActionIntent.upload))

        elif isinstance(action, ButtonClickAction):
            if _NON_ACTIONABLE_PATTERN.search(action.selector):
                skipped.append(
                    SkippedAction(action, SkipReason.non_actionable, action.selector)
                )
            elif _SUBMIT_PATTERN.search(action.selector):
                validated.append(ValidatedAction(action, ActionIntent.submit))
            else:
                validated.append(ValidatedAction(action, ActionIntent.click))

        elif isinstance(action, FormFillAction):
            validated.append(ValidatedAction(action, ActionIntent.fill))

    if skipped:
        logger.debug(
            "[action_filter] Filtered %d/%d actions: %s",
            len(skipped),
            len(actions),
            ", ".join(f"{s.reason}({s.detail[:30]})" for s in skipped),
        )

    return FilterResult(actions=validated, skipped=skipped)
