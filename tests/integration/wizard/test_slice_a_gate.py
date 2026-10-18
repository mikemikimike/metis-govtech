"""Slice A gate: a hand-written specification compiles to something the engine actually loads.

This is the end of the first build slice. No model call has happened anywhere in it — the
specification is written by hand, the compiler is a pure function, and the engine's own validator
is the judge. If this passes, the output contract is proven before anything upstream of it
exists.

`_validate_inputs` is the engine's real load path, not a stand-in: it parses `specification.yaml`
through `Specification`, checks persona references resolve, checks every fixture file is present,
and imports every grader FQN via `importlib` to confirm it is a real grader class. That last
part is the one that matters most here — grader FQNs are strings until run time, so a typo in
a compiled file is invisible until something tries to import it.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from metis.wizard import (
    InterviewState,
    Specification,
    SpecificationFixture,
    package_specification,
)
from metis.wizard.application.compile import (
    write_experiment,
    write_review,
)
from tests.fixtures.wizard.context import interview_context
from tests.fixtures.wizard.specifications import CITATION_GRADER, research_assistant

EXPERIMENT_ID = "research-assistant"


def _input_dir(tmp_path: Path) -> Path:
    """Compile a specification into the directory layout the engine reads.

    The engine's input directory is `specification.yaml` plus a `fixtures/` folder — there is
    no separate personas file, because personas are inline.
    """
    specification = research_assistant()
    write_experiment(specification, EXPERIMENT_ID, tmp_path / "specification.yaml")
    write_review(specification, EXPERIMENT_ID, tmp_path / "review.md")

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for scenario in specification.tasks:
        for name in scenario.fixtures:
            (fixtures / name).write_text("stand-in fixture\n")

    return tmp_path


def test_the_engine_loads_the_compiled_experiment(tmp_path: Path) -> None:
    from metis.engine.cli import _validate_inputs

    input_dir = _input_dir(tmp_path)

    # `_validate_inputs` calls sys.exit(1) on any problem, so reaching the end is the pass.
    _validate_inputs(input_dir)

    assert (input_dir / "specification.yaml").is_file()
    assert (input_dir / "review.md").is_file()


def test_the_gate_would_catch_an_unimportable_grader(tmp_path: Path) -> None:
    """Proves the gate is actually checking, rather than passing vacuously.

    FQNs are resolved by importlib at run time, so an experiment naming a grader that has
    moved stops loading. Not silent — which is what this asserts.
    """
    from metis.engine.cli import _validate_inputs

    input_dir = _input_dir(tmp_path)
    experiment = input_dir / "specification.yaml"
    original = experiment.read_text()
    # The graders' old home, deleted when they moved to metis-library. Deliberately dead —
    # an experiment compiled before the move names this and must fail loudly. Sourced from
    # the fixture so this cannot quietly become a no-op if the compiled graders change.
    dead_fqn = CITATION_GRADER.replace("metis.library.", "metis.engine.")
    assert CITATION_GRADER in original, (
        "the corrupted grader must actually be compiled in"
    )
    experiment.write_text(original.replace(CITATION_GRADER, dead_fqn))

    with pytest.raises(SystemExit) as exit_info:
        _validate_inputs(input_dir)

    assert exit_info.value.code == 1


@pytest.mark.parametrize("interview", [False, True])
def test_the_specification_package_passes_the_engine_input_gate(
    interview: bool,
    tmp_path: Path,
    repo_root: Path,
) -> None:
    """The web transform's shared Specification produces the complete runnable package."""
    from metis.engine.cli import _validate_inputs

    specification_path = repo_root / "tests/fixtures/wizard/manual_specification.json"
    specification = Specification.model_validate(
        json.loads(specification_path.read_text())
    )
    source = (
        InterviewState(specification=specification, context=interview_context())
        if interview
        else specification
    )
    archive_bytes = package_specification(
        source,
        [
            SpecificationFixture("policy.pdf", io.BytesIO(b"policy")),
            SpecificationFixture("notes.txt", io.BytesIO(b"notes")),
        ],
    )
    archive = tmp_path / "specification.zip"
    archive.write_bytes(archive_bytes.content)

    root = archive_bytes.filename.removesuffix(".zip")
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as specification:
        expected = {
            "inputs/",
            "outputs/specification.yaml",
            "outputs/fixtures/",
            "outputs/fixtures/notes.txt",
            "outputs/fixtures/policy.pdf",
        }
        if interview:
            expected.add("inputs/interview_state.json")
        assert set(specification.namelist()) == {f"{root}/{name}" for name in expected}
        specification.extractall(extracted)

    extracted = extracted / root

    from metis.engine.simulation.types import Specification as EngineSpecification

    experiment = yaml.safe_load((extracted / "outputs/specification.yaml").read_text())
    assert [task["id"] for task in experiment["tasks"]] == [
        "TC-001",
        "TC-002",
        "TC-003",
    ]
    graders = {
        scenario.id: [ref.fqn for ref in scenario.grader_refs]
        for scenario in EngineSpecification.model_validate(experiment).resolved_tasks()
    }
    assert graders == {
        "supported-answer": [
            "metis.library.graders.SynthesisFaithfulnessGrader",
            "metis.library.graders.TurnBudgetGrader",
        ],
        "short-recovery": ["metis.library.graders.TurnBudgetGrader"],
    }
    _validate_inputs(extracted / "outputs")
