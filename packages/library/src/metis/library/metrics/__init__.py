"""metis.library.metrics — Shared metric catalog for the METIS evaluation suite.

Canonical import path: ``from metis.library.metrics import XMetric``

Internal file layout (one file per metric) is a developer ergonomics choice
with no semantic weight. Classification is via the ``tags`` ClassVar on each
metric class.
"""

from ._abandonment import AbandonmentMetric as AbandonmentMetric
from ._agent_status_communication import (
    AgentStatusCommunicationMetric as AgentStatusCommunicationMetric,
)
from ._analytical_assumption_transparency import (
    AnalyticalAssumptionTransparencyMetric as AnalyticalAssumptionTransparencyMetric,
)
from ._analytical_correctness import (
    AnalyticalCorrectnessMetric as AnalyticalCorrectnessMetric,
)
from ._assumption_transparency import (
    AssumptionTransparencyMetric as AssumptionTransparencyMetric,
)
from ._bounded_troubleshooting import (
    BoundedTroubleshootingMetric as BoundedTroubleshootingMetric,
)
from ._brief_audience_appropriateness import (
    BriefAudienceAppropriatenessMetric as BriefAudienceAppropriatenessMetric,
)
from ._brief_completeness import BriefCompletenessMetric as BriefCompletenessMetric
from ._brief_goal_details import BriefGoalDetailsMetric as BriefGoalDetailsMetric
from ._brief_goal_non_prescriptive import (
    BriefGoalNonPrescriptiveMetric as BriefGoalNonPrescriptiveMetric,
)
from ._brief_source_faithfulness import (
    BriefSourceFaithfulnessMetric as BriefSourceFaithfulnessMetric,
)
from ._cancellation import CancellationMetric as CancellationMetric
from ._capability_honesty import CapabilityHonestyMetric as CapabilityHonestyMetric
from ._chart_format_compliance import (
    ChartFormatComplianceMetric as ChartFormatComplianceMetric,
)
from ._chart_granularity import ChartGranularityMetric as ChartGranularityMetric
from ._chart_necessity import ChartNecessityMetric as ChartNecessityMetric
from ._chart_purposefulness import (
    ChartPurposefulnessMetric as ChartPurposefulnessMetric,
)
from ._chart_technical_correctness import (
    ChartTechnicalCorrectnessMetric as ChartTechnicalCorrectnessMetric,
)
from ._chart_type_fitness import ChartTypeFitnessMetric as ChartTypeFitnessMetric
from ._chatbot_response_quality import (
    ChatbotResponseQualityMetric as ChatbotResponseQualityMetric,
)
from ._clarification_judgement import (
    ClarificationJudgementMetric as ClarificationJudgementMetric,
)
from ._clarification_precision import (
    ClarificationPrecisionMetric as ClarificationPrecisionMetric,
)
from ._constraint_adherence import (
    ConstraintAdherenceMetric as ConstraintAdherenceMetric,
)
from ._context_reuse import ContextReuseMetric as ContextReuseMetric
from ._correction import CorrectionMetric as CorrectionMetric
from ._cross_agent_context_retention import (
    CrossAgentContextRetentionMetric as CrossAgentContextRetentionMetric,
)
from ._cross_slide_logical_flow import (
    CrossSlideLogicalFlowMetric as CrossSlideLogicalFlowMetric,
)
from ._data_analysis_recovery import (
    DataAnalysisRecoveryMetric as DataAnalysisRecoveryMetric,
)
from ._deck_audience_calibration import (
    DeckAudienceCalibrationMetric as DeckAudienceCalibrationMetric,
)
from ._deck_brief_coverage import DeckBriefCoverageMetric as DeckBriefCoverageMetric
from ._deck_source_faithfulness import (
    DeckSourceFaithfulnessMetric as DeckSourceFaithfulnessMetric,
)
from ._decomposition_quality import (
    DecompositionQualityMetric as DecompositionQualityMetric,
)
from ._delegation_argument_correctness import (
    DelegationArgumentCorrectnessMetric as DelegationArgumentCorrectnessMetric,
)
from ._delegation_quality import DelegationQualityMetric as DelegationQualityMetric
from ._diagnosis_quality import DiagnosisQualityMetric as DiagnosisQualityMetric
from ._direct_handle_recognition import (
    DirectHandleRecognitionMetric as DirectHandleRecognitionMetric,
)
from ._direct_mode_escape import DirectModeEscapeMetric as DirectModeEscapeMetric
from ._failure_report_quality import (
    FailureReportQualityMetric as FailureReportQualityMetric,
)
from ._finding_consistency import FindingConsistencyMetric as FindingConsistencyMetric
from ._finding_deduplication import (
    FindingDeduplicationMetric as FindingDeduplicationMetric,
)
from ._first_look_inspection_cleaning import (
    FirstLookInspectionCleaningMetric as FirstLookInspectionCleaningMetric,
)
from ._follow_up_relevance import FollowUpRelevanceMetric as FollowUpRelevanceMetric
from ._gap_acknowledgement import GapAcknowledgementMetric as GapAcknowledgementMetric
from ._harmful_content_refusal import (
    HarmfulContentRefusalMetric as HarmfulContentRefusalMetric,
)
from ._insight_quality import InsightQualityMetric as InsightQualityMetric
from ._method_appropriateness import (
    MethodAppropriatenessMetric as MethodAppropriatenessMetric,
)
from ._outlier_handling_quality import (
    OutlierHandlingQualityMetric as OutlierHandlingQualityMetric,
)
from ._output_verification import OutputVerificationMetric as OutputVerificationMetric
from ._proceed_with_defaults import (
    ProceedWithDefaultsMetric as ProceedWithDefaultsMetric,
)
from ._redelegation_on_failure import (
    RedelegationOnFailureMetric as RedelegationOnFailureMetric,
)
from ._report_coherence import ReportCoherenceMetric as ReportCoherenceMetric
from ._report_completeness import ReportCompletenessMetric as ReportCompletenessMetric
from ._report_format_and_length import (
    ReportFormatAndLengthMetric as ReportFormatAndLengthMetric,
)
from ._report_format_compliance import (
    ReportFormatComplianceMetric as ReportFormatComplianceMetric,
)
from ._report_length_appropriateness import (
    ReportLengthAppropriatenessMetric as ReportLengthAppropriatenessMetric,
)
from ._reproducible_analysis_script import (
    ReproducibleAnalysisScriptMetric as ReproducibleAnalysisScriptMetric,
)
from ._routing_accuracy import RoutingAccuracyMetric as RoutingAccuracyMetric
from ._scope_correctness import ScopeCorrectnessMetric as ScopeCorrectnessMetric
from ._session_action_honesty import (
    SessionActionHonestyMetric as SessionActionHonestyMetric,
)
from ._session_bounded_troubleshooting import (
    SessionBoundedTroubleshootingMetric as SessionBoundedTroubleshootingMetric,
)
from ._session_completeness import (
    SessionCompletenessMetric as SessionCompletenessMetric,
)
from ._session_context_reuse import (
    SessionContextReuseMetric as SessionContextReuseMetric,
)
from ._session_conversation_faithfulness import (
    SessionConversationFaithfulnessMetric as SessionConversationFaithfulnessMetric,
)
from ._session_cross_agent_context_retention import (
    SessionCrossAgentContextRetentionMetric as SessionCrossAgentContextRetentionMetric,
)
from ._session_step_efficiency import (
    SessionStepEfficiencyMetric as SessionStepEfficiencyMetric,
)
from ._session_synthesis_faithfulness import (
    SessionSynthesisFaithfulnessMetric as SessionSynthesisFaithfulnessMetric,
)
from ._session_task_decomposition_accuracy import (
    SessionTaskDecompositionAccuracyMetric as SessionTaskDecompositionAccuracyMetric,
)
from ._single_prompt_clarification import (
    SinglePromptClarificationMetric as SinglePromptClarificationMetric,
)
from ._slide_protocol_ordering import (
    SlideProtocolOrderingMetric as SlideProtocolOrderingMetric,
)
from ._slide_spec_compliance import (
    SlideSpecComplianceMetric as SlideSpecComplianceMetric,
)
from ._slide_title_quality import SlideTitleQualityMetric as SlideTitleQualityMetric
from ._slide_visual_quality import SlideVisualQualityMetric as SlideVisualQualityMetric
from ._step_efficiency import StepEfficiencyMetric as StepEfficiencyMetric
from ._synthesis_faithfulness import (
    SynthesisFaithfulnessMetric as SynthesisFaithfulnessMetric,
)
from ._turn_budget import TurnBudgetMetric as TurnBudgetMetric
from ._turns_to_task_start import TurnsToTaskStartMetric as TurnsToTaskStartMetric
from .default import CriterionGEvalMetric as CriterionGEvalMetric
