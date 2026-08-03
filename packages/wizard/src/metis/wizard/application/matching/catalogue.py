"""Reading the metric library.

**This is the one function that knows where the metrics live.** The engine import below is a
deliberate, temporary break of the `wizard ↛ engine` invariant in the root CLAUDE.md: the
metrics are still at `metis.engine.metrics.*` and metis-library is nearly empty. It is
isolated here so that the move is a one-line change and nothing else in the package is
affected. See the wizard CHANGELOG.

Design-time metadata only. The wizard never instantiates a metric and never runs one — which
is why specs are built from class names and docstrings rather than from instances. Many
metrics take constructor arguments, so building one just to read its display name would be
the wizard doing exactly what it says it never does.
"""

from __future__ import annotations

import inspect
import pkgutil
import re
from functools import lru_cache
from importlib import import_module

from metis.wizard.contracts.catalogue import MetricParam, MetricSpec

# The one string that changes when the metrics land in metis-library.
METRICS_PACKAGE = "metis.engine.metrics"


def _human_name(class_name: str) -> str:
    """`TurnBudgetMetric` → `Turn budget`. What the user sees on a criterion card."""
    stem = re.sub(r"Metric$", "", class_name)
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", stem)
    if not words:
        return class_name
    return " ".join([words[0], *[w.lower() for w in words[1:]]])


def _summary(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    return doc.split("\n\n")[0].replace("\n", " ").strip()


def _params(cls: type) -> list[MetricParam]:
    """Read the constructor signature without calling it."""
    try:
        signature = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []

    params = []
    for name, parameter in list(signature.parameters.items())[1:]:  # skip self
        if name in {"args", "kwargs"}:
            continue
        empty = inspect.Parameter.empty
        params.append(
            MetricParam(
                name=name,
                type=(
                    getattr(parameter.annotation, "__name__", str(parameter.annotation))
                    if parameter.annotation is not empty
                    else "unknown"
                ),
                default=None if parameter.default is empty else parameter.default,
                required=parameter.default is empty,
            )
        )
    return params


def _is_metric(obj: object, module_name: str) -> bool:
    if not inspect.isclass(obj):
        return False
    if not obj.__name__.endswith("Metric"):
        return False
    if obj.__name__.startswith(("Base", "Sync")):  # abstract bases, not choices
        return False
    # Defined here rather than imported from somewhere else, so each metric is catalogued
    # once under the module it actually lives in.
    return obj.__module__ == module_name


@lru_cache(maxsize=1)
def catalogue() -> list[MetricSpec]:
    """Every metric the wizard may match against.

    Cached: the catalogue cannot change within a run, and it is read once per session start
    and once per matcher construction.
    """
    package = import_module(METRICS_PACKAGE)
    specs: list[MetricSpec] = []

    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        module_name = f"{METRICS_PACKAGE}.{info.name}"
        module = import_module(module_name)

        for name, obj in vars(module).items():
            if not _is_metric(obj, module_name):
                continue
            specs.append(
                MetricSpec(
                    fqn=f"{module_name}.{name}",
                    name=_human_name(name),
                    description=_summary(obj),
                    params=_params(obj),
                )
            )

    return sorted(specs, key=lambda s: s.fqn)
