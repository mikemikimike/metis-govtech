"""The output end: `ProductProfile` → `experiment.yaml` + `review.md`.

Both are pure functions of the profile. Neither needs a session, a step or any history,
which is what makes the golden-file test possible.
"""

from metis.wizard.application.compile.experiment import (
    SCHEMA_VERSION,
    CompilationError,
    build_experiment_document,
    compile_experiment,
    to_yaml,
    write_experiment,
)
from metis.wizard.application.compile.review import render_review, write_review

__all__ = [
    "SCHEMA_VERSION",
    "CompilationError",
    "build_experiment_document",
    "compile_experiment",
    "render_review",
    "to_yaml",
    "write_experiment",
    "write_review",
]
