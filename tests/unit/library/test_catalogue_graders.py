"""The Execution and Decision Quality and Task and Output Quality graders, with a mocked judge.

The shared steps (evidence items, prompt layout, judgment form, aggregation) are tested in
``test_judge.py`` and ``tests/unit/core``. These tests check what each grader owns: its required
settings, the text its settings put in the prompt, its evidence checks, and the scope of its
results.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

import metis.library.graders as catalog
from metis.core.artifacts import Artifact
from metis.core.traces import GradingInput, Observation, Trace
from metis.library.grader import LLMSettings
from metis.library.taxonomy import Scope
from tests.fixtures.criterion_judge import judge_client

if TYPE_CHECKING:
    from pathlib import Path

    from metis.core.grading import GraderResult

VERDICT = {"status": "scored", "score": 1, "reason": "Met."}
NOT_APPLICABLE = {
    "status": "not_applicable",
    "score": None,
    "reason": "Nothing to judge.",
}

REQUIRED: dict[str, dict[str, Any]] = {
    "ActionChoiceAppropriatenessGrader": {},
    "AdaptationToChangedConditionsGrader": {},
    "AppropriateHandlingOfCapabilityLimitsGrader": {},
    "AttributionAccuracyGrader": {"source_materials": ["Annual report 2025"]},
    "AvoidingUnproductiveRepetitionGrader": {},
    "ClaimSupportByEvidenceGrader": {"designated_evidence": ["Revenue rose 12%."]},
    "ContentFidelityGrader": {"source_content": "The meeting moved to Friday."},
    "CoordinationQualityGrader": {},
    "ErrorDetectionGrader": {},
    "ErrorRecoveryGrader": {},
    "EvidenceSourceSuitabilityGrader": {
        "suitability_requirements": ["Published after 2024"],
        "sources": ["The 2025 product manual"],
    },
    "FactualAccuracyGrader": {"ground_truth": ["Paris is the capital of France."]},
    "FormatSchemaComplianceGrader": {"format_requirements": ["Use a bulleted list."]},
    "InputInterpretationAccuracyGrader": {
        "interpretation_criteria": ["The date the user gave"]
    },
    "LanguageIdentificationAccuracyGrader": {"expected_languages": ["Malay"]},
    "OutcomeVerificationGrader": {},
    "OutputCorrectnessGrader": {"correctness_conditions": ["The total is 42."]},
    "PlanningQualityGrader": {},
    "ReasoningValidityGrader": {},
    "RequiredComponentCompletenessGrader": {"required_components": ["A summary"]},
    "SpeechRecognitionAccuracyGrader": {
        "reference_transcript": "Book a table for two."
    },
    "SpokenContentFidelityGrader": {"intended_content": "Your order has shipped."},
    "StateTrackingGrader": {},
    "StoppingAppropriatenessGrader": {},
    "TaskConstraintAdherenceGrader": {"constraints": ["Spend under 100 dollars."]},
    "TaskSuccessGrader": {},
    "ToolArgumentCorrectnessGrader": {},
    "ToolChoiceAppropriatenessGrader": {},
    "UseOfObservedStateGrader": {},
    "UseOfPriorInformationGrader": {},
}
MULTI_RULE = {
    "EvidenceSourceSuitabilityGrader": "sources",
    "RequiredComponentCompletenessGrader": "required_components",
    "TaskConstraintAdherenceGrader": "constraints",
}
NEEDS_TOOL_CALLS = {"ToolArgumentCorrectnessGrader", "ToolChoiceAppropriatenessGrader"}


def _session(*, agent: str | None = "planner", **extra: Any) -> GradingInput:
    """Two turns. The second calls a search tool, inside an agent when ``agent`` is set."""
    first = Trace(
        id="t1",
        session_id="s",
        observations=(Observation(id="r1", trace_id="t1", input="hi", output="hello"),),
    )
    tool_parent = "a2" if agent else "r2"
    observations = [
        Observation(id="r2", trace_id="t2", input="find x", output="found x"),
        Observation(
            id="tool",
            trace_id="t2",
            type="TOOL",
            name="search",
            input={"q": "x"},
            output={"hits": 1},
            parent_observation_id=tool_parent,
        ),
    ]
    if agent:
        observations.insert(
            1,
            Observation(
                id="a2",
                trace_id="t2",
                type="AGENT",
                name=agent,
                parent_observation_id="r2",
            ),
        )
    second = Trace(id="t2", session_id="s", observations=tuple(observations))
    return GradingInput(traces=(first, second), **extra)


def _with_tools(**extra: Any) -> GradingInput:
    return _session(tools_available=("search: Searches the index",), **extra)


def _grader(name: str, **args: Any):
    cls = getattr(catalog, name)
    return cls(
        cls.args_model.model_validate({"model": "judge", **REQUIRED[name], **args})
    )


def _grade(
    grader, gi: GradingInput, reply: object
) -> tuple[list[GraderResult], list[dict]]:
    requests: list[dict] = []
    content = (
        [json.dumps(r) for r in reply] if isinstance(reply, list) else json.dumps(reply)
    )
    client = judge_client(content, requests)

    async def run():
        async with client:
            return await grader.grade(gi, LLMSettings(client))

    return asyncio.run(run()).results, requests


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_the_default_judges_one_item_and_names_it(name: str) -> None:
    grader = _grader(name)
    [result], [request] = _grade(grader, _with_tools(), VERDICT)
    assert result.status == "scored", result.reason
    assert result.score == 1.0
    expected_scope = "turn:2" if grader.taxonomy.scopes[0] == Scope.TRACE else "session"
    assert result.scope == expected_scope
    system = request["input"][0]["content"]
    assert "untrusted evidence" in system
    for value in REQUIRED[name].values():
        for text in value if isinstance(value, list) else [value]:
            assert text in system, f"{name} leaves {text!r} out of the prompt"


@pytest.mark.parametrize("name", sorted(n for n in REQUIRED if n not in MULTI_RULE))
def test_a_criterion_that_does_not_apply_is_errored(name: str) -> None:
    [result], _ = _grade(_grader(name), _with_tools(), NOT_APPLICABLE)
    assert (result.status, result.reason) == ("errored", "Nothing to judge.")


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_an_empty_session_is_errored_without_a_judge_call(name: str) -> None:
    [result], requests = _grade(
        _grader(name), GradingInput(traces=(), tools_available=("t",)), VERDICT
    )
    assert result.status == "errored"
    assert requests == []


@pytest.mark.parametrize(
    "name", sorted(n for n, required in REQUIRED.items() if required)
)
def test_the_measure_reference_is_required(name: str) -> None:
    cls = getattr(catalog, name)
    with pytest.raises(ValidationError):
        cls.args_model.model_validate({"model": "judge"})


@pytest.mark.parametrize(
    "name",
    sorted(
        n
        for n in REQUIRED
        if "task_description" in getattr(catalog, n).args_model.model_fields
    ),
)
def test_a_task_description_is_optional_and_reaches_the_prompt(name: str) -> None:
    _, [unset] = _grade(_grader(name), _with_tools(), VERDICT)
    assert "Infer what the user asked for" in unset["input"][0]["content"]
    _, [set_] = _grade(
        _grader(name, task_description="Book a flight to Osaka."),
        _with_tools(),
        VERDICT,
    )
    assert "Book a flight to Osaka." in set_["input"][0]["content"]


@pytest.mark.parametrize("name", sorted(NEEDS_TOOL_CALLS))
def test_tool_graders_need_recorded_tool_calls(name: str) -> None:
    no_tools = GradingInput(
        traces=_session().traces[:1], tools_available=("search: Searches",)
    )
    [result], requests = _grade(_grader(name), no_tools, VERDICT)
    assert result.status == "errored"
    assert "no recorded tool calls" in result.reason
    assert requests == []


def test_tool_choice_needs_the_tool_catalogue_and_shows_it() -> None:
    [result], requests = _grade(
        _grader("ToolChoiceAppropriatenessGrader"), _session(), VERDICT
    )
    assert result.status == "errored"
    assert "tools_available" in result.reason
    assert requests == []
    _, [request] = _grade(
        _grader("ToolChoiceAppropriatenessGrader"), _with_tools(), VERDICT
    )
    assert "search: Searches the index" in request["input"][0]["content"]


def test_coordination_needs_a_recorded_agent() -> None:
    [result], requests = _grade(
        _grader("CoordinationQualityGrader"), _session(agent=None), VERDICT
    )
    assert result.status == "errored"
    assert "delegation" in result.reason
    assert requests == []


def test_session_graders_see_tool_results() -> None:
    _, [request] = _grade(_grader("ErrorRecoveryGrader"), _session(), VERDICT)
    [evidence] = request["input"][1]["content"]
    assert 'Tool result [ok]: {"hits": 1}' in evidence["text"]


@pytest.mark.parametrize(
    "name",
    sorted(
        n for n in REQUIRED if Scope.ARTIFACT in getattr(catalog, n).taxonomy.scopes
    ),
)
def test_artifact_scope_attaches_each_revision(name: str, tmp_path: Path) -> None:
    path = tmp_path / "report.txt"
    path.write_text("- one\n- two")
    file = Artifact(
        name="report.txt", source="target", state="received", path=str(path)
    )
    grader = _grader(name, scope="artifact", artifact="report.txt")
    results, requests = _grade(grader, _with_tools(artifacts=(file, file)), VERDICT)
    assert [r.scope for r in results] == [
        "artifact:report.txt:0",
        "artifact:report.txt:1",
    ]
    [attached] = requests[0]["input"][1]["content"]
    assert (attached["type"], attached["filename"]) == ("input_file", "report.txt")


@pytest.mark.parametrize("name", sorted(MULTI_RULE))
@pytest.mark.parametrize(
    ("replies", "status", "score"),
    [
        ([(1, "Yes."), (1, "Yes.")], "scored", 1.0),
        ([(1, "Yes."), (0, "No.")], "scored", 0.0),
        ([(1, "Yes."), (None, "Cannot tell.")], "errored", None),
        ([(0, "No."), (None, "Cannot tell.")], "errored", None),
    ],
)
def test_multi_rule_graders_judge_each_rule_and_pass_only_if_all_pass(
    name: str, replies, status, score
) -> None:
    rules = ["First rule.", "Second rule."]
    grader = _grader(name, **{MULTI_RULE[name]: rules})
    reply = [
        {"status": "scored", "score": s, "reason": r}
        if s is not None
        else {"status": "not_applicable", "score": None, "reason": r}
        for s, r in replies
    ]
    [result], requests = _grade(grader, _with_tools(), reply)
    assert (result.status, result.score) == (status, score)
    assert len(requests) == 2
    assert "First rule." in requests[0]["input"][0]["content"]
    assert "Second rule." in requests[1]["input"][0]["content"]
    assert "Second rule." not in requests[0]["input"][0]["content"]


@pytest.mark.parametrize(
    "name",
    sorted(
        n for n in REQUIRED if getattr(catalog, n).taxonomy.scopes[0] == Scope.TRACE
    ),
)
def test_trace_graders_can_judge_every_turn(name: str) -> None:
    results, requests = _grade(_grader(name, turn="each"), _with_tools(), VERDICT)
    assert [r.scope for r in results] == ["turn:1", "turn:2"]
    assert len(requests) == 2


class TestFormatSchemaCompliance:
    SCHEMA = json.dumps(
        {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    )

    def _run(self, reply: str, **args: Any):
        cls = catalog.FormatSchemaComplianceGrader
        grader = cls(
            cls.args_model.model_validate(
                {"model": "judge", "json_schema_spec": self.SCHEMA, **args}
            )
        )
        gi = GradingInput(
            traces=(
                Trace(
                    id="t1",
                    session_id="s",
                    observations=(
                        Observation(id="r", trace_id="t1", input="q", output=reply),
                    ),
                ),
            )
        )
        return _grade(grader, gi, VERDICT)

    def test_a_valid_reply_passes_without_a_judge_call(self) -> None:
        [result], requests = self._run('{"a": 1}')
        assert (result.status, result.score, result.scope) == ("scored", 1.0, "turn:1")
        assert requests == []

    @pytest.mark.parametrize("reply", ['{"a": "x"}', "not json"])
    def test_an_invalid_reply_fails_without_a_judge_call(self, reply: str) -> None:
        [result], requests = self._run(reply)
        assert (result.status, result.score) == ("scored", 0.0)
        assert requests == []

    def test_prose_rules_go_to_the_judge_after_the_schema_passes(self) -> None:
        [result], [request] = self._run(
            '{"a": 1}', format_requirements=["Use one key."]
        )
        assert result.status == "scored"
        assert "Use one key." in request["input"][0]["content"]

    def test_it_needs_a_requirement_or_a_schema(self) -> None:
        cls = catalog.FormatSchemaComplianceGrader
        with pytest.raises(ValidationError):
            cls.args_model.model_validate({"model": "judge"})
