# Changelog

All notable changes to `metis-wizard` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-08-03

Initial release: an interview that turns a prose product description into a runnable
`experiment.yaml` plus a human-readable `review.md`.

### Added

- **The interview.** Six steps that build a `ProductProfile` — the document the interview
  writes — covering the product, its architecture, personas, epics and behaviours, tasks, and
  a final review. The always-on universal epic is held in the same `epics` list rather than a
  second one, so nothing downstream has to know it is special.
- **A headless door contract.** `render(request) -> response`, with the package composing
  every string a door displays. Two doors ship against it: a Typer/Rich CLI (`metis wizard
  init`, `metis wizard resume`, `--restart`) and a React web door (`metis wizard serve`) whose
  built bundle is committed so the server runs without a Node toolchain. Step metadata
  (`title`, `step`, `steps`) rides on the request so either door can show where the interview
  is without learning what a behaviour or a persona is.
- **Patch-based editing.** What the model may write is checked against the step that *owns*
  the address, so an edit works from wherever the user is standing. Two addresses are
  unwritable by anyone — a behaviour's `priority`, and anything under `EP-UNI`. Edits that
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

### Also lands in other packages

- `metis-library` — `universal_behaviours.yaml` and its loader: the always-on epic,
  hand-authored, with every criterion already bound to a metric.
- `metis-library` — `metrics/default.py`, the parameterised judge the matcher falls back to.
  Without it a degraded experiment would reference an FQN that does not import.

### Known debt

- **Dependency on `metis-engine`.** A deliberate break of the `wizard ↛ engine` invariant in
  the root `CLAUDE.md`, for one reason: the compiler locates the engine's
  `experiment.schema.json` relative to the installed module. Nothing is imported from the
  engine. It closes when the schema moves to a package both sides may depend on.

  **Consequence while it stands:** metric FQNs are resolved by `importlib` at run time, so any
  `experiment.yaml` compiled before the metrics move stops loading after it, as does the
  universal behaviours YAML. Not silent — the engine raises on an unimportable FQN — but every
  file produced in the interim needs a find-and-replace.
