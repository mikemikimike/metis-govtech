# metis-core

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Core data models and abstractions for the METIS suite. Zero workspace dependencies — only Pydantic v2 + stdlib.

## Package-Specific Notes

- Dependencies: Pydantic v2, structlog, Rich (plus stdlib). Zero workspace dependencies.
- Public logging API: `from metis.core.logging import get_logger, configure_logging`
- Public console API: `from metis.core.console import console`
