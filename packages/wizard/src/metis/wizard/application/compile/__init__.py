"""The output end: `ProductProfile` → `experiment.yaml` + `review.md`.

Both are pure functions of the profile. Neither needs an interview, a step or any history,
which is what makes the golden-file test possible.
"""

from metis.wizard.application.compile.experiment import (
    DEFAULT_RUNNER_FACTORY_REF,
    SCHEMA_VERSION,
    CompilationError,
    build_experiment_document,
    compile_experiment,
    to_yaml,
    write_experiment,
)
from metis.wizard.application.compile.review import render_review, write_review
from metis.wizard.application.compile.specification import (
    SpecificationError,
    temporary_specification_directory,
    write_specification,
)

__all__ = [
    "DEFAULT_RUNNER_FACTORY_REF",
    "SCHEMA_VERSION",
    "SpecificationError",
    "CompilationError",
    "build_experiment_document",
    "compile_experiment",
    "render_review",
    "to_yaml",
    "write_experiment",
    "write_review",
    "temporary_specification_directory",
    "write_specification",
]
