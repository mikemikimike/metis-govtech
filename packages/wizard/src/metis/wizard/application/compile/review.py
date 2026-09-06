"""`ProductProfile` → `review.md`, the human-readable half of the output.

`experiment.yaml` is what the engine runs; this is what a person reads. The difference that
matters is that this keeps the behaviours nobody ticked. Those are the record of what was
considered and deliberately not measured, which `experiment.yaml` has no way to express and
no reason to.

Like the compiler, this is a pure function of the profile — no session, no step, no history.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from metis.wizard.application.trials import format_trials

if TYPE_CHECKING:
    from metis.wizard.domain.profile import Behaviour, Criterion, ProductProfile


def _criterion_lines(criterion: Criterion) -> list[str]:
    measured = criterion.metric_fqn or "not yet matched"
    return [
        f"    - **{criterion.name}** — given {criterion.description.given}, "
        f"when {criterion.description.when}, then {criterion.description.then}",
        f"      *measured by:* `{measured}`",
    ]


def _behaviour_lines(behaviour: Behaviour) -> list[str]:
    mark = "measured" if behaviour.measured else "considered, not measured"

    lines = [f"- **{behaviour.name}** — {behaviour.description}  _({mark})_"]
    for criterion in behaviour.criteria:
        lines.extend(_criterion_lines(criterion))
    if not behaviour.criteria:
        lines.append("    - _no acceptance criteria_")
    return lines


def render_review(profile: ProductProfile, experiment_id: str) -> str:
    product = profile.product
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
    for task in profile.tasks:
        out += [f"### {task.id} · {task.name}", ""]
        if task.description:
            out += [task.description, ""]
        for behaviour in task.behaviours:
            out += _behaviour_lines(behaviour)
        out += [""]

    out += ["## Personas", ""]
    for persona in profile.personas:
        out += [f"- **{persona.name}** (`{persona.id}`) — {persona.description}"]
    if not profile.personas:
        out += ["_none_"]
    out += [""]

    out += ["## Scenarios", ""]
    for scenario in profile.scenarios:
        covers = ", ".join(scenario.behaviour_refs) or "nothing"
        runs = ", ".join(scenario.persona_refs) or "nobody"
        out += [
            f"### {scenario.name} (`{scenario.id}`)",
            "",
            scenario.description,
            "",
            f"- *covers:* {covers}",
            f"- *run as:* {runs}",
            f"- *trials:* {scenario.num_trials}",
        ]
        if scenario.fixtures:
            out += [f"- *files:* {', '.join(scenario.fixtures)}"]
        out += [""]

    # The same calculation the interview footer shows, so the document and the screen the
    # user decided on cannot disagree.
    out += [
        "## Trials",
        "",
        format_trials(profile.trial_count()),
        "",
    ]

    not_measured = [
        b for task in profile.tasks for b in task.behaviours if not b.measured
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


def write_review(profile: ProductProfile, experiment_id: str, path: Path) -> str:
    text = render_review(profile, experiment_id)
    Path(path).write_text(text)
    return text
