"""gen_1 writes one LLM-call row per user-agent and summarizer call (#476)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from metis.core.trials import TrialConfig
from metis.engine.simulation import model_settings as simulation_model_settings
from metis.engine.simulation.experiment import TrialPlanItem, _worker, trial_folder_name
from metis.engine.simulation.gen_1 import artifact_summarizer
from metis.engine.simulation.gen_1 import trial as gen_1_trial
from metis.engine.simulation.gen_1.trial import build_trial
from metis.engine.simulation.llm_calls import LLMCallLog, LLMCallRecord
from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    Artifact,
    ChosenAction,
    Observation,
    Persona,
    Scenario,
    UserAgentOutput,
)


class _FakeOpenAI:
    """Stands in for ``AsyncOpenAI``; answers by the requested response format."""

    def __init__(self, **kwargs: Any) -> None:
        assert kwargs["max_retries"] == 0  # retries belong to the wrapper
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        )

    async def _parse(self, *, response_format: type, **_kwargs: Any) -> object:
        if response_format is UserAgentOutput:
            # Opening continues into turn 1; the reply after it ends the trial.
            parsed: object = UserAgentOutput(message="hi", decision="continue")
            _FakeOpenAI.user_agent_calls += 1
            if _FakeOpenAI.user_agent_calls > 1:
                parsed = UserAgentOutput(message="thanks", decision="goal_achieved")
        else:
            parsed = response_format(
                content_description="2 rows", state_description="delivered"
            )
        return SimpleNamespace(
            model="served-model",
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3),
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))],
        )

    user_agent_calls = 0


class _OneFileRunner(Runner):
    """Delivers one text file on the first turn."""

    async def setup(self, config: TrialConfig) -> None:
        return None

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        return Observation(
            text="here is your file",
            artifacts=[Artifact(name="out.csv", path="out.csv", state="received")],
        )

    async def teardown(self) -> None:
        pass

    async def get_session_id(self) -> str | None:
        return "sess-1"


@pytest.fixture(autouse=True)
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeOpenAI.user_agent_calls = 0
    monkeypatch.setattr(simulation_model_settings, "AsyncOpenAI", _FakeOpenAI)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_a_trial_logs_every_user_agent_and_summarizer_call(
    tmp_path: Path,
) -> None:
    (tmp_path / "out.csv").write_text("a,b\n1,2\n")
    run_dir = tmp_path / "outputs" / "trials" / "s-p-1"
    scenario = Scenario(id="s", description="get a file", persona_refs=["p"])

    trial = build_trial(
        runner=_OneFileRunner(),
        persona=Persona(id="p", description="a user"),
        scenario=scenario,
        trial_config=TrialConfig(persona="p", scenario="s", max_turns=5),
        run_dir=run_dir,
        fixtures_dir=tmp_path / "fixtures",
        experiment_root=tmp_path,
        fixture_artifacts=[],
        trial_index=1,
        state=None,
        tui_ctx=None,
        shutdown_event=None,
    )
    record = await trial.execute()

    assert record.outcome.stop_reason == "goal_achieved"
    rows = _rows(run_dir / "evidence" / "llm_calls.jsonl")
    # Opening, the download's summary, then the reply to turn 1.
    assert [r["component"] for r in rows] == [
        "user_agent",
        "artifact_summarizer",
        "user_agent",
    ]
    assert all(r["returned_model"] == "served-model" for r in rows)
    assert all((r["tokens_in"], r["tokens_out"]) == (11, 3) for r in rows)


@pytest.mark.asyncio
async def test_fixture_descriptions_go_to_the_experiment_log(tmp_path: Path) -> None:
    fixtures_dir = tmp_path / "inputs" / "fixtures"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "sales.csv").write_text("region,total\nnorth,1\n")

    resolved = await artifact_summarizer.resolve_fixture_descriptions(
        ["sales.csv", "sales.csv"], fixtures_dir, tmp_path, {}
    )

    assert resolved == {"sales.csv": "2 rows"}
    [row] = _rows(tmp_path / "logs" / "llm_calls.jsonl")
    assert row["component"] == "artifact_summarizer"
    assert not (tmp_path / "outputs").exists()


@pytest.mark.asyncio
async def test_a_retried_trial_keeps_the_earlier_attempts_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Each attempt starts a new file; the earlier one is moved aside, not lost."""

    def failing_agent(*, llm_log: LLMCallLog, **_kwargs: Any) -> None:
        llm_log.append(
            LLMCallRecord(
                at=datetime.now(tz=UTC),
                component="user_agent",
                requested_model="m",
                returned_model=None,
                tokens_in=None,
                tokens_out=None,
                latency_ms=1,
                error="InternalServerError: down",
            )
        )
        raise RuntimeError("user agent down")

    monkeypatch.setattr(gen_1_trial, "UserAgent", failing_agent)
    scenario = Scenario(id="s", description="d", persona_refs=["p"], max_turns=1)
    persona = Persona(id="p", description="a user")

    class _Factory:
        async def create(self, *_args: object) -> Runner:
            return _OneFileRunner()

    await _worker(
        worker_id=0,
        runner_factory=_Factory(),  # type: ignore[arg-type]
        worker_trials=[TrialPlanItem(scenario, persona, 1)],
        experiment_root=tmp_path,
        fixtures_dir=tmp_path / "fixtures",
        fixture_content_descriptions={},
        console_lock=asyncio.Lock(),
        started_scenarios=set(),
        trial_max_retries=1,
        trial_retry_delay_seconds=0,
    )

    evidence = (
        tmp_path
        / "outputs"
        / "trials"
        / trial_folder_name(scenario, persona, 1)
        / "evidence"
    )
    current = evidence / "llm_calls.jsonl"
    superseded = list(evidence.glob("llm_calls-superseded-*.jsonl"))
    assert len(_rows(current)) == 1
    assert len(superseded) == 1 and len(_rows(superseded[0])) == 1
