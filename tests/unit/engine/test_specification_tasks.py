"""Task and Criterion identity across planning, evaluation, resume and reporting."""

from pathlib import Path

import pytest
from deepeval.test_case import LLMTestCase
from pydantic import ValidationError

from metis.engine.cli import _classify_resume_trials
from metis.engine.evaluation.orchestrator import _resolve_graders, _run_grader
from metis.engine.simulation.experiment import expand_trial_plan, trial_folder_name
from metis.engine.simulation.types import (
    Specification,
    TrialConfig,
    TrialOutcome,
    TrialRecord,
)
from metis.insights._models import Report
from metis.insights._report import build_report


def specification() -> Specification:
    data = Specification.model_validate(
        {
            "schema_version": 2,
            "id": "task-identity",
            "runner_factory_ref": "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory",
            "product": {
                "name": "Chatbot",
                "users": "Analysts",
                "description": "Answer questions.",
            },
            "features": [
                {
                    "id": "F-1",
                    "name": "Chat",
                    "description": "Answer questions.",
                    "behaviours": [
                        {
                            "id": "B-1",
                            "name": "Efficiency",
                            "description": "Use few turns.",
                            "measured": True,
                            "criteria": [
                                {
                                    "id": "AC-UNI-22",
                                    "name": "Short budget",
                                    "description": {
                                        "given": "a question",
                                        "when": "the session ends",
                                        "then": "at most 4 turns",
                                    },
                                    "grader_fqn": "metis.library.graders.TurnBudgetGrader",
                                    "grader_args": {"max_turns": 4},
                                }
                            ],
                        }
                    ],
                }
            ],
            "personas": [
                {
                    "id": "P-1",
                    "name": "Cooperative user",
                    "description": "Gives details.",
                }
            ],
            "scenarios": [
                {"id": "S-1", "name": "Question", "description": "Ask a question."}
            ],
            "tasks": [
                {
                    "id": "TC-001",
                    "scenario_ref": "S-1",
                    "persona_ref": "P-1",
                    "fixtures": [],
                    "num_trials": 1,
                    "criterion_refs": ["AC-UNI-22"],
                }
            ],
        }
    ).model_dump()
    short = data["features"][0]["behaviours"][0]["criteria"][0]
    long = {**short, "id": "AC-LONG", "grader_args": {"max_turns": 10}}
    data["features"][0]["behaviours"][0]["criteria"].append(long)
    first = data["tasks"][0]
    data["tasks"].append({**first, "id": "TC-002", "criterion_refs": ["AC-LONG"]})
    return Specification.model_validate(data)


@pytest.mark.asyncio
async def test_task_scores_keep_criterion_configuration_and_trial_identity(
    tmp_path: Path,
) -> None:
    import asyncio

    experiment = specification()
    plan = expand_trial_plan(experiment, {p.id: p for p in experiment.personas})
    assert len(plan) == 2
    names = [trial_folder_name(*item) for item in plan]
    assert len(set(names)) == 2
    rows = []
    outcomes = []
    for item in plan:
        scenario, persona, index = item
        grader = _resolve_graders(scenario.grader_refs)[0]
        case = LLMTestCase(
            input="A question", actual_output="An answer", metadata={"total_turns": 7}
        )
        result = await _run_grader(grader, case, asyncio.Semaphore(1))
        assert result.grader_args == scenario.grader_refs[0].args
        assert result.criterion_id == scenario.grader_refs[0].criterion_id
        rows.append(
            {
                "session_id": scenario.task_id,
                "scenario_id": scenario.id,
                "graders": [
                    {
                        "name": result.name,
                        "criterion_id": result.criterion_id,
                        "grader_fqn": result.grader_fqn,
                        "grader_args": result.grader_args,
                        "task_id": scenario.task_id,
                        "trial_index": index,
                        "success": result.success,
                        "skipped": result.skipped,
                    }
                ],
            }
        )
        outcomes.append(
            {
                "id": scenario.task_id,
                "task_id": scenario.task_id,
                "trial_index": index,
                "session": scenario.task_id,
                "persona": persona.id,
                "scenario": scenario.id,
                "stopReason": "goal_achieved",
                "message": "goal_achieved",
                "failureSource": "outcome",
                "turns": 7,
            }
        )
        path = tmp_path / "trials" / trial_folder_name(*item) / "record.json"
        path.parent.mkdir(parents=True)
        record = TrialRecord(
            config=TrialConfig(
                task_id=scenario.task_id,
                trial_index=index,
                persona=persona.id,
                scenario=scenario.id,
                grader_refs=scenario.grader_refs,
            ),
            outcome=TrialOutcome(
                stop_reason="goal_achieved", total_turns=7, duration_seconds=1
            ),
        )
        path.write_text(record.model_dump_json())
    assert _classify_resume_trials(tmp_path, plan)[0] == []
    report = build_report(experiment.model_dump(), rows, trial_outcomes=outcomes)
    assert report["criteria"]["AC-UNI-22"]["rate"] == 0
    assert report["criteria"]["AC-LONG"]["rate"] == 100
    assert [r["task_id"] for r in report["resultTable"]["rows"]] == ["TC-001", "TC-002"]
    saved = Report.model_validate(report).model_dump()
    assert saved["criteria"]["AC-LONG"]["evidence"][0]["grader_args"] == {
        "max_turns": 10
    }


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_task",
        "duplicate_criterion",
        "scenario",
        "persona",
        "criterion",
        "coverage",
        "trials",
    ],
)
def test_specification_rejects_invalid_task_graph(fault: str) -> None:
    data = specification().model_dump()
    if fault == "duplicate_task":
        data["tasks"][1]["id"] = data["tasks"][0]["id"]
    elif fault == "duplicate_criterion":
        criteria = data["features"][0]["behaviours"][0]["criteria"]
        criteria[1]["id"] = criteria[0]["id"]
    elif fault in {"scenario", "persona"}:
        data["tasks"][0][f"{fault}_ref"] = "missing"
    elif fault == "criterion":
        data["tasks"][0]["criterion_refs"] = ["missing"]
    elif fault == "coverage":
        data["tasks"] = []
    else:
        data["tasks"][0]["num_trials"] = 0
    with pytest.raises(ValidationError):
        Specification.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_turns", 0),
        ("timeout_minutes", 0),
        ("response_wait_ms", 0),
        ("max_run_retries", -1),
    ],
)
def test_execution_settings_require_positive_limits_and_nonnegative_retries(
    field: str,
    value: int,
) -> None:
    document = specification().model_dump()
    document["tasks"][0][field] = value
    with pytest.raises(ValidationError, match=field):
        Specification.model_validate(document)


def test_omitted_execution_settings_use_engine_defaults() -> None:
    document = specification().model_dump()
    task_fields = (
        "max_turns",
        "timeout_minutes",
        "response_wait_ms",
        "max_run_retries",
    )
    resolved_fields = (
        "max_turns",
        "timeout_minutes",
        "response_wait_ms",
        "max_trial_retries",
    )
    for field in task_fields:
        document["tasks"][0].pop(field)
    parsed = Specification.model_validate(document)
    resolved = parsed.resolved_tasks()[0]
    assert tuple(getattr(resolved, field) for field in resolved_fields) == (
        20,
        15,
        300000,
        None,
    )
