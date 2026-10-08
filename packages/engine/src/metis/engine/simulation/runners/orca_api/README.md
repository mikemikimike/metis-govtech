# Orca API Runner

Drives a simulation over Orca's key-authenticated `/api/v1` — no browser. Each persona message becomes one Orca turn: submit, poll until it settles, map the settled digest onto an `Observation`.

This README covers the **call sequence**, the **identifiers**, and **which parts of the published v1 surface the runner uses**. Three things it deliberately does not repeat:

| For | See |
|-----|-----|
| Resilience policy, status mapping, form handling, platform-key rationale | the module docstring in `__init__.py` |
| Factory lifecycle, shared resources, `--concurrency` interaction | [Engine guide → API runner](../../../../../../../../docs/guide/engine.md#api-runner-orcaapirunner) |
| `Runner` ABC, action/upload semantics common to both runners | [simulation README](../../README.md) |

The authoritative protocol description is Orca's own published spec (`GET /api/v1/docs`, keyless). Orca owns it; where this README and the spec disagree, the spec is right and this file is stale.

## Turn lifecycle

```
factory.start()          once per experiment — client, submit limiter,
                         fixture cache, GET /usage pre-flight
  │
  └─ factory.create()    once per run attempt
       │
       ├─ setup(config)          no I/O: records response_wait_ms + fixture names
       │                         NO session is created here
       │
       ├─ send_turn(msg, actions)          repeated, strictly sequential
       │    ├─ _build_submit_body    validate, upload fixtures → POST /files
       │    ├─ _submit              POST /chat  (submit lane, paced)
       │    ├─ _poll_until_settled  GET /chat/{turnId} until status != running
       │    └─ _build_observation   status → text/errors; download artifacts
       │
       └─ teardown()             cancel any in-flight turn; delete session
                                 only if delete_session_on_teardown
```

The session is **minted lazily** by the first `POST /chat` that carries no `sessionId` — `POST /sessions` is never called. So `get_session_id()` returns `None` until the first successful submit, and a run that dies before then has no target session id at all.

### The four seams

Each is a separate method so transport concerns stay separable. The first two can short-circuit and return an error `Observation` **without spending a turn on Orca**:

| Seam | Short-circuits on |
|------|-------------------|
| `_build_submit_body` | an upload naming a non-scenario fixture or a file missing on disk; a required form field unanswered or a mistyped `number`; an empty message with no form answer to send in its place; a fixture Orca rejects at upload |
| `_submit` | a submit `404` attributable to an attached `fileId` (`_StaleAttachment`) |

Two ordering rules in `_build_submit_body` are load-bearing:

- **The empty-body check runs before any upload**, so a persona-side defect costs no upload and no submit.
- **`_attaching` is staged, not committed.** A fixture stops being offered only after the submit succeeds (`send_turn` drains `_attaching` into `_attached`), so a failed submit leaves it available. No assumed uploads.

## What the digest is

`POST /chat` returns **202 Accepted** with a `turnId` — not an answer. `GET /chat/{turnId}` returns a `TurnDigest`, the polled read-only view of that turn. Its own one-line description in the spec is the whole design:

> The whole turn so far — cursor-free, so polling is idempotent.

| Property | Consequence here |
|----------|------------------|
| Complete, not a delta — every poll returns the full `output`, `files[]` and current `form`; no cursor or `since` parameter | `poll_until` simply replaces the previous result. Polling late, twice, or from another worker yields the same thing. |
| Idempotent, no side effects; on the read lane (120/min). Polling "neither kills nor duplicates" a running turn | This is what makes the `409 turn_in_progress` recovery safe: adopt the other turn's id and poll it. Nothing is resubmitted; nothing double-spends. |
| It is the turn's status machine: `running` → `completed` / `needs_input` / `failed` / `cancelled` | `_poll_until_settled` polls on exactly one predicate — `status != "running"`. `_build_observation` is then a pure status→`Observation` mapping. |
| **Ephemeral** — held ~10 min after the last poll, then the `turnId` 404s | `_fetch_digest` names that window explicitly. The digest is a working view of a turn in flight, deliberately not a record. |

The spec is explicit about the division of labour, and it is the reason the digest is not sufficient on its own:

> The session, not the digest, is the durable record.

Four of the digest's five fields (`status`, `output`, `error`, `form`) are inherently per-turn and can come from nowhere else. `files` is the exception: it also exists — cumulatively, authoritatively, and without a 10-minute expiry — on `GET /sessions/{id}` as `Session.files`, tagged `source: "uploaded" | "generated"`. The runner reads only the transient view. See issue #337.

> [!NOTE]
> **Two unrelated things are called "digest."** Orca's *turn digest* is the `TurnDigest` above — turn state, always the local variable `digest` in this module. `Artifact.digest` (in `metis-core`) is a **SHA256 content hash** of a downloaded file, with `hash_algorithm` beside it. Same word, no relationship.

## Identifiers

Orca's identifier space and METIS's never meet, which is what makes a finished run un-auditable against Orca.

| | Orca `fileId` | `Artifact.id` |
|---|---|---|
| Minted by | Orca — `POST /files`, or during a turn for generated files | METIS — `uuid4()` at model construction |
| Addresses | bytes in the key's file library; usable on `POST /chat` and `GET /files/{id}/content` | a row in this run's record; meaningless outside it |
| Lifetime | 30 days from **upload**, not last use | forever, in `record.json` |
| Persisted on `Artifact`? | **no** | yes |

`FixtureLibrary` is a cache over **Orca's** ids — `dict[str, str | FixtureRejected]` maps a fixture *name* to Orca's `fileId` (or to the rejection). It does not import `Artifact`. On the download side, `collect_artifacts` reads `entry["fileId"]`, splices it into a URL, and drops it; the resulting `Artifact` carries `name`, `path`, and a fresh UUID4.

Consequence: `record.json` holds no route from a recorded artefact back to the file on Orca, so "did we capture everything?" cannot be re-checked after a run. That is why #337 treats an `external_id` field on `Artifact` as a prerequisite rather than a nicety.

Two more, both per **run attempt** (a fresh runner is created per attempt):

- **`_session_id`** — write-once. Set from the first submit's response, sent on every later submit, exposed via `get_session_id()`. That value is also the Langfuse `session_id` used to link traces.
- **`_inflight_turn_id`** — the cancel target only, cleared the moment the digest settles. No history of turn ids is kept, consistent with the ~10-minute digest window.

## v1 surface: what the runner uses

| Endpoint | Lane | Used | Where |
|----------|------|:----:|-------|
| `POST /chat` | submit | ✅ | `_submit` |
| `GET /chat/{turnId}` | read | ✅ | `_fetch_digest` |
| `POST /chat/cancel` | read | ✅ | `_cancel_inflight_turn` (read lane, so a throttled client can still stop spend) |
| `POST /files` | submit | ✅ | `FixtureLibrary._upload` |
| `GET /files/{fileId}/content` | read | ✅ | `collect_artifacts` → `download_to` |
| `GET /usage` | read | ✅ | `OrcaApiRunnerFactory._report_usage`, once per experiment |
| `DELETE /sessions/{id}` | read | ⚠️ | `teardown`, **only** when `delete_session_on_teardown` — default `false` |
| `POST /sessions` | submit | ❌ | not needed; the session is minted lazily by `POST /chat` |
| `GET /sessions/{id}` | read | ❌ | **the #337 gap** — the authoritative cumulative file list is never read |
| `GET /files` | read | ❌ | would let a run reconcile against the key's whole library |
| `DELETE /files/{id}` | read | ❌ | fixtures are left to the 30-day expiry |

`TurnFile` fields currently discarded: `contentType` (Orca's *declared* type — stronger than `Artifact.media_type`, which guesses from the filename), `size`, and `spoke` (which sub-agent produced the file).

## Fixture rejection: two mechanisms

Different causes, opposite handling. The distinction is between a property of the **file** and a property of an **id**.

**`FixtureRejected` — rejected at upload, permanent.** `POST /files` answers `413` (too large) or `415` (content type not accepted). Cached two ways: the exception replaces the `fileId` in `FixtureLibrary` (experiment-wide, so the file is never re-sent), and the name enters the runner's `_rejected` set (run-scoped, so the slot stops being offered). The turn is not submitted. Re-uploading could only earn the same rejection, which is why `forget()` deliberately leaves a cached `FixtureRejected` in place.

**`_StaleAttachment` — a `fileId` that has died, recoverable.** `POST /chat` answers `404` on a submit that carried `files`. The file is fine; the id is not (deleted, or 30 days past upload). `forget()` drops the cached id and the fixture **stays offered**, so a later turn re-uploads it and gets a new `fileId`. Cost: one turn.

Orca answers the *same* `404` for a dead `sessionId` and a dead `fileId` — by design, so that an id cannot be probed for existence. The response therefore cannot be interrogated, and `_attribute_submit_404` infers the cause from **what was sent**: a submit carrying `files` is blamed on the files, because that is both the recoverable cause and the one that would otherwise repeat at the same turn of every retry.

Three known rough edges:

- Only `413`/`415` are treated as rejection. The spec also documents `422` on `POST /files`, which reaches `raise_for_status()` and surfaces as a raw `httpx.HTTPStatusError` rather than as "this fixture is bad."
- Nothing is pre-checked locally: size and content type are discovered only by uploading, spending a submit-lane slot to find out.
- `_rejected` is run-scoped while the library cache is experiment-scoped, so a rejected fixture is offered again on the next run. Attaching it costs a turn but no upload (the cached rejection raises immediately).

## Retention

One rule, one number — **30 days** — with three different anchors, none of which the runner tracks proactively:

| Thing | Expires | Runner's response |
|-------|---------|-------------------|
| Sessions | 30 days idle (no turn submitted) | none — `TargetSessionLostError` on the 404, run retried with a fresh session |
| Files | 30 days after **upload**, not last use | reactive: `forget()` on a stale-attachment 404, one wasted turn each time |
| Turn digests | ~10 min after the last poll | `_fetch_digest` reports it as its own error, not a bare status failure |

Because `delete_session_on_teardown` defaults to `false`, sessions are normally **left alive on Orca** after a run, for inspection. That is how #337's evidence was gathered days later.

## Structure

```
orca_api/
├── __init__.py    — OrcaApiRunner + OrcaApiRunnerFactory (turn loop, forms,
│                    submit/poll/observe seams, cancel, usage pre-flight)
├── _config.py     — OrcaApiRunnerConfig: config.yaml + env credentials
├── _transport.py  — v1_request: one resilient /api/v1 call; reason_text
├── _fixtures.py   — FixtureLibrary: experiment-wide name → fileId cache
├── _artifacts.py  — collect_artifacts: digest files → downloaded Artifacts
└── config.yaml    — poll interval, submit rpm, retry window, TLS, teardown
```

Credentials come from the environment (`ORCA_API_URL`, `ORCA_API_KEY`, optional `ORCA_PLATFORM_AI_KEY`); `response_wait_ms` comes from the Task. See the module docstring for what each does.
