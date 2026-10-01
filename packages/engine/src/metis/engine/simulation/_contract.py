"""Enforcement of the Runner↔Observation contract at the call boundary.

The normative contract lives in ``docs/runner-contract.md``. This module is
where the orchestrator checks it — one place, so a violation surfaces as a
`RunnerContractError` naming the runner's mistake rather than as a wrong
number in a report three stages downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .exceptions import RunnerContractError
from .types import ActionResult, UploadFileAction

if TYPE_CHECKING:
    from .types import ChosenAction, Observation


def validate_action_results(
    observation: Observation,
    actions: list[ChosenAction],
) -> None:
    """Enforce I1 (completeness) against the list the runner was handed.

    Positional correlation is the mechanism: ``action_results[i]`` describes
    ``actions[i]``. ``slot_id`` is deliberately *not* the join key — it is
    advisory, and ``types.py:36-38`` records that the browser runner offers no
    upload slots at all, so an upload's ``slot_id`` matches nothing on offer.

    I2 (minimal verdict) is not re-checked here. ``ActionResult``'s own
    validators enforce it at construction time, and a second copy of the rule
    would eventually drift from the first.
    """
    results = observation.action_results
    if len(results) != len(actions):
        raise RunnerContractError(
            f"I1: the runner returned {len(results)} ActionResult rows for"
            f" {len(actions)} submitted actions"
        )
    for position, row in enumerate(results):
        if row.action_index != position:
            raise RunnerContractError(
                f"I1: action_results[{position}].action_index is"
                f" {row.action_index}, expected {position}"
            )
        if row.withheld:
            raise RunnerContractError(
                f"I1: action_results[{position}] sets withheld=True;"
                " withholding is the caller's verdict, not the runner's"
            )


def withhold_unstaged_uploads(
    actions: list[ChosenAction],
    staged: set[str],
    declared: set[str],
) -> tuple[list[ChosenAction], list[ActionResult]]:
    """Reject, caller-side, an upload naming a fixture that was never staged.

    Returns ``(forwarded, withheld_rows)``. The runner is handed only
    ``forwarded``; each withheld row carries the **original** index so
    :func:`merge_withheld` can splice it back afterwards.

    Two inputs rather than one because two distinct messages must survive: a
    name in ``declared`` but not in ``staged`` was asked for and is missing
    from disk, while a name in neither was invented by the persona. Collapsing
    them would turn a staging bug and a persona defect into the same string.

    ``withheld=True`` marks a caller-side rejection: the persona still sees it
    (it is feedback they can act on), but the report must not count it against
    the target, which never saw the action at all.
    """
    forwarded: list[ChosenAction] = []
    withheld: list[ActionResult] = []
    for index, action in enumerate(actions):
        if isinstance(action, UploadFileAction) and action.filename not in staged:
            if action.filename in declared:
                detail = (
                    f"Turn not submitted: file {action.filename!r} was not found"
                    " under the fixtures directory"
                )
            else:
                detail = (
                    f"Turn not submitted: file {action.filename!r} is not a"
                    " fixture for this scenario"
                )
            withheld.append(
                ActionResult(
                    action_index=index,
                    succeeded=False,
                    detail=detail,
                    withheld=True,
                )
            )
        else:
            forwarded.append(action)
    return forwarded, withheld


def merge_withheld(
    results: list[ActionResult],
    withheld: list[ActionResult],
) -> list[ActionResult]:
    """Splice withheld rows back into the runner's results.

    The withheld rows' ``action_index`` values say which original positions to
    reserve; the runner's rows fill what is left, in order. Every returned row
    is re-stamped so ``merged[i].action_index == i`` over the persona's
    original list, which is what every downstream consumer assumes.

    ``model_copy`` is safe here, unlike in the runners: it changes only
    ``action_index``, and there is no validator governing that field, so
    nothing needs re-running.
    """
    total = len(results) + len(withheld)
    reserved = {row.action_index for row in withheld}
    if len(reserved) != len(withheld) or any(i >= total for i in reserved):
        raise RunnerContractError(
            f"cannot re-base {len(results)} runner rows around withheld"
            f" positions {sorted(reserved)} over {total} submitted actions"
        )
    by_position = {row.action_index: row for row in withheld}
    remaining = iter(results)
    merged: list[ActionResult] = []
    for position in range(total):
        row = by_position.get(position)
        if row is None:
            row = next(remaining)
        merged.append(row.model_copy(update={"action_index": position}))
    return merged
