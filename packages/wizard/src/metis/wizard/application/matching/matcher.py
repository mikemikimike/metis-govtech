"""Criterion prose → grader FQN, by embedding similarity.

A separate pass, not folded into criteria generation, for two reasons: the catalogue may grow
large enough to need retrieval rather than a prompt, and a swappable matcher can be replaced
with an LLM-based one later without touching how criteria are written.

Below the threshold, a single parameterised judge built from the criterion text — no codegen,
no generated files. That fallback is what makes a dead embedding provider a degraded
experiment rather than a stopped interview.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass, field
from importlib import import_module
from typing import TYPE_CHECKING, Any, Protocol

from metis.wizard.application.matching.library_catalogue import library_catalogue

if TYPE_CHECKING:
    from metis.wizard.contracts.grader_spec import GraderSpec
    from metis.wizard.domain.specification import Criterion, Specification

# One parameterised class that builds a judge from the criterion text. Not codegen: the
# criterion travels as an argument, so there is no generated file to keep in sync.
GENERATED_JUDGE_FQN = "metis.library.graders.default.CriterionGEvalGrader"

DEFAULT_THRESHOLD = 0.62


class Embedder(Protocol):
    def embed(self, texts: list[str], model: str = "") -> list[list[float]]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass
class EmbeddingMatcher:
    """Best cosine match above a threshold, or the generated judge."""

    embedder: Embedder
    specs: list[GraderSpec] = field(default_factory=library_catalogue)
    threshold: float = DEFAULT_THRESHOLD
    degraded: bool = False  # the provider failed at least once this run
    _catalogue_vectors: list[list[float]] | None = None

    def _vectors(self) -> list[list[float]] | None:
        """Embed the catalogue once. It cannot change within a run."""
        if self._catalogue_vectors is None:
            self._catalogue_vectors = self.embedder.embed(
                [spec.match_text for spec in self.specs]
            )
        return self._catalogue_vectors

    def match(self, criterion: Criterion) -> str:
        """The FQN that will judge this criterion.

        Never raises. A criterion bound to the generated judge is a working criterion, and an
        interview that stops because an embedding endpoint is down is not something the user
        can act on.
        """
        try:
            vectors = self._vectors()
            if not vectors:
                return GENERATED_JUDGE_FQN
            [query] = self.embedder.embed([str(criterion.description)])
        except Exception:
            self.degraded = True
            return GENERATED_JUDGE_FQN

        scored = [
            (cosine(query, vector), spec)
            for vector, spec in zip(vectors, self.specs, strict=False)
        ]
        if not scored:
            return GENERATED_JUDGE_FQN

        score, best = max(scored, key=lambda pair: pair[0])
        return best.fqn if score >= self.threshold else GENERATED_JUDGE_FQN


def match_specification(specification: Specification, matcher: EmbeddingMatcher) -> int:
    """Resolve every criterion that needs it. Returns how many were matched.

    Preserve existing mappings and parameters. Dormant Criteria also need a Grader
    because they remain in the shared document.
    """
    matched = 0
    for behaviour in specification.behaviours():
        for criterion in behaviour.criteria:
            if criterion.grader_fqn:
                continue
            criterion.grader_fqn = matcher.match(criterion)
            criterion.grader_args = default_grader_args(criterion)
            matched += 1
    return matched


def rematch(criterion: Criterion, matcher: EmbeddingMatcher) -> str:
    """Re-resolve after the criterion's text changed.

    Silent, and it takes nothing from the user: the matcher chose the previous value, so
    re-choosing overwrites only its own work. This stops being true the day a grader picker
    exists — a user-chosen grader would be destroyed here without a word.
    """
    previous = criterion.grader_fqn
    criterion.grader_fqn = matcher.match(criterion)
    if previous != criterion.grader_fqn or criterion.grader_fqn == GENERATED_JUDGE_FQN:
        criterion.grader_args = default_grader_args(criterion)
    return criterion.grader_fqn


def default_grader_args(criterion: Criterion) -> dict[str, Any]:
    if criterion.grader_fqn == GENERATED_JUDGE_FQN:
        return {"criterion": str(criterion.description), "name": criterion.name}
    spec = next((s for s in library_catalogue() if s.fqn == criterion.grader_fqn), None)
    return {p.name: p.default for p in spec.params if not p.required} if spec else {}


def validate_grader_args(fqn: str | None, args: Any) -> None:
    if not fqn or not isinstance(args, dict):
        raise ValueError("Select a Grader and supply a JSON object.")
    try:
        module, name = fqn.rsplit(".", 1)
        cls = getattr(import_module(module), name)
        inspect.signature(cls).bind(**args)
    except (ImportError, AttributeError, TypeError) as exc:
        raise ValueError(str(exc)) from exc
