# Changelog

All notable changes to `metis-wizard` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-08-03

Initial release: an interview that turns a prose product description into a runnable
`experiment.yaml` plus a human-readable `review.md`.

### Added

- **The interview.** Six steps that build a `ProductProfile` — the document the interview
  writes — covering the product, its architecture, personas, epics and behaviours, tasks, and
  a final review.
- **A headless door contract.** `render(request) -> response`, with the package composing
  every string a door displays. Two doors ship against it: a Typer/Rich CLI (`metis wizard
  init`, `metis wizard resume`, `--restart`) and a React web door (`metis wizard serve`) whose
  built bundle is committed so the server runs without a Node toolchain. Step metadata
  (`title`, `step`, `steps`) rides on the request so either door can show where the interview
  is without learning what a behaviour or a persona is.
- **Patch-based editing.** What the model may write is checked against the step that *owns*
  the address, so an edit works from wherever the user is standing. One address is unwritable
  by the model at any step — a behaviour's `priority`, the user's own decision. Edits that
  invalidate derived work ask in the same turn and leave no staleness flag.
- **Metric matching by embedding similarity.** Each acceptance criterion is matched against
  the metric catalogue by cosine similarity, with `CriterionGEvalMetric` as the fallback when
  nothing scores above the threshold or the embedding provider is unreachable — so a dead
  provider yields a degraded experiment rather than a stopped interview. A criterion's metric
  follows its wording: asking for a different metric rewords the criterion and re-resolves.
- **Compilation.** `ProductProfile` → `experiment.yaml`, emitted as a plain dict and validated
  against the engine's own JSON schema so the wizard never writes a file the engine refuses to
  load, plus `review.md` for the human record.
- **Session persistence.** One JSON file, written atomically, with a format version checked
  before parsing so `resume` fails by name rather than by traceback. `init` refuses when a
  session already exists, naming both ways forward.
- **The agentic primer** (`application/agentic-primer.md`), loaded into the session system
  prompt so the interview asks about tools, delegation, memory and recovery.
- **Package-owned copy** in `statuses.yaml`, shared by both doors through the session facade,
  so activity wording changes without editing an adapter.
- **A hand-authoring door in the web UI.** A form that writes `experiment.yaml` directly — id,
  description, personas, and tasks — for people who already know what to evaluate. It creates
  no session and stores nothing: the document is compiled and downloaded in one shot, and
  leaving the form discards it. Serialised through the interview's own `to_yaml`, so a
  hand-authored file and an interviewed one of the same content are byte-identical; a stateless
  `POST /api/experiment.yaml` validates against the engine schema, and `GET /api/metrics` serves
  the catalogue for the metric picker. Its field names are hardcoded in `ManualForm.tsx` — a
  deliberate, contained exception to the web door's shape-only discipline, since the labels name
  the experiment schema's own fields.
- **A "connect a repo" screen in the web UI — a facade.** A screen depicting what connecting a
  repository would require, with a locked submission. The omissions are specified, not incidental:
  the chosen archive's contents never leave the browser, the address is never validated or
  contacted, nothing is retained on leaving, and no result is shown. Frontend-only — no server
  route is added.

### Also lands in other packages

- `metis-library` — `metrics/default.py`, the parameterised judge the matcher falls back to.
  Without it a degraded experiment would reference an FQN that does not import.

### Known debt

- **Dependency on `metis-engine`.** A deliberate break of the `wizard ↛ engine` invariant in
  the root `CLAUDE.md`, for one reason: the compiler locates the engine's
  `experiment.schema.json` relative to the installed module. Nothing is imported from the
  engine. It closes when the schema moves to a package both sides may depend on.

  **Consequence while it stands:** metric FQNs are resolved by `importlib` at run time, so any
  `experiment.yaml` compiled before the metrics move stops loading after it. Not silent — the
  engine raises on an unimportable FQN — but every file produced in the interim needs a
  find-and-replace.
