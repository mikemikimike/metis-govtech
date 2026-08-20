"""Tests for the custom _evaluate_turn_metrics loop."""

import asyncio
from typing import ClassVar

from deepeval.test_case import LLMTestCase

from metis.library.metrics._base import MetisTurnMetric, mark_skipped


class FakeCodeMetric(MetisTurnMetric):
    """A fake code-graded turn metric for testing."""

    tags: ClassVar[tuple[str, ...]] = ("test", "per-turn", "code-graded")
    async_mode = False

    def __init__(self):
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        self.score = 0.9
        self.reason = "looks good"
        self.success = True
        return 0.9

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Fake Code Metric"


class FakeSkipMetric(MetisTurnMetric):
    """A fake metric that always skips."""

    tags: ClassVar[tuple[str, ...]] = ("test", "per-turn", "code-graded")
    async_mode = False

    def __init__(self):
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return mark_skipped(self, "not applicable")

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Fake Skip Metric"


class FakeAsyncMetric(MetisTurnMetric):
    """A fake async metric for testing."""

    tags: ClassVar[tuple[str, ...]] = ("test", "per-turn", "judge-graded")

    def __init__(self):
        self.score = 0.0
        self.reason = ""
        self.success = False
        self.skipped = False

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        self.score = 0.7
        self.reason = "async result"
        self.success = True
        return 0.7

    def is_successful(self):
        return self.success

    @property
    def __name__(self):
        return "Fake Async Metric"


def test_evaluate_turn_metrics_sync():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_metrics

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_metrics([tc], [FakeCodeMetric()]))

    assert len(results) == 1
    assert len(results[0].metric_results) == 1
    mr = results[0].metric_results[0]
    assert mr.name == "Fake Code Metric"
    assert mr.score == 0.9
    assert mr.skipped is False


def test_evaluate_turn_metrics_skipped():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_metrics

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_metrics([tc], [FakeSkipMetric()]))

    mr = results[0].metric_results[0]
    assert mr.skipped is True
    assert mr.score == 1.0
    assert mr.reason == "not applicable"


def test_evaluate_turn_metrics_async():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_metrics

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_metrics([tc], [FakeAsyncMetric()]))

    mr = results[0].metric_results[0]
    assert mr.name == "Fake Async Metric"
    assert mr.score == 0.7
    assert mr.skipped is False


def test_evaluate_turn_metrics_multiple():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_metrics

    tc = LLMTestCase(input="hi", actual_output="hello")
    metrics = [FakeCodeMetric(), FakeSkipMetric(), FakeAsyncMetric()]
    results = asyncio.run(_evaluate_turn_metrics([tc], metrics))

    assert len(results[0].metric_results) == 3
