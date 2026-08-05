# Changelog

All notable changes to `metis-library` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.2] — 2026-08-05

### Changed

- Removed `retry_counts` field from `TraceMetadata` (no longer populated by extractor)
- `SynthesisFaithfulnessMetric`, `RedelegationOnFailureMetric`, and `GapAcknowledgementMetric` now read subagent output from `test_case.context` instead of `delegation["response"]`
- `BoundedTroubleshootingMetric` computes retry counts directly from `tool_calls` instead of relying on pre-computed `retry_counts` metadata
## [0.1.1] — 2026-08-03

### Added

- `metrics/default.py` — `CriterionGEvalMetric`, a parameterised judge built from a criterion's own text. What a criterion falls back to when nothing in the library matches it

## [0.1.0] — 2026-08-03

### Added

- Shared metric catalog: 53 metric classes across 5 modules (universal, orchestration, analysis, presentation, session)
- Supporting types (`TraceMetadata`, `OrcaChatMetadata`, `ClarificationRequest`) in `metrics._types`
- DeepEval and OpenAI as runtime dependencies
