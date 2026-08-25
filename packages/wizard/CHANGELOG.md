# Changelog

All notable changes to `metis-wizard` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-08-25

### Added

- `.env.example` documenting the interview environment: `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
  optional `INTERVIEW_MODEL`, and optional `LANGFUSE_*`.

### Changed

- **Standardised LLM credentials on `OPENAI_API_KEY` / `OPENAI_BASE_URL`** — the
  interview gateway reads the shared `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Set
  `OPENAI_BASE_URL` to the full OpenAI-compatible endpoint.
  ([#153](https://github.com/govtech-responsibleai/metis/issues/153))
- **Renamed `PLATFORM_INTERVIEW_MODEL` to `INTERVIEW_MODEL`** — selects the
  interview model on the shared provider.
- Default interview model is now `gpt-5.6-luna` (was `gemini-3.5-flash-lite`);
  override with `INTERVIEW_MODEL`.

## [0.1.1] — 2026-08-19

### Removed

- `DemoMetric` re-export from the package facade — use `metis.library.metrics` for real metrics.

### Changed

- Workspace-sibling dependency floors now enforced in `pyproject.toml`:
  `metis-core>=0.3.0`, `metis-library>=0.1.4`, `metis-engine>=0.7.0`.
  These only matter when the package is installed from a registry; the local
  workspace override continues to resolve to the checked-out code.

### Known debt closed

- **Library compatibility floor** — enforced.

## [0.1.0] — 2026-08-07

Initial release candidate: an interview that turns a prose product description into a runnable
`experiment.yaml` plus a human-readable `review.md`.

### Added

- **The interview.** Six steps that build a `ProductProfile` — the document the interview
writes — covering product clarification, behaviours, what to measure, acceptance criteria,
personas and scenarios. The interview also writes a separate `review.md` record. It clarifies
the product before asking about its machinery, asks high-breadth
product-manager handover questions before drilling into examples or internal handoffs, and
opens with one package-owned question shared by the CLI and web doors. The product depth field
is `detail`: an evidence-proportional, cumulative handover rather than a compression of rich
sources into another summary. Product fields persist across the conversation, and the document
pane presents short audience labels such as `Public Officers` with initial capitals.
- **A headless door contract.** `render(request) -> response`, with the package composing
interview and domain copy while each door owns its layout and interface chrome. Two doors ship
against it: a Typer/Rich CLI (`metis wizard init`, `metis wizard resume`, `--restart`) and a React web door (`metis wizard serve`) whose
built bundle is committed so the server runs without a Node toolchain. Step metadata
(`title`, `step`, `steps`) rides on the request so either door can show where the interview
is without learning what a behaviour or a persona is.
- **Patch-based editing.** The model edits by patch, and the address is checked against the
step that *owns* it — so an edit works from wherever the user is standing. Provider JSON is
parsed into strict semantic drafts (`extra="forbid"`) before any persisted object exists;
application code then owns ids, authorship, defaults, references and matcher fields. This
closes the bundled-value hole that a recursive post-parse filter could not close. A few things
remain the user's alone — a behaviour's `priority`, a scenario's `num_trials` and `fixtures`.
Edits that invalidate derived work ask in the same turn and leave no staleness flag.
- **Scenario-card field editing.** Trials and fixture references are editable in the CLI and web
interview through typed, request-bound wizard responses, and evaluation work is named in runs
throughout — per-scenario run counts and totals show on the interview, document pane,
hand-authoring form and generated review, and persist through the version-5 session wire
contract. The web door reuses the hand-authoring number and filename-reference controls.
- **Fixture upload.** Scenario fixtures upload through a per-session fixture library in the web
door, accepting CSV, PDF, DOCX, XLSX, PPTX, TXT, JSON, PNG, JPG, GIF, WEBP, Markdown and HTML,
bounded at 20 files and 100 MB total. Identical re-uploads are idempotent; different content
under the same filename is rejected. The web door uses a compact upload-icon Choose file control
with a No file chosen
status, and accepted extensions live in the fixture policy rather than repeating on every task
card. Downloaded experiments bundle `experiment.yaml` and `fixtures/` into an `experiment.zip`
while the visible download action keeps its label.
- **Metric matching by embedding similarity.** Each acceptance criterion is matched against
the metric catalogue by cosine similarity, with `CriterionGEvalMetric` as the fallback when
nothing scores above the threshold or the embedding provider is unreachable — so a dead
provider yields a degraded experiment rather than a stopped interview. A criterion's metric
follows its wording: asking for a different metric rewords the criterion and re-resolves.
- **Compilation.** `ProductProfile` → `experiment.yaml`, emitted as a plain dict and validated
against the engine's own JSON schema before writing, plus `review.md` for the human record.
Runtime metric imports and fixture files are checked separately by the engine input gate.
- **Session persistence.** One JSON file, written atomically, with a format version checked
before model validation so `resume` reports an incompatible session by name. `init` refuses
when a session already exists, naming both ways forward.
- **The agentic primer** (`application/agentic-primer.md`), loaded into the session system
prompt so the interview asks about tools, delegation, memory and recovery. Package-owned model
prompts live in `prompts.yaml`, strictly validated with one complete `ModelPrompt` per model
call; the clarify limit and status copy stay in `interview.yaml`, read fresh through their
separate application owners. The primer stays separate, and primer edits are visible on the next
model call.
- **Package-owned copy** in `interview.yaml`, shared by both doors through the session facade,
so activity wording changes without editing an adapter. Product prose reveals by word in the
document pane — a scaffolded Product section shows Name, Users and Details while the short
summary stays in the header — animating only changed word runs during corrections, preserving
line breaks and capitalisation, and resting the reveal and writing marker under reduced motion.
- **Langfuse tracing.** Model-call tracing for a self-hosted Langfuse v3 server (`v3.153.0`):
prompts, replies, retries, usage and latency. The gateway imports its client from
`langfuse.openai`, the drop-in for the OpenAI client, so every call is traced with no tracing
code in the retry loop; `@observe` groups a call's three attempts into one trace named by the
interview step and carrying the session id. `langfuse` is a base dependency; tracing turns on
only when `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, and stays
a quiet no-op otherwise. Traces are written on a background thread, so tracing does not block or
stop the interview.
- **A hand-authoring door in the web UI.** A form for people who already know what to evaluate;
it collects an id, description, personas and scenarios, creates no session, and downloads a
one-shot `experiment.zip` containing `experiment.yaml` and any uploaded fixtures. Leaving the
form discards it. The package serialises the YAML through its own `to_yaml`, so an interviewed
document and a hand-authored document with the same content are byte-identical inside the
bundle. Stateless `POST /api/experiment.yaml` and `POST /api/experiment.zip` routes validate
the document, and `GET /api/metrics` serves the catalogue for the metric picker. Its field
names are hardcoded in `ManualForm.tsx` — a deliberate, contained exception to the web door's
shape-only discipline, since the labels name the experiment schema's own fields.
- **A composer source menu in the web UI — a facade.** The opening screen offers a composer
source menu with honest Documents, Source Code and Traces trays tucked beneath it, their source
controls disabled. It depicts what connecting a source would require, with a locked submission.
The omissions are specified, not incidental: chosen contents never leave the browser, an address
is never validated or contacted, nothing is retained on leaving, and no result is shown.
Frontend-only — no server route is added.

### Also lands in other packages

- `metis-library` — `metrics/default.py`, the parameterised judge the matcher falls back to.
Without it a degraded experiment would reference an FQN that does not import.

### Known debt

- **Dependency on `metis-engine`.** A deliberate break of the `wizard ↛ engine` invariant in
`docs/architecture.md`, for one reason: the compiler locates the engine's
`experiment.schema.json` relative to the installed module. Nothing is imported from the
engine. It closes when the schema moves to a package both sides may depend on.

  **Separate compatibility note:** metric FQNs are resolved by `importlib` at run time. Files
  produced before the metrics moved to `metis-library` may contain old FQNs and will be rejected
  by the engine; current wizard output uses the library FQNs.
- **Library compatibility floor.** The fallback judge requires `metis-library` 0.1.1 or later;
the package dependency metadata must enforce that floor before release.
- **`api` and `web` are not yet packages.** The two applications stay under `apps/` as `api` and
`web`. They must move to `metis-api` and `metis-web`, so that they are workspace members with the
same layout and naming as the other packages. It closes when both apps are migrated.

