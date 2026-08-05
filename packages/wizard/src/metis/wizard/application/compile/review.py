"""`ProductProfile` → `review.md`, the human-readable half of the output.

`experiment.yaml` is what the engine runs; this is what a person reads. The difference that
matters is that this keeps the behaviours nobody ticked. Those are the record of what was
considered and deliberately not measured, which `experiment.yaml` has no way to express and
no reason to.

Like the compiler, this is a pure function of the profile — no session, no step, no history.
"""

from __future__ import annotations

from pathlib import Path

from metis.wizard.application.runs import format_runs
from metis.wizard.domain.profile import Behaviour, Criterion, ProductProfile


def _criterion_lines(criterion: Criterion) -> list[str]:
    measured = criterion.metric_fqn or "not yet matched"
    return [
        f"    - **{criterion.id}** — given {criterion.given}, "
        f"when {criterion.when}, then {criterion.then}",
        f"      *measured by:* `{measured}`",
    ]


def _behaviour_lines(behaviour: Behaviour) -> list[str]:
    mark = "measured" if behaviour.priority else "considered, not measured"

    lines = [f"- **{behaviour.id}** — {behaviour.statement}  _({mark})_"]
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
        product.summary,
        "",
        "## Who uses it",
        "",
        product.users,
        "",
    ]

    if product.architecture:
        out += ["## How it works", "", product.architecture, ""]

    out += ["## What should be true", ""]
    for epic in profile.epics:
        out += [f"### {epic.id} · {epic.name}", ""]
        for behaviour in epic.behaviours:
            out += _behaviour_lines(behaviour)
        out += [""]

    out += ["## Personas", ""]
    for persona in profile.personas:
        out += [f"- **{persona.id}** — {persona.description}"]
    if not profile.personas:
        out += ["_none_"]
    out += [""]

    out += ["## Tasks", ""]
    for task in profile.tasks:
        covers = ", ".join(task.behaviour_refs) or "nothing"
        runs = ", ".join(task.persona_refs) or "nobody"
        out += [
            f"### {task.id}",
            "",
            task.description,
            "",
            f"- *covers:* {covers}",
            f"- *run as:* {runs}",
            f"- *trials:* {task.num_trials}",
        ]
        if task.fixtures:
            out += [f"- *files:* {', '.join(task.fixtures)}"]
        out += [""]

    # The same calculation the interview footer shows, so the document and the screen the
    # user decided on cannot disagree.
    out += [
        "## Runs",
        "",
        format_runs(profile.run_count()),
        "",
    ]

    not_measured = [
        b for epic in profile.epics for b in epic.behaviours if not b.priority
    ]
    if not_measured:
        out += [
            "## Considered, not measured",
            "",
            "These were drafted and deliberately left out. They are kept as the record of "
            "what was decided against, not as an oversight.",
            "",
        ]
        out += [f"- **{b.id}** — {b.statement}" for b in not_measured]
        out += [""]

    return "\n".join(out)


def write_review(profile: ProductProfile, experiment_id: str, path: Path) -> str:
    text = render_review(profile, experiment_id)
    Path(path).write_text(text)
    return text
