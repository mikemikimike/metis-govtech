"""The checks the wizard makes on a Criterion's Grader before it compiles."""

import pytest

from metis.wizard.application.compile import CompilationError, compile_experiment
from metis.wizard.application.matching import CRITERION_JUDGE_FQN
from metis.wizard.application.matching.matcher import validate_grader_args
from tests.fixtures.wizard.specifications import research_assistant


@pytest.mark.parametrize(
    "args", [{"criterion": "override"}, {"unknown": 1}, {"threshold": 2}]
)
def test_compile_reports_invalid_fallback_settings_by_criterion(args) -> None:
    specification = research_assistant()
    criterion = specification.features[0].behaviours[0].criteria[0]
    criterion.grader_fqn = CRITERION_JUDGE_FQN
    criterion.grader_args = args
    with pytest.raises(CompilationError, match=criterion.id):
        compile_experiment(specification, "fallback")


def test_fallback_validation_uses_the_description_without_storing_instructions() -> (
    None
):
    specification = research_assistant()
    criterion = specification.features[0].behaviours[0].criteria[0]
    criterion.grader_fqn = CRITERION_JUDGE_FQN
    criterion.grader_args = {"threshold": 0.75}
    validate_grader_args(
        criterion.grader_fqn, criterion.grader_args, description=criterion.description
    )
    assert criterion.grader_args == {"threshold": 0.75}


def test_the_abstract_grader_base_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="abstract base"):
        validate_grader_args("metis.library.grader.Grader", {})


def test_a_concrete_grader_with_valid_args_passes() -> None:
    validate_grader_args(
        "tests.unit.engine.graders_for_tests.FixedScoreGrader", {"score": 1.0}
    )


def test_embeddings_warning_names_the_variables_when_the_key_is_missing() -> None:
    from metis.wizard.application.matching import embeddings_warning

    warning = embeddings_warning({"INTERVIEW_API_KEY": "k"})
    assert warning is not None
    assert "EMBEDDING_API_KEY or OPENAI_API_KEY" in warning
    assert "criterion judge" in warning
    assert embeddings_warning({"OPENAI_API_KEY": "k"}) is None
