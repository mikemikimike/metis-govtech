"""Catalog invariants for the CSV-aligned metric coverage change.

Guards the public export surface: the new metrics are importable, the two
renamed metrics are gone (no compatibility aliases), and every metric class
carries a well-formed ``tags`` ClassVar.
"""

import inspect

import metis.library.metrics as catalog

# Metrics introduced by the align-csv-metric-coverage change.
NEW_METRICS = [
    "FirstLookInspectionCleaningMetric",  # M-DA-20 (renamed)
    "ProceedWithDefaultsMetric",  # M-DA-28 (renamed)
    "ChartTechnicalCorrectnessMetric",
    "ReportFormatAndLengthMetric",
    "ReproducibleAnalysisScriptMetric",  # M-DA-23
    "DataAnalysisRecoveryMetric",  # M-DA-26
    "OutputVerificationMetric",  # M-DA-27
    "HarmfulContentRefusalMetric",
    "CorrectionMetric",  # M-UNI-19
    "AbandonmentMetric",  # M-UNI-20
    "CancellationMetric",  # M-UNI-21
    "DirectModeEscapeMetric",
    "SlideProtocolOrderingMetric",  # M-SM-1
    "BriefGoalDetailsMetric",  # M-SM-2
    "BriefGoalNonPrescriptiveMetric",  # M-SM-6
    "BriefSourceFaithfulnessMetric",  # M-SM-7
    "BriefCompletenessMetric",  # M-SM-8
    "BriefAudienceAppropriatenessMetric",  # M-SM-9
    "DeckBriefCoverageMetric",  # M-SM-11
    "SlideVisualQualityMetric",  # M-SM-13
    "SlideTitleQualityMetric",  # M-SM-15
    "DeckAudienceCalibrationMetric",  # M-SM-19
]

# Removed by the two BREAKING renames — must not resolve, even as aliases.
REMOVED_METRICS = [
    "DataIngestionAccuracyMetric",  # -> FirstLookInspectionCleaningMetric
    "OpenEndedScopeQualityMetric",  # -> ProceedWithDefaultsMetric
]

_VALID_CATEGORY = {"analysis", "presentation", "universal", "orchestration"}
_VALID_LEVEL = {"per-turn", "session-level"}
_VALID_GRADING = {"code-graded", "judge-graded"}


def test_new_metrics_are_exported():
    for name in NEW_METRICS:
        assert hasattr(catalog, name), f"missing new metric export: {name}"


def test_renamed_metrics_have_no_alias():
    for name in REMOVED_METRICS:
        assert not hasattr(catalog, name), f"stale metric still exported: {name}"


def test_every_metric_has_wellformed_tags():
    for name in NEW_METRICS:
        cls = getattr(catalog, name)
        assert inspect.isclass(cls)
        tags = getattr(cls, "tags", None)
        assert isinstance(tags, tuple) and tags, f"{name} has no tags tuple"
        assert any(t in _VALID_CATEGORY for t in tags), f"{name} missing category tag"
        assert any(t in _VALID_LEVEL for t in tags), f"{name} missing level tag"
        assert any(t in _VALID_GRADING for t in tags), f"{name} missing grading tag"
