"""Tests for the custom _evaluate_turn_graders loop."""

import asyncio
from typing import ClassVar

from deepeval.test_case import LLMTestCase

from metis.library.graders._base import MetisTurnGrader, mark_skipped


class FakeCodeGrader(MetisTurnGrader):
    """A fake code-graded turn grader for testing."""

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
        return "Fake Code Grader"


class FakeSkipGrader(MetisTurnGrader):
    """A fake grader that always skips."""

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
        return "Fake Skip Grader"


class FakeAsyncGrader(MetisTurnGrader):
    """A fake async grader for testing."""

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
        return "Fake Async Grader"


def test_evaluate_turn_graders_sync():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_graders

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_graders([tc], [FakeCodeGrader()]))

    assert len(results) == 1
    assert len(results[0].grader_results) == 1
    mr = results[0].grader_results[0]
    assert mr.name == "Fake Code Grader"
    assert mr.score == 0.9
    assert mr.skipped is False


def test_evaluate_turn_graders_skipped():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_graders

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_graders([tc], [FakeSkipGrader()]))

    mr = results[0].grader_results[0]
    assert mr.skipped is True
    assert mr.score == 1.0
    assert mr.reason == "not applicable"


def test_evaluate_turn_graders_async():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_graders

    tc = LLMTestCase(input="hi", actual_output="hello")
    results = asyncio.run(_evaluate_turn_graders([tc], [FakeAsyncGrader()]))

    mr = results[0].grader_results[0]
    assert mr.name == "Fake Async Grader"
    assert mr.score == 0.7
    assert mr.skipped is False


def test_evaluate_turn_graders_multiple():
    from metis.engine.evaluation.orchestrator import _evaluate_turn_graders

    tc = LLMTestCase(input="hi", actual_output="hello")
    graders = [FakeCodeGrader(), FakeSkipGrader(), FakeAsyncGrader()]
    results = asyncio.run(_evaluate_turn_graders([tc], graders))

    assert len(results[0].grader_results) == 3
