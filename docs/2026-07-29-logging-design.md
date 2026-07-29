# METIS Centralized Logging — Design Document

## 1. Overview

This document specifies the design for a centralized logging module in `packages/core` (`metis-core`). The module provides a single, consistent logging interface for all METIS packages and applications, with output that adapts between human-friendly console rendering and machine-parseable structured logs.

---

## 2. Goals

1. **One import, consistent interface** — All packages use `from metis.core.logging import get_logger` rather than configuring their own handlers.
2. **Structured by default** — Log events carry typed key-value context (e.g., `metric_name`, `trace_id`, `duration_ms`), enabling filtering and aggregation downstream.
3. **Adaptive output** — Pretty, colored console output when running in a terminal (TTY); JSON lines when piped, running in CI, or deployed as a service.
4. **Zero-config for package authors** — Reasonable defaults out of the box; configuration is centralized at the application entry point.
5. **Minimal dependency footprint** — Only `structlog` and `rich` are added to `metis-core`.

---

## 3. Technology Choice

| Library | Role |
|---------|------|
| **structlog** | Structured logging API — bound loggers, processor pipeline, context propagation |
| **rich** | Console renderer — colored output, readable tracebacks, timestamp formatting |

### Why structlog + Rich (not alternatives)

| Alternative | Issue |
|-------------|-------|
| Rich `RichHandler` alone (stdlib `logging`) | No structured context; log calls are format-string based |
| loguru | Replaces stdlib `logging` globally — breaks third-party library integration |
| stdlib `logging` + JSON formatter | Verbose configuration; no bound context; ugly console output |

structlog sits on top of stdlib `logging`, so third-party libraries (httpx, SQLAlchemy, etc.) still route through the same handler chain without conflict.

---

## 4. Architecture

```text
┌────────────────────────────────────────────────────────────────┐
│  Application Entry Point (metis_cli.py / apps/api/main.py)     │
│  ─────────────────────────────────────────────────────────────  │
│  configure_logging(level=..., json=..., ...)                   │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  metis.core.logging                                            │
│  ─────────────────────────────────────────────────────────────  │
│  get_logger(name) → structlog.BoundLogger                      │
│  configure_logging(level, json, pretty, ...)                   │
│                                                                │
│  Processor pipeline:                                           │
│    1. add_log_level                                            │
│    2. add_caller_info (module:lineno)                          │
│    3. TimeStamper (ISO 8601)                                   │
│    4. StackInfoRenderer                                        │
│    5. [if TTY]  → Rich ConsoleRenderer                         │
│       [if pipe] → JSONRenderer                                 │
└────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  stdlib logging (root handler)                                 │
│  Receives structlog output via structlog.stdlib integration    │
└────────────────────────────────────────────────────────────────┘
```

---

## 5. Public API

### `metis.core.logging.get_logger(name: str | None = None) -> structlog.BoundLogger`

Returns a bound logger. If `name` is omitted, infers from the calling module.

```python
from metis.core.logging import get_logger

log = get_logger()
log.info("evaluation_started", trace_id="abc-123", metrics_count=5)
log.warning("metric_skipped", metric="latency_p99", reason="no spans")
```

### `metis.core.logging.configure_logging(...)`

Called once at the application entry point. Configures output format and level for the entire process.

```python
from metis.core.logging import configure_logging

configure_logging(
    level="INFO",  # DEBUG | INFO | WARNING | ERROR
    json=False,  # Force JSON output (overrides TTY detection)
    pretty=True,  # Force pretty output (overrides TTY detection)
    show_caller=True,  # Include module:lineno in output
)
```

If neither `json` nor `pretty` is set, the renderer is chosen automatically:
- **TTY detected** → Rich console renderer (colors, aligned columns)
- **Non-TTY** (pipe, CI, Docker) → JSON lines

---

## 6. Output Examples

### Pretty (TTY)

```
2026-07-29 14:32:01 [INFO]  engine.evaluator  evaluation_started  trace_id=abc-123 metrics_count=5
2026-07-29 14:32:01 [WARN]  engine.evaluator  metric_skipped      metric=latency_p99 reason="no spans"
2026-07-29 14:32:02 [INFO]  engine.evaluator  evaluation_complete  duration_ms=1042 passed=4 failed=1
```

### JSON (non-TTY / CI)

```json
{"timestamp":"2026-07-29T14:32:01.123Z","level":"info","logger":"engine.evaluator","event":"evaluation_started","trace_id":"abc-123","metrics_count":5}
{"timestamp":"2026-07-29T14:32:01.456Z","level":"warning","logger":"engine.evaluator","event":"metric_skipped","metric":"latency_p99","reason":"no spans"}
```

---

## 7. Integration with Typer/Rich CLI Output

Logging and CLI user-facing output serve different purposes:

| Concern | Mechanism |
|---------|-----------|
| **User-facing output** (tables, progress, results) | `rich.console.Console` / Typer's built-in Rich integration |
| **Operational logging** (debug, diagnostics, audit) | `metis.core.logging` (structlog) |

These should not be conflated. CLI commands use Rich directly for formatted output (tables, panels, progress bars) and use the logger for operational events that a developer or CI system would want to capture.

The logger's Rich renderer writes to `stderr` by default, keeping `stdout` clean for structured CLI output that may be piped.

---

## 8. Configuration Hierarchy

Log level can be set via (highest precedence first):

1. `configure_logging(level=...)` call in application code
2. `METIS_LOG_LEVEL` environment variable
3. `--verbose` / `-v` flag on CLI commands (maps to DEBUG)
4. Default: `INFO`

---

## 9. Dependency Changes

### `packages/core/pyproject.toml`

```toml
[project]
dependencies = [
    "structlog>=24.0.0",
    "rich>=13.0.0",
]
```

This is the only dependency change. All other packages inherit these transitively via their existing `metis-core` dependency.

---

## 10. File Layout

```text
packages/core/src/metis/core/
├── __init__.py
├── logging.py              # Public API: get_logger, configure_logging
└── ...existing modules...
```

---

## 11. Usage in Downstream Packages

```python
# packages/engine/src/metis/engine/evaluator.py
from metis.core.logging import get_logger

log = get_logger()


class Evaluator:
    def run(self, trace: Trace) -> EvaluationReport:
        log.info(
            "evaluation_started", trace_id=trace.id, metrics_count=len(self.metrics)
        )
        ...
        log.info("evaluation_complete", duration_ms=elapsed, passed=p, failed=f)
```

```python
# metis_cli.py (entry point)
from metis.core.logging import configure_logging


def main():
    configure_logging(level="INFO")
    app()
```

---

## 12. Design Decisions

| Decision | Rationale |
|----------|-----------|
| structlog over stdlib logging alone | Bound context (`log.bind(trace_id=...)`) avoids repetitive key-value threading through function signatures |
| Logger in `core`, not a separate `packages/logging` | Logging is infrastructure, not a domain concept; it belongs with other shared infrastructure in core |
| Rich as a core dependency | Already used by engine/wizard/insights for CLI output; centralizing it avoids version conflicts |
| stderr for log output | Keeps stdout available for piped structured data (JSON results, reports) |
| No log file rotation built-in | Deployment concerns (logrotate, Docker log drivers) handle this at the infrastructure layer |

---

## 13. Future Considerations

- **OpenTelemetry integration** — When `apps/api` and `apps/worker` are implemented (Phase 4), the processor pipeline can be extended with an OTLP log exporter for centralized observability.
- **Correlation IDs** — `structlog.contextvars` can propagate `trace_id` / `request_id` across async boundaries without explicit passing.
- **Log sampling** — For high-throughput production workloads, a sampling processor can be added to the pipeline to reduce volume at DEBUG level.
