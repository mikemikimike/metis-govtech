# Changelog

All notable changes to `metis-library` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.3] — 2026-08-05

### Changed

- Restructured metrics from 5 component files to one-file-per-metric layout (56 files). Canonical import path is now `metis.library.metrics.XMetric` (package-level FQNs). Old script-level FQNs (`metis.library.metrics.orchestration.X`) no longer resolve.
- Added multi-dimensional `tags: ClassVar[tuple[str, ...]]` to every metric class for classification (component, granularity, grading method). Enforced at import time via `__init_subclass__`.
- Eliminated `session` pseudo-component — session metrics now carry their real component tag + `"session-level"` granularity tag.
- Extracted shared infrastructure into `_base.py` (`SyncBaseMetric`, `_ContextAwareGEval`, etc.) and `_constants.py`.
- Renamed `task` / `task_id` fields in `TraceMetadata` to `scenario` / `scenario_id` (old names retained as deprecated aliases).

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
