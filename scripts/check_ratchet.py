"""Fail when a gate term appears in more tracked files than its ceiling allows.

The ceilings only go down: lower a number in ``CEILINGS`` in the same change that
removes the matches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from metis.core.console import console

REPO_ROOT = Path(__file__).resolve().parent.parent

# Number of tracked files that may contain each term, matched case-insensitively.
CEILINGS = {
    "orca": 0,
    "gen_1": 0,
    "gen_2": 0,
    "platformai": 0,
    "platform_ai": 0,
    "X-PlatformAI": 0,
    "a2i": 0,
    "gen1": 0,
    "elb.amazonaws": 0,
    "langfuse.ai": 0,
    "mom.gov": 0,
}

# Lockfile integrity hashes match short terms by chance, and this script names every term.
EXCLUDED_PATHS = (
    "apps/web/package-lock.json",
    "website/package-lock.json",
    "scripts/check_ratchet.py",
)


def count_files(term: str) -> int:
    """Count the tracked files that contain ``term``, ignoring case."""
    result = subprocess.run(
        [
            "git",
            "grep",
            "--files-with-matches",
            "--ignore-case",
            "--fixed-strings",
            "-e",
            term,
            "--",
            ".",
            *(f":!{path}" for path in EXCLUDED_PATHS),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # git grep exits 1 when nothing matches and 2 on an error.
    if result.returncode not in (0, 1):
        raise SystemExit(f"git grep failed for {term!r}: {result.stderr.strip()}")
    return len(result.stdout.splitlines())


def main() -> None:
    failures: list[str] = []
    for term, ceiling in CEILINGS.items():
        count = count_files(term)
        if count > ceiling:
            failures.append(f"{term}: {count} files, ceiling {ceiling}")
        elif count < ceiling:
            console.print(
                f"{term}: {count} files, below ceiling {ceiling}. "
                "Lower the ceiling in scripts/check_ratchet.py."
            )
    if failures:
        console.print("Ratchet exceeded:")
        for failure in failures:
            console.print(f"  {failure}")
        raise SystemExit(1)
    console.print("Ratchet OK")


if __name__ == "__main__":
    main()
