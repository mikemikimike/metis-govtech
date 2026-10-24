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


def test_run_mode_takes_the_binding_from_the_cli_or_from_a_file(tmp_path) -> None:
    from metis.wizard.adapters.cli.connection import read_binding_source

    def ask(*answers: str):
        replies = iter(answers)
        return read_binding_source(
            out=lambda _line: None, read=lambda _p: next(replies)
        )

    assert ask("") is None
    binding = tmp_path / "binding.yaml"
    binding.write_text("schema_version: 1\n")
    assert ask("2", str(tmp_path / "absent.yaml"), str(binding)) == binding
