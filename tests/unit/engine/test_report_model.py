"""Unit tests for the report Pydantic models."""

import json
from pathlib import Path

import pytest

from metis.engine.reporting._report import build_report
from metis.engine.reporting._types import (
    SessionMetricResult,
    SessionReport,
    TurnMetricResult,
    TurnReport,
)


class TestTurnMetricResult:
    def test_required_fields(self):
        m = TurnMetricResult(
            name="TestMetric",
            score=0.85,
            reason="good",
            success=True,
            skipped=False,
        )
        assert m.name == "TestMetric"
        assert m.score == 0.85

    def test_optional_cost_fields(self):
        m = TurnMetricResult(
            name="TestMetric",
            score=0.85,
            reason="good",
            success=True,
            skipped=False,
            cost=0.002,
            input_tokens=100,
            output_tokens=50,
        )
        assert m.cost == 0.002
        assert m.input_tokens == 100
        assert m.output_tokens == 50

    def test_optional_cost_fields_default_none(self):
        m = TurnMetricResult(
            name="TestMetric",
            score=0.85,
            reason="good",
            success=True,
            skipped=False,
        )
        assert m.cost is None
        assert m.input_tokens is None
        assert m.output_tokens is None


class TestTurnReport:
    def test_construction(self):
        t = TurnReport(
            trace_id="trace-1",
            session_id="sess-1",
            scenario_id="sc-1",
            turn_index=0,
            total_turns=3,
            input="hello",
            output="world",
            routed_to="direct",
            metrics=[],
        )
        assert t.trace_id == "trace-1"
        assert t.metrics == []


class TestSessionMetricResult:
    def test_construction(self):
        m = SessionMetricResult(
            name="SessionMetric",
            score=0.9,
            reason="ok",
            success=True,
            skipped=False,
        )
        assert m.name == "SessionMetric"


class TestSessionReport:
    def test_construction(self):
        s = SessionReport(
            session_id="sess-1",
            metrics=[],
        )
        assert s.session_id == "sess-1"


def test_specification_fields_map_to_report():
    specification = {
        "product": {"name": "Assistant"},
        "features": [
            {
                "id": "F-1",
                "name": "Answer",
                "behaviours": [
                    {
                        "id": "B-1",
                        "name": "Cite sources",
                        "description": "Cite each factual claim. Use a relevant source.",
                        "measured": True,
                        "criteria": [
                            {
                                "id": "C-1",
                                "description": {
                                    "given": "a factual question",
                                    "when": "the assistant answers",
                                    "then": "each claim has a source",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
        "personas": [],
        "scenarios": [],
    }

    report = build_report(specification, [])

    behaviour = report["behaviours"]["B-1"]
    assert {
        key: behaviour[key] for key in ("label", "statement", "detail", "priority")
    } == {
        "label": "Cite sources",
        "statement": "Cite each factual claim. Use a relevant source.",
        "detail": "Use a relevant source.",
        "priority": True,
    }
    criterion = report["criteria"]["C-1"]
    assert {key: criterion[key] for key in ("given", "when", "then")} == {
        "given": "a factual question",
        "when": "the assistant answers",
        "then": "each claim has a source",
    }


class TestReportModel:
    @pytest.fixture
    def sample_report(self, repo_root: Path) -> dict:
        report_path = (
            repo_root
            / "experiments"
            / "orca-eval-20260827-222704"
            / "reports"
            / "report.json"
        )
        if not report_path.exists():
            pytest.skip("sample report.json not available")
        return json.loads(report_path.read_text())

    def test_validates_real_report(self, sample_report: dict):
        from metis.engine.reporting._models import Report

        report = Report.model_validate(sample_report)
        assert report.product == "Orca"
        assert report.run == "report"
        assert isinstance(report.features, list)
        assert isinstance(report.behaviours, dict)
        assert isinstance(report.criteria, dict)

    def test_round_trips_to_dict(self, sample_report: dict):
        from metis.engine.reporting._models import Report

        report = Report.model_validate(sample_report)
        dumped = report.model_dump()
        assert dumped["product"] == sample_report["product"]
        assert dumped["threshold"] == sample_report["threshold"]
        assert set(dumped["behaviours"]) == set(sample_report["behaviours"])
