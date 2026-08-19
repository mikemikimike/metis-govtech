"""Tests for MetisMetric base class and mark_skipped utility."""

import pytest
from deepeval.metrics import BaseMetric


def test_metis_metric_requires_tags():
    """Subclass without tags raises TypeError at definition time."""
    from metis.library.metrics._base import MetisMetric

    with pytest.raises(TypeError, match="must define a 'tags' class variable"):

        class BadMetric(MetisMetric):
            pass


def test_metis_metric_rejects_non_tuple_tags():
    """Subclass with list tags raises TypeError."""
    from metis.library.metrics._base import MetisMetric

    with pytest.raises(TypeError, match="must define a 'tags' class variable"):

        class BadMetric(MetisMetric):
            tags = ["not", "a", "tuple"]


def test_metis_metric_accepts_valid_tags():
    """Subclass with tuple tags is accepted."""
    from metis.library.metrics._base import MetisMetric

    class GoodMetric(MetisMetric):
        tags = ("test", "per-turn", "code-graded")

        def measure(self, test_case):
            return 1.0

        def is_successful(self):
            return True

        @property
        def __name__(self):
            return "Good Metric"

    assert issubclass(GoodMetric, BaseMetric)
    assert issubclass(GoodMetric, MetisMetric)


def test_metis_metric_inherits_base_metric():
    """MetisMetric is a subclass of BaseMetric."""
    from metis.library.metrics._base import MetisMetric

    assert issubclass(MetisMetric, BaseMetric)


def test_mark_skipped_sets_fields():
    """mark_skipped sets skipped, score, reason, success."""
    from metis.library.metrics._base import MetisMetric, mark_skipped

    class TestMetric(MetisMetric):
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

    m = TestMetric()
    result = mark_skipped(m, "not applicable")

    assert result == 1.0
    assert m.skipped is True
    assert m.score == 1.0
    assert m.reason == "not applicable"
    assert m.success is True
