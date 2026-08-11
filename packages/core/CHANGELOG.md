# Changelog

All notable changes to `metis-core` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-08-11

### Added

- _(nothing yet)_

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
