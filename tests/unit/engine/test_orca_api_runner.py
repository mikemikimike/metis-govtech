"""Tests for the Orca API runner package."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

import metis.engine.simulation.runners.orca_api._artifacts as _artifacts_mod
from metis.engine.simulation.runners.orca_api import (
    OrcaApiRunner,
    OrcaApiRunnerConfig,
    OrcaApiRunnerFactory,
)
from metis.engine.simulation.runners.orca_api._fixtures import content_type_for
from metis.engine.simulation.types import (
    ButtonClickAction,
    FormFillAction,
    UploadFileAction,
)


class TestOrcaApiRunnerConfig:
    def test_load_from_env(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("poll_interval_ms: 5000\nsubmit_rpm: 10\n")
        monkeypatch.setenv("ORCA_API_URL", "https://orca.example.com")
        monkeypatch.setenv("ORCA_API_KEY", "test-key")
        config = OrcaApiRunnerConfig.load(config_yaml)
        assert config.base_url == "https://orca.example.com"
        assert config.api_key.get_secret_value() == "test-key"
        assert config.poll_interval_ms == 5000
        assert config.submit_rpm == 10

    def test_missing_env_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.delenv("ORCA_API_URL", raising=False)
        monkeypatch.delenv("ORCA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="missing required environment"):
            OrcaApiRunnerConfig.load(config_yaml)

    def test_invalid_url_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("{}")
        monkeypatch.setenv("ORCA_API_URL", "not-a-url")
        monkeypatch.setenv("ORCA_API_KEY", "key")
        with pytest.raises(ValueError, match="must be an http"):
            OrcaApiRunnerConfig.load(config_yaml)


class TestOrcaApiRunnerFactory:
    def test_factory_init_with_config(self) -> None:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
        )
        factory = OrcaApiRunnerFactory(config)
        assert factory.retry_defaults == (2, 5.0)

    def test_factory_satisfies_protocol(self) -> None:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
        )
        factory = OrcaApiRunnerFactory(config)
        assert callable(getattr(factory, "start", None))
        assert callable(getattr(factory, "create", None))
        assert callable(getattr(factory, "close", None))

    def test_resolver_finds_factory(self) -> None:
        from metis.engine.simulation.runner_resolver import resolve_runner_factory

        cls = resolve_runner_factory(
            "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory"
        )
        assert cls is OrcaApiRunnerFactory


class TestContentTypeFor:
    @pytest.mark.parametrize(
        "suffix, expected",
        [
            (".pdf", "application/pdf"),
            (".csv", "text/csv"),
            (".png", "image/png"),
            (".json", "application/json"),
        ],
    )
    def test_known_types(self, suffix: str, expected: str, tmp_path: Path) -> None:
        path = tmp_path / f"file{suffix}"
        path.touch()
        assert content_type_for(path) == expected


def _make_runner(tmp_path, fixtures=()):
    config = OrcaApiRunnerConfig(
        base_url="https://orca.example.com", api_key="test-key"
    )
    client = httpx.AsyncClient(base_url="https://orca.example.com")
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    runner = OrcaApiRunner(
        client,
        config,
        fixtures_dir=fixtures_dir,
        run_dir=run_dir,
        experiment_root=tmp_path,
    )
    runner._fixtures = list(fixtures)
    return runner, fixtures_dir


class TestBuildSubmitBody:
    @pytest.mark.asyncio
    async def test_form_fill_keys_on_slot_id(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path)
        runner._pending_form = {
            "stepId": "step-1",
            "fields": [{"id": "q1", "type": "text", "label": "Q1"}],
        }
        body = await runner._build_submit_body(
            "prose", [FormFillAction(slot_id="q1", value="answer")]
        )
        assert isinstance(body, dict)
        assert body["formAnswers"] == {"q1": "answer"}
        assert "message" not in body

    @pytest.mark.asyncio
    async def test_valid_upload_attaches_file(self, tmp_path, monkeypatch) -> None:
        runner, fixtures_dir = _make_runner(tmp_path, fixtures=["sales.csv"])
        (fixtures_dir / "sales.csv").write_text("a,b\n1,2\n")

        async def fake_file_id(name, path):
            return "file-123"

        monkeypatch.setattr(runner._fixture_library, "file_id", fake_file_id)
        actions = [UploadFileAction(slot_id="sales.csv", filename="sales.csv")]
        # send_turn plans the rows before building the body, and the attachment
        # guard reads the row belonging to each upload, so a body built without
        # planned rows is a state the runner cannot reach.
        runner._plan_actions(actions)
        body = await runner._build_submit_body("hi", actions)
        assert isinstance(body, dict)
        assert body["files"] == ["file-123"]
        assert body["message"] == "hi"

    @pytest.mark.asyncio
    async def test_button_click_is_skipped_message_sent(self, tmp_path) -> None:
        runner, _ = _make_runner(tmp_path)
        actions = [ButtonClickAction(slot_id="run")]
        runner._plan_actions(actions)
        body = await runner._build_submit_body("hello", actions)
        assert isinstance(body, dict)
        assert body["message"] == "hello"
        assert "files" not in body and "formAnswers" not in body


@pytest.mark.asyncio
async def test_collect_artifacts_emits_relative_path_and_skips_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import metis.engine.simulation.runners.orca_api._artifacts as _artifacts_mod
    from metis.engine.simulation.runners.orca_api._artifacts import collect_artifacts

    async def _fake_download(
        client: object, url: str, dest: object, **kwargs: object
    ) -> None:
        # kwargs: the retry window, clock and sleep the collector now passes.
        Path(str(dest)).write_bytes(b"a,b\n1,2\n")

    monkeypatch.setattr(_artifacts_mod, "download_to", _fake_download)

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    artifacts, notes = await collect_artifacts(
        client=object(),  # type: ignore[arg-type]
        files=[
            {"fileId": "f1", "name": "report.csv"},
            {"fileId": None, "name": "skipped.csv"},
        ],
        artifacts_dir=artifacts_dir,
        experiment_root=artifacts_dir.parent,
    )

    # First entry: downloaded, path is set, file exists on disk
    assert artifacts[0].path is not None
    assert Path(artifacts_dir / "report.csv").exists()

    # Second entry: no fileId, unavailable (not retryable), a note was recorded
    assert artifacts[1].state == "unavailable"
    assert len(notes) == 1
    assert "skipped.csv" in notes[0].text


@pytest.mark.asyncio
async def test_send_turn_appends_submitted_fixtures_as_artifacts(
    tmp_path, monkeypatch
) -> None:
    from metis.engine.simulation.types import Observation

    runner, fixtures_dir = _make_runner(tmp_path, fixtures=["q3.csv"])
    (fixtures_dir / "q3.csv").write_text("a,b\n1,2\n")

    async def fake_build_submit_body(message, actions):
        # Simulate the body-builder having staged one fixture this turn.
        runner._attaching = ["q3.csv"]
        return {"message": message}

    monkeypatch.setattr(runner, "_build_submit_body", fake_build_submit_body)
    monkeypatch.setattr(runner, "_submit", AsyncMock(return_value=("turn-1", True)))
    monkeypatch.setattr(runner, "_poll_until_settled", AsyncMock(return_value={}))
    monkeypatch.setattr(
        runner, "_build_observation", AsyncMock(return_value=Observation(text="ok"))
    )

    obs = await runner.send_turn("hi", [])

    fixtures = [a for a in obs.artifacts if a.source == "fixture"]
    assert [a.name for a in fixtures] == ["q3.csv"]
    assert fixtures[0].state == "received"
    assert runner._attached == {"q3.csv"}  # committed
    assert runner._attaching == []  # drained


@pytest.mark.asyncio
async def test_submitted_fixture_artifact_carries_the_file_id(
    tmp_path, monkeypatch
) -> None:
    """An uploaded fixture has an Orca fileId too; the cache already holds it."""
    from metis.engine.simulation.types import Observation

    runner, fixtures_dir = _make_runner(tmp_path, fixtures=["q3.csv"])
    (fixtures_dir / "q3.csv").write_text("a,b\n1,2\n")
    runner._fixture_library._entries["q3.csv"] = "a2ba407140fb5cda"

    async def fake_build_submit_body(message, actions):
        runner._attaching = ["q3.csv"]
        return {"message": message}

    monkeypatch.setattr(runner, "_build_submit_body", fake_build_submit_body)
    monkeypatch.setattr(runner, "_submit", AsyncMock(return_value=("turn-1", True)))
    monkeypatch.setattr(runner, "_poll_until_settled", AsyncMock(return_value={}))
    monkeypatch.setattr(
        runner, "_build_observation", AsyncMock(return_value=Observation(text="ok"))
    )

    obs = await runner.send_turn("hi", [])

    fixtures = [a for a in obs.artifacts if a.source == "fixture"]
    assert [a.external_id for a in fixtures] == ["a2ba407140fb5cda"]


def test_cached_file_id_is_a_lookup_not_an_upload(tmp_path) -> None:
    """Runs after a successful submit, so it must neither upload nor raise."""
    from metis.engine.simulation.runners.orca_api._fixtures import FixtureRejected

    runner, _ = _make_runner(tmp_path)
    library = runner._fixture_library

    assert library.cached_file_id("absent.csv") is None

    library._entries["sales.csv"] = "a2ba407140fb5cda"
    assert library.cached_file_id("sales.csv") == "a2ba407140fb5cda"

    # A cached rejection is an absent id, not an error to re-raise.
    library._entries["big.csv"] = FixtureRejected("big.csv", 413, "too large")
    assert library.cached_file_id("big.csv") is None


@pytest.mark.asyncio
async def test_send_turn_appends_no_fixtures_when_none_submitted(
    tmp_path, monkeypatch
) -> None:
    # A turn that attached nothing (resolution failed → not in _attaching) must
    # surface no fixture artifact: no assumed uploads.
    from metis.engine.simulation.types import Observation

    runner, _ = _make_runner(tmp_path, fixtures=["q3.csv"])

    async def fake_build_submit_body(message, actions):
        runner._attaching = []
        return {"message": message}

    monkeypatch.setattr(runner, "_build_submit_body", fake_build_submit_body)
    monkeypatch.setattr(runner, "_submit", AsyncMock(return_value=("turn-1", True)))
    monkeypatch.setattr(runner, "_poll_until_settled", AsyncMock(return_value={}))
    monkeypatch.setattr(
        runner, "_build_observation", AsyncMock(return_value=Observation(text="ok"))
    )

    obs = await runner.send_turn("hi", [])

    assert [a for a in obs.artifacts if a.source == "fixture"] == []


class TestExternalIdIsRecorded:
    @pytest.mark.asyncio
    async def test_downloaded_artifact_carries_the_file_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_download(client, url, dest, **kwargs) -> None:
            dest.write_text("{}")

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        artifacts, notes = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(),
            [{"fileId": "73da06dac970f8a9", "name": "chart.vl.json"}],
            artifacts_dir,
            tmp_path,
        )

        assert notes == []
        assert [a.external_id for a in artifacts] == ["73da06dac970f8a9"]

    @pytest.mark.asyncio
    async def test_undownloadable_entry_is_still_identifiable(
        self, tmp_path: Path
    ) -> None:
        """A null fileId has nothing to record; a *failed* download does."""
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        artifacts, notes = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(),
            [{"fileId": None, "name": "ghost.vl.json"}],
            artifacts_dir,
            tmp_path,
        )

        assert artifacts[0].path is None
        assert artifacts[0].state == "unavailable"  # no fileId, nothing to retry
        assert artifacts[0].external_id is None
        assert notes and "not downloadable" in notes[0].text
        assert notes[0].file_id is None  # no identity to reconcile on

    @pytest.mark.asyncio
    async def test_failed_download_keeps_the_file_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This is the entry a later re-check most wants to retry."""

        async def failing_download(client, url, dest, **kwargs) -> None:
            raise httpx.ConnectError("boom")

        monkeypatch.setattr(_artifacts_mod, "download_to", failing_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()

        artifacts, notes = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(),
            [{"fileId": "73da06dac970f8a9", "name": "chart.vl.json"}],
            artifacts_dir,
            tmp_path,
        )

        assert artifacts[0].state == "unfetched"  # download failed, but retryable
        assert artifacts[0].external_id == "73da06dac970f8a9"
        assert notes and "could not be downloaded" in notes[0].text
        # The id travels with the note, not only in the log: notes are
        # reconciled across the digest and sweep lanes by identity, never by
        # name. It rides in its own field, so it can do that job without
        # reaching the persona (see the persona-visibility test below).
        assert notes[0].file_id == "73da06dac970f8a9"
        assert "73da06dac970f8a9" not in notes[0].text


class TestIdentityDedupe:
    @pytest.mark.asyncio
    async def test_relisted_file_is_not_downloaded_twice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The digest re-lists the same fileId each turn; one copy is correct."""
        downloads: list[str] = []

        async def fake_download(client, url, dest, **kwargs) -> None:
            downloads.append(url)
            dest.write_text("x")

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        seen: set[str] = set()
        entry = [{"fileId": "file-1", "name": "analysis_script.py"}]

        first, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path, seen_file_ids=seen
        )
        second, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path, seen_file_ids=seen
        )

        assert len(downloads) == 1
        assert first[0].state == "received"
        assert second == []  # already held; nothing new to report this turn
        assert not (artifacts_dir / "analysis_script-2.py").exists()

    @pytest.mark.asyncio
    async def test_a_revision_under_the_same_name_is_still_kept(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Orca files are immutable: a new fileId reusing a name is a new file.

        Also covers: a null-fileId entry in the same list is still collected
        (the seen guard sits downstream of the ``if not file_id: continue``
        branch, so it cannot block a null entry).
        """

        async def fake_download(client, url, dest, **kwargs) -> None:
            dest.write_text(url)

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        seen: set[str] = set()

        first, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(),
            [
                {"fileId": "file-1", "name": "Q3_Analysis_Methodology.md"},
                {"fileId": None, "name": "no_id.txt"},
            ],
            artifacts_dir,
            tmp_path,
            seen_file_ids=seen,
        )
        revised, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(),
            [{"fileId": "file-2", "name": "Q3_Analysis_Methodology.md"}],
            artifacts_dir,
            tmp_path,
            seen_file_ids=seen,
        )

        # Revision is kept with its new identity.
        assert revised[0].external_id == "file-2"
        assert revised[0].state == "received"
        original = artifacts_dir / "Q3_Analysis_Methodology.md"
        revision = artifacts_dir / "Q3_Analysis_Methodology-2.md"
        assert original.exists()
        assert revision.exists()
        # The two files carry different content: fake_download writes the URL,
        # which differs between file-1 and file-2 — a revision is kept, not aliased.
        assert original.read_text() != revision.read_text()
        # The null-fileId entry in the first call was still collected: the seen
        # guard sits downstream of the ``if not file_id: continue`` branch, so
        # it cannot block a null entry.
        null_artifacts = [a for a in first if a.name == "no_id.txt"]
        assert len(null_artifacts) == 1
        assert null_artifacts[0].path is None
        assert null_artifacts[0].external_id is None

    @pytest.mark.asyncio
    async def test_a_failed_download_is_retried_next_turn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only a file actually on disk counts as seen."""
        attempts: list[str] = []

        async def flaky_download(client, url, dest, **kwargs) -> None:
            attempts.append(url)
            if len(attempts) == 1:
                raise httpx.ConnectError("boom")
            dest.write_text("x")

        monkeypatch.setattr(_artifacts_mod, "download_to", flaky_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        seen: set[str] = set()
        entry = [{"fileId": "file-1", "name": "chart.vl.json"}]

        await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path, seen_file_ids=seen
        )
        recovered, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path, seen_file_ids=seen
        )

        assert len(attempts) == 2
        assert recovered[0].state == "received"
        assert "file-1" in seen

    @pytest.mark.asyncio
    async def test_omitting_the_set_preserves_the_old_behaviour(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No caller is forced to track identity; the parameter is optional."""

        async def fake_download(client, url, dest, **kwargs) -> None:
            dest.write_text("x")

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        entry = [{"fileId": "file-1", "name": "chart.vl.json"}]

        await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path
        )
        again, _ = await _artifacts_mod.collect_artifacts(
            httpx.AsyncClient(), entry, artifacts_dir, tmp_path
        )

        assert again[0].state == "received"
        assert (artifacts_dir / "chart.vl-2.json").exists()

    @pytest.mark.asyncio
    async def test_runner_holds_identity_across_turns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two turns, one re-listed file, one download."""
        downloads: list[str] = []

        async def fake_download(client, url, dest, **kwargs) -> None:
            downloads.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("x")

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
        runner, _ = _make_runner(tmp_path)  # this helper returns a tuple
        digest = {
            "status": "completed",
            "output": "here it is",
            "files": [{"fileId": "file-1", "name": "analysis_script.py"}],
        }

        first = await runner._build_observation(digest)
        second = await runner._build_observation(digest)

        assert len(downloads) == 1
        assert len(first.artifacts) == 1
        assert second.artifacts == []


class TestFetchDigestPollLaneDelivery:
    """A TargetUnavailableError from the digest read means the turn already
    reached Orca (I5) only when this run's own submit minted the turn —
    ``submit_confirmed=True``. A turn adopted via 409 turn_in_progress can be
    an unrelated, still-draining prior turn, so the same failure there must
    leave delivery unconfirmed instead."""

    @pytest.mark.asyncio
    async def test_becomes_post_submission_observation_error_when_submit_confirmed(
        self, tmp_path, monkeypatch
    ) -> None:
        from metis.engine.simulation.exceptions import (
            PostSubmissionObservationError,
            TargetUnavailableError,
        )

        runner, _ = _make_runner(tmp_path)
        monkeypatch.setattr(
            runner,
            "_request",
            AsyncMock(
                side_effect=TargetUnavailableError(
                    "Orca key store unavailable (503) for longer than 30 s"
                )
            ),
        )

        with pytest.raises(PostSubmissionObservationError) as excinfo:
            await runner._fetch_digest("turn-1", submit_confirmed=True)

        assert "503" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_stays_target_unavailable_when_turn_was_adopted_via_409(
        self, tmp_path, monkeypatch
    ) -> None:
        """A turn adopted via 409 turn_in_progress may belong to an unrelated
        prior message (e.g. one whose cancel didn't land in time), so a
        digest-read failure on it must not be promoted to delivered=True."""
        from metis.engine.simulation.exceptions import TargetUnavailableError

        runner, _ = _make_runner(tmp_path)
        monkeypatch.setattr(
            runner,
            "_request",
            AsyncMock(
                side_effect=TargetUnavailableError(
                    "Orca key store unavailable (503) for longer than 30 s"
                )
            ),
        )

        with pytest.raises(TargetUnavailableError) as excinfo:
            await runner._fetch_digest("turn-1", submit_confirmed=False)

        assert "503" in str(excinfo.value)


class TestPollLaneUnavailabilityDeliversTrue:
    """End-to-end through the real 503-retry-window logic in _transport.py."""

    @staticmethod
    def _stalled_digest_runner(tmp_path: Path) -> OrcaApiRunner:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
            poll_interval_ms=1,
            store_retry_window_s=0.0,
        )
        client = httpx.AsyncClient(
            base_url="https://orca.example.com/api/v1/",
            transport=httpx.MockTransport(lambda request: httpx.Response(503)),
        )
        for directory in ("fixtures", "run"):
            (tmp_path / directory).mkdir(exist_ok=True)
        return OrcaApiRunner(
            client,
            config,
            fixtures_dir=tmp_path / "fixtures",
            run_dir=tmp_path / "run",
            experiment_root=tmp_path,
        )

    @pytest.mark.asyncio
    async def test_polling_a_submitted_turn_through_a_persistent_503(
        self, tmp_path: Path
    ) -> None:
        from metis.engine.simulation.exceptions import PostSubmissionObservationError

        runner = self._stalled_digest_runner(tmp_path)

        with pytest.raises(PostSubmissionObservationError):
            await runner._poll_until_settled("turn-1", True)

    @pytest.mark.asyncio
    async def test_cancel_confirmation_still_swallows_it(self, tmp_path: Path) -> None:
        """_confirm_cancelled already treats every SimulationError as
        best-effort; the new exception type must not change that (it is a
        SimulationError subclass too)."""
        runner = self._stalled_digest_runner(tmp_path)

        await runner._confirm_cancelled("turn-1")  # must not raise


class TestConflictAdoptedTurnDoesNotDeliverOnDigestFailure:
    """A 409 turn_in_progress on submit can adopt an unrelated, still-draining
    prior turn (e.g. one whose best-effort cancel didn't land in time — see
    _cancel_inflight_turn), not one this submit itself created. When the
    subsequent digest read then fails, the current message's delivery is
    unconfirmed, so the raw TargetUnavailableError must reach the caller
    instead of being promoted to PostSubmissionObservationError."""

    @staticmethod
    def _runner_409_then_persistent_503(tmp_path: Path) -> OrcaApiRunner:
        config = OrcaApiRunnerConfig(
            base_url="https://orca.example.com",
            api_key="test-key",
            poll_interval_ms=1,
            store_retry_window_s=0.0,
        )
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    409,
                    json={"error": "turn_in_progress", "turnId": "earlier-turn"},
                )
            return httpx.Response(503)

        client = httpx.AsyncClient(
            base_url="https://orca.example.com/api/v1/",
            transport=httpx.MockTransport(handler),
        )
        for directory in ("fixtures", "run"):
            (tmp_path / directory).mkdir(exist_ok=True)
        return OrcaApiRunner(
            client,
            config,
            fixtures_dir=tmp_path / "fixtures",
            run_dir=tmp_path / "run",
            experiment_root=tmp_path,
        )

    @pytest.mark.asyncio
    async def test_submit_returns_the_adopted_turn_unconfirmed(
        self, tmp_path: Path
    ) -> None:
        runner = self._runner_409_then_persistent_503(tmp_path)

        turn_id, submit_confirmed = await runner._submit({"message": "hi"})

        assert turn_id == "earlier-turn"
        assert submit_confirmed is False

    @pytest.mark.asyncio
    async def test_send_turn_leaves_delivery_unconfirmed_on_409_then_503(
        self, tmp_path: Path
    ) -> None:
        from metis.engine.simulation.exceptions import TargetUnavailableError

        runner = self._runner_409_then_persistent_503(tmp_path)

        with pytest.raises(TargetUnavailableError):
            await runner.send_turn("hi", [])
