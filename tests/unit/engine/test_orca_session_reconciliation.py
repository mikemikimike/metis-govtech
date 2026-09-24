"""Recovering generated files that Orca's turn digest omits (issue #337 §1).

``TurnDigest.files`` excludes Vega-Lite chart specs that ``GET /sessions/{id}``
reports as ``source: "generated"``. Verified on two live sessions: the digest is
the generated set with every ``.vl.json`` removed. These tests pin the sweep
that closes the gap, and the ways it must fail quietly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

import metis.engine.simulation.runners.orca_api._artifacts as _artifacts_mod
from metis.engine.simulation.runners.orca_api import (
    OrcaApiRunner,
    OrcaApiRunnerConfig,
)

# The real shape from sess-260902063909-77210318868f5ff9: one uploaded fixture,
# two generated non-chart files (which the digest reported), two .vl.json chart
# specs (which the digest omitted).
_SESSION_FILES = [
    {"fileId": "f-up", "name": "q3_sales.csv", "source": "uploaded"},
    {"fileId": "f-txt", "name": "ANALYSIS_SUMMARY.txt", "source": "generated"},
    {"fileId": "f-py", "name": "q3_revenue_analysis.py", "source": "generated"},
    {"fileId": "f-c1", "name": "q3_revenue_by_region.vl.json", "source": "generated"},
    {
        "fileId": "f-c2",
        "name": "q3_avg_revenue_by_region.vl.json",
        "source": "generated",
    },
]
_DIGEST_FILES = [
    {"fileId": "f-txt", "name": "ANALYSIS_SUMMARY.txt"},
    {"fileId": "f-py", "name": "q3_revenue_analysis.py"},
]


async def _no_sleep(_seconds: float) -> None:
    return None


def _make_runner(tmp_path: Path, handler: Any) -> OrcaApiRunner:
    config = OrcaApiRunnerConfig(
        base_url="https://orca.example.com", api_key="test-key", poll_interval_ms=1
    )
    client = httpx.AsyncClient(
        base_url="https://orca.example.com/api/v1/",
        transport=httpx.MockTransport(handler),
    )
    for directory in ("fixtures", "run"):
        (tmp_path / directory).mkdir(exist_ok=True)
    (tmp_path / "run" / "artifacts").mkdir(exist_ok=True)
    runner = OrcaApiRunner(
        client,
        config,
        fixtures_dir=tmp_path / "fixtures",
        run_dir=tmp_path / "run",
        experiment_root=tmp_path,
        sleep=_no_sleep,
    )
    runner._session_id = "session-1"
    return runner


@pytest.fixture
def stub_download(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    urls: list[str] = []

    async def fake_download(client, url, dest, **kwargs) -> None:
        urls.append(url)
        dest.write_text("{}")

    monkeypatch.setattr(_artifacts_mod, "download_to", fake_download)
    return urls


class TestSweepRecoversOmittedFiles:
    @pytest.mark.asyncio
    async def test_charts_missing_from_the_digest_are_downloaded(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"files": _SESSION_FILES})

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "4 charts", "files": _DIGEST_FILES}
        )

        names = sorted(a.name for a in observation.artifacts)
        assert names == [
            "ANALYSIS_SUMMARY.txt",
            "q3_avg_revenue_by_region.vl.json",
            "q3_revenue_analysis.py",
            "q3_revenue_by_region.vl.json",
        ]
        assert all(a.path is not None for a in observation.artifacts)

    @pytest.mark.asyncio
    async def test_uploaded_files_are_not_swept(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """A fixture is already recorded by send_turn; re-downloading it is wrong."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"files": _SESSION_FILES})

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": _DIGEST_FILES}
        )

        assert "q3_sales.csv" not in {a.name for a in observation.artifacts}
        assert not any("f-up" in url for url in stub_download)

    @pytest.mark.asyncio
    async def test_a_second_turn_downloads_nothing_new(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """Session.files is cumulative; without identity dedupe this accumulates."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"files": _SESSION_FILES})

        runner = _make_runner(tmp_path, handler)
        digest = {"status": "completed", "output": "ok", "files": _DIGEST_FILES}

        await runner._build_observation(digest)
        before = len(stub_download)
        second = await runner._build_observation(digest)

        assert len(stub_download) == before
        assert second.artifacts == []
        assert not list((tmp_path / "run" / "artifacts").glob("*-2.*"))

    @pytest.mark.asyncio
    async def test_recovered_files_have_identity_and_target_source(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """Charts recovered by the sweep carry their Orca fileId and source='target'."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"files": _SESSION_FILES})

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": _DIGEST_FILES}
        )

        chart_ids = {"f-c1", "f-c2"}
        recovered = [a for a in observation.artifacts if a.external_id in chart_ids]
        assert len(recovered) == 2
        assert all(a.source == "target" for a in recovered)
        assert all(a.path is not None for a in recovered)


class TestSweepFailsQuietly:
    @pytest.mark.asyncio
    async def test_no_session_yet_is_a_no_op(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """Before the first submit there is no session to sweep."""
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"files": _SESSION_FILES})

        runner = _make_runner(tmp_path, handler)
        runner._session_id = None
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": []}
        )

        assert calls == []
        assert observation.artifacts == []

    @pytest.mark.asyncio
    async def test_a_failed_session_read_never_loses_the_turn(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """The digest's own files must still arrive when the sweep cannot run."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": _DIGEST_FILES}
        )

        assert observation.text == "ok"
        assert {a.name for a in observation.artifacts} == {
            "ANALYSIS_SUMMARY.txt",
            "q3_revenue_analysis.py",
        }
        # Log-only: response_notices is the persona's prompt, not a
        # diagnostics channel, and a sweep failure is METIS-internal.
        assert observation.response_notices == []

    @pytest.mark.asyncio
    async def test_a_malformed_session_body_never_raises(
        self, tmp_path: Path, stub_download: list[str]
    ) -> None:
        """A dict ``files`` value (one entry, not a list) is rejected by the guard."""

        def handler(request: httpx.Request) -> httpx.Response:
            # A dict that looks like a single file entry — not a list.  Without
            # the isinstance(session_files, list) guard this would be passed to
            # collect_session_artifacts, which iterates over its keys as strings.
            return httpx.Response(
                200, json={"files": {"fileId": "x", "source": "generated"}}
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": []}
        )

        assert observation.text == "ok"
        assert stub_download == []
        # Log-only, as for any other sweep-level failure.
        assert observation.artifacts == []
        assert observation.response_notices == []

    @pytest.mark.asyncio
    async def test_an_entry_without_a_file_id_is_skipped(
        self,
        tmp_path: Path,
        stub_download: list[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Null fileId means not downloadable; there is nothing to fetch.

        Skipped, but never silently. With no id to match on, the sweep cannot
        tell whether the digest lane reported the same file; the digest is empty
        here, so this warning is the run's only trace of it. No artifact is
        minted either, for the same missing identity: it would reconcile against
        nothing and stand as a second phantom beside the digest lane's whenever
        that lane did report the file.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {"fileId": None, "name": "ghost.vl.json", "source": "generated"}
                    ]
                },
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {"status": "completed", "output": "ok", "files": []}
        )

        assert stub_download == []
        assert observation.artifacts == []
        # capsys, not caplog: core's logger is structlog, which writes to its own
        # stream rather than through stdlib logging handlers.
        logged = capsys.readouterr()
        assert "ghost.vl.json" in logged.out + logged.err

    @pytest.mark.asyncio
    async def test_auth_loss_on_session_read_is_not_swallowed(
        self, tmp_path: Path
    ) -> None:
        """A 401 on the session read is run-level auth loss, not a quiet note."""
        from metis.engine.simulation.exceptions import AuthLossError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        runner = _make_runner(tmp_path, handler)
        with pytest.raises(AuthLossError):
            await runner._build_observation(
                {"status": "completed", "output": "ok", "files": []}
            )


class TestSweepDeduplicateMerge:
    @pytest.mark.asyncio
    async def test_digest_failure_superseded_by_sweep_yields_one_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A digest download failure followed by a successful sweep yields exactly
        one artifact with a real path and no note — not a contradictory pair.

        The stale "could not be downloaded" note goes with the placeholder it
        described, and nothing replaces it: the file arrived, so there is
        nothing for the persona to be told.
        """
        # download_to fails on the first call for f-fail (from the digest path),
        # succeeds on subsequent calls (from the session sweep).
        attempts: dict[str, int] = {}

        async def fake_download_first_fails(client, url, dest, **kwargs) -> None:
            count = attempts.get(url, 0)
            attempts[url] = count + 1
            if "f-fail" in url and count == 0:
                raise httpx.ConnectError("simulated network error")
            dest.write_text("{}")

        monkeypatch.setattr(_artifacts_mod, "download_to", fake_download_first_fails)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "fileId": "f-fail",
                            "name": "chart.vl.json",
                            "source": "generated",
                        }
                    ]
                },
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {
                "status": "completed",
                "output": "ok",
                "files": [{"fileId": "f-fail", "name": "chart.vl.json"}],
            }
        )

        # Exactly one artifact for f-fail, with a real path
        fail_artifacts = [a for a in observation.artifacts if a.external_id == "f-fail"]
        assert len(fail_artifacts) == 1
        assert fail_artifacts[0].path is not None

        # The stale failure note is gone, and no sweep-internal note replaces it.
        assert observation.response_notices == []

    @pytest.mark.asyncio
    async def test_a_file_failing_on_both_lanes_is_recorded_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both lanes fail: one placeholder and one note, not two of each.

        A failed download deliberately does not mark its id as held, so the
        sweep retries it in the same turn. Without identity reconciliation the
        turn records two ``path=None`` artifacts and two identical notes — and
        every non-fixture artifact is shown to the persona as a file it has
        received, so an N-turn run would accumulate 2N phantom deliverables
        under a header promising the list is exhaustive.
        """

        async def always_fails(client, url, dest, **kwargs) -> None:
            raise httpx.ConnectError("simulated network error")

        monkeypatch.setattr(_artifacts_mod, "download_to", always_fails)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "fileId": "f-fail",
                            "name": "chart.vl.json",
                            "source": "generated",
                        }
                    ]
                },
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {
                "status": "completed",
                "output": "ok",
                "files": [{"fileId": "f-fail", "name": "chart.vl.json"}],
            }
        )

        assert len(observation.artifacts) == 1
        assert observation.artifacts[0].external_id == "f-fail"
        assert observation.artifacts[0].path is None
        assert len(observation.response_notices) == 1
        assert "could not be downloaded" in observation.response_notices[0]

    @pytest.mark.asyncio
    async def test_the_persona_is_never_shown_a_raw_orca_file_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``response_notices`` is prompt text, not a diagnostics channel.

        It is rendered under "Problems reported on your previous turn — take
        them into account", and no real user of a chat product is ever shown a
        backend file id. The id still has to travel with the note so both
        collection lanes' diagnostics can be reconciled by identity rather than
        by name; it rides in ``ArtifactNote.file_id``, which stops at the
        runner boundary.
        """
        file_id = "73da06dac970f8a9-8f3c2a1e"

        async def always_fails(client, url, dest, **kwargs) -> None:
            raise httpx.ConnectError("simulated network error")

        monkeypatch.setattr(_artifacts_mod, "download_to", always_fails)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "fileId": file_id,
                            "name": "chart.vl.json",
                            "source": "generated",
                        }
                    ]
                },
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {
                "status": "completed",
                "output": "ok",
                "files": [{"fileId": file_id, "name": "chart.vl.json"}],
            }
        )

        assert observation.response_notices  # the failure is still reported
        assert all(file_id not in err for err in observation.response_notices)
        assert all("(file " not in err for err in observation.response_notices)
        # And the id is not lost — it is on the artifact, where a re-check reads it.
        assert observation.artifacts[0].external_id == file_id

    def test_two_names_under_one_id_merge_and_warn(self) -> None:
        """A reused id breaks ``external_id``'s uniqueness contract.

        Nothing can validate that contract — uniqueness is a property of the
        set — so the collapse still happens and a file is still lost. All this
        pins is that the detection branch runs and names the cause rather than
        raising: the log line is the only trace such a target would leave.
        """
        from metis.core import Artifact
        from metis.engine.simulation.runners.orca_api._artifacts import (
            reconcile_by_identity,
        )

        merged, notes = reconcile_by_identity(
            [
                Artifact(
                    name="summary.txt", external_id="reused", path="a/summary.txt"
                ),
                Artifact(name="script.py", external_id="reused", path="a/script.py"),
            ],
            [],
        )

        assert len(merged) == 1
        assert notes == []

    @pytest.mark.asyncio
    async def test_a_same_named_sibling_keeps_its_own_note(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Superseding one entry must not erase an unrelated entry's diagnostic.

        Orca reuses names by design, so a digest can list a downloadable
        ``report.txt`` beside a second entry of the same name that it never
        stored (``fileId: null``). Filtering stale notes by *name* would drop
        the null entry's only explanation while leaving its ``path=None``
        artifact in the record — the silent loss issue #337 exists to end.
        """
        attempts: dict[str, int] = {}

        async def first_call_fails(client, url, dest, **kwargs) -> None:
            count = attempts.get(url, 0)
            attempts[url] = count + 1
            if count == 0:
                raise httpx.ConnectError("simulated network error")
            dest.write_text("{}")

        monkeypatch.setattr(_artifacts_mod, "download_to", first_call_fails)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "files": [
                        {"fileId": "f-1", "name": "report.txt", "source": "generated"}
                    ]
                },
            )

        runner = _make_runner(tmp_path, handler)
        observation = await runner._build_observation(
            {
                "status": "completed",
                "output": "ok",
                "files": [
                    {"fileId": "f-1", "name": "report.txt"},
                    {"fileId": None, "name": "report.txt"},
                ],
            }
        )

        # f-1 failed on the digest lane and was recovered by the sweep: one
        # artifact, with a path, and its stale note dropped.
        recovered = [a for a in observation.artifacts if a.external_id == "f-1"]
        assert len(recovered) == 1
        assert recovered[0].path is not None

        # The null-fileId sibling survives *with* its own diagnostic.
        orphans = [
            a
            for a in observation.artifacts
            if a.external_id is None and a.name == "report.txt"
        ]
        assert len(orphans) == 1
        assert orphans[0].path is None
        assert observation.response_notices == [
            "Artifact 'report.txt' is not downloadable (no fileId)"
        ]
