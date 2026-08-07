"""Deck Source Faithfulness metric (AC-SM-18)."""

from typing import ClassVar, cast

from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from ._base import SyncBaseMetric, _with_eval_context
from ._judge import _get_judge_model
from ._types import TraceMetadata


def _extract_source_facts(test_case: LLMTestCase) -> list:
    """Pull source file contents from read_source_file tool call outputs."""
    metadata = cast(TraceMetadata, test_case.metadata)
    observations = metadata.get("observations", [])
    source_texts = []

    for obs in observations:
        tool_name = obs.get("name", "")
        if "read_source" in tool_name or "source_file" in tool_name:
            output = obs.get("output")
            if output and isinstance(output, str):
                source_texts.append(output)
            elif output and isinstance(output, dict):
                content = output.get("content") or output.get("text") or ""
                if content:
                    source_texts.append(content)

    return source_texts


class DeckSourceFaithfulnessMetric(SyncBaseMetric):
    """Does the generated slide deck stay faithful to the source material, without contradicting or misrepresenting facts from the uploaded data? (AC-SM-18)

    Does the deck contradict or misrepresent facts from the source material?
    Extracts source file contents from read_source_file tool calls and passes
    them as retrieval_context to DeepEval's built-in FaithfulnessMetric.
    Skips if no source material is found in the trace.
    """

    tags: ClassVar[tuple[str, ...]] = (
        "presentation",
        "per-turn",
        "judge-graded",
    )
    async_mode = False

    def __init__(self):
        self.threshold = 0.6
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._metric = None

    def _get_metric(self):
        if self._metric is None:
            self._metric = FaithfulnessMetric(
                threshold=0.6,
                model=_get_judge_model(),
                include_reason=True,
            )
        return self._metric

    def measure(self, test_case: LLMTestCase) -> float:
        source_texts = _extract_source_facts(test_case)

        if not source_texts and test_case.context:
            source_texts = list(test_case.context)

        if not source_texts:
            self.score = 1.0
            self.skipped = True
            self.reason = "No source material found in trace — SKIPPED"
            self.success = True
            return self.score or 0.0

        combined_source = "\n\n---\n\n".join(source_texts)
        faith_tc = _with_eval_context(
            LLMTestCase(
                input=test_case.input,
                actual_output=test_case.actual_output,
                retrieval_context=[combined_source],
                metadata=test_case.metadata,
            )
        )

        metric = self._get_metric()
        metric.measure(faith_tc)
        self.score = metric.score
        self.evaluation_cost = getattr(metric, "evaluation_cost", None)
        self.reason = metric.reason
        self.success = (self.score or 0) >= self.threshold
        return self.score or 0.0

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> str:
        return "Deck Source Faithfulness"

    def is_successful(self) -> bool:
        return self.success is True
