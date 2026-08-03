"""`ProductProfile` → `experiment.yaml`.

A pure function. Give it a profile, get back a dict; nothing is read from disk except the
schema, and nothing is written unless validation passes.

**No output models.** The compiler emits a plain dict and validates it against the engine's
own JSON schema. Mirroring `Experiment` / `ExperimentTask` / `MetricRef` as wizard-side
Pydantic classes would be more classes that silently drift from the real schema, and the
schema file is already the contract. The cost is real and accepted: no autocomplete while
writing this module, and a mistyped key surfaces at validation rather than construction.
That is affordable because this is one function with a golden-file test behind it.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from metis.wizard.domain.profile import Behaviour, ProductProfile, Task

# The engine declares `schema_version: Literal[1]` with no default and requires it. A file
# without it is one the engine refuses to load, so the compiler states it explicitly rather
# than defaulting it — when the engine bumps, this has to move with it, visibly.
SCHEMA_VERSION = 1

SCHEMA_FILENAME = "experiment.schema.json"


class CompilationError(Exception):
    """The compiled document does not satisfy the experiment schema."""


@lru_cache(maxsize=1)
def _schema_path() -> Path:
    """Find the engine's schema on disk.

    It lives beside the engine package rather than inside it, so it is located relative to
    the installed module rather than imported. In this workspace the packages are installed
    editable, so this resolves to `packages/engine/schemas/`.
    """
    spec = importlib.util.find_spec("metis.engine")
    if spec is None or not spec.origin:
        raise CompilationError(
            "metis-engine is not installed, so the experiment schema cannot be found."
        )
    # .../packages/engine/src/metis/engine/__init__.py → .../packages/engine
    engine_root = Path(spec.origin).resolve().parents[3]
    path = engine_root / "schemas" / SCHEMA_FILENAME
    if not path.is_file():
        raise CompilationError(f"Experiment schema not found at {path}.")
    return path


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    import json

    return json.loads(_schema_path().read_text())


def _metric_refs(profile: ProductProfile, behaviours: list[Behaviour]) -> list[str]:
    """Every metric that will judge this task.

    The union of the criteria metrics of the behaviours it covers, plus the universal epic's
    — which ride along on every task rather than becoming tasks of their own.

    De-duplicated in document order rather than sorted: two behaviours often share a metric,
    and document order is the one a reader of `review.md` already has in their head. Order
    is stable either way, which is what the golden-file test needs.
    """
    fqns = [
        criterion.metric_fqn
        for behaviour in [*behaviours, *profile.universal_behaviours()]
        for criterion in behaviour.criteria
        if criterion.metric_fqn
    ]
    return list(dict.fromkeys(fqns))  # order-preserving dedup


def _compile_task(profile: ProductProfile, task: Task) -> dict[str, Any]:
    known_personas = {p.id for p in profile.personas}
    ticked = {b.id for b in profile.ticked()}

    # Drop references that would not resolve. The harness raises ValueError on an unknown
    # persona_ref rather than skipping it, so emitting one produces a file that fails at run
    # time instead of here. Unticked behaviours contribute nothing by the same logic — they
    # were deliberately not measured, and they survive in review.md.
    persona_refs = [ref for ref in task.persona_refs if ref in known_personas]
    covered = [b for b in profile.ticked() if b.id in set(task.behaviour_refs) & ticked]

    compiled: dict[str, Any] = {
        "id": task.id,
        "description": task.description,
        "num_trials": task.num_trials,
        "persona_refs": persona_refs,
        "metric_refs": _metric_refs(profile, covered),
    }
    if task.fixtures:
        compiled["fixtures"] = list(task.fixtures)
    return compiled


def compile_experiment(profile: ProductProfile, experiment_id: str) -> dict[str, Any]:
    """Compile a profile into an experiment document, validated against the schema.

    Raises `CompilationError` if the result does not satisfy the schema — the caller writes
    nothing in that case, so a malformed experiment never reaches disk.
    """
    tasks = [_compile_task(profile, task) for task in profile.tasks]

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": experiment_id,
        "description": profile.product.summary,
        # Personas are inline: one output file, one schema. The input directory the engine
        # reads is experiment.yaml plus a fixtures/ folder — there is no personas file.
        "personas": [
            {"id": p.id, "description": p.description} for p in profile.personas
        ],
        "tasks": tasks,
    }

    try:
        jsonschema.validate(document, _schema())
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        raise CompilationError(
            f"The compiled experiment does not satisfy {SCHEMA_FILENAME} "
            f"at {location}: {exc.message}"
        ) from exc

    return document


def to_yaml(document: dict[str, Any]) -> str:
    """Serialise a compiled document.

    `sort_keys=False` keeps the field order the compiler chose, which is the order a human
    reads the schema in. `default_flow_style=False` keeps it block-structured like the
    hand-written examples.
    """
    return yaml.dump(
        document,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=88,
    )


def write_experiment(
    profile: ProductProfile, experiment_id: str, path: Path
) -> dict[str, Any]:
    """Compile, validate, then write. Nothing is written if validation fails."""
    document = compile_experiment(profile, experiment_id)
    Path(path).write_text(to_yaml(document))
    return document
