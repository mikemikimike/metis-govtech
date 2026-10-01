"""`ProductProfile` → `experiment.yaml`.

A pure function. Give it a profile, get back a dict; nothing is read from disk except the
schema, and nothing is written unless validation passes.

**No output models.** The compiler emits a plain dict and validates it against the engine's
own JSON schema. Mirroring `Experiment` / `Scenario` / `MetricRef` as wizard-side
Pydantic classes would be more classes that silently drift from the real schema, and the
schema file is already the contract. The cost is real and accepted: no autocomplete while
writing this module, and a mistyped key surfaces at validation rather than construction.
That is affordable because this is one function with a golden-file test behind it.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import yaml

if TYPE_CHECKING:
    from metis.wizard.domain.profile import Behaviour, ProductProfile, Scenario

# The engine declares `schema_version: Literal[2]` with no default and requires it. A file
# without it is one the engine refuses to load, so the compiler states it explicitly rather
# than defaulting it — when the engine bumps, this has to move with it, visibly.
SCHEMA_VERSION = 2

SCHEMA_FILENAME = "experiment.schema.json"

# The engine schema requires runner_factory_ref, and its loader resolves the FQN to a
# real class. There is one runner factory today, so the compiler stamps it as a default
# rather than asking the user — the interview is about product behaviour, not the runner.
# This is a plain string, not an import of engine code, so it keeps the same arrangement
# as the schema-on-disk lookup below.
DEFAULT_RUNNER_FACTORY_REF = (
    "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
)


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


def _metric_refs(behaviours: list[Behaviour]) -> list[str]:
    """Every metric that will judge this scenario.

    The criteria metrics of the behaviours it covers, and nothing else — a scenario is
    measured on what it was written to exercise.

    De-duplicated in document order rather than sorted: two behaviours often share a metric,
    and document order is the one a reader of `review.md` already has in their head. Order
    is stable either way, which is what the golden-file test needs.
    """
    fqns = [
        criterion.metric_fqn
        for behaviour in behaviours
        for criterion in behaviour.criteria
        if criterion.metric_fqn
    ]
    return list(dict.fromkeys(fqns))  # order-preserving dedup


def _compile_scenario(profile: ProductProfile, scenario: Scenario) -> dict[str, Any]:
    known_personas = {p.id for p in profile.personas}
    measured = {b.id for b in profile.measured_behaviours()}

    # Drop references that would not resolve. The harness raises ValueError on an unknown
    # persona_ref rather than skipping it, so emitting one produces a file that fails at run
    # time instead of here. Unticked behaviours contribute nothing by the same logic — they
    # were deliberately not measured, and they survive in review.md.
    persona_refs = [ref for ref in scenario.persona_refs if ref in known_personas]
    covered = [
        b
        for b in profile.measured_behaviours()
        if b.id in set(scenario.behaviour_refs) & measured
    ]

    compiled: dict[str, Any] = {
        "id": scenario.id,
        "description": scenario.description,
        "num_trials": scenario.num_trials,
        "persona_refs": persona_refs,
        "metric_refs": _metric_refs(covered),
    }
    if scenario.fixtures:
        compiled["fixtures"] = list(scenario.fixtures)
    return compiled


def build_experiment_document(
    *,
    experiment_id: str,
    description: str,
    personas: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    runner_factory_ref: str = DEFAULT_RUNNER_FACTORY_REF,
) -> dict[str, Any]:
    """Assemble and validate an experiment document from its parts.

    The one place the document's shape and field order are decided, so every door that
    produces one — the interview's compiler and the web door's stateless compile route —
    emits the same bytes from the same content. The schema version is stamped here rather
    than supplied by a caller: a form never asks the user for it. The runner factory ref
    is stamped the same way — it defaults to the one runner factory that is live today, and
    a form never asks the user for it either.

    `personas` and `scenarios` arrive already in document shape (the dicts the schema
    expects), so this function neither knows nor cares whether they came from a
    `ProductProfile` or a submitted form.

    Raises `CompilationError` if the result does not satisfy the schema — the caller writes
    nothing in that case, so a malformed experiment never reaches disk or a browser.
    """
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": experiment_id,
        "description": description,
        # The engine reads this FQN, loads the class and uses it to run each scenario. The
        # field order matches the schema, so the ref comes after the description.
        "runner_factory_ref": runner_factory_ref,
        # Personas are inline: one output file, one schema. The input directory the engine
        # reads is experiment.yaml plus a fixtures/ folder — there is no personas file.
        "personas": personas,
        "scenarios": scenarios,
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


def compile_experiment(profile: ProductProfile, experiment_id: str) -> dict[str, Any]:
    """Compile a profile into an experiment document, validated against the schema.

    Raises `CompilationError` if the result does not satisfy the schema — the caller writes
    nothing in that case, so a malformed experiment never reaches disk.
    """
    return build_experiment_document(
        experiment_id=experiment_id,
        description=profile.product.description,
        personas=[{"id": p.id, "description": p.description} for p in profile.personas],
        scenarios=[
            _compile_scenario(profile, scenario) for scenario in profile.scenarios
        ],
    )


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
