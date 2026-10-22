"""The generic HTTP runner: the request tool and the rules code enforces on it.

``HttpRunnerFactory`` loads the specification's target binding and holds one HTTP
transport for every trial. Its runner fetches the target's OpenAPI specification once,
and ``http_request`` is the one call the runner agent makes on the target: code checks
the path, the headers and the binding's rules, substitutes the user's quoted words,
adds the credentials, and records which responses answered a submission. Polling
(``poll_until``), file downloads (#525) and the agent loop (#481) arrive in later steps.
"""

from __future__ import annotations

import asyncio
import mimetypes
import time
from dataclasses import dataclass
from json import loads
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from ...config import TrialRetryConfig
from ...transport_log import LoggingTransport, TransportLog
from ..binding import TargetBindingError, load_target_binding
from ..evidence import Pointer, PointerError, resolve
from ..runner import Runner
from .rules import SUBMIT_METHODS, ToolRefused, check_call, check_headers, matches
from .spans import Spans

if TYPE_CHECKING:
    from metis.core.specification import Specification
    from metis.core.trials import TrialConfig

    from ...artifacts import ArtifactLedger
    from ..binding import LoadedBinding
    from ..types import Observation, Promise

MAX_429_RESENDS = 3
_TIMEOUT = httpx.Timeout(60.0)
POLL_INTERVAL = 5.0
"""Seconds between polls; the binding and ``TrialConfig`` have no field for it."""
_sleep = asyncio.sleep  # names tests replace
_now = time.monotonic


@dataclass(frozen=True)
class OpenSubmission:
    """A submission the target accepted and nothing has settled yet (``poll_until`` settles it)."""

    request: str
    """The transport-log entry of the request."""
    response: str
    """The entry of the response that accepted it."""
    turn: int


@dataclass(frozen=True)
class Unresolved:
    """A submission a poll could not settle because the target answered it with a 4xx."""

    submission: OpenSubmission
    response: str
    """The entry of the response that showed the failure."""


class HttpRunner(Runner):
    """Carries out the runner agent's HTTP calls on one trial, under the binding's rules."""

    def __init__(
        self,
        binding: LoadedBinding,
        client: httpx.AsyncClient,
        log: TransportLog,
        experiment_root: Path,
    ) -> None:
        self._binding = binding
        self._client = client
        self._log = log
        self._root = experiment_root
        self._base = ""
        self._deadline = 0.0
        self._wait = 0.0
        self._last_poll: tuple[str, str, list[Any] | None, list[Any] | None] | None = (
            None
        )
        self._turn = 0
        self._session_id: str | None = None
        self.spans = Spans.of("")
        self.spec_entry = ""
        """The log entry holding the specification: the target's description, not an answer."""
        self.results: list[str] = []
        """Response entries of the agent's calls, in order: what a pointer may cite."""
        self.answers: list[str] = []
        """Response entries that accepted a submission. #525 uses them to tell this
        conversation's listings from an account-wide one."""
        self.open_submission: OpenSubmission | None = None
        """The accepted submission nothing has settled yet; ``poll_until`` clears it."""
        self.unresolved: Unresolved | None = None
        """Set by a 4xx during a poll while a submission was open; a timeout leaves it open."""

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def use_ledger(self, ledger: ArtifactLedger) -> None:
        self.ledger = ledger

    async def setup(self, config: TrialConfig) -> None:
        """Fetch and log the specification, once, and work out the server URL."""
        self._deadline = _now() + config.timeout_minutes * 60
        self._wait = config.response_wait_ms / 1000
        url = self._binding.spec_url
        parts = urlsplit(url)
        if parts.scheme in ("http", "https") and not parts.netloc:
            raise TargetBindingError(
                f"spec_url {self._binding.binding.spec_url!r} has no host"
            )
        if parts.scheme == "file":
            raw = Path(unquote(parts.path)).read_bytes()
            request = self._log.append("request", "GET (specification file)", b"")
            self.spec_entry = self._log.append(
                "response", "GET (specification file) -> 200", raw, pairs_with=request
            )
        else:
            response = await self._client.get(url)
            self.spec_entry = self._log.last_id() or ""
            if not response.is_success:
                raise TargetBindingError(
                    f"the specification could not be fetched: {response.status_code}"
                )
            raw = response.content
        servers = loads(raw).get("servers") or [{"url": "/"}]
        self._base = urljoin(url, str(servers[0].get("url") or "/")).rstrip("/")
        if not self._base.startswith(("http://", "https://")):
            raise TargetBindingError(
                "the specification's first server is not an http(s) URL; "
                "a file spec needs an absolute one"
            )

    def begin_action(self, action: str) -> None:
        """Start a turn: number the action's quoted spans. ``act`` calls this first."""
        self._turn += 1
        self.spans = Spans.of(action)

    def record_session_id(self, pointer: Pointer) -> None:
        """Copy the session ID from a submission's response, and from nothing else.

        :raises PointerError: When the pointer does not lead to such a response.
        """
        value, _ = resolve(pointer, self._log, allowed=self.answers)
        self._session_id = str(value)

    async def http_request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json: Any = None,
        multipart: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send one request for the runner agent, if the rules allow it.

        :param path: As the specification writes it; code joins it to the server.
        :param json: A body; ``{{n}}`` stands for the user's n-th quoted span.
        :param multipart: Part name to value; ``@name`` is a held file, anything else
            text that may hold placeholders.
        :raises ToolRefused: Whatever breaks a rule; nothing is sent.
        """
        method = method.upper()
        check_call(method, path, self._binding.binding.forbidden_calls)
        extra = check_headers(headers)
        if json is not None and multipart is not None:
            raise ToolRefused("send json or multipart, not both")
        submission = self._is_submission(method, path, json is not None)
        if submission and self.open_submission is not None:
            raise ToolRefused(
                f"a submission ({self.open_submission.request}) is still open; "
                "it must settle before another is sent"
            )
        if submission and not self.spans.texts:
            raise ToolRefused(
                "the user's action quoted nothing to send, so nothing may be submitted"
            )
        body = self.spans.substitute(json)
        data, files = self._multipart(multipart)

        wire = {**extra, **self._credentials(method, path)}
        response = await self._send(
            method, path, wire, query, body if json is not None else None, data, files
        )
        response_id = self._log.last_id() or ""
        request_id = self._log.get(response_id).pairs_with or ""
        self.results.append(response_id)
        if submission and response.is_success:
            self.open_submission = OpenSubmission(request_id, response_id, self._turn)
            self.answers.append(response_id)
        return {
            "request_entry": request_id,
            "response_entry": response_id,
            "status": response.status_code,
            "body": _preview(response),
        }

    async def poll_until(
        self,
        path: str,
        at: str,
        *,
        not_in: list[Any] | None = None,
        in_: list[Any] | None = None,
    ) -> dict[str, Any]:
        """``GET path`` every few seconds until the JSON value at ``at`` settles.

        :param not_in: Values that mean still waiting; anything else is done.
        :param in_: Values that mean done; anything else is still waiting.
        :raises ToolRefused: Unless exactly one of ``not_in`` and ``in_`` is given, or
            when the path breaks a rule.
        """
        if (not_in is None) == (in_ is None):
            raise ToolRefused(
                "give exactly one of not_in (values that mean still waiting) "
                "or in_ (values that mean done)"
            )
        check_call("GET", path, self._binding.binding.forbidden_calls)
        self._last_poll = (path, at, not_in, in_)
        stop_at = _now() + min(self._wait, max(0.0, self._deadline - _now()))
        wire = self._credentials("GET", path)
        polls = 0
        while True:
            response = await self._send("GET", path, wire, None, None, None, None)
            polls += 1
            response_id = self._log.last_id() or ""
            self.results.append(response_id)
            reply: dict[str, Any] = {
                "response_entry": response_id,
                "status": response.status_code,
                "polls": polls,
                "body": _preview(response),
            }
            if response.status_code != 429:  # _send waited it out; carry on
                if not response.is_success:
                    if 400 <= response.status_code < 500 and self.open_submission:
                        self.unresolved = Unresolved(self.open_submission, response_id)
                        self.open_submission = None
                    return reply
                try:
                    value, _ = resolve(Pointer(response_id, at), self._log)
                except PointerError as exc:
                    return {**reply, "error": str(exc)}
                waiting = (
                    value in not_in if not_in is not None else value not in (in_ or [])
                )
                if not waiting:
                    self.open_submission = None
                    return {**reply, "condition": "holds", "value": value}
            if _now() + POLL_INTERVAL > stop_at:
                return {
                    **reply,
                    "condition": "timed out; the submission is still open",
                }
            await _sleep(POLL_INTERVAL)

    async def resume_poll(self) -> dict[str, Any] | None:
        """Repeat the last poll if a submission is still open; ``act`` calls it first."""
        if self.open_submission is None or self._last_poll is None:
            return None
        path, at, not_in, in_ = self._last_poll
        return await self.poll_until(path, at, not_in=not_in, in_=in_)

    def _is_submission(self, method: str, path: str, has_json: bool) -> bool:
        patterns = self._binding.binding.submissions
        if patterns:
            return any(matches(p, method, path) for p in patterns)
        return method in SUBMIT_METHODS and has_json

    def _multipart(
        self, parts: dict[str, str] | None
    ) -> tuple[dict[str, str] | None, dict[str, tuple[str, bytes, str]] | None]:
        if parts is None:
            return None, None
        data: dict[str, str] = {}
        files: dict[str, tuple[str, bytes, str]] = {}
        for part, value in parts.items():
            if not value.startswith("@"):
                data[part] = self.spans.substitute_text(value)
                continue
            name = value[1:]
            held = next((a for a in self.ledger.artifacts() if a.name == name), None)
            if held is None or held.path is None:
                raise ToolRefused(f"{name!r} is not a file you hold")
            kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
            files[part] = (name, (self._root / held.path).read_bytes(), kind)
            self.ledger.record_upload(name, at_turn=self._turn)
        return data or None, files or None

    def _credentials(self, method: str, path: str) -> dict[str, str]:
        """The headers code adds. A secret that is not set adds nothing."""
        binding = self._binding
        found: dict[str, str] = {}
        if binding.binding.auth and (
            key := binding.secret(binding.binding.auth.secret_env)
        ):
            found["Authorization"] = f"Bearer {key.get_secret_value()}"
        for rule in binding.binding.secret_headers:
            value = binding.secret(rule.env)
            if value is not None and matches(rule.match, method, path):
                found[rule.header] = value.get_secret_value()
        return found

    async def _send(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        query: dict[str, Any] | None,
        body: Any,
        data: dict[str, str] | None,
        files: dict[str, tuple[str, bytes, str]] | None,
    ) -> httpx.Response:
        """Send, resending a 429 after its ``Retry-After`` while the trial has time."""
        for attempt in range(MAX_429_RESENDS + 1):
            response = await self._client.request(
                method,
                self._base + path,
                params=query,
                headers=headers,
                json=body,
                data=data,
                files=files,
            )
            if response.status_code != 429 or attempt == MAX_429_RESENDS:
                break
            wait = _retry_after(response)
            if wait > self._deadline - _now():
                break
            await _sleep(wait)
        return response

    async def act(self, action: str, promised: list[Promise]) -> Observation:
        """Not implemented until #481.

        It raises rather than returning an empty ``Observation``, which would record a
        reply the target never sent.
        """
        raise NotImplementedError("HttpRunner.act is not implemented until #481")

    async def end_chat(self, promised: list[Promise]) -> None:
        pass

    async def teardown(self) -> None:
        pass  # the HTTP transport is the factory's


def _preview(response: httpx.Response) -> str:
    return response.content.decode("utf-8", errors="replace")[:4000]


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(0.0, float(response.headers.get("retry-after", "5")))
    except ValueError:  # an HTTP date
        return 5.0


class HttpRunnerFactory:
    """Builds :class:`HttpRunner`s for the app the specification's target binding names."""

    generation: ClassVar[str] = "gen_2"

    def __init__(
        self, binding: LoadedBinding, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._binding = binding
        self._transport = transport
        """Replaced by a fake in tests; otherwise ``start`` opens the real one."""

    @property
    def binding(self) -> LoadedBinding:
        return self._binding

    @classmethod
    def from_specification(
        cls, specification: Specification, inputs_dir: Path
    ) -> HttpRunnerFactory:
        """Load ``specification.target_binding`` from the experiment's ``inputs_dir``.

        :raises TargetBindingError: When the specification names no binding, or the
            binding cannot be loaded.
        """
        if specification.target_binding is None:
            raise TargetBindingError(
                "HttpRunnerFactory needs the specification's target_binding, "
                "which is not set"
            )
        return cls(load_target_binding(inputs_dir, specification.target_binding))

    @property
    def retry_defaults(self) -> tuple[int, float]:
        defaults = TrialRetryConfig()
        return defaults.trial_max_retries, defaults.trial_retry_delay_seconds

    async def start(self) -> None:
        """Open the HTTP transport every trial's client shares."""
        if self._transport is None:
            self._transport = httpx.AsyncHTTPTransport(
                verify=self._binding.binding.tls_verify
            )

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> HttpRunner:
        """A runner whose requests are logged to this trial's own transport log."""
        assert self._transport is not None, "start() must run before create()"
        log = TransportLog.for_trial(run_dir)
        logged = LoggingTransport(
            _Shared(self._transport),
            log,
            secret_headers=[h.header for h in self._binding.binding.secret_headers],
        )
        client = httpx.AsyncClient(transport=logged, timeout=_TIMEOUT)
        return HttpRunner(self._binding, client, log, experiment_root)

    async def close(self) -> None:
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None


class _Shared(httpx.AsyncBaseTransport):
    """Lends the factory's transport to one trial's client, which must not close it."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._inner.handle_async_request(request)
