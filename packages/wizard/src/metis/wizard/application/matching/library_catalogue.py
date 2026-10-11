"""Reading the grader library.

**This is the one function that knows where the graders live.** They live in metis-library,
which the wizard is allowed to depend on, so nothing here breaks the `wizard ↛ engine`
invariant in the root CLAUDE.md. Keeping the location in one string is what made moving them
out of the engine a one-line change here.

The graders each live in their own `_`-prefixed module and are re-exported flat from
`metis.library.graders.__init__`, which documents that path as canonical and calls the file
layout semantically weightless. So this reads the classes the package re-exports rather than
walking submodules — walking the submodules would skip every `_`-prefixed file and find
almost nothing. The emitted FQN is the flat canonical path, `metis.library.graders.<Class>`,
which is what the engine resolves by ``import_module`` + ``getattr``.

Design-time metadata only. The wizard never instantiates a grader and never runs one — which
is why specs are built from class names and docstrings rather than from instances. Many
graders take constructor arguments, so building one just to read its display name would be
the wizard doing exactly what it says it never does.
"""

from __future__ import annotations

import inspect
import re
from functools import lru_cache
from importlib import import_module

from metis.wizard.contracts.grader_spec import GraderParam, GraderSpec

# The one string that says where the graders live.
GRADERS_PACKAGE = "metis.library.graders"


def _human_name(class_name: str) -> str:
    """`TurnBudgetGrader` → `Turn budget`. What the user sees on a criterion card."""
    stem = re.sub(r"Grader$", "", class_name)
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", stem)
    if not words:
        return class_name
    return " ".join([words[0], *[w.lower() for w in words[1:]]])


def _summary(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    return doc.split("\n\n")[0].replace("\n", " ").strip()


def _params(cls: type) -> list[GraderParam]:
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
            GraderParam(
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


def _is_grader(obj: object) -> bool:
    if not inspect.isclass(obj):
        return False
    if not obj.__name__.endswith("Grader"):
        return False
    if obj.__name__.startswith(("Base", "Sync")):  # abstract bases, not choices
        return False
    # Defined inside the library, not something the package happens to import from elsewhere.
    return obj.__module__.startswith(GRADERS_PACKAGE)


@lru_cache(maxsize=1)
def library_catalogue() -> list[GraderSpec]:
    """Every grader the wizard may match against.

    Read from the classes `metis.library.graders` re-exports, so it is the full set the
    library publishes rather than whatever a submodule walk would happen to find.

    Cached: the catalogue cannot change within a run, and it is read once per interview start
    and once per matcher construction.
    """
    package = import_module(GRADERS_PACKAGE)
    specs: list[GraderSpec] = []

    for name, obj in vars(package).items():
        if not _is_grader(obj):
            continue
        specs.append(
            GraderSpec(
                fqn=f"{GRADERS_PACKAGE}.{name}",
                name=_human_name(name),
                description=_summary(obj),
                params=_params(obj),
            )
        )

    return sorted(specs, key=lambda s: s.fqn)
