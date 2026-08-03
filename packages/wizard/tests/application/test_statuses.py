from __future__ import annotations

from metis.wizard.application import Session
from metis.wizard.application.statuses import status_for
from metis.wizard.contracts import Product, ProductProfile
from metis.wizard.domain.permissions import SessionStep


def test_every_session_phase_has_finished_status_copy() -> None:
    for step in SessionStep:
        message = status_for(step)

        assert message.strip()
        assert message.endswith("…")


def test_the_session_facade_exposes_package_owned_status_copy() -> None:
    session = Session.start(
        ProductProfile(product=Product(name="Agent", summary="", users=""))
    )

    assert session.busy_message() == "Understanding your agent…"
