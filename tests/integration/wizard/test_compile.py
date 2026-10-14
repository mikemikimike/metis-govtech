"""The complete Specification survives compilation, packaging and engine loading."""

from pathlib import Path

import pytest
import yaml

from metis.engine.simulation.types import Specification
from metis.wizard.application.compile import (
    CompilationError,
    compile_experiment,
    render_review,
    to_yaml,
    write_experiment,
)
from tests.fixtures.wizard.specifications import research_assistant


def test_specification_round_trip_and_golden(fixtures_dir: Path) -> None:
    specification = research_assistant()
    document = compile_experiment(specification, "research-assistant")
    output = to_yaml(document)
    assert output == to_yaml(compile_experiment(specification, "research-assistant"))
    assert output == (fixtures_dir / "golden_specification.yaml").read_text()
    loaded = Specification.model_validate(yaml.safe_load(output))
    assert loaded.target == specification.target
    assert loaded.features == specification.features
    assert loaded.tasks == specification.tasks
    assert loaded.trial_count() == 9
    assert document["tasks"][0]["behaviour_refs"] == ["EB-1"]
    assert [ref.criterion_id for ref in loaded.resolved_tasks()[0].grader_refs] == [
        "AC-1-1",
        "AC-1-2",
    ]


@pytest.mark.parametrize("fault", ["persona", "behaviour", "trials", "coverage"])
def test_invalid_specification_is_not_written(tmp_path: Path, fault: str) -> None:
    specification = research_assistant()
    if fault == "persona":
        specification.tasks[0].persona_ref = "missing"
    elif fault == "behaviour":
        specification.tasks[0].behaviour_refs = ["missing"]
    elif fault == "trials":
        specification.tasks[0].num_trials = 0
    else:
        specification.tasks = specification.tasks[:2]
    target = tmp_path / "specification.yaml"
    with pytest.raises(CompilationError):
        write_experiment(specification, "research-assistant", target)
    assert not target.exists()


def test_specification_and_review_preserve_unicode(tmp_path: Path) -> None:
    specification = research_assistant()
    specification.target.description = "Swipe → see detail"
    path = tmp_path / "specification.yaml"
    write_experiment(specification, "research-assistant", path)
    assert (
        Specification.load_file(path).target.description
        == specification.target.description
    )
    review = render_review(specification, "research-assistant")
    assert specification.target.description in review
    assert specification.target.detail in review
    assert "TC-001" in review
    assert "9 trials" in review


def test_assigned_task_ids_survive_edits_and_new_tasks_get_new_ids() -> None:
    from metis.wizard.domain.specification import Specification

    specification = research_assistant()
    specification.tasks[0].id = ""
    first = Specification.model_validate(compile_experiment(specification, "test"))
    assigned = first.tasks[0].id
    first.tasks.reverse()
    task = first.task(assigned)
    assert task is not None
    task.num_trials = 7
    task.max_turns = 9
    task.timeout_minutes = 2
    task.response_wait_ms = 45000
    task.max_run_retries = 0
    second = Specification.model_validate(compile_experiment(first, "test"))
    restored = second.task(assigned)
    assert restored is not None
    assert restored.num_trials == 7
    assert restored.max_turns == 9
    assert restored.timeout_minutes == 2
    assert restored.response_wait_ms == 45000
    assert restored.max_run_retries == 0
    first.tasks.append(task.model_copy(deep=True, update={"id": ""}))
    replacement = compile_experiment(first, "test")["tasks"][-1]
    assert replacement["id"] != assigned


def test_criterion_parameters_survive_compilation_and_reject_unknown_arguments() -> (
    None
):
    specification = research_assistant()
    criterion = specification.behaviour("EB-2").criteria[0]  # type: ignore[union-attr]
    criterion.grader_args = {"max_turns": 4}
    compiled = Specification.model_validate(compile_experiment(specification, "test"))
    assert compiled.criterion(criterion.id).grader_args == {"max_turns": 4}  # type: ignore[union-attr]
    criterion.grader_args = {"turn_buget": 4}
    with pytest.raises(CompilationError, match=criterion.id):
        compile_experiment(specification, "test")
