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
output) only in ``errors``. There is no session-level exhaustion to map — v1
has no session budget, only a per-call input cap — so two ``failed`` reasons
are singled out from the rest: the input cap twice in a row ends the run as
:class:`TargetSessionEnded` (nothing a persona sends can shrink the context
that caused it, so every later turn would fail the same way), and a rejected
``X-PlatformAI-Key`` is :class:`AuthLossError`.

Each submit carries the evaluator's own ``X-PlatformAI-Key`` when one is
configured, which bills the turn to their platform project on a fixed model
instead of Orca's shared weekly allowance — the allowance matters because
Orca *silently downgrades to a cheaper model* once it is spent, which would
change the model under test mid-experiment. The header goes on submits only;
polling, cancelling and downloading do not take it. The factory reads
``GET /usage`` once at start so an allowance about to run out is reported
before the spend rather than inferred from the results afterwards.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import httpx

from metis.core.console import console
from metis.core.logging import get_logger

from ...exceptions import (
    AuthLossError,
    ResponseTimeoutError,
    SimulationError,
    TargetSessionEnded,
    TargetSessionLostError,
)
from ...runner import Runner
from ...types import (
    ActionSlot,
    Artifact,
    ButtonClickAction,
    ChosenAction,
    FormFillAction,
    Observation,
    RunConfig,
    UploadFileAction,
)
from .._http import (
    Clock,
    PollTimeout,
    Sleep,
    SubmitRateLimiter,
    build_client,
    poll_until,
)
from ._artifacts import collect_artifacts
from ._config import PLATFORM_AI_KEY_HEADER, OrcaApiRunnerConfig
from ._fixtures import FixtureLibrary, FixtureRejected
from ._transport import reason_text, v1_request

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

#: Lowercase substrings that identify a ``failed`` digest as the per-call
#: input cap (200,000 tokens by default) rather than a guardrail block or a
#: stream failure. Orca's spec promises the ``error`` "names the limit" but
#: publishes no machine-readable code for it, so text is the only signal
#: there is; every unmatched ``failed`` reason is logged verbatim so a wording
#: change shows up as a diagnostic instead of as a run burning to its turn
#: limit. Asking Orca for a code on the digest is tracked in issue #338.
_INPUT_CAP_MARKERS = ("input cap", "input token", "per-call input", "input limit")

#: Consecutive input-cap failures before the session is called unusable. One
#: may be a single oversized fixture the persona can drop; two in a row means
#: the accumulated context is the cause, and no message can shrink that.
_INPUT_CAP_FAILURE_LIMIT = 2

#: Lowercase marker for a ``failed`` digest caused by the platform key. Covers
#: both published reasons ("was rejected", "hit its rate limit or budget");
#: neither recovers inside a run, and Orca does not fall back to its own
#: gateway, so the turn is not retried against a different payer.
_PLATFORM_KEY_FAILURE_MARKER = "platformai key"

#: Cancel is best-effort and stops a turn "at its next step", so the digest is
#: polled this many intervals for confirmation before giving up on it.
_CANCEL_CONFIRM_POLLS = 5

#: Fraction of the weekly allowance that makes a downgrade mid-experiment
#: likely enough to warn about. Not a threshold Orca publishes — a run's spend
#: is not knowable in advance — so it is set where the warning is still useful
#: (there is room to finish or to fetch a platform key) rather than where the
#: downgrade is certain.
_USAGE_WARN_FRACTION = 0.8


class _StaleAttachment(Exception):
    """A submit 404 this runner attributes to an attached ``fileId``.

    Internal to this module: raised by :meth:`OrcaApiRunner._submit` and
    consumed by :meth:`OrcaApiRunner.send_turn`, never seen by the
    orchestrator. It exists because Orca answers the same 404 for an unknown
    session and an unknown attachment — *"an id cannot be probed for
    existence"* — so the cause has to be inferred from what was sent, and the
    two causes need opposite handling: a dead session ends the run, a dead
    fixture id costs one turn.
    """

    def __init__(self, names: list[str]) -> None:
        super().__init__(f"Attached file(s) rejected as unknown: {', '.join(names)}")
        self.names = names


class OrcaApiRunner(Runner):
    """One run attempt over ``/api/v1``: one Orca session, one turn per message.

    Upload-rejection semantics (differs from :class:`OrcaPlaywrightRunner` by
    design): its action slots are derived synchronously (no live DOM), so a
    rejected turn returns an error ``Observation`` that re-offers
    ``available_actions=self._action_slots()``, letting the persona retry next
    turn. The Playwright runner omits ``available_actions`` on rejection because
    it returns before its DOM-capture step; that asymmetry is intentional.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: OrcaApiRunnerConfig,
        *,
        fixtures_dir: Path,
        run_dir: Path,
        experiment_root: Path,
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
        self._experiment_root = experiment_root
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
        #: Consecutive turns lost to the per-call input cap (see
        #: ``_INPUT_CAP_FAILURE_LIMIT``); reset by any other settled outcome.
        self._input_cap_failures = 0

    async def setup(self, config: RunConfig) -> None:
        """Record the scenario's response ceiling and fixtures; no session is created eagerly."""
        self._response_wait_ms = config.response_wait_ms
        self._fixtures = list(config.fixtures)
        logger.info(
            "[orca-api-runner] Setup: session will be minted on first submit; "
            "turns billed to %s",
            "the evaluator's own PlatformAI key"
            if self._config.platform_ai_key is not None
            else "Orca's shared weekly allowance (model may be downgraded)",
        )

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Submit one turn and return what Orca answered.

        Four seams, each a method so transport concerns stay separable:
        build the submit body (form answers, fixture uploads), submit it
        (rate limits, HTTP resilience), poll until the turn settles (response
        ceiling, cancel on timeout), map the digest to an ``Observation``
        (status mapping, forms, artifacts). A malformed form answer or a rejected fixture is
        reported as an ``Observation`` from the first seam and never
        submitted.
        """
        body = await self._build_submit_body(message, actions)
        if isinstance(body, Observation):
            return body
        try:
            turn_id = await self._submit(body)
        except _StaleAttachment as exc:
            return self._recover_stale_attachments(exc.names)
        # Only a submitted attachment stops being offered. Capture the names
        # committed this turn — each becomes a source="fixture" artifact on the
        # observation, so it flows through the SAME channel as target outputs
        # (the orchestrator enriches it; the persona sees it as a file it has
        # uploaded). No-assumed-uploads: only post-submit attachments appear.
        newly_attached = list(self._attaching)
        self._attached.update(self._attaching)
        self._attaching = []
        digest = await self._poll_until_settled(turn_id)
        observation = await self._build_observation(digest)
        for name in newly_attached:
            path = self._fixture_path(name)
            observation.artifacts.append(
                Artifact(
                    name=name,
                    source="fixture",
                    path=(
                        path.relative_to(self._experiment_root.resolve()).as_posix()
                        if path is not None
                        else None
                    ),
                )
            )
        return observation

    async def _build_submit_body(
        self, message: str, actions: list[ChosenAction]
    ) -> dict[str, Any] | Observation:
        """The ``POST /chat`` body for this turn, or an error ``Observation``.

        Actions are partitioned by their typed variant, never by sniffing an
        id: a :class:`FormFillAction` whose ``slot_id`` names a pending-form
        field is a form answer; an :class:`UploadFileAction` names a fixture
        to attach; anything else (a button, a form fill for no pending field)
        is skipped with a warning. With a pending form and at least one
        answer, the body carries typed ``formAnswers`` and no ``message`` —
        the prose is kept to be reported as discarded. Otherwise the message
        is sent as usual. An upload naming a fixture that is not a scenario
        fixture, or whose file is missing on disk, comes back as an error
        ``Observation`` with no submit (loud, never a silent drop); so do a
        required field left unanswered, a mistyped number, or a fixture Orca
        rejects.
        """
        self._discarded_message = None
        self._attaching = []
        fields = self._form_fields()
        offered = set(self._fixtures)

        # Keyed by form-field id (the ``slot_id`` naming a pending-form field).
        answers: dict[str, FormFillAction] = {}
        attachments: list[str] = []
        upload_errors: list[str] = []
        skipped: list[str] = []
        for action in actions:
            match action:
                case FormFillAction(slot_id=slot_id) if slot_id in fields:
                    answers[slot_id] = action
                case UploadFileAction(filename=filename):
                    if filename not in offered:
                        upload_errors.append(
                            f"file '{filename}' is not a fixture for this scenario"
                        )
                    elif self._fixture_path(filename) is None:
                        upload_errors.append(
                            f"file '{filename}' not found under the fixtures directory"
                        )
                    else:
                        attachments.append(filename)
                case FormFillAction(slot_id=slot_id):
                    skipped.append(slot_id)
                case ButtonClickAction(slot_id=slot_id):
                    skipped.append(slot_id)
        if skipped:
            logger.warning(
                "[orca-api-runner] Skipping %d action(s) with no matching "
                "pending-form field: %s",
                len(skipped),
                ", ".join(skipped),
            )
        if upload_errors:
            logger.warning(
                "[orca-api-runner] Upload(s) rejected before submit: %s",
                "; ".join(upload_errors),
            )
            return Observation(
                errors=["Turn not submitted: " + "; ".join(upload_errors)],
                available_actions=self._action_slots(),
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
        # Orca requires exactly one of ``message`` (minLength 1) or
        # ``formAnswers``, so a blank message with nothing to answer has no
        # valid body — it would be a 422. Checked before any upload so a turn
        # the persona has already broken costs no spend, and reported rather
        # than papered over with substitute text: a blank message is a
        # persona-side defect, and putting words in its mouth would hide it
        # from the transcript the evaluation is built on.
        if not form_answers and not message.strip():
            logger.warning(
                "[orca-api-runner] Turn not submitted: the persona produced an "
                "empty message and no usable form answer"
            )
            self._attaching = []
            return Observation(
                errors=[
                    "Turn not submitted: the message was empty and there was no "
                    "form answer to send in its place"
                ],
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
            # No usable answer: the persona is ignoring the question. Orca
            # rejects an empty ``formAnswers`` with a 422, so send the message.
            body["message"] = message
        if self._session_id is not None:
            body["sessionId"] = self._session_id
        return body

    async def _submit(self, body: dict[str, Any]) -> str:
        """``POST /chat``; records a newly minted session id; returns the turn id.

        Rate limiting and the key-store outage are absorbed by :meth:`_request`.
        What reaches here is mapped: a 409 ``turn_in_progress`` names the turn
        to poll (a runner race never loses a turn, and nothing is resubmitted);
        a 400 is a platform key Orca would not read, which every later submit
        would repeat — run-level; a 404 is attributed by what was sent (see
        :meth:`_attribute_submit_404`); a 422 is a schema divergence. Anything
        else unmapped raises ``httpx.HTTPStatusError``.

        :raises _StaleAttachment: the 404 is attributable to an attached file.
        """
        logger.info("[orca-api-runner] Submitting turn...")
        response = await self._request(
            "POST",
            "chat",
            json=body,
            submit=True,
            headers=self._platform_ai_headers(),
        )
        if response.status_code == 400 and self._config.platform_ai_key is not None:
            # The config validator rejects everything Orca documents as a 400,
            # so reaching here means its rules and ours have diverged. Nothing
            # was started, and the next submit would be identical.
            raise AuthLossError(
                "Orca rejected the PlatformAI key as malformed (400); no turn "
                f"was started. Orca's reason: {reason_text(response)}"
            )
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
        if response.status_code == 404:
            self._attribute_submit_404(body)
        if response.status_code == 422:
            # The body did not match ``ChatSubmitRequest``: a divergence between
            # this runner and the deployment's schema, not anything the persona
            # did. Named here so the next such mismatch reads as a protocol
            # violation instead of a bare, message-less HTTPStatusError.
            raise SimulationError(
                "Orca rejected the submit body as invalid (422); the runner and "
                "the deployment's chat schema have diverged. Orca's reason: "
                f"{reason_text(response)}"
            )
        response.raise_for_status()
        submitted = response.json()
        turn_id = str(submitted["turnId"])
        if self._session_id is None:
            self._session_id = submitted["sessionId"]
            logger.info("[orca-api-runner] Session minted: %s", self._session_id)
        self._inflight_turn_id = turn_id
        return turn_id

    def _attribute_submit_404(self, body: dict[str, Any]) -> None:
        """Decide whether a submit 404 was the session or an attached file.

        Orca answers the same 404 for an unknown, foreign, expired, deleted or
        malformed ``sessionId`` *or* ``fileId``, deliberately, so that an id
        cannot be probed for existence. The response therefore cannot be
        interrogated; what *was sent* is the only evidence available.

        A submit carrying files is attributed to those files, because that is
        both the recoverable cause and the one that repeats: a dead fixture id
        lives in an experiment-scoped cache, so blaming the session instead
        would retry the whole run and re-send the same dead id at the same
        turn, until the retry budget is gone. When both are dead the fixture
        is handled first; the next submit then carries no files and the
        session loss is reported correctly, one turn later.

        A 404 on a first submit that carried no files and had minted no session
        yet has neither candidate to blame, so this returns and the caller's
        ``raise_for_status`` reports the 404 as it stands — that combination
        points at the endpoint (a wrong base URL) rather than at a dead id.

        :raises _StaleAttachment: the submit carried files.
        :raises TargetSessionLostError: it did not, and a session was in play.
        """
        attached: list[str] = list(body.get("files") or [])
        if attached:
            raise _StaleAttachment(list(self._attaching))
        if self._session_id is not None:
            raise TargetSessionLostError(
                f"Orca session {self._session_id} is gone (404): reaped or "
                "deleted mid-run"
            )

    def _recover_stale_attachments(self, names: list[str]) -> Observation:
        """Evict the dead ``fileId``s and report the lost turn to the persona.

        The fixtures stay *offered*: nothing is wrong with the files
        themselves, only with the ids cached for them, so the next turn can
        attach the same names and the library will upload them again. That is
        the difference between this and :class:`FixtureRejected`, which is
        permanent and spends the fixture for the run.
        """
        self._attaching = []
        for name in names:
            self._fixture_library.forget(name)
        listed = ", ".join(f"'{name}'" for name in names) or "the attached file(s)"
        logger.warning(
            "[orca-api-runner] Submit rejected (404) for attached file(s) %s; "
            "cached id(s) dropped and the turn was not started",
            listed,
        )
        return Observation(
            errors=[
                f"Turn not submitted: Orca no longer recognises {listed}. The "
                "file(s) will be uploaded again if attached on a later turn."
            ],
            available_actions=self._action_slots(),
        )

    async def _poll_until_settled(self, turn_id: str) -> dict[str, Any]:
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

        :raises TargetSessionEnded: the per-call input cap has failed
            ``_INPUT_CAP_FAILURE_LIMIT`` turns in a row.
        :raises AuthLossError: the evaluator's platform key was refused.
        """
        status = digest.get("status")
        output: str = digest.get("output") or ""

        text = output
        errors: list[str] = []
        # Any other settled outcome breaks an input-cap streak: the session
        # answered, so whatever was too large for one call is not permanent.
        if status != "failed":
            self._input_cap_failures = 0
        if status == "failed":
            text = ""
            reason = digest.get("error") or "no reason given"
            self._triage_failure(str(reason))
            errors.append(f"Turn failed: {reason}")
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
            self._client,
            digest.get("files") or [],
            self._run_dir / "artifacts",
            self._experiment_root,
            store_retry_window_s=self._config.store_retry_window_s,
            clock=self._clock,
            sleep=self._sleep,
        )
        return Observation(
            text=text,
            artifacts=artifacts,
            errors=[*errors, *notes],
            available_actions=available_actions,
            discarded_message=discarded_message,
        )

    def _triage_failure(self, reason: str) -> None:
        """Single out the two ``failed`` reasons that must not read as one turn.

        Everything else about a ``failed`` digest is a normal turn error: a
        guardrail block or a stream failure is genuinely per-turn, retrying
        the same message is allowed, and the persona should see it and adapt.
        Two reasons are not per-turn:

        - **The per-call input cap.** The cause is the accumulated session
          context, which no message the persona can send will shrink, so every
          later turn fails identically — and because a ``failed`` digest is a
          *successful* ``send_turn``, the orchestrator's consecutive-failure
          counter resets each time and the run would burn to its turn limit,
          paying for every attempt. Counted rather than acted on at once: one
          oversized call may be a single large fixture.
        - **A refused platform key.** Orca does not fall back to its own
          gateway, so the turn is never billed to a payer the evaluator did
          not choose — and neither a rejection nor a spent platform budget
          recovers inside a run.

        :raises TargetSessionEnded: the input cap, ``_INPUT_CAP_FAILURE_LIMIT``
            turns in a row.
        :raises AuthLossError: the platform key was rejected or is out of
            allowance.
        """
        lowered = reason.lower()
        if _PLATFORM_KEY_FAILURE_MARKER in lowered:
            raise AuthLossError(f"Orca refused the PlatformAI key: {reason}")
        if any(marker in lowered for marker in _INPUT_CAP_MARKERS):
            self._input_cap_failures += 1
            logger.warning(
                "[orca-api-runner] Turn failed on the per-call input cap "
                "(%d in a row): %s",
                self._input_cap_failures,
                reason,
            )
            if self._input_cap_failures >= _INPUT_CAP_FAILURE_LIMIT:
                raise TargetSessionEnded(
                    f"Orca session {self._session_id} is unusable: the per-call "
                    f"input cap failed {self._input_cap_failures} turns in a row "
                    f"({reason})"
                )
            return
        # Not a reason this runner acts on — but the input-cap wording is the
        # only signal Orca offers for it, so log every other reason verbatim.
        # A silent change to that wording would otherwise show up as a run
        # burning to its turn limit rather than as a diagnostic.
        self._input_cap_failures = 0
        logger.warning("[orca-api-runner] Turn failed: %s", reason)

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
        self, fields: dict[str, dict[str, Any]], answers: dict[str, FormFillAction]
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
            if action is None:
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
            # Through the shared layer, not the raw client: a delete lost to a
            # throttled read lane would leak the session silently, which is
            # exactly the kind of failure a 429 retry exists to prevent.
            response = await self._request("DELETE", f"sessions/{self._session_id}")
            response.raise_for_status()
            logger.info("[orca-api-runner] Deleted session %s", self._session_id)
        except (httpx.HTTPError, SimulationError) as exc:
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
        if response.status_code == 404:
            # Orca holds a digest only ~10 minutes after its last poll, then
            # the turnId 404s. The normal loop polls every few seconds and
            # cannot reach that, so this is here for the paths that poll after
            # a gap — cancel confirmation today, a resumed turn if one is ever
            # added. Named explicitly so the next such caller finds the window
            # written down instead of a bare status error.
            raise SimulationError(
                f"Orca no longer has a digest for turn {turn_id} (404): the id "
                "is unknown, or the digest aged out of its retention window"
            )
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
            status = response.json().get("status")
            logger.info("[orca-api-runner] Cancel for turn %s: %s", turn_id, status)
        except (httpx.HTTPError, SimulationError) as exc:
            logger.warning(
                "[orca-api-runner] Could not cancel turn %s: %s", turn_id, exc
            )
            return
        if status == "not_running":
            # Worth its own line: on the response-timeout path it means the
            # turn settled between the last poll and the cancel, so an answer
            # was very likely there and has been discarded.
            logger.info(
                "[orca-api-runner] Turn %s had already settled when the cancel "
                "was sent; nothing was stopped",
                turn_id,
            )
            return
        await self._confirm_cancelled(turn_id)

    async def _confirm_cancelled(self, turn_id: str) -> None:
        """Poll the digest until it reads ``cancelled``, briefly and best-effort.

        Orca stops a turn "at its next step", so an accepted cancel does not
        mean the spend has stopped yet — the spec is explicit that a cancel is
        confirmed by polling, not assumed. Both callers are already on an error
        path (a response timeout, teardown), so the budget here is a handful of
        intervals and nothing raises: an unconfirmed cancel is logged for the
        evaluator, since the alternative is holding a finished run open.
        """
        interval_s = self._config.poll_interval_ms / 1000
        try:
            digest = await poll_until(
                lambda: self._fetch_digest(turn_id),
                lambda d: d.get("status") != "running",
                interval_s=interval_s,
                deadline_s=interval_s * _CANCEL_CONFIRM_POLLS,
            )
        except PollTimeout:
            logger.warning(
                "[orca-api-runner] Cancel for turn %s not confirmed after %.1f s; "
                "it may still be running",
                turn_id,
                interval_s * _CANCEL_CONFIRM_POLLS,
            )
            return
        except (httpx.HTTPError, SimulationError) as exc:
            logger.warning(
                "[orca-api-runner] Could not confirm the cancel of turn %s: %s",
                turn_id,
                exc,
            )
            return
        logger.info(
            "[orca-api-runner] Cancel of turn %s confirmed: status=%s",
            turn_id,
            digest.get("status"),
        )

    def _platform_ai_headers(self) -> dict[str, str] | None:
        """The ``X-PlatformAI-Key`` header for a submit, or ``None`` if unset.

        Built per call and only for the submit lane. The header belongs to
        ``POST /chat`` alone — polling, cancelling and downloading do not read
        it — so it is not set on the client, where it would ride along on
        every request and widen the exposure of a credential for nothing.
        """
        key = self._config.platform_ai_key
        if key is None:
            return None
        return {PLATFORM_AI_KEY_HEADER: key.get_secret_value()}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        headers: dict[str, str] | None = None,
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
            headers=headers,
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
            insecure=self._config.insecure,
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
        await self._report_usage()

    async def _report_usage(self) -> None:
        """Report the key's week-to-date allowance before any spend starts.

        The pre-flight for the silent downgrade: once the weekly allowance is
        spent, Orca *"downgrades later turns to a cheaper model rather than
        refusing them"* and says so nowhere in the API. An experiment that
        crosses its allowance mid-flight therefore swaps the model under test
        with nothing in the run record to mark where — so the runs before and
        after are not comparable, and no metric can detect it.

        One read-lane call says so before the spend rather than after. Never
        blocks: the evaluator may have accepted the downgrade, and the
        threshold is far too fuzzy to end a run over. Never raises either — a
        pre-flight that fails must not stop the experiment it was only
        reporting on.
        """
        if self._client is None or self._submit_limiter is None:
            return
        try:
            response = await v1_request(
                self._client,
                "GET",
                "usage",
                limiter=self._submit_limiter,
                store_retry_window_s=self._config.store_retry_window_s,
                clock=self._clock,
                sleep=self._sleep,
            )
            response.raise_for_status()
            usage = response.json()
        except (httpx.HTTPError, SimulationError, ValueError) as exc:
            logger.warning("[orca-api-runner] Could not read GET /usage: %s", exc)
            return

        # daPct gets its own line rather than being folded into pct: METIS's
        # data-analysis scenarios spend that allowance specifically, so it can
        # be the binding constraint while the overall figure still looks fine.
        fractions = {
            "overall": usage.get("pct"),
            "data-analysis": usage.get("daPct"),
            "doc-generation": usage.get("docPct"),
        }
        summary = ", ".join(
            f"{label} {value:.0%}"
            for label, value in fractions.items()
            if isinstance(value, int | float)
        )
        logger.info(
            "[orca-api-runner] Weekly allowance used — %s (tier=%s, resets %s)",
            summary or "unreported",
            usage.get("planTier"),
            usage.get("resetAt"),
        )
        if self._config.platform_ai_key is not None:
            # Billed to the evaluator's own project: outside this allowance
            # and its downgrades, so the numbers are informational only.
            return
        highest = max(
            (v for v in fractions.values() if isinstance(v, int | float)),
            default=0.0,
        )
        if highest >= _USAGE_WARN_FRACTION:
            console.print(
                f"[yellow]Orca weekly allowance is {highest:.0%} used[/yellow] "
                f"({summary}; resets {usage.get('resetAt')}). No PlatformAI key "
                "is configured, so turns will be silently downgraded to a "
                "cheaper model once the allowance is spent — which changes the "
                "model under test mid-experiment."
            )
            logger.warning(
                "[orca-api-runner] Weekly allowance %.0f%% used with no "
                "PlatformAI key configured; later turns may run on a "
                "downgraded model",
                highest * 100,
            )

    async def create(
        self, run_dir: Path, fixtures_dir: Path, experiment_root: Path
    ) -> Runner:
        if self._client is None or self._fixture_library is None:
            raise RuntimeError("OrcaApiRunnerFactory.create() called before start()")
        return OrcaApiRunner(
            self._client,
            self._config,
            fixtures_dir=fixtures_dir,
            run_dir=run_dir,
            experiment_root=experiment_root,
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
