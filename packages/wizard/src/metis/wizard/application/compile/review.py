"""Render the complete Specification as a human-readable review, including dormant Criteria."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from metis.wizard.application.trials import format_trials

if TYPE_CHECKING:
    from metis.wizard.domain.specification import Behaviour, Criterion, Specification


def _criterion_lines(criterion: Criterion) -> list[str]:
    measured = criterion.metric_fqn or "not yet matched"
    return [
        f"    - **{criterion.name}** — given {criterion.description.given}, "
        f"when {criterion.description.when}, then {criterion.description.then}",
        f"      *measured by:* `{measured}`",
        f"      *parameters:* `{json.dumps(criterion.metric_args, ensure_ascii=False, sort_keys=True)}`",
    ]


def _behaviour_lines(behaviour: Behaviour) -> list[str]:
    mark = "measured" if behaviour.measured else "considered, not measured"

    lines = [f"- **{behaviour.name}** — {behaviour.description}  _({mark})_"]
    for criterion in behaviour.criteria:
        lines.extend(_criterion_lines(criterion))
    if not behaviour.criteria:
        lines.append("    - _no acceptance criteria_")
    return lines


def render_review(specification: Specification, experiment_id: str) -> str:
    product = specification.product
    out: list[str] = [
        f"# {product.name} — evaluation review",
        "",
        f"Experiment id: `{experiment_id}`",
        "",
        "## What it is",
        "",
        product.description,
        "",
        "## Who uses it",
        "",
        product.users,
        "",
    ]

    if product.detail:
        out += ["## How it works", "", product.detail, ""]

    out += ["## What should be true", ""]
    for feature in specification.features:
        out += [f"### {feature.id} · {feature.name}", ""]
        if feature.description:
            out += [feature.description, ""]
        for behaviour in feature.behaviours:
            out += _behaviour_lines(behaviour)
        out += [""]

    out += ["## Personas", ""]
    for persona in specification.personas:
        out += [f"- **{persona.name}** (`{persona.id}`) — {persona.description}"]
    if not specification.personas:
        out += ["_none_"]
    out += [""]

    out += ["## Test Cases", ""]
    for task in specification.tasks:
        scenario = specification.scenario(task.scenario_ref)
        out += [
            f"### {task.id}",
            "",
            scenario.description if scenario else "",
            "",
            f"- Scenario: {task.scenario_ref}",
            f"- Persona: {task.persona_ref}",
            f"- Criteria: {', '.join(task.criterion_refs)}",
            f"- Trials: {task.num_trials}",
            f"- Files: {', '.join(task.fixtures)}",
            "",
        ]

    # The same calculation the interview footer shows, so the document and the screen the
    # user decided on cannot disagree.
    out += [
        "## Trials",
        "",
        format_trials(specification.trial_count()),
        "",
    ]

    not_measured = [
        b
        for feature in specification.features
        for b in feature.behaviours
        if not b.measured
    ]
    if not_measured:
        out += [
            "## Considered, not measured",
            "",
            "These were drafted and deliberately left out. They are kept as the record of "
            "what was decided against, not as an oversight.",
            "",
        ]
        out += [f"- **{b.name}** — {b.description}" for b in not_measured]
        out += [""]

    return "\n".join(out)


def write_review(specification: Specification, experiment_id: str, path: Path) -> str:
    text = render_review(specification, experiment_id)
    # encoding is explicit — write_text() otherwise falls back to the platform
    # locale encoding (cp1252 on Windows), and this text is arbitrary user- or
    # model-authored prose (product.description, criteria, personas) that can
    # contain any character.
    Path(path).write_text(text, encoding="utf-8")
    return text
