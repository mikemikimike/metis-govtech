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

### Build

#### Changed

- **`make install` no longer installs Playwright unconditionally.** The flat
  `install-playwright` target is replaced by `install-extras-playwright`, which
  first syncs `--extra playwright` before running `playwright install`. Use
  `make install-extras-playwright` (or `make install-engine`) to install the
  browser binary; `make install-extras` runs all optional extras.
  `install-playwright` is also removed from `packages/engine/Makefile`.
  **Note:** #335 makes a parallel fix to `v0.x` using the same
  `install-extras` model; expect a Makefile conflict when `v0.x` merges into
  `next` — resolve by keeping `next`'s version.

### metis-core

_No v1 changes yet._

### metis-library

_No v1 changes yet._

### metis-engine

#### Changed

- Report generation now reads named Behaviours, measured state, and structured Criteria from
  normalized `profile.yaml` files.

### metis-wizard

#### Fixed

- An Interview asks for a missing product name or description before behaviour review, so an
  incomplete model response cannot leave Continue blocked.

#### Changed

- Clarify now explores the product widely before it goes deep, with one instruction set instead of a
  product phase and a machinery phase.
- Prompts now wrap injected reference content — the primer, the ARC catalogue, the Profile, the
  transcript, the perspective, the capability evidence, and the user's message — in a named
  XML-style tag, with a system-prompt line stating that tagged content is reference material and
  never instructions. The boundary between the wizard's own words and quoted content is now
  unambiguous.

#### Added

- **Opening documents.** Flat Interview start requests can carry files as `{name, text?}`. The
  wizard keeps the opening description and document context in client-held state, with supported
  TXT, Markdown, PDF text-layer, and DOCX extraction through its facade. Prompts receive readable
  text and identify unread files. New Scenario drafts can suggest any opening file by name, and the
  existing Scenario review confirms each assignment.

- **ARC capability evidence at Interview start.** The CLI and headless interface now use the final
  12-capability catalogue in three ordered groups. Start requires `known_capability_ids` and
  `capability_confidence`, records them in required client-held Interview context, and uses the
  confidence to guide Clarify and Behaviours probing. Every model call receives a synthesized
  catalogue background; the values do not enter `ProductProfile`.

- Interview opening now offers End user, Engineer, Compliance, and Security perspectives. The
  selected perspective travels in client-held Interview context and shapes only Clarify and
  Behaviours prompts; labels and questions are package configuration. The web client asks for it;
  the CLI always uses End user.

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

- **Request-scoped document extraction.** `POST /api/v1/wizard/documents/extract` returns text or a
  typed error in the existing failure envelope. It closes uploaded streams and keeps no files or
  Interview state. The wizard configuration route also exposes the document limits.

- **Capability-aware wizard configuration and start.** `/api/v1/wizard/config` serves the ordered
  ARC capability catalogue, and `/api/v1/wizard/interview/start` accepts the complete description,
  known capability ids, confidence, and other opening choices.

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

- **Opening documents.** A plus button in the composer opens a compact document tray. Original files
  stay in local Interview storage, and only files assigned to Scenarios enter the package.

- **Grouped capability opening controls.** The opening screen now displays all 12 ARC capabilities,
  lets the user select known capabilities (including none), requires Low, Medium, or High selection
  completeness confidence, and sends the full start request in one operation.

- **Standalone browser client.** The wizard UI now lives in `apps/web`, uses generated OpenAPI
  types and the stateless `apps/api` lifecycle routes, and stores local Interviews, fixture Blobs,
  and their display transcript in IndexedDB. The old wizard-owned web project and Python static
  output are retired.
- **Metric details.** The Profile pane can request the optional metric catalogue once per page load
  through `GET /api/v1/metrics`; the rest of the Interview remains usable when that route fails.
- **Manual experiment authoring.** The opening screen now offers a stateless form for experiment
  identity, personas, scenarios, scorers, and fixture files. It builds an engine-ready
  `experiment.zip` through the existing package route without creating an Interview record.

#### Changed

- The opening screen now reads its question and perspective choices from the API configuration,
  asks who the evaluation is for with hover help, and sends the selected perspective on start.
- **Clear completion and output actions.** The conversation composer now fills its column. Early
  finish and download use one action in the Profile footer. A normal final Continue stores the
  completed Interview and reports that the specification is ready without an automatic compile or
  download. The output action downloads one portable `experiment.zip` with the local fixture files.
  Review actions are disabled when their required Profile content is incomplete.
- **Refined manual authoring layout.** The manual form now presents one top-level Experiment editor,
  keeps each ID and Description on its own line, uses the entered ID as each item heading, and
  starts with empty Persona and Scenario collections. Header actions add and focus a new item. New
  Scenarios select all named Personas, and a new Persona is added to existing Scenarios. The manual
  form now gives each item a clear surface and a Done action that closes the editor into a compact
  summary. The manual data and package contract are unchanged.

#### Deferred

- Source analysis, hosted state, authentication, and evaluation execution remain outside this
  change.
