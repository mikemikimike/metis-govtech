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

_No v1 changes yet._

### metis-wizard

#### Changed

- **Standardized wizard profile nodes.** Tasks, behaviours, criteria, personas, and scenarios now
  use explicit `name` and `description` fields; criteria use structured Given/When/Then clauses;
  behaviour selection is `measured`; and Product uses `description`.
- **Renamed the "run" count to "trial", to agree with the evaluation glossary.** The glossary
  calls one execution a **trial**. The wizard called the total execution count
  (`Σ scenarios of personas × trials`) a "run count". This was wrong. The count is now a trial
  count on every surface: the domain method `ProductProfile.run_count()` is now `trial_count()`,
  the `application/runs.py` module is now `trials.py` (`format_runs` → `format_trials`), and all
  interview, review-document and hand-authoring copy states "trials". The arithmetic does not
  change. The compiled `experiment.yaml` does not change.
  ([#254](https://github.com/govtech-responsibleai/metis/issues/254))

#### Breaking

- **Profile and saved-session schemas changed.** Profile-owned authorship and generated IDs are
  removed, with authorship and issued-ID history held by the session. Saved sessions use format 7.
  The compiled experiment schema remains unchanged.
- **The scenario card field `runs` is now `trials`, and `SESSION_FORMAT_VERSION` advances from 5
  to 6.** The web bundle mirrors the field, so it is rebuilt. A session file at an older format is
  refused with the existing clear message rather than misread.

### metis-api

_No v1 changes yet._
