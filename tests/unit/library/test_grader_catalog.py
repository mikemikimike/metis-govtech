"""Catalog invariants for the CSV-aligned grader coverage change.

Guards the public export surface: the new graders are importable, the two
renamed graders are gone (no compatibility aliases), and every grader class
carries a well-formed ``tags`` ClassVar.
"""

import inspect

import metis.library.graders as catalog

# Graders introduced by the align-csv-metric-coverage change.
NEW_GRADERS = [
    "FirstLookInspectionCleaningGrader",  # M-DA-20 (renamed)
    "ProceedWithDefaultsGrader",  # M-DA-28 (renamed)
    "ChartTechnicalCorrectnessGrader",
    "ReportFormatAndLengthGrader",
    "ReproducibleAnalysisScriptGrader",  # M-DA-23
    "DataAnalysisRecoveryGrader",  # M-DA-26
    "OutputVerificationGrader",  # M-DA-27
    "HarmfulContentRefusalGrader",
    "CorrectionGrader",  # M-UNI-19
    "AbandonmentGrader",  # M-UNI-20
    "CancellationGrader",  # M-UNI-21
    "DirectModeEscapeGrader",
    "SlideProtocolOrderingGrader",  # M-SM-1
    "BriefGoalDetailsGrader",  # M-SM-2
    "BriefGoalNonPrescriptiveGrader",  # M-SM-6
    "BriefSourceFaithfulnessGrader",  # M-SM-7
    "BriefCompletenessGrader",  # M-SM-8
    "BriefAudienceAppropriatenessGrader",  # M-SM-9
    "DeckBriefCoverageGrader",  # M-SM-11
    "SlideVisualQualityGrader",  # M-SM-13
    "SlideTitleQualityGrader",  # M-SM-15
    "DeckAudienceCalibrationGrader",  # M-SM-19
]

# Removed by the two BREAKING renames — must not resolve, even as aliases.
REMOVED_GRADERS = [
    "DataIngestionAccuracyMetric",  # -> FirstLookInspectionCleaningGrader
    "OpenEndedScopeQualityMetric",  # -> ProceedWithDefaultsGrader
]

_VALID_CATEGORY = {"analysis", "presentation", "universal", "orchestration"}
_VALID_LEVEL = {"per-turn", "session-level"}
_VALID_GRADING = {"code-graded", "judge-graded"}


def test_new_graders_are_exported():
    for name in NEW_GRADERS:
        assert hasattr(catalog, name), f"missing new grader export: {name}"


def test_removed_graders_have_no_alias():
    for name in REMOVED_GRADERS:
        assert not hasattr(catalog, name), f"stale grader still exported: {name}"


def test_every_grader_has_wellformed_tags():
    for name in NEW_GRADERS:
        cls = getattr(catalog, name)
        assert inspect.isclass(cls)
        tags = getattr(cls, "tags", None)
        assert isinstance(tags, tuple) and tags, f"{name} has no tags tuple"
        assert any(t in _VALID_CATEGORY for t in tags), f"{name} missing category tag"
        assert any(t in _VALID_LEVEL for t in tags), f"{name} missing level tag"
        assert any(t in _VALID_GRADING for t in tags), f"{name} missing grading tag"
