"""Orca API runner — drives simulations over Orca's key-authenticated ``/api/v1``.

No browser: each persona message is submitted as a turn (``POST /chat``), the
turn digest is polled until its status leaves ``running``, and the digest's
``output`` becomes the observation text. The first submit of a run carries no
``sessionId`` and so mints a fresh Orca session, whose id the runner reports
as the run's target session id.

Resilience is handled here so it is invisible in the run record: every
submit-lane call is paced by a limiter the factory shares across all of an
experiment's runners, a 429 is retried after ``Retry-After``, a key-store 503
is retried with backoff for ``store_retry_window_s`` and only then becomes a
turn failure, a 401 is run-level auth loss, a 404 on a session the runner was
driving is run-recoverable (the experiment runner retries with a fresh
session), and a 409 ``turn_in_progress`` polls the named turn instead of
resubmitting. A turn still running at the scenario's ``response_wait_ms`` is
cancelled on Orca before the response timeout is raised, and teardown cancels
any turn still in flight so no spend continues after the run ends.

Orca's typed forms (a ``needs_input`` digest) are offered to the persona as
one action slot per field — ``kind`` is Orca's field type verbatim and
``options`` show the option *labels* — and answered with ``formAnswers`` on
the next submit, typed per field, with labels mapped back to option values.
A form answer travels instead of the prose message, which is handed back as
``Observation.discarded_message`` for the run record.

The scenario's fixtures are offered as one ``file_upload`` slot each (id =
fixture name) until attached; a chosen one is uploaded to Orca's file
library on first use anywhere in the experiment — the factory's
:class:`FixtureLibrary` caches the ``fileId`` per name, so every run reuses
it — and attached to the submit via ``files``. An unknown name is skipped
with a warning, as in the browser runner; a fixture Orca rejects (413 / 415)
is reported as an observation error with Orca's reason and the turn is not
submitted.

Turn statuses map as: ``completed``/``needs_input`` → the output is the
text; ``failed`` and ``cancelled`` → empty text, the reason (and any partial
output) only in ``errors``; ``exhausted`` (or a submit rejected with 409
``session_exhausted``) → :class:`TargetSessionEnded`.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import httpx

from metis.core.logging import get_logger

from ...exceptions import (
    ResponseTimeoutError,
    SimulationError,
    TargetSessionEnded,
    TargetSessionLostError,
)
from ...runner import Runner
from ...types import ActionSlot, ChosenAction, Observation, RunConfig
from .._http import (
    Clock,
    PollTimeout,
    Sleep,
    SubmitRateLimiter,
    build_client,
    poll_until,
)
from ._artifacts import collect_artifacts
from ._config import OrcaApiRunnerConfig
from ._fixtures import FixtureLibrary, FixtureRejected
from ._transport import v1_request

__all__ = [
    "FixtureLibrary",
    "FixtureRejected",
    "OrcaApiRunnerConfig",
    "OrcaApiRunner",
    "OrcaApiRunnerFactory",
]

logger = get_logger()

#: Orca field types whose answer is a list of strings.
_LIST_FIELD_TYPES = frozenset({"multiselect", "dynamic_list"})

#: A form answer as it goes on the wire (typed per Orca field type).
FormValue = str | list[str] | int | float


class OrcaApiRunner(Runner):
    """One run attempt over ``/api/v1``: one Orca session, one turn per message."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: OrcaApiRunnerConfig,
        *,
        fixtures_dir: Path,
        run_dir: Path,
        submit_limiter: SubmitRateLimiter | None = None,
        fixture_library: FixtureLibrary | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """
        :param submit_limiter: The experiment-wide submit-lane pacer, shared by
            every runner of one factory. A private one is built when omitted,
            which is only right for a runner used on its own.
        :param fixture_library: The experiment-wide fixture ``fileId`` cache,
            likewise shared; a private one is built when omitted.
        :param clock: / :param sleep: Injected by tests so retry waits are instant.
        """
        self._client = client
        self._config = config
        self._fixtures_dir = fixtures_dir
        self._run_dir = run_dir
        self._clock = clock
        self._sleep = sleep
        self._submit_limiter = submit_limiter or SubmitRateLimiter(
            config.submit_rpm, clock=clock, sleep=sleep
        )
        self._fixture_library = fixture_library or FixtureLibrary(
            client,
            self._submit_limiter,
            store_retry_window_s=config.store_retry_window_s,
            clock=clock,
            sleep=sleep,
        )
        #: The scenario's fixture names (from ``RunConfig``), offered until attached.
        self._fixtures: list[str] = []
        self._attached: set[str] = set()
        #: Fixtures Orca rejected in this run: reported once, then not offered.
        self._rejected: set[str] = set()
        #: Fixtures on the body being built; committed to ``_attached`` once submitted.
        self._attaching: list[str] = []
        self._session_id: str | None = None
        #: The turn submitted but not yet settled — what a cancel would stop.
        self._inflight_turn_id: str | None = None
        self._response_wait_ms = RunConfig.model_fields["response_wait_ms"].default
        # The form from the most recent digest (``None`` once a digest carries
        # no form) and the prose the persona sent alongside a form answer.
        self._pending_form: dict[str, Any] | None = None
        self._discarded_message: str | None = None

    async def setup(self, config: RunConfig) -> None:
        """Record the scenario's response ceiling and fixtures; no session is created eagerly."""
        self._response_wait_ms = config.response_wait_ms
        self._fixtures = list(config.fixtures)
        logger.info("[orca-api-runner] Setup: session will be minted on first submit")

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Submit one turn and return what Orca answered.

        Four seams, each a method so transport concerns stay separable:
        build the submit body (form answers, fixture uploads), submit it
        (rate limits, HTTP resilience), await the digest (polling, response
        ceiling), map the digest to an ``Observation`` (status mapping,
        forms, artifacts). A malformed form answer or a rejected fixture is
        reported as an ``Observation`` from the first seam and never
        submitted.
        """
        body = await self._build_submit_body(message, actions)
        if isinstance(body, Observation):
            return body
        turn_id = await self._submit(body)
        # Only a submitted attachment stops being offered.
        self._attached.update(self._attaching)
        self._attaching = []
        digest = await self._await_digest(turn_id)
        return await self._build_observation(digest)

    async def _build_submit_body(
        self, message: str, actions: list[ChosenAction]
    ) -> dict[str, Any] | Observation:
        """The ``POST /chat`` body for this turn, or an error ``Observation``.

        Actions whose id names a field of the pending form are form answers;
        actions naming a fixture (an offered ``file_upload`` slot's id, or the
        persona's first-turn ``file_upload`` shape with the name as value) are
        attachments, resolved through the experiment's fixture library and
        sent as ``files``; any others are skipped with a warning. With a
        pending form and at least one answer, the body carries typed
        ``formAnswers`` and no ``message`` — the prose is kept to be reported
        as discarded. Otherwise the message is sent as usual, whether or not
        a form is pending ("user ignores the question" is a real behaviour).
        Required fields left unanswered, a non-numeric answer to a number
        field, or a fixture Orca rejects come back as an error
        ``Observation`` with no submit.
        """
        self._discarded_message = None
        self._attaching = []
        fields = self._form_fields()
        # A form action without a value is not an answer; if none carries one
        # the persona is not answering the form at all.
        answers = {a.id: a for a in actions if a.id in fields and a.value is not None}
        attachments: list[str] = []
        skipped: list[str] = []
        for action in actions:
            if action.id in fields:
                continue
            name = self._fixture_name(action)
            if name is None:
                skipped.append(action.id)
            else:
                attachments.append(name)
        if skipped:
            logger.warning(
                "[orca-api-runner] Skipping %d action(s) that are neither a "
                "pending-form field nor a fixture: %s",
                len(skipped),
                ", ".join(skipped),
            )

        body: dict[str, Any] = {}
        form_answers: dict[str, FormValue] = {}
        if answers:
            form_answers, problems = self._typed_form_answers(fields, answers)
            if problems:
                logger.warning(
                    "[orca-api-runner] Form answer rejected before submit: %s",
                    "; ".join(problems),
                )
                return Observation(
                    errors=["Form not submitted: " + "; ".join(problems)],
                    available_actions=self._action_slots(),
                )
        if attachments:
            file_ids, rejected = await self._resolve_attachments(attachments)
            if rejected:
                self._attaching = []
                return Observation(
                    errors=rejected, available_actions=self._action_slots()
                )
            if file_ids:
                body["files"] = file_ids
        if form_answers:
            body["formAnswers"] = form_answers
            self._discarded_message = message or None
            logger.info(
                "[orca-api-runner] Answering form %s with %d field(s)%s",
                (self._pending_form or {}).get("stepId"),
                len(form_answers),
                "; prose message discarded" if message else "",
            )
            # Orca holds a form until it is answered; this submit answers it.
            self._pending_form = None
        else:
            # No usable answer (none chosen, or only empty optional fields):
            # the persona is ignoring the question. Orca rejects an empty
            # ``formAnswers`` with a 422, so send the message instead.
            body["message"] = message
        if self._session_id is not None:
            body["sessionId"] = self._session_id
        return body

    async def _submit(self, body: dict[str, Any]) -> str:
        """``POST /chat``; records a newly minted session id; returns the turn id.

        Rate limiting and the key-store outage are absorbed by :meth:`_request`.
        What reaches here is mapped: a 409 ``turn_in_progress`` names the turn
        to poll (a runner race never loses a turn, and nothing is resubmitted);
        a 404 on a session this runner already drove means Orca reaped or
        deleted it, which only a fresh session can fix — run-level. Anything
        else unmapped raises ``httpx.HTTPStatusError``.
        """
        logger.info("[orca-api-runner] Submitting turn...")
        response = await self._request("POST", "chat", json=body, submit=True)
        # -- session exhausted: Orca refuses further turns before any spend --
        if response.status_code == 409 and _error_code(response) == "session_exhausted":
            raise TargetSessionEnded(
                f"Orca session {self._session_id} is exhausted: submit rejected"
            )
        # -------------------------------------------------------------------
        if response.status_code == 409 and _error_code(response) == "turn_in_progress":
            in_progress = response.json().get("turnId")
            if in_progress:
                turn_id = str(in_progress)
                logger.warning(
                    "[orca-api-runner] Turn %s already in progress; polling it",
                    turn_id,
                )
                self._inflight_turn_id = turn_id
                return turn_id
            # Other 409 bodies (e.g. ``no_form_pending``) are not transport
            # races; they fall through to raise_for_status.
        if response.status_code == 404 and self._session_id is not None:
            raise TargetSessionLostError(
                f"Orca session {self._session_id} is gone (404): reaped or "
                "deleted mid-run"
            )
        response.raise_for_status()
        submitted = response.json()
        turn_id = str(submitted["turnId"])
        if self._session_id is None:
            self._session_id = submitted["sessionId"]
            logger.info("[orca-api-runner] Session minted: %s", self._session_id)
        self._inflight_turn_id = turn_id
        return turn_id

    async def _await_digest(self, turn_id: str) -> dict[str, Any]:
        """Poll the turn's digest until its status leaves ``running``.

        At the response ceiling the turn is cancelled on Orca *before* the
        timeout is raised, so an abandoned turn stops spending.
        """
        try:
            digest = await poll_until(
                lambda: self._fetch_digest(turn_id),
                lambda d: d.get("status") != "running",
                interval_s=self._config.poll_interval_ms / 1000,
                deadline_s=self._response_wait_ms / 1000,
            )
        except PollTimeout as exc:
            await self._cancel_inflight_turn()
            raise ResponseTimeoutError(
                f"Turn {turn_id} still running after {self._response_wait_ms} ms"
            ) from exc
        self._inflight_turn_id = None
        logger.info(
            "[orca-api-runner] Turn %s settled: status=%s", turn_id, digest["status"]
        )
        return digest

    async def _build_observation(self, digest: dict[str, Any]) -> Observation:
        """Map a settled digest onto the transport-agnostic ``Observation``.

        :raises TargetSessionEnded: when the session's lifetime budget is spent.
        """
        status = digest.get("status")
        output: str = digest.get("output") or ""
        if status == "exhausted":
            raise TargetSessionEnded(
                f"Orca session {self._session_id} is exhausted (turn status)"
            )

        text = output
        errors: list[str] = []
        if status == "failed":
            text = ""
            errors.append(f"Turn failed: {digest.get('error') or 'no reason given'}")
        elif status == "cancelled":
            # Partial output must never read as the assistant's answer.
            text = ""
            errors.append(
                "Turn cancelled before completion"
                + (f"; partial output: {output}" if output else "")
            )

        # A new form replaces the pending one. A digest without a form does
        # not clear it: Orca keeps a question pending until it is answered,
        # even when the persona sends prose instead, so keep offering it.
        form = digest.get("form")
        if form is not None:
            self._pending_form = form
        available_actions = self._action_slots()

        discarded_message = self._discarded_message
        self._discarded_message = None

        artifacts, notes = await collect_artifacts(
            self._client, digest.get("files") or [], self._run_dir / "artifacts"
        )
        return Observation(
            text=text,
            artifacts=artifacts,
            errors=[*errors, *notes],
            available_actions=available_actions,
            discarded_message=discarded_message,
        )

    # -- forms ----------------------------------------------------------------

    def _form_fields(self) -> dict[str, dict[str, Any]]:
        """The pending form's fields by id (empty when no form is pending)."""
        if not self._pending_form:
            return {}
        return {f["id"]: f for f in self._pending_form.get("fields") or []}

    def _form_slots(self) -> list[ActionSlot]:
        """One action slot per pending-form field; options show their labels."""
        slots: list[ActionSlot] = []
        for field in self._form_fields().values():
            options = field.get("options")
            slots.append(
                ActionSlot(
                    id=field["id"],
                    kind=field.get("type") or "text",
                    label=field.get("label") or field["id"],
                    options=(
                        [label for label, _ in map(_option_pair, options)]
                        if options
                        else None
                    ),
                    required=field.get("required"),
                )
            )
        return slots

    # -- fixtures -------------------------------------------------------------

    def _action_slots(self) -> list[ActionSlot]:
        """Everything the persona may do next: pending-form fields, then fixtures."""
        return [*self._form_slots(), *self._file_slots()]

    def _file_slots(self) -> list[ActionSlot]:
        """One ``file_upload`` slot per scenario fixture not yet attached in this run.

        A fixture Orca rejected is spent too: the rejection holds for the
        whole experiment, so offering it again could only block more turns.
        """
        return [
            ActionSlot(id=name, kind="file_upload", label=f"Attach file '{name}'")
            for name in self._fixtures
            if name not in self._attached and name not in self._rejected
        ]

    def _fixture_name(self, action: ChosenAction) -> str | None:
        """The fixture an action names, or ``None`` if it is not an attachment.

        Two shapes are attachments: an offered slot chosen by id (a fixture
        name), and the persona's first-turn shape — an id reading like
        ``file_upload`` with the name as the value (the value or, failing
        that, the id is the name, as in the browser runner).
        """
        if action.id in self._fixtures:
            return action.id
        lowered = action.id.lower()
        if "file" in lowered and "upload" in lowered:
            return _value_text(action.value) or action.id
        return None

    async def _resolve_attachments(
        self, names: list[str]
    ) -> tuple[list[str], list[str]]:
        """``fileId``s for the fixtures to attach this turn, plus rejection errors.

        A name already attached in this run (or twice in one turn) is skipped;
        one with no file under the fixtures directory is skipped with a
        warning; one Orca rejects contributes an error and no id, and is
        reported once per run — a later attempt at the same name is skipped
        with a warning so a persona that keeps trying does not stall the
        run. Every resolvable name is still uploaded (and cached) even when
        another is rejected, so the evaluator sees all the problems at once
        and a rerun re-sends nothing.
        """
        file_ids: list[str] = []
        errors: list[str] = []
        for name in names:
            if name in self._attached or name in self._attaching:
                logger.info(
                    "[orca-api-runner] Fixture %r already attached; skipped", name
                )
                continue
            if name in self._rejected:
                logger.warning(
                    "[orca-api-runner] Fixture %r was already rejected by Orca; skipped",
                    name,
                )
                continue
            path = self._fixture_path(name)
            if path is None:
                logger.warning(
                    "[orca-api-runner] Skipping upload %r: no such fixture under %s",
                    name,
                    self._fixtures_dir,
                )
                continue
            try:
                file_id = await self._fixture_library.file_id(name, path)
            except FixtureRejected as exc:
                logger.warning("[orca-api-runner] %s", exc)
                self._rejected.add(name)
                errors.append(
                    f"Turn not submitted: file '{name}' rejected by Orca "
                    f"({exc.status}): {exc.reason}"
                )
                continue
            file_ids.append(file_id)
            self._attaching.append(name)
        return file_ids, errors

    def _fixture_path(self, name: str) -> Path | None:
        """``fixtures_dir/name`` if it is a file inside the fixtures directory."""
        root = self._fixtures_dir.resolve()
        path = (self._fixtures_dir / name).resolve()
        if path == root or not path.is_relative_to(root) or not path.is_file():
            return None
        return path

    def _typed_form_answers(
        self, fields: dict[str, dict[str, Any]], answers: dict[str, ChosenAction]
    ) -> tuple[dict[str, FormValue], list[str]]:
        """Type each answer per its field; report what Orca would reject.

        ``number`` → int/float (numeric strings coerced); ``multiselect`` /
        ``dynamic_list`` → list of strings (a lone value wrapped); anything
        else → string. Option labels are mapped back to option values; a raw
        value is accepted as is.
        """
        typed: dict[str, FormValue] = {}
        problems: list[str] = []
        for field_id, field in fields.items():
            action = answers.get(field_id)
            if action is None or action.value is None:
                if field.get("required"):
                    problems.append(f"required field '{field_id}' was not answered")
                continue
            kind = field.get("type")
            value = action.value
            if kind == "number":
                number = _as_number(value)
                if number is None:
                    problems.append(
                        f"field '{field_id}' expects a number, got {value!r}"
                    )
                    continue
                typed[field_id] = number
            elif kind in _LIST_FIELD_TYPES:
                items = value if isinstance(value, list) else [value]
                typed[field_id] = [_option_value(field, str(item)) for item in items]
            else:
                text = ", ".join(map(str, value)) if isinstance(value, list) else value
                typed[field_id] = _option_value(field, str(text))
        return typed, problems

    async def teardown(self) -> None:
        """Cancel a turn still in flight; delete the session only when configured to.

        The cancel is what stops spend when a run ends mid-turn (a run timeout,
        an escalation); the session is otherwise left for inspection.
        """
        await self._cancel_inflight_turn()
        if not self._config.delete_session_on_teardown or self._session_id is None:
            return
        try:
            response = await self._client.delete(f"sessions/{self._session_id}")
            response.raise_for_status()
            logger.info("[orca-api-runner] Deleted session %s", self._session_id)
        except httpx.HTTPError as exc:
            logger.warning(
                "[orca-api-runner] Could not delete session %s: %s",
                self._session_id,
                exc,
            )

    async def get_session_id(self) -> str | None:
        """Orca's ``sessionId`` — the key assessment uses to fetch Langfuse traces."""
        return self._session_id

    async def _fetch_digest(self, turn_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"chat/{turn_id}")
        response.raise_for_status()
        return response.json()

    async def _cancel_inflight_turn(self) -> None:
        """``POST /chat/cancel`` for the session's running turn, at most once per turn.

        Cancel sits on Orca's read lane so a throttled client can still stop
        spend. Failures are logged, never raised: the caller is already on an
        error path (timeout, teardown) and the turn's budget is the only thing
        at stake.
        """
        turn_id, self._inflight_turn_id = self._inflight_turn_id, None
        if turn_id is None or self._session_id is None:
            return
        try:
            response = await self._request(
                "POST", "chat/cancel", json={"sessionId": self._session_id}
            )
            response.raise_for_status()
            logger.info(
                "[orca-api-runner] Cancel for turn %s: %s",
                turn_id,
                response.json().get("status"),
            )
        except (httpx.HTTPError, SimulationError) as exc:
            logger.warning(
                "[orca-api-runner] Could not cancel turn %s: %s", turn_id, exc
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        submit: bool = False,
    ) -> httpx.Response:
        """One v1 call with the shared resilience applied (see :func:`v1_request`).

        ``submit=True`` marks a submit-lane call, paced by the experiment's
        limiter on every attempt. 429 / 503 are retried; a 503 that outlasts
        ``store_retry_window_s`` is a turn failure; a 401 is auth loss at run
        level. Any other response is returned for the caller to map.
        """
        return await v1_request(
            self._client,
            method,
            path,
            json=json,
            limiter=self._submit_limiter,
            submit=submit,
            store_retry_window_s=self._config.store_retry_window_s,
            clock=self._clock,
            sleep=self._sleep,
        )


def _error_code(response: httpx.Response) -> str | None:
    """The ``error`` field of a JSON error body, if there is one."""
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _option_pair(option: Any) -> tuple[str, str]:
    """``(label, value)`` of an Orca option (``{value, label}``; a bare string is both)."""
    if isinstance(option, dict):
        value = str(option.get("value", ""))
        label = option.get("label")
        return (str(label) if label is not None else value, value)
    return (str(option), str(option))


def _option_value(field: dict[str, Any], chosen: str) -> str:
    """Map a chosen option label back to its value; pass anything else through."""
    options = field.get("options") or []
    pairs = [_option_pair(o) for o in options]
    if any(value == chosen for _, value in pairs):
        return chosen
    for label, value in pairs:
        if label == chosen:
            return value
    return chosen


def _value_text(value: str | list[str] | int | float | None) -> str:
    """A chosen action's value as the one string a fixture name must be."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def _as_number(value: str | list[str] | int | float) -> int | float | None:
    """An int or float for a ``number`` field, or ``None`` if it is not one."""
    if isinstance(value, bool | list):
        return None
    if isinstance(value, int | float):
        return value
    text = value.strip()
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return None


class OrcaApiRunnerFactory:
    """Owns the HTTP client and submit limiter; mints a runner per attempt."""

    def __init__(
        self,
        config: OrcaApiRunnerConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._config = config or OrcaApiRunnerConfig.load()
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._client: httpx.AsyncClient | None = None
        self._submit_limiter: SubmitRateLimiter | None = None
        self._fixture_library: FixtureLibrary | None = None

    @property
    def retry_defaults(self) -> tuple[int, float]:
        return (
            self._config.retry.run_max_retries,
            self._config.retry.run_retry_delay_seconds,
        )

    async def start(self) -> None:
        logger.info("[orca-api-runner] Using Orca API at %s", self._config.base_url)
        self._client = build_client(
            self._config.base_url,
            self._config.api_key.get_secret_value(),
            transport=self._transport,
        )
        self._submit_limiter = SubmitRateLimiter(
            self._config.submit_rpm, clock=self._clock, sleep=self._sleep
        )
        self._fixture_library = FixtureLibrary(
            self._client,
            self._submit_limiter,
            store_retry_window_s=self._config.store_retry_window_s,
            clock=self._clock,
            sleep=self._sleep,
        )

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        if self._client is None or self._fixture_library is None:
            raise RuntimeError("OrcaApiRunnerFactory.create() called before start()")
        return OrcaApiRunner(
            self._client,
            self._config,
            fixtures_dir=fixtures_dir,
            run_dir=run_dir,
            submit_limiter=self._submit_limiter,
            fixture_library=self._fixture_library,
            clock=self._clock,
            sleep=self._sleep,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._submit_limiter = None
        self._fixture_library = None
