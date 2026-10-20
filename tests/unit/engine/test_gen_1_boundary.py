"""Only the listed shared modules may import from ``simulation.gen_1`` (#475).

Retiring gen_1 means deleting its folder; this list is everything that would then
need changing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO = Path(__file__).parents[3]
SRC_ROOTS = [*REPO.glob("packages/*/src"), *REPO.glob("apps/*/src")]
GEN_1 = "metis.engine.simulation.gen_1"
ALLOWED = {  # module importing gen_1 → gen_1 modules it may import
    "metis.engine.simulation.runner": {f"{GEN_1}.runner"},
    "metis.engine.simulation.types": {f"{GEN_1}.types"},
    "metis.engine.simulation.runners.orca_api": {f"{GEN_1}.runners.orca_api"},
    "metis.engine.simulation.runners.orca_playwright": {
        f"{GEN_1}.runners.orca_playwright"
    },
    # gen_1.runner: the Runner type in annotations, until gen_2's sub-issue splits
    # RunnerFactory per generation.
    "metis.engine.simulation.trial": {f"{GEN_1}.trial", f"{GEN_1}.runner"},
    "metis.engine.simulation.factory": {f"{GEN_1}.runner"},
    # Runs once per experiment, before workers start; gen_2's sub-issue moves it
    # behind the seam.
    "metis.engine.simulation.experiment": {f"{GEN_1}.artifact_summarizer"},
}


def _imports() -> Iterator[tuple[str, set[str]]]:
    """Yield each source module's dotted name and the modules it imports."""
    for root in SRC_ROOTS:
        for path in root.rglob("*.py"):
            parts = list(path.relative_to(root).with_suffix("").parts)
            is_package = parts[-1] == "__init__"
            if is_package:
                parts.pop()
            module = ".".join(parts)
            package = parts if is_package else parts[:-1]
            imported: set[str] = set()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        base = package[: len(package) - (node.level - 1)]
                        name = ".".join(
                            [*base, *([node.module] if node.module else [])]
                        )
                    else:
                        name = node.module or ""
                    imported.add(name)
            yield module, imported


def test_only_allowed_modules_import_gen_1() -> None:
    found: dict[str, set[str]] = {}
    for module, imported in _imports():
        if module == GEN_1 or module.startswith(GEN_1 + "."):
            continue
        hits = {m for m in imported if m == GEN_1 or m.startswith(GEN_1 + ".")}
        if hits:
            found[module] = hits
    assert found == ALLOWED
