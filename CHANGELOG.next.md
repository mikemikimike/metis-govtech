# Changelog — v1.0 pre-release (`next`)

> **Temporary, `next`-only file.** For the whole v1 pre-release phase, all v1
> changelog entries live here in one place instead of in each package's
> `CHANGELOG.md`. This avoids churning five separate changelog files (and the
> merge conflicts that come with them) while the API is still unstable.
>
> **Do not add v1 entries to the per-package `CHANGELOG.md` files while on
> `next`.** Those files keep their v0.x history untouched. At graduation, the
> entries below are split out — each package's section is folded into its own
> `CHANGELOG.md` under a `## [1.0.0]` heading — and this file is deleted. See
> [docs/version-maintenance.md](docs/version-maintenance.md#graduating-next-to-main)
> and [CONTRIBUTING.md](CONTRIBUTING.md#target-branch-next-vs-v0x).
>
> v0.x bugfixes cherry-picked into `next` are already recorded in the
> per-package changelogs on `v0.x`; do not duplicate them here.

The format is based on [Keep a Changelog](https://keepachangelog.com/). All
packages sit at a static `1.0.0a1` for the entire pre-release phase (see
[issue #221](https://github.com/govtech-responsibleai/metis/issues/221)); the
single `[1.0.0a1] — Unreleased` heading below is not bumped per change.

## [1.0.0a1] — Unreleased

### metis-core

_No v1 changes yet._

### metis-library

_No v1 changes yet._

### metis-engine

#### Changed

- Report generation now reads named Behaviours, measured state, and structured Criteria from
  normalized `profile.yaml` files.

### metis-wizard

#### Added

- Interview opening now offers End user, Engineer, Compliance, and Security perspectives. The
  selected perspective travels in client-held Interview context and shapes only Clarify and
  Behaviours prompts; labels and questions are package configuration.

- **JSON schema for `profile.yaml`.** `packages/wizard/schemas/profile.schema.json` is generated
  from the `ProductProfile` model and CI-guarded by `make check-schema`, giving schema-aware
  editors autocomplete and validation for hand-authored profiles. `profile.yaml` now carries a
  `schema_version` field (defaulted to `1`; an unreadable version is refused, not misread).
- **A stateless Interview lifecycle interface.** `handle_interview` accepts a start, turn, or end
  request against client-held state and returns the next state with a derived stage, or a typed
  failure with a stable error code and the caller's state unchanged. `compile_profile` turns a
  finished Profile into the `profile.yaml` and `experiment.yaml` strings in memory, and
  `package_specification` returns a complete in-memory `experiment.zip` with validated fixture bytes
  read from bounded streams.
  `derive_stage` computes progress from the Profile and two confirmation flags, so no stage is stored.
  The Interview state travels whole in each request and is never written to a file.
- **Standardized wizard profile nodes.** Tasks, behaviours, criteria, personas, and scenarios use
  explicit `name` and `description` fields; criteria use structured Given/When/Then clauses;
  behaviour selection is `measured`; and Product uses `description`.

#### Changed

- **Renamed the wizard control model from Session to Interview.** The runtime object and its state
  carry the Interview name: `Interview`, `InterviewState`, and `InterviewStep`.
- **Behaviour review and measurement are now one stage.** Every wizard-created Behaviour starts
  selected for measurement. One screen shows each Behaviour with its measurement control, and the
  user clears any Behaviour they do not want to measure. Continue needs at least one measured
  Behaviour and writes Criteria for that final subset only.
- **Renamed the "run" count to "trial", to agree with the evaluation glossary.** The glossary
  calls one execution a **trial**. The wizard called the total execution count
  (`Σ scenarios of personas × trials`) a "run count". This was wrong. The count is now a trial
  count on every surface: the domain method `ProductProfile.run_count()` is now `trial_count()`,
  the `application/runs.py` module is now `trials.py` (`format_runs` → `format_trials`), and all
  interview, review-document and hand-authoring copy states "trials". The arithmetic does not
  change. The compiled `experiment.yaml` does not change.
  ([#254](https://github.com/govtech-responsibleai/metis/issues/254))
- **Moved the wizard tests into the root `tests/` tree.** Unit tests now live under
  `tests/unit/wizard/`, integration tests under `tests/integration/wizard/`, and shared fixtures
  under `tests/fixtures/wizard/`, matching the documented repository convention. Test behaviour is
  unchanged.

#### Removed

- **The wizard no longer serves its own HTTP door or frontend.** The stateful web server, the
  per-interview store, the `metis-wizard serve` command, the committed React bundle, and the wizard
  FastAPI, Uvicorn, and multipart dependencies are gone. A web client now talks to the new
  `metis-api` service over HTTP. The interview itself — models, driver, screens, compiler — does not
  change.
- **`InterviewStep.PRIORITISE` is removed**, with its screen, transitions, and status. The interview
  now shows five steps.

#### Breaking

- **Interview state is client-held and file-free.** The server-owned session file, its format
  version, and the `/api/interviews` routes are gone. A caller holds the returned state and sends it
  back on the next operation. `InterviewState` now carries only the Profile, the two confirmation
  flags, a bounded clarification history, and one pending request; the resolved-request
  transcript, stored step, and file methods are removed. Old session files are not migrated — start a
  new interview.

### metis-api

#### Added

- **New package: a stateless HTTP door over the wizard.** `POST /api/v1/wizard/interview/start`
  creates state from the raw product description, `POST /api/v1/wizard/interview/turn` applies one
  typed response, and `POST /api/v1/wizard/interview/end` performs best-effort completion.
  `POST /api/v1/wizard/compile` compiles a Profile; `/health` reports liveness. The service holds
  no Interview state — each turn or end request carries the whole client-held state — so any instance
  can serve any operation. Typed wizard results map to 200, 400, 422, 503, and 500, all in one error
  shape. Runs as
  the `metis-api` executable and ships with a `Dockerfile` built from the repository root.
- **Metric catalogue route.** `GET /api/v1/metrics` returns installed metric summaries through the
  public wizard facade without user state or filesystem writes.
- **Wizard client configuration route.** `GET /api/v1/wizard/config` returns the package-owned
  Interview busy message, so HTTP clients do not copy wizard presentation text.
- **Specification package route.** `POST /api/v1/wizard/package` accepts a Profile and request-scoped
  fixture files and returns one `experiment.zip` containing `profile.yaml`, `experiment.yaml`, and
  an explicit `fixtures/` directory. The API retains no uploaded bytes.
- **Shared model environment names.** The API reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
  `INTERVIEW_MODEL`, matching the wizard and engine provider configuration, and can load one root
  `.env` for local development.

#### Changed

- The wizard configuration payload now includes the opening question and the four perspective
  definitions. The Interview start request accepts an optional perspective and records it in the
  returned client-held context.
- **Moved the API tests into the root `tests/` tree.** Door tests now live under `tests/unit/api/`
  and end-to-end tests under `tests/integration/api/`, sharing the wizard's offline fixtures from
  `tests/fixtures/wizard/` directly instead of through a `sys.path` insertion. Test behaviour is
  unchanged.

### metis-web

#### Added

- **Standalone browser client.** The wizard UI now lives in `apps/web`, uses generated OpenAPI
  types and the stateless `apps/api` lifecycle routes, and stores local Interviews, fixture Blobs,
  and their display transcript in IndexedDB. The old wizard-owned web project and Python static
  output are retired.
- **Metric details.** The Profile pane can request the optional metric catalogue once per page load
  through `GET /api/v1/metrics`; the rest of the Interview remains usable when that route fails.

#### Changed

- The opening screen now reads its question and perspective choices from the API configuration,
  asks who the evaluation is for with hover help, and sends the selected perspective on start.
- **Clear completion and output actions.** The conversation composer now fills its column. Early
  finish and download use one action in the Profile footer. A normal final Continue stores the
  completed Interview and reports that the specification is ready without an automatic compile or
  download. The output action downloads one portable `experiment.zip` with the local fixture files.
  Review actions are disabled when their required Profile content is incomplete.

#### Deferred

- Direct authoring, source analysis, hosted state, authentication, and evaluation execution remain
  outside this change.
