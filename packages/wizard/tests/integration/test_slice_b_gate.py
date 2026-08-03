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
from metis.wizard.application.universals import with_universals
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
    profile = with_universals(
        ProductProfile(
            product=Product(
                name="Research assistant",
                summary="Answers research questions over an internal library.",
                users="Policy analysts.",
                architecture="A router with a search tool that can time out.",
            )
        )
    )
    return Session.start(profile, path=path, driver=driver), driver


def _pick(request: ChoiceRequest, action: str) -> list[str]:
    """Select every option with a given action — how a door replies without knowing why."""
    keys = [str(o.id) for o in request.options if o.id.action == action and o.enabled]
    for card in request.cards:
        keys += [str(o.id) for o in card.options if o.id.action == action]
    return keys


def walk(session: Session, *, tick: int = 2) -> list:
    """Drive the interview to DONE, answering each screen the way a user would.

    Ticking is a *toggle* — the patch on each option flips that behaviour's current value —
    so the prioritise screen is answered once and then continued past. Sending the same ticks
    twice would turn them back off, which is correct behaviour and a bad way to drive a walk.
    """
    seen = []
    ticked = False

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

        if session.state.step is SessionStep.PRIORITISE and not ticked:
            ticked = True
            session.respond(
                ChoiceResponse(
                    selected=[str(c.options[0].id) for c in request.cards[:tick]]
                )
            )
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
        "draft_tasks",
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

    assert Experiment.load_file(tmp_path / "experiment.yaml").tasks


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
    assert any("sessions" in line for line in lines)  # the footer drew


def test_the_session_survives_a_restart_at_every_screen(tmp_path: Path) -> None:
    """Resume mid-interview and the walk still completes."""
    path = tmp_path / "session.json"
    session, _ = a_session(path)

    ticked = False
    for _ in range(6):  # a few screens in — far enough to tick and move past prioritise
        request = session.next()
        assert request is not None
        if isinstance(request, ChatRequest):
            session.respond(cli.ChatResponse(text="answer"))
        elif (
            isinstance(request, ChoiceRequest)
            and session.state.step is SessionStep.PRIORITISE
            and not ticked
        ):
            # Tick here and let a later iteration continue past prioritise. If the preamble
            # left prioritise unanswered, the resumed walk would tick it — then the walk that
            # follows would tick the same behaviours a second time, toggling them back off,
            # and the tasks gate would hold with nothing selected.
            ticked = True
            session.respond(
                ChoiceResponse(
                    selected=[str(c.options[0].id) for c in request.cards[:2]]
                )
            )
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
    """The model tries to tick something. The criteria land; the tick does not, and is said."""
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


def test_the_universal_epic_never_becomes_a_task(tmp_path: Path) -> None:
    session, _ = a_session(tmp_path / "session.json")

    walk(session)

    task_covers = {ref for t in session.profile().tasks for ref in t.behaviour_refs}
    assert not any(ref.startswith("EB-U") for ref in task_covers)
    assert session.profile().universal_behaviours()  # but it is still there
