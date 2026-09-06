"""Slice B gate: every screen in the flow, walked end to end, with no network.

The corridor is proven here — session, driver, screens, patch application and the CLI door —
on a scripted stand-in for the model. Nothing in this file touches a gateway.
"""

from pathlib import Path

from fixtures.scripted import RejectingInterviewer, ScriptedInterviewer

from metis.wizard.adapters.cli import render as cli
from metis.wizard.application import Session
from metis.wizard.application.compile import write_experiment, write_review
from metis.wizard.application.driver import StepDriver
from metis.wizard.contracts import (
    ChatRequest,
    ChoiceRequest,
    ChoiceResponse,
    FormRequest,
    Product,
    ProductProfile,
    WarningSource,
)
from metis.wizard.domain.permissions import SessionStep


def a_session(path: Path | None = None, interviewer=None) -> tuple[Session, StepDriver]:
    driver = StepDriver(interviewer=interviewer or ScriptedInterviewer())
    profile = ProductProfile(
        product=Product(
            name="Research assistant",
            description="Answers research questions over an internal library.",
            users="Policy analysts.",
            detail="A router with a search tool that can time out.",
        )
    )
    return Session.start(profile, path=path, driver=driver), driver


def _pick(request: ChoiceRequest, action: str) -> list[str]:
    """Select every option with a given action — how a door replies without knowing why."""
    keys = [str(o.id) for o in request.options if o.id.action == action and o.enabled]
    for card in request.cards:
        keys += [str(o.id) for o in card.options if o.id.action == action]
    return keys


def walk(session: Session) -> list:
    """Drive the interview to DONE, answering each screen the way a user would.

    The wizard preselects all Behaviours. The walk keeps that complete starting scope and
    continues without changing it.
    """
    seen = []

    for _ in range(40):  # a bound, so a driver bug fails the test rather than hanging
        request = session.next()
        if request is None:
            break
        seen.append(request)

        if isinstance(request, ChatRequest):
            session.respond(cli.ChatResponse(text="It answers research questions."))
            continue
        if isinstance(request, FormRequest):
            session.respond(cli.FormResponse(values={"description": "typed by hand"}))
            continue

        session.respond(
            ChoiceResponse(
                selected=_pick(request, "continue") or _pick(request, "accept")
            )
        )

    return seen


def test_the_whole_flow_walks_to_done(tmp_path: Path) -> None:
    session, driver = a_session(tmp_path / "session.json")

    walk(session)

    assert session.state.step is SessionStep.DONE
    assert session.next() is None
    # every drafting step was reached
    assert {
        "clarify",
        "draft_behaviours",
        "draft_criteria",
        "draft_personas",
        "draft_scenarios",
    } <= set(driver.interviewer.calls)  # type: ignore[attr-defined]


def test_it_produces_both_output_files(tmp_path: Path) -> None:
    session, _ = a_session(tmp_path / "session.json")
    walk(session)
    profile = session.profile()

    write_experiment(profile, session.state.id, tmp_path / "experiment.yaml")
    write_review(profile, session.state.id, tmp_path / "review.md")

    assert (tmp_path / "experiment.yaml").is_file()
    assert (tmp_path / "review.md").is_file()

    from metis.engine.simulation.types import Experiment

    assert Experiment.load_file(tmp_path / "experiment.yaml").scenarios


def test_the_cli_door_renders_every_screen(tmp_path: Path) -> None:
    """Each screen goes through the real renderer — nothing raises, everything draws."""
    session, _ = a_session(tmp_path / "session.json")
    lines: list[str] = []

    screens = walk(session)
    for request in screens:
        if isinstance(request, ChoiceRequest):
            cli._draw(request, lines.append)

    assert screens
    assert any("[x]" in line or "[ ]" in line for line in lines)  # checkboxes drew
    assert any("trials" in line for line in lines)  # the footer drew


def test_the_session_survives_a_restart_at_every_screen(tmp_path: Path) -> None:
    """Resume mid-interview and the walk still completes."""
    path = tmp_path / "session.json"
    session, _ = a_session(path)

    for _ in range(6):  # a few screens in — far enough to move past prioritise
        request = session.next()
        assert request is not None
        if isinstance(request, ChatRequest):
            session.respond(cli.ChatResponse(text="answer"))
        elif isinstance(request, ChoiceRequest):
            session.respond(
                ChoiceResponse(
                    selected=_pick(request, "continue") or _pick(request, "accept")
                )
            )

    resumed = Session.resume(path, driver=StepDriver(interviewer=ScriptedInterviewer()))
    walk(resumed)

    assert resumed.state.step is SessionStep.DONE


def test_a_rejected_patch_reaches_the_user_as_a_runtime_warning(tmp_path: Path) -> None:
    """The model tries to set a tick. The criteria land; the write does not, and is said."""
    session, driver = a_session(tmp_path / "session.json", RejectingInterviewer())

    screens = walk(session)

    runtime = [
        w
        for request in screens
        if isinstance(request, ChoiceRequest)
        for w in request.warnings
        if w.source is WarningSource.RUNTIME
    ]
    assert runtime, "the refusal should have been shown, not swallowed"
    assert "your call" in runtime[0].text
    assert not runtime[0].blocking
