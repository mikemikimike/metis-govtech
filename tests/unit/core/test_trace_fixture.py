"""The scrubbed Orca case-study session (#431) that demo graders and processor tests share.

Captured from nprd as session sess-261019165653-ed52, after the server's v4 upgrade. The counts
below are what that session held when it was captured; a refresh that changes them means the
session changed, and the expected values must be re-derived, not edited to match.
"""

from __future__ import annotations

import json
import re

from metis.core.trace_processing import turns
from tests.fixtures.traces import FIXTURE, load_orca_session
from tests.fixtures.traces.refresh import _EMAIL, _PLACEHOLDER


def test_fixture_matches_the_captured_session() -> None:
    gi = load_orca_session()
    assert len(gi.traces) == 5
    assert sum(len(t.observations) for t in gi.traces) == 85
    session_turns = turns(gi.traces)
    assert sum(len(turn.tool_calls) for turn in session_turns) == 27
    last = session_turns[4].tool_calls[-1]
    assert (last.name, last.agent) == ("make_ppt", "Slide_Maker.arun")


def test_every_root_resolves_to_the_turn_span() -> None:
    assert all(t.root.parent_observation_id is None for t in load_orca_session().traces)


def test_fixture_holds_no_sensitive_values() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    for pattern in (
        r"arn:aws",
        r"/aws/",
        r"resourceAttributes\.",
        r"pk-lf-",
        r"sk-lf-",
        r"projectId",
        r"\bAKIA[0-9A-Z]{16}\b",
    ):
        assert not re.search(pattern, raw), pattern


def test_every_email_and_user_id_is_the_placeholder() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert {m.group(0) for m in _EMAIL.finditer(raw)} <= {_PLACEHOLDER}
    rows = json.loads(raw)["rows"]
    assert {row.get("userId") for row in rows} <= {None, "", _PLACEHOLDER}


def test_twelve_digit_numbers_are_only_session_timestamps() -> None:
    """A 12-digit number could be an AWS account id; here every one is a session timestamp.

    The last group of a UUID can also be 12 digits, so those are not counted.
    """
    raw = FIXTURE.read_text(encoding="utf-8")
    standalone = set(re.findall(r"(?<![\w-])\d{12}(?![\w-])", raw))
    assert standalone <= {"261019165653", "261019085653"}


def test_fixture_is_small() -> None:
    assert FIXTURE.stat().st_size < 1_000_000


def test_trimming_kept_every_structured_payload_readable() -> None:
    """Long strings are trimmed inside parsed payloads, so trimming never breaks their JSON."""
    observations = [o for t in load_orca_session().traces for o in t.observations]
    assert not [
        o.name for o in observations if o.type == "TOOL" and isinstance(o.input, str)
    ]
    assert not [
        o.name
        for o in observations
        if o.type == "GENERATION" and isinstance(o.input, str)
    ]


def test_the_last_turn_still_holds_the_users_message() -> None:
    """The user's form response sits at the end of Orca's long root input; trimming must keep it."""
    user = turns(load_orca_session().traces)[4].user
    assert isinstance(user, str)
    assert '"skin_id":"kraft-paper"' in user


def test_a_python_syntax_tool_result_reaches_graders_as_text() -> None:
    (call,) = turns(load_orca_session().traces)[0].tool_calls
    assert call.name == "delegate_to_agent"
    assert isinstance(call.observation.output, str)
    assert call.observation.output.startswith("{'_type'")
