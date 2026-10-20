"""OrcaApiRunner against the published Orca REST API v1 spec (issue #338).

One test per behaviour the spec pins down and the runner used to get wrong:
there is no session exhaustion (only a per-call input cap), a submit 404 is
attributable only by what was sent, ``X-PlatformAI-Key`` belongs to submits
alone, a cancel is confirmed rather than assumed, the weekly allowance is
readable before the spend, and an empty message has no valid body.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from rich.console import Console

import metis.engine.simulation.gen_1.runners.orca_api as orca_api
from metis.engine.simulation.exceptions import (
    AuthLossError,
    SimulationError,
    TargetSessionEnded,
    TargetSessionLostError,
)
from metis.engine.simulation.gen_1.runners.orca_api import (
    OrcaApiRunner,
    OrcaApiRunnerConfig,
    OrcaApiRunnerFactory,
)
from metis.engine.simulation.gen_1.runners.orca_api._config import (
    ENV_PLATFORM_AI_KEY,
    PLATFORM_AI_KEY_HEADER,
)
from metis.engine.simulation.types import Observation

_PLATFORM_KEY = "platform-key-abcdef"


async def _no_sleep(_seconds: float) -> None:
    return None


def _make_runner(
    tmp_path: Path,
    handler: Any = None,
    *,
    requests: list[httpx.Request] | None = None,
    **config_kwargs: Any,
) -> OrcaApiRunner:
    """A runner whose transport is ``handler``, recording requests into ``requests``."""

    def _record(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        assert handler is not None
        return handler(request)

    config = OrcaApiRunnerConfig(
        base_url="https://orca.example.com",
        api_key="test-key",
        poll_interval_ms=1,
        **config_kwargs,
    )
    client = httpx.AsyncClient(
        base_url="https://orca.example.com/api/v1/",
        transport=httpx.MockTransport(_record) if handler else None,
    )
    for directory in ("fixtures", "run"):
        (tmp_path / directory).mkdir(exist_ok=True)
    return OrcaApiRunner(
        client,
        config,
        fixtures_dir=tmp_path / "fixtures",
        run_dir=tmp_path / "run",
        experiment_root=tmp_path,
        sleep=_no_sleep,
    )


# -- 1. there is no session exhaustion, only a per-call input cap -------------


class TestInputCapEscalation:
    @pytest.mark.asyncio
    async def test_first_input_cap_failure_is_an_ordinary_turn_error(
        self, tmp_path: Path
    ) -> None:
        """One oversized call may be a single large fixture; the run continues."""
        runner = _make_runner(tmp_path)
        observation = await runner._build_observation(
            {"status": "failed", "error": "Request exceeds the per-call input cap"}
        )
        assert isinstance(observation, Observation)
        assert observation.text == ""
        assert (
            observation.response_notices
            and "input cap" in observation.response_notices[0]
        )
        assert runner._input_cap_failures == 1

    @pytest.mark.asyncio
    async def test_second_consecutive_input_cap_failure_ends_the_run(
        self, tmp_path: Path
    ) -> None:
        """The cause is the accumulated context, so no later turn could succeed."""
        runner = _make_runner(tmp_path)
        digest = {"status": "failed", "error": "input cap of 200000 tokens exceeded"}
        await runner._build_observation(digest)
        with pytest.raises(TargetSessionEnded, match="input cap"):
            await runner._build_observation(digest)

    @pytest.mark.asyncio
    async def test_a_settled_turn_clears_the_streak(self, tmp_path: Path) -> None:
        """A session that answered is not wedged, whatever was too big for one call."""
        runner = _make_runner(tmp_path)
        await runner._build_observation(
            {"status": "failed", "error": "per-call input limit reached"}
        )
        await runner._build_observation({"status": "completed", "output": "ok"})
        assert runner._input_cap_failures == 0
        # No escalation: the next cap failure is the first of a new streak.
        await runner._build_observation(
            {"status": "failed", "error": "per-call input limit reached"}
        )

    @pytest.mark.asyncio
    async def test_other_failures_stay_per_turn(self, tmp_path: Path) -> None:
        """A guardrail block is genuinely one turn; the persona sees it and adapts."""
        runner = _make_runner(tmp_path)
        digest = {"status": "failed", "error": "Blocked by a content guardrail"}
        for _ in range(3):
            observation = await runner._build_observation(digest)
            assert (
                observation.response_notices
                and "guardrail" in observation.response_notices[0]
            )

    def test_no_session_exhaustion_remains_in_the_runner(self) -> None:
        """v1 has no session budget, so nothing may branch on one."""
        source = Path(orca_api.__file__).read_text()
        assert "session_exhausted" not in source
        assert '"exhausted"' not in source


# -- 2. a submit 404 is attributed by what was sent ---------------------------


class TestSubmit404Attribution:
    @pytest.mark.asyncio
    async def test_404_on_a_submit_with_files_blames_the_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dead fileId is recoverable and repeats; a session loss retries the run."""
        runner = _make_runner(
            tmp_path, lambda request: httpx.Response(404, json={"error": "not_found"})
        )
        runner._session_id = "session-1"
        runner._fixtures = ["sales.csv"]
        runner._fixture_library._entries["sales.csv"] = "file-dead"

        async def staged(message: str, actions: list[Any]) -> dict[str, Any]:
            runner._attaching = ["sales.csv"]
            return {"message": message, "files": ["file-dead"]}

        monkeypatch.setattr(runner, "_build_submit_body", staged)

        observation = await runner.send_turn("hi", [])

        assert (
            observation.response_notices
            and "sales.csv" in observation.response_notices[0]
        )
        # The id is evicted so the next attach re-uploads the file...
        assert "sales.csv" not in runner._fixture_library._entries
        # ...and the fixture is still offered, unlike a rejected one.
        assert "sales.csv" not in runner._attached
        assert runner._attaching == []
        assert any(slot.id == "sales.csv" for slot in observation.available_actions)
        assert observation.delivered is False  # I5: Orca rejected the request

    @pytest.mark.asyncio
    async def test_404_on_a_submit_without_files_blames_the_session(
        self, tmp_path: Path
    ) -> None:
        runner = _make_runner(
            tmp_path, lambda request: httpx.Response(404, json={"error": "not_found"})
        )
        runner._session_id = "session-1"
        with pytest.raises(TargetSessionLostError, match="session-1"):
            await runner._submit({"message": "hi", "sessionId": "session-1"})

    @pytest.mark.asyncio
    async def test_422_names_the_schema_divergence(self, tmp_path: Path) -> None:
        """Not a bare HTTPStatusError: the body and the deployment disagree."""
        runner = _make_runner(
            tmp_path,
            lambda request: httpx.Response(422, json={"detail": "message too short"}),
        )
        with pytest.raises(SimulationError, match="message too short"):
            await runner._submit({"message": "hi"})


# -- 3. X-PlatformAI-Key ------------------------------------------------------


class TestPlatformAiKey:
    def test_malformed_keys_are_rejected_at_construction(self) -> None:
        """Checkable locally, so an experiment never dies on its first submit."""
        for bad, problem in (
            ("", "is empty"),
            ("has space", "whitespace"),
            ("short", "shorter than"),
            ("x" * 513, "longer than"),
        ):
            with pytest.raises(ValueError, match=problem):
                OrcaApiRunnerConfig(
                    base_url="https://orca.example.com",
                    api_key="test-key",
                    platform_ai_key=bad,
                )

    def test_absent_env_var_leaves_the_shared_allowance_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.setenv("ORCA_API_URL", "https://orca.example.com")
        monkeypatch.setenv("ORCA_API_KEY", "test-key")
        monkeypatch.delenv(ENV_PLATFORM_AI_KEY, raising=False)
        assert OrcaApiRunnerConfig.load(config_yaml).platform_ai_key is None

    def test_env_var_is_read(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.setenv("ORCA_API_URL", "https://orca.example.com")
        monkeypatch.setenv("ORCA_API_KEY", "test-key")
        monkeypatch.setenv(ENV_PLATFORM_AI_KEY, _PLATFORM_KEY)
        config = OrcaApiRunnerConfig.load(config_yaml)
        assert config.platform_ai_key is not None
        assert config.platform_ai_key.get_secret_value() == _PLATFORM_KEY

    @pytest.mark.asyncio
    async def test_header_is_sent_on_the_submit_only(self, tmp_path: Path) -> None:
        """Polling and cancelling do not read it; sending it there is exposure."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/chat") and request.method == "POST":
                return httpx.Response(
                    200, json={"turnId": "turn-1", "sessionId": "session-1"}
                )
            return httpx.Response(200, json={"status": "completed", "output": "hi"})

        runner = _make_runner(
            tmp_path,
            handler,
            requests=requests,
            platform_ai_key=_PLATFORM_KEY,
        )
        observation = await runner.send_turn("hi", [])

        assert observation.text == "hi"
        submits = [r for r in requests if r.method == "POST"]
        polls = [r for r in requests if r.method == "GET"]
        assert submits and all(
            r.headers.get(PLATFORM_AI_KEY_HEADER) == _PLATFORM_KEY for r in submits
        )
        assert polls and not any(PLATFORM_AI_KEY_HEADER in r.headers for r in polls)

    @pytest.mark.asyncio
    async def test_no_header_when_unconfigured(self, tmp_path: Path) -> None:
        requests: list[httpx.Request] = []
        runner = _make_runner(
            tmp_path,
            lambda request: httpx.Response(
                200, json={"turnId": "turn-1", "sessionId": "session-1"}
            ),
            requests=requests,
        )
        await runner._submit({"message": "hi"})
        assert requests and PLATFORM_AI_KEY_HEADER not in requests[0].headers

    @pytest.mark.asyncio
    async def test_rejected_key_is_run_level_not_a_turn_error(
        self, tmp_path: Path
    ) -> None:
        """Orca does not fall back to its own gateway, and this never recovers."""
        runner = _make_runner(tmp_path, platform_ai_key=_PLATFORM_KEY)
        with pytest.raises(AuthLossError, match="PlatformAI"):
            await runner._build_observation(
                {"status": "failed", "error": "Your PlatformAI key was rejected"}
            )

    @pytest.mark.asyncio
    async def test_spent_platform_budget_is_run_level_too(self, tmp_path: Path) -> None:
        """A fresh session cannot refill a platform project's allowance."""
        runner = _make_runner(tmp_path, platform_ai_key=_PLATFORM_KEY)
        with pytest.raises(AuthLossError):
            await runner._build_observation(
                {
                    "status": "failed",
                    "error": "Your PlatformAI key hit its rate limit or budget",
                }
            )

    @pytest.mark.asyncio
    async def test_malformed_key_at_submit_time_is_run_level(
        self, tmp_path: Path
    ) -> None:
        """Reaching a 400 means Orca's rules and ours diverged; nothing started."""
        runner = _make_runner(
            tmp_path,
            lambda request: httpx.Response(400, json={"detail": "Malformed key"}),
            platform_ai_key=_PLATFORM_KEY,
        )
        with pytest.raises(AuthLossError, match="Malformed key"):
            await runner._submit({"message": "hi"})

    @pytest.mark.asyncio
    async def test_setup_logs_the_mode_and_never_the_key(self, tmp_path: Path) -> None:
        from metis.core.trials import TrialConfig

        runner = _make_runner(tmp_path, platform_ai_key=_PLATFORM_KEY)
        with structlog.testing.capture_logs() as logs:
            await runner.setup(TrialConfig(persona="p", scenario="s"))
        rendered = repr(logs)
        assert "PlatformAI" in rendered
        assert _PLATFORM_KEY not in rendered

    def test_secret_is_not_in_the_config_repr(self) -> None:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
            platform_ai_key=_PLATFORM_KEY,
        )
        assert _PLATFORM_KEY not in repr(config)


# -- 4. a cancel is confirmed, not assumed ------------------------------------


class TestCancelConfirmation:
    @pytest.mark.asyncio
    async def test_accepted_cancel_is_polled_until_settled(
        self, tmp_path: Path
    ) -> None:
        polls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"status": "cancelled"})
            polls.append(request)
            if len(polls) < 2:
                return httpx.Response(200, json={"status": "running"})
            return httpx.Response(200, json={"status": "cancelled"})

        runner = _make_runner(tmp_path, handler)
        runner._session_id = "session-1"
        runner._inflight_turn_id = "turn-1"

        await runner._cancel_inflight_turn()

        assert len(polls) == 2  # confirmed rather than assumed
        assert runner._inflight_turn_id is None

    @pytest.mark.asyncio
    async def test_unconfirmed_cancel_does_not_raise(self, tmp_path: Path) -> None:
        """Both callers are already on an error path; a finished run must end."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"status": "cancelled"})
            return httpx.Response(200, json={"status": "running"})

        runner = _make_runner(tmp_path, handler)
        runner._session_id = "session-1"
        runner._inflight_turn_id = "turn-1"

        await runner._cancel_inflight_turn()  # bounded, then gives up quietly

    @pytest.mark.asyncio
    async def test_not_running_skips_confirmation(self, tmp_path: Path) -> None:
        """The turn had already settled; there is nothing to poll for."""
        polls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"status": "not_running"})
            polls.append(request)
            return httpx.Response(200, json={"status": "completed"})

        runner = _make_runner(tmp_path, handler)
        runner._session_id = "session-1"
        runner._inflight_turn_id = "turn-1"

        await runner._cancel_inflight_turn()

        assert polls == []

    @pytest.mark.asyncio
    async def test_failed_cancel_does_not_raise(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, lambda request: httpx.Response(500))
        runner._session_id = "session-1"
        runner._inflight_turn_id = "turn-1"
        await runner._cancel_inflight_turn()

    @pytest.mark.asyncio
    async def test_aged_out_digest_names_the_retention_window(
        self, tmp_path: Path
    ) -> None:
        runner = _make_runner(tmp_path, lambda request: httpx.Response(404))
        with pytest.raises(SimulationError, match="retention window"):
            await runner._fetch_digest("turn-1")


# -- 5. the weekly allowance is readable before the spend --------------------


class TestUsagePreflight:
    @staticmethod
    def _factory(
        usage: httpx.Response, monkeypatch: pytest.MonkeyPatch, **config_kwargs: Any
    ) -> tuple[OrcaApiRunnerFactory, io.StringIO]:
        stream = io.StringIO()
        monkeypatch.setattr(
            orca_api, "console", Console(file=stream, width=200, no_color=True)
        )
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
            **config_kwargs,
        )
        factory = OrcaApiRunnerFactory(
            config,
            transport=httpx.MockTransport(lambda request: usage),
            sleep=_no_sleep,
        )
        return factory, stream

    @pytest.mark.asyncio
    async def test_high_usage_without_a_key_warns_about_the_downgrade(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory, stream = self._factory(
            httpx.Response(
                200,
                json={
                    "planTier": "shared",
                    "pct": 0.62,
                    "daPct": 0.97,
                    "docPct": 0.1,
                    "resetAt": "2026-09-22T00:00:00Z",
                },
            ),
            monkeypatch,
        )
        await factory.start()
        await factory.close()

        printed = " ".join(stream.getvalue().split())
        # daPct is the binding constraint even though the overall figure is fine.
        assert "97%" in printed
        assert "2026-09-22T00:00:00Z" in printed
        assert "downgraded" in printed

    @pytest.mark.asyncio
    async def test_high_usage_with_a_key_is_informational(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The evaluator's own project is outside the allowance and its downgrades."""
        factory, stream = self._factory(
            httpx.Response(200, json={"planTier": "shared", "pct": 0.99}),
            monkeypatch,
            platform_ai_key=_PLATFORM_KEY,
        )
        await factory.start()
        await factory.close()
        assert stream.getvalue() == ""

    @pytest.mark.asyncio
    async def test_low_usage_prints_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        factory, stream = self._factory(
            httpx.Response(200, json={"planTier": "shared", "pct": 0.05}),
            monkeypatch,
        )
        await factory.start()
        await factory.close()
        assert stream.getvalue() == ""

    @pytest.mark.asyncio
    async def test_unreadable_usage_never_blocks_the_experiment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A pre-flight that fails must not stop the run it was reporting on."""
        factory, _ = self._factory(httpx.Response(500), monkeypatch)
        await factory.start()
        assert factory._client is not None
        await factory.close()


# -- 6. an empty message has no valid body ------------------------------------


class TestEmptyMessage:
    @pytest.mark.asyncio
    async def test_blank_message_is_never_submitted(self, tmp_path: Path) -> None:
        """``message`` is minLength 1, so this body would be an unmapped 422."""
        requests: list[httpx.Request] = []
        runner = _make_runner(
            tmp_path,
            lambda request: httpx.Response(500),
            requests=requests,
        )
        observation = await runner.send_turn("   ", [])

        assert requests == []  # nothing reached the transport
        assert (
            observation.response_notices and "empty" in observation.response_notices[0]
        )
        assert observation.available_actions is not None
        assert observation.delivered is False  # I5: nothing was ever sent

    @pytest.mark.asyncio
    async def test_blank_message_with_a_form_answer_is_submitted(
        self, tmp_path: Path
    ) -> None:
        """``formAnswers`` is the other half of Orca's exactly-one requirement."""
        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [{"id": "q1", "type": "text", "label": "Q1"}],
        }
        from metis.engine.simulation.types import FormFillAction

        body = await runner._build_submit_body(
            "", [FormFillAction(slot_id="q1", value="answer")]
        )
        assert isinstance(body, dict)
        assert body["formAnswers"] == {"q1": "answer"}

    @pytest.mark.asyncio
    async def test_delivered_is_false_even_when_an_unrelated_action_already_failed(
        self, tmp_path: Path
    ) -> None:
        """The turn-level delivered=False must not disturb a sibling action's
        own failure detail — the two channels have different owners (I1 vs I5)."""
        from metis.engine.simulation.types import ButtonClickAction

        runner = _make_runner(tmp_path)
        actions = [ButtonClickAction(slot_id="invented")]
        runner._plan_actions(actions)
        observation = await runner._build_submit_body("   ", actions)

        assert isinstance(observation, Observation)
        assert observation.delivered is False
        assert not observation.action_results[0].succeeded
        assert "invented" in observation.action_results[0].detail

    @pytest.mark.asyncio
    async def test_blank_message_costs_no_upload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The guard sits before attachment resolution, so a broken turn is free."""
        runner = _make_runner(tmp_path)
        runner._fixtures = ["sales.csv"]
        (tmp_path / "fixtures" / "sales.csv").write_text("a,b\n1,2\n")
        uploads: list[str] = []

        async def spy(name: str, path: Path) -> str:
            uploads.append(name)
            return "file-1"

        monkeypatch.setattr(runner._fixture_library, "file_id", spy)

        from metis.engine.simulation.types import UploadFileAction

        result = await runner._build_submit_body(
            "", [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
        )
        assert isinstance(result, Observation)
        assert uploads == []


# -- 8. a malformed form answer falls back to the message, never abandons ----


class TestFormAnswerFailureFallsBackToMessage:
    """Orca's schema accepts ``message`` alone while a form is pending — a
    plain message just leaves the question open, and Orca may ask it again
    (Orca API v1 spec, ``POST /api/v1/chat``: ``message`` and ``formAnswers``
    are mutually exclusive, and a form stays pending until answered). A
    locally-invalid form answer therefore has no basis to abandon the turn:
    the message is a request Orca would accept on its own, so it is
    submitted instead of nothing at all."""

    @pytest.mark.asyncio
    async def test_a_mistyped_answer_does_not_abandon_the_turn(
        self, tmp_path: Path
    ) -> None:
        from metis.engine.simulation.types import FormFillAction

        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [{"id": "qty", "type": "number", "label": "How many?"}],
        }
        actions = [FormFillAction(slot_id="qty", value="lots")]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("please just use the default", actions)
        assert isinstance(body, dict)
        assert body["message"] == "please just use the default"

    @pytest.mark.asyncio
    async def test_a_correctly_typed_answer_alongside_a_bad_one_is_still_discarded(
        self, tmp_path: Path
    ) -> None:
        """Whether Orca accepts a partial formAnswers is not documented, so
        the runner never risks it: any problem discards the whole dict."""
        from metis.engine.simulation.types import FormFillAction

        runner = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [
                {"id": "qty", "type": "number", "label": "How many?"},
                {"id": "note", "type": "text", "label": "Note"},
            ],
        }
        actions = [
            FormFillAction(slot_id="qty", value="lots"),
            FormFillAction(slot_id="note", value="fine"),
        ]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("fallback text", actions)
        assert isinstance(body, dict)
        assert "formAnswers" not in body
        assert body["message"] == "fallback text"
