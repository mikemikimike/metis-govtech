"""Build an engine-ready ZIP from compiled YAML and a fixture directory."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from metis.wizard.application.fixtures import (
    FixtureError,
    normalize_fixture_name,
    normalize_upload_name,
)

from .experiment import to_yaml

if TYPE_CHECKING:
    from metis.wizard.domain.profile import ProductProfile


class SpecificationError(ValueError):
    """The YAML and fixture directory cannot form a runnable specification."""


def _referenced_names(document: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for scenario in document.get("scenarios", []):
        for raw_name in scenario.get("fixtures", []) or []:
            try:
                names.add(normalize_fixture_name(raw_name))
            except FixtureError as exc:
                raise SpecificationError(str(exc)) from exc
    return names


def write_specification(
    document: dict[str, Any],
    fixture_dir: Path,
    target: Path,
    *,
    profile: ProductProfile | None = None,
) -> Path:
    """Write engine inputs and an optional profile at the root of a ZIP archive."""

    fixture_root = Path(fixture_dir)
    files: dict[str, Path] = {}
    if fixture_root.exists():
        if not fixture_root.is_dir():
            raise SpecificationError("The fixture library is not a directory.")
        for path in fixture_root.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            try:
                name = normalize_upload_name(path.name)
            except FixtureError as exc:
                raise SpecificationError(str(exc)) from exc
            if name in files:
                raise SpecificationError(f"Duplicate fixture '{name}'.")
            files[name] = path

    missing = sorted(_referenced_names(document) - files.keys())
    if missing:
        joined = ", ".join(missing)
        raise SpecificationError(f"Missing fixture file(s): {joined}.")

    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            destination, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            archive.writestr("experiment.yaml", to_yaml(document))
            if profile is not None:
                archive.writestr("profile.yaml", profile.to_yaml())
            archive.writestr("fixtures/", b"")
            for name, path in sorted(files.items()):
                archive.write(path, f"fixtures/{name}")
    except OSError as exc:
        raise SpecificationError(f"Could not create experiment.zip: {exc}") from exc
    return destination


def temporary_specification_directory(prefix: str = "metis-specification-") -> Path:
    """Create a caller-owned temporary directory for a response-scoped specification."""

    return Path(tempfile.mkdtemp(prefix=prefix))
