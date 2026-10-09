"""Criterion prose → metric FQN.

`library_catalogue` is the one function that reads the metric library, and the one place that
knows where the metrics currently live. `matcher` is the embedding pass, behind an interface so
it can be swapped for an LLM-based one without touching criteria generation.
"""

from metis.wizard.application.matching.library_catalogue import (
    METRICS_PACKAGE,
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
    "METRICS_PACKAGE",
    "Embedder",
    "EmbeddingMatcher",
    "cosine",
    "library_catalogue",
    "match_specification",
    "rematch",
]
