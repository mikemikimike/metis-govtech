# Changelog

All notable changes to `metis-library` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).


## [0.11.0] — Unreleased

### Changed

- **`SlideVisualQualityMetric` renders slides itself, no engine-supplied images (issue #381, rescoped from #380)** — the metric now locates the most recently delivered `source="target"` artifact whose name ends in `.pdf` (turn-scoped; latest `at_turn` wins) and rasterizes each page to PNG via the new `pymupdf` dependency, instead of reading pre-rendered paths from `metadata["slide_image_refs"]`. New helpers in `_extraction.py`: `_latest_target_pdf_path`, `render_pdf_slides`, `get_deck_slide_images`. A target deck delivered only as `.pptx`, with no accompanying `.pdf`, has no local conversion path — METIS does not shell out to a system-level renderer such as LibreOffice for this — so the metric skips it, same as when no deck artifact exists at all. `pymupdf` is AGPL-3.0/commercial dual-licensed (Artifex); flagged for sign-off as a new runtime dependency of `metis-library`.

### Removed

- **`slide_image_refs` is gone (issue #382).** Now that `SlideVisualQualityMetric` renders slides itself from `test_case.metadata["artifacts"]` (#381), the field had no remaining reader. `get_slide_image_refs()` (`_extraction.py`) and the `slide_image_refs` key on both `LlmTestCaseMetadata` and `ConversationalTestCaseMetadata` (`_types.py`) are deleted.

### Fixed

- `ReproducibleAnalysisScriptMetric` accepts existing script files in any directory, including Orca's `artifacts/` directory. Absolute paths and paths relative to the current working directory are supported. Missing files and directories fail the file check; descriptive names and response references are still required (#366).

## [0.10.0] — 2026-09-23

### Changed

- **Artifact metrics read the unified `metis.core.Artifact` (issue #307)** — the library's local `ArtifactSummary` TypedDict is removed; `metrics._extraction.get_artifacts` now validates each `metadata["artifacts"]` dict into a `metis.core.Artifact` (skipping malformed/legacy dicts) and returns `list[Artifact]`. `_artifact_paths` and the output-verification, reproducible-analysis-script, and report-format-and-length metrics take the on-disk location from `Artifact.path` and the filename from `Artifact.name`, replacing the old `filename` key. Lockstep with the engine's artifact unification; requires `metis-core` ≥ 0.5.0. Old-shape (`{filename, path}`) metadata is no longer read (forward-only).

---

## [0.9.0] — 2026-09-03

### Changed

- Default judge model (`JUDGE_MODEL`) is now `gemini-3.5-flash-lite` (was `gpt-5.6-luna`);
override with `JUDGE_MODEL`. DeepEval's `GPTModel` always sends a `temperature` field,
which `gpt-5.6-luna` rejects on Bedrock with a 400, so every GEval-graded metric errored.
`gemini-3.5-flash-lite` tolerates the field.
([#264](https://github.com/govtech-responsibleai/metis/issues/264))

### Removed

### Added

---

## [0.8.1] — 2026-08-27

### Changed

- **Typing modernization** — replaced `typing_extensions.TypedDict` with `typing.TypedDict`; added return type annotations to all `_get_geval`/`_get_metric` methods (55 total); added `-> None` to all metric `__init__` methods; annotated `*args: Any`/`**kwargs: Any` on measure method overrides; fixed `_build_context_block(metadata: dict)` → `dict[str, Any]`.
- Moved annotation-only imports into `TYPE_CHECKING` blocks (ruff TCH compliance).

### Removed

- `typing-extensions` dependency — no longer needed on Python 3.11+.

### Added

- `py.typed` marker file (PEP 561).

---

## [0.8.0] — 2026-08-26

### Removed (BREAKING)

- **`TraceMetadata` alias removed** — `metis.library.metrics` and `metis.library.metrics._types` no longer export `TraceMetadata`. Use `LlmTestCaseMetadata` directly. The engine's extractor module no longer re-exports this alias either (pruned in engine v0.11.0).



## [0.7.0] — 2026-08-26

### Added



### Changed

- **Exported metadata TypedDicts from `metis.library.metrics`** — `ConversationalTestCaseMetadata`, `LlmTestCaseMetadata`, `OrcaChatMetadata`, and the deprecated `TraceMetadata` alias are now importable from the public `metis.library.metrics` path instead of only the private `_types` module.

### Fixed



## [0.6.0] — 2026-08-26

### Added

- `ConversationalTestCaseMetadata` TypedDict — typed contract for `ConversationalTestCase.metadata` fields consumed by session-level metrics (`session_id`, `trace_ids`, `stop_reason`, `cancellation_available`, `slide_image_refs`, plus `NotRequired` fields `scenario`, `persona`, `expected_minimum_steps`).

### Changed

- **Renamed `TraceMetadata` → `LlmTestCaseMetadata`** — the TypedDict is now named after the test case type it annotates. `TraceMetadata` remains importable as a deprecated alias.
- All 38 metric modules updated to import and cast `LlmTestCaseMetadata` instead of `TraceMetadata`.
- `SessionStepEfficiencyMetric` now uses a typed `cast(ConversationalTestCaseMetadata, ...)` for type-safe metadata access.

### Fixed

## [0.5.0] — 2026-08-25

### Changed

- **Standardised LLM-judge credentials on `OPENAI_API_KEY` / `OPENAI_BASE_URL`** —
`_get_judge_model()` now reads the shared `OPENAI_API_KEY` and `OPENAI_BASE_URL` instead of
`JUDGE_API_KEY` and `JUDGE_BASE_URL`. The judge model stays selectable via `JUDGE_MODEL`.
([#153](https://github.com/govtech-responsibleai/metis/issues/153))
- Default judge model is now `gemini-3.5-flash-lite` (was `gpt-4.1-mini`);
override with `JUDGE_MODEL`.

## [0.4.0] — 2026-08-20

### Changed (BREAKING)

- Renamed `DataIngestionAccuracyMetric` to `FirstLookInspectionCleaningMetric` (M-DA-20). No compatibility alias — update imports.
- Renamed `OpenEndedScopeQualityMetric` to `ProceedWithDefaultsMetric` (M-DA-28). No compatibility alias — update imports.

### Added

- New analysis metrics: `ReproducibleAnalysisScriptMetric` (M-DA-23), `DataAnalysisRecoveryMetric` (M-DA-26), `OutputVerificationMetric` (M-DA-27), `ChartTechnicalCorrectnessMetric`, and `ReportFormatAndLengthMetric`.
- New universal metrics: `CorrectionMetric` (M-UNI-19), `AbandonmentMetric` (M-UNI-20), `CancellationMetric` (M-UNI-21), `HarmfulContentRefusalMetric`, and `DirectModeEscapeMetric`.
- New presentation metrics: `SlideProtocolOrderingMetric` (M-SM-1), `BriefGoalDetailsMetric` (M-SM-2), `BriefGoalNonPrescriptiveMetric` (M-SM-6), `BriefSourceFaithfulnessMetric` (M-SM-7), `BriefCompletenessMetric` (M-SM-8), `BriefAudienceAppropriatenessMetric` (M-SM-9), `DeckBriefCoverageMetric` (M-SM-11), `SlideVisualQualityMetric` (M-SM-13), `SlideTitleQualityMetric` (M-SM-15), and `DeckAudienceCalibrationMetric` (M-SM-19).
- `SlideVisualQualityMetric` (M-SM-13) grades rendered slide images. It builds a multimodal judge case from `slide_image_refs`.
- Shared extraction helpers in `_extraction.py`: portable PPTX slide-text extraction (stdlib ZIP/XML, no presentation library), deck-slide access, and session-turn normalization.
- Three observable-execution fields on the `TraceMetadata` TypedDict: `stop_reason`, `cancellation_available`, and `slide_image_refs`. The engine supplies these values.

### Changed

- `CrossSlideLogicalFlowMetric` (M-SM-14), `SlideSpecComplianceMetric` (M-SM-10), and `DeckSourceFaithfulnessMetric` (M-SM-20) now read deck content through the PPTX artifact when trace observations do not contain deck properties.
- **Deprecated `task`/`task_id` aliases** from `TraceMetadata` and the fallback read path in `_build_context_block`; callers must use `scenario`/`scenario_id` exclusively

## [0.3.0] — 2026-08-20

### Added

- `**MetisSessionMetric` base class** (`_base.py`) — new base for session-level metrics that extends `BaseConversationalMetric`; enforces `tags` ClassVar like `MetisTurnMetric`; session metrics now have an explicit, documented base class rather than inheriting directly from DeepEval's `BaseConversationalMetric`
- `**mark_skipped()` helper** (`_base.py`) — standalone function to mark a metric as skipped with a reason; sets `skipped=True`, `score=1.0`, `success=True` so DeepEval assertions pass while reporters exclude the metric from pass-rate aggregation

### Changed

- **BREAKING: `SyncBaseMetric` renamed to `MetisTurnMetric`** — all per-turn metric classes now inherit from `MetisTurnMetric` instead of `SyncBaseMetric`; the class is no longer "sync-only" (supports both sync `measure()` and async `a_measure()` dispatch based on `async_mode`)
- `**_absorb_geval_cost()` replaced by `_accrue_cost()`** — simplified to a single `cost: float | None` parameter; no longer manually copies `input_tokens`/`output_tokens` (DeepEval's framework handles token tracking)
- Removed hardcoded `async_mode = False` and `skipped: bool = False` from the base class; `async_mode` now defaults to DeepEval's default (True), and skip state is managed via `mark_skipped()`

### Removed

## [0.2.0] — 2026-08-19

### Added

- LLM-judge model (shared by all GEval-based metrics) is now configurable via environment variables in `_get_judge_model()`: `JUDGE_MODEL` (default `gpt-4.1-mini`), `JUDGE_API_KEY` (falls back to `OPENAI_API_KEY`), and `JUDGE_BASE_URL` (unset → default OpenAI endpoint). Lets the judge point at any OpenAI-wire-compatible provider (e.g. Platform AI) without code changes.

### Changed

### Removed

## [0.1.4] — 2026-08-17

### Changed

- Added concrete TypedDicts (`ArtifactSummary`, `ObservationSummary`, `ToolCallSummary`, `ChatMessage`, `Delegation`, `PriorTurn`) describing the serialized shapes in `TraceMetadata`. Fields narrowed from bare `list`/`dict` to parameterized types for static type-checking and IDE autocomplete.

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

