"""Deterministic (code-graded) grader behavior — no judge, no network.

Covers the trigger/skip and pass/fail contracts of the code-graded graders
added by the align-csv-metric-coverage change.
"""

import pytest

from metis.library.graders import (
    AbandonmentGrader,
    CancellationGrader,
    ReproducibleAnalysisScriptGrader,
    SlideProtocolOrderingGrader,
)
from metis.library.graders._types import OrcaChatMetadata

from .conftest import artifact, make_case, make_session, tool_call, turn

# --------------------------------------------------------------------------
# ReproducibleAnalysisScriptGrader (M-DA-23)
# --------------------------------------------------------------------------


def test_reproducible_script_skips_without_code_execution():
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(make_case(metadata={"tool_calls": [tool_call("read_source")]}))
    assert grader.skipped is True
    assert grader.success is True
    assert grader.reason.startswith("SKIPPED")


@pytest.mark.parametrize("directory", ["outputs", "runs/orca/artifacts", "custom"])
@pytest.mark.parametrize("absolute", [True, False])
def test_reproducible_script_passes_when_descriptive_and_presented(
    tmp_path, monkeypatch, directory, absolute
):
    monkeypatch.chdir(tmp_path)
    script = tmp_path / directory / "sales_trend_analysis.py"
    script.parent.mkdir(parents=True)
    script.write_text("x = 1\n")
    path = str(script if absolute else script.relative_to(tmp_path))
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(
        make_case(
            actual_output="I saved the reproducible script sales_trend_analysis.py.",
            metadata={
                "tool_calls": [tool_call("execute_python", {"code": "print(1)"})],
                "artifacts": [{"name": script.name, "path": path, "state": "received"}],
            },
        )
    )
    assert grader.success is True
    assert grader.score == 1.0
    assert grader.skipped is False


def test_reproducible_script_fails_on_generic_name(tmp_path):
    script = tmp_path / "script.py"
    script.write_text("x = 1\n")
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(
        make_case(
            actual_output="Saved script.py.",
            metadata={
                "tool_calls": [tool_call("execute_python", {"code": "x=1"})],
                "artifacts": [artifact("script.py", str(script))],
            },
        )
    )
    assert grader.success is False
    assert grader.score == 0.0
    assert "generically named" in grader.reason


@pytest.mark.parametrize("kind", ["missing", "directory", "no_path"])
def test_reproducible_script_requires_a_file(tmp_path, kind):
    script = tmp_path / "outputs" / "revenue_breakdown.py"
    if kind == "directory":
        script.mkdir(parents=True)
    path = str(script) if kind != "no_path" else None
    state = "unavailable" if kind == "no_path" else "received"
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(
        make_case(
            actual_output="Saved revenue_breakdown.py.",
            metadata={
                "tool_calls": [tool_call("execute_python", {"code": "x=1"})],
                "artifacts": [
                    {"name": "revenue_breakdown.py", "path": path, "state": state}
                ],
            },
        )
    )
    assert grader.success is False
    assert grader.score == 0.0
    assert "no .py script file found" in grader.reason


def test_reproducible_script_excludes_a_path_bearing_record_not_yet_received(
    tmp_path,
):
    """Mirrors test_artifact_paths_skips_a_path_bearing_record_not_yet_received
    in test_extraction.py: a script artifact can carry a real, existing path
    while state != "received" (mid-capture case). The new gate
    (`a.state == "received"`) must exclude it even though the old gate
    (`a.path and Path(a.path).is_file()`) would have included it, since the
    file genuinely exists on disk."""
    script_path = tmp_path / "analysis.py"
    script_path.write_text("# script")
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(
        make_case(
            actual_output="Saved analysis.py.",
            metadata={
                "tool_calls": [tool_call("execute_python", {"code": "x=1"})],
                "artifacts": [
                    {
                        "name": "analysis.py",
                        "path": str(script_path),
                        "state": "unfetched",
                    }
                ],
            },
        )
    )
    assert grader.success is False
    assert grader.score == 0.0
    assert "no .py script file found" in grader.reason


def test_reproducible_script_fails_when_not_presented(tmp_path):
    script = tmp_path / "revenue_breakdown.py"
    script.write_text("x = 1\n")
    grader = ReproducibleAnalysisScriptGrader()
    grader.measure(
        make_case(
            actual_output="Analysis complete.",
            metadata={
                "tool_calls": [tool_call("execute_python", {"code": "x=1"})],
                "artifacts": [artifact("revenue_breakdown.py", str(script))],
            },
        )
    )
    assert grader.success is False
    assert "not presented" in grader.reason


# --------------------------------------------------------------------------
# CancellationGrader (M-UNI-21)
# --------------------------------------------------------------------------


def test_cancellation_skips_when_availability_unknown():
    grader = CancellationGrader()
    grader.measure(make_case(metadata={}))
    assert grader.skipped is True
    assert grader.success is True


def test_cancellation_passes_when_not_cancelled():
    grader = CancellationGrader()
    grader.measure(
        make_case(
            metadata={
                "cancellation_available": True,
                "chat_metadata": OrcaChatMetadata(was_cancelled=False),
            }
        )
    )
    assert grader.success is True
    assert grader.score == 1.0


def test_cancellation_fails_when_cancelled():
    grader = CancellationGrader()
    grader.measure(
        make_case(
            metadata={
                "cancellation_available": True,
                "chat_metadata": OrcaChatMetadata(was_cancelled=True),
            }
        )
    )
    assert grader.success is False
    assert grader.score == 0.0


# --------------------------------------------------------------------------
# AbandonmentGrader (M-UNI-20)
# --------------------------------------------------------------------------


def test_abandonment_skips_when_no_work_started():
    grader = AbandonmentGrader()
    session = make_session(
        [turn("user", "hi"), turn("assistant", "hello")],
        metadata={"stop_reason": "user_abandoned"},
    )
    grader.measure(session)
    assert grader.skipped is True
    assert grader.success is True


def test_abandonment_skips_on_external_stop_reason():
    grader = AbandonmentGrader()
    session = make_session(
        [turn("user", "go"), turn("assistant", "on it", tools=["execute_python"])],
        metadata={"stop_reason": "timeout"},
    )
    grader.measure(session)
    assert grader.skipped is True


def test_abandonment_passes_on_terminal_outcome():
    grader = AbandonmentGrader()
    session = make_session(
        [turn("user", "go"), turn("assistant", "done", tools=["execute_python"])],
        metadata={"stop_reason": "completed"},
    )
    grader.measure(session)
    assert grader.skipped is False
    assert grader.success is True
    assert grader.score == 1.0


def test_abandonment_fails_on_user_abandoned():
    grader = AbandonmentGrader()
    session = make_session(
        [turn("user", "go"), turn("assistant", "working", tools=["execute_python"])],
        metadata={"stop_reason": "user_abandoned"},
    )
    grader.measure(session)
    assert grader.skipped is False
    assert grader.success is False
    assert grader.score == 0.0


# --------------------------------------------------------------------------
# SlideProtocolOrderingGrader (M-SM-1)
# --------------------------------------------------------------------------


def test_slide_protocol_skips_without_deck():
    grader = SlideProtocolOrderingGrader()
    grader.measure(make_session([turn("user", "make slides"), turn("assistant", "ok")]))
    assert grader.skipped is True
    assert grader.success is True


def test_slide_protocol_passes_style_then_brief_then_deck():
    grader = SlideProtocolOrderingGrader()
    session = make_session(
        [
            turn("user", "make a deck"),
            turn("assistant", "What style or theme would you like?"),
            turn("user", "clean and modern"),
            turn("assistant", "Here is the brief for the deck."),
            turn("assistant", "building", tools=["make_ppt"]),
        ]
    )
    grader.measure(session)
    assert grader.success is True
    assert grader.score == 1.0


def test_slide_protocol_fails_when_brief_precedes_style():
    grader = SlideProtocolOrderingGrader()
    session = make_session(
        [
            turn("user", "make a deck"),
            turn("assistant", "Here is the brief."),
            turn("assistant", "What theme do you want?"),
            turn("assistant", "building", tools=["make_ppt"]),
        ]
    )
    grader.measure(session)
    assert grader.success is False
    assert grader.score == 0.0
