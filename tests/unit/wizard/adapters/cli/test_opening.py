"""The CLI interview-opening fields."""

from metis.wizard.adapters.cli.opening import read_capability_evidence


def test_capability_input_shows_the_catalogue_and_reads_selection_and_confidence() -> (
    None
):
    replies = iter(["1, Tool Use", "medium"])
    out: list[str] = []

    selected, confidence = read_capability_evidence(
        out=out.append, read=lambda _: next(replies)
    )

    assert [item.value for item in selected] == [
        "planning_goal_management",
        "tool_use",
    ]
    assert confidence.value == "medium"
    text = "\n".join(out)
    assert all(
        category in text for category in ("Cognitive", "Interaction", "Operational")
    )
    assert all(
        label in text
        for label in (
            "Planning & Goal Management",
            "Tool Use",
            "System Management",
        )
    )
