"""The checks the wizard makes on a Criterion's Grader before it compiles."""

import pytest

from metis.wizard.application.compile import CompilationError, compile_experiment
from metis.wizard.application.matching import GENERATED_JUDGE_FQN
from metis.wizard.application.matching.matcher import validate_grader_args
from tests.fixtures.wizard.specifications import research_assistant


def test_the_fallback_judge_names_the_redesign_and_asks_for_a_grader() -> None:
    with pytest.raises(ValueError) as caught:
        validate_grader_args(GENERATED_JUDGE_FQN, {"criterion": "x", "name": "x"})

    message = str(caught.value)
    assert "no grader matched" in message
    assert "#428" in message
    assert "choose a grader for this criterion" in message


def test_compile_reports_the_fallback_judge_by_criterion() -> None:
    specification = research_assistant()
    criterion = next(
        criterion
        for behaviour in specification.measured_behaviours()
        for criterion in behaviour.criteria
    )
    criterion.grader_fqn = GENERATED_JUDGE_FQN
    criterion.grader_args = {"criterion": "x", "name": "x"}

    with pytest.raises(CompilationError) as caught:
        compile_experiment(specification, "fallback")

    assert f"Criterion {criterion.id}: no grader matched" in str(caught.value)


def test_the_abstract_grader_base_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="abstract base"):
        validate_grader_args("metis.library.grader.Grader", {})


def test_a_concrete_grader_with_valid_args_passes() -> None:
    validate_grader_args(
        "tests.unit.engine.graders_for_tests.FixedScoreGrader", {"score": 1.0}
    )
