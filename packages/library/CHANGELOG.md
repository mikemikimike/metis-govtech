# Changelog

All notable changes to `metis-library` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-08-03

### Added

- `metrics/default.py` — `CriterionGEvalMetric`, a parameterised judge built from a criterion's own text. What a criterion falls back to when nothing in the library matches it

## [0.1.0] — 2026-08-03

### Added

- Shared metric catalog: 53 metric classes across 5 modules (universal, orchestration, analysis, presentation, session)
- Supporting types (`TraceMetadata`, `OrcaChatMetadata`, `ClarificationRequest`) in `metrics._types`
- DeepEval and OpenAI as runtime dependencies
