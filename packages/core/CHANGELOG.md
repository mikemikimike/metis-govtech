# Changelog

All notable changes to `metis-core` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] — Unreleased

### Added

- **`Artifact.external_id`** — the target system's own identifier for a file
  (Orca's `fileId`). Optional and additive, so `RunRecord.schema_version` stays
  `1` and existing `record.json` files load unchanged. Named target-agnostically
  because `metis-core` has zero workspace dependencies. Two payoffs: a collector
  can dedupe by file identity instead of filename, and a completed run becomes
  re-checkable against the target while its session is still in retention
  (issue #337 §0). The field doc states the uniqueness contract the dedupe rests
  on: an id must name exactly one file within its `source`, including across the
  target's own revisions of a file, and a runner that cannot promise that must
  leave the field `None`. Nothing enforces it — uniqueness is a property of the
  set, not of one record — and a target that reused one id across different
  files would make them collapse into a single record and disappear from the run.
- `Artifact` domain model — a single lifecycle-spanning record for any file crossing the persona↔target boundary, inbound (`source="fixture"`) or outbound (`source="target"`), plus the `uri_to_local_path` URI resolver. Relocated from `metis-engine` so all packages share one definition (#307). Fields: `id`, `name`, `source` (default `"target"`), `uri`, `digest`, `hash_algorithm`, `at_turn`, `content_description`, `state_description`, and a derived `media_type` computed field (MIME from `name`/`uri`). The Orca-UI-specific `type` enum was removed and `collected_at_turn` renamed to the direction-neutral `at_turn` (#321).

### Changed

- `Artifact.uri` renamed to `Artifact.path` — stores a POSIX-style path relative to the experiment root instead of an absolute `file://` URI, keeping experiment output directories portable when copied or moved
- `uri_to_local_path(uri)` replaced with `resolve_artifact_path(experiment_root, path)` — plain path-joining against the experiment root, no scheme parsing

---

## [0.4.1] — Unreleased

### Added

- `structlog.processors.format_exc_info` added to the `shared_processors` and `foreign_processors` chains in `configure_logging()` — events carrying `exc_info` (e.g. from `logger.exception(...)` or `logger.error(..., exc_info=True)`) now have their traceback rendered into an `exception` string before the terminal renderer runs. This makes the traceback available to downstream renderers (including `metis-engine`'s per-run file router) and produces a clean `exception` string in the JSON sink instead of a stringified `(type, value, tb)` tuple.

---

## [0.4.0] — 2026-09-02

### Added

- `iso_timestamp()` in `metis.core.logging` — returns the current UTC time as an ISO-8601 string with a `Z` suffix and always-six-digit microseconds (e.g. `2026-09-02T03:27:51.790384Z`), matching the format of `structlog.processors.TimeStamper(fmt="iso")`. Provides a single source of truth for the canonical log-timestamp format so log lines written outside the structlog pipeline stay consistent with structlog-rendered logs.

---

## [0.3.1] — 2026-08-27

### Added

- `py.typed` marker file (PEP 561) — downstream consumers and type checkers can now discover inline type information from this package.

---

## [0.3.0] — 2026-08-11

### Fixed

- `configure_logging()` no longer crashes when third-party libraries (e.g. deepeval) emit stdlib log messages — the `DropEvent`-raising level filter was incorrectly included in `ProcessorFormatter.foreign_pre_chain`, where structlog does not catch it

---

## [0.2.0] — 2026-08-05

### Fixed

- `configure_logging()` now inserts a level-filtering processor into structlog's chain so that `get_logger()` respects the configured verbosity threshold — previously only stdlib (third-party) loggers were gated by the root logger level

---

## [0.1.0] — 2026-08-01

### Added

- `metis.core.logging` module — centralized structured logging via structlog + Rich
  - `get_logger(name?)` — returns a bound structured logger (infers caller module if name omitted)
  - `configure_logging(level?, json?, pretty?, show_caller?)` — one-call process-wide configuration
  - Adaptive output: Rich console rendering for TTY, JSON lines for pipes/CI
  - Config hierarchy: explicit arg > `METIS_LOG_LEVEL` env var > default (WARNING)
  - All output to stderr; stdout stays clean for piped data
- `metis.core.console` module — shared Rich `Console` instance for user-facing output (stdout)
