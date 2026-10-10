"""Criterion prose → grader FQN.

`library_catalogue` is the one function that reads the grader library, and the one place that
knows where the graders currently live. `matcher` is the embedding pass, behind an interface so
it can be swapped for an LLM-based one without touching criteria generation.
"""

from metis.wizard.application.matching.library_catalogue import (
    GRADERS_PACKAGE,
    library_catalogue,
)
from metis.wizard.application.matching.matcher import (
    DEFAULT_THRESHOLD,
    GENERATED_JUDGE_FQN,
    Embedder,
    EmbeddingMatcher,
    cosine,
    match_specification,
    rematch,
)

__all__ = [
    "DEFAULT_THRESHOLD",
    "GENERATED_JUDGE_FQN",
    "GRADERS_PACKAGE",
    "Embedder",
    "EmbeddingMatcher",
    "cosine",
    "library_catalogue",
    "match_specification",
    "rematch",
]
