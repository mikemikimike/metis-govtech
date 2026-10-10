"""Tests for MetisTurnGrader base class and mark_skipped utility."""

import pytest
from deepeval.metrics import BaseMetric


def test_metis_grader_requires_tags():
    """Subclass without tags raises TypeError at definition time."""
    from metis.library.graders._base import MetisTurnGrader

    with pytest.raises(TypeError, match="must define a 'tags' class variable"):

        class BadGrader(MetisTurnGrader):
            pass


def test_metis_grader_rejects_non_tuple_tags():
    """Subclass with list tags raises TypeError."""
    from metis.library.graders._base import MetisTurnGrader

    with pytest.raises(TypeError, match="must define a 'tags' class variable"):

        class BadGrader(MetisTurnGrader):
            tags = ["not", "a", "tuple"]


def test_metis_grader_accepts_valid_tags():
    """Subclass with tuple tags is accepted."""
    from metis.library.graders._base import MetisTurnGrader

    class GoodGrader(MetisTurnGrader):
        tags = ("test", "per-turn", "code-graded")

        def measure(self, test_case):
            return 1.0

        def is_successful(self):
            return True

        @property
        def __name__(self):
            return "Good Grader"

    assert issubclass(GoodGrader, BaseMetric)
    assert issubclass(GoodGrader, MetisTurnGrader)


def test_metis_grader_inherits_base_metric():
    """MetisTurnGrader is a subclass of BaseMetric."""
    from metis.library.graders._base import MetisTurnGrader

    assert issubclass(MetisTurnGrader, BaseMetric)


def test_mark_skipped_sets_fields():
    """mark_skipped sets skipped, score, reason, success."""
    from metis.library.graders._base import MetisTurnGrader, mark_skipped

    class TestGrader(MetisTurnGrader):
        tags = ("test",)

        def __init__(self):
            self.score = 0.0
            self.reason = ""
            self.success = False
            self.skipped = False

        def measure(self, test_case):
            return 0.0

        def is_successful(self):
            return self.success

        @property
        def __name__(self):
            return "Test"

    m = TestGrader()
    result = mark_skipped(m, "not applicable")

    assert result == 1.0
    assert m.skipped is True
    assert m.score == 1.0
    assert m.reason == "not applicable"
    assert m.success is True
