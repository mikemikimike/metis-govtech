"""metis.library.graders — Shared grader catalog for the METIS evaluation suite.

Canonical import path: ``from metis.library.graders import XGrader``

Internal file layout (one file per grader) is a developer ergonomics choice
with no semantic weight. Classification is via the ``tags`` ClassVar on each
grader class.
"""

from ._abandonment import AbandonmentGrader as AbandonmentGrader
from ._agent_status_communication import (
    AgentStatusCommunicationGrader as AgentStatusCommunicationGrader,
)
from ._analytical_assumption_transparency import (
    AnalyticalAssumptionTransparencyGrader as AnalyticalAssumptionTransparencyGrader,
)
from ._analytical_correctness import (
    AnalyticalCorrectnessGrader as AnalyticalCorrectnessGrader,
)
from ._assumption_transparency import (
    AssumptionTransparencyGrader as AssumptionTransparencyGrader,
)
from ._bounded_troubleshooting import (
    BoundedTroubleshootingGrader as BoundedTroubleshootingGrader,
)
from ._brief_audience_appropriateness import (
    BriefAudienceAppropriatenessGrader as BriefAudienceAppropriatenessGrader,
)
from ._brief_completeness import BriefCompletenessGrader as BriefCompletenessGrader
from ._brief_goal_details import BriefGoalDetailsGrader as BriefGoalDetailsGrader
from ._brief_goal_non_prescriptive import (
    BriefGoalNonPrescriptiveGrader as BriefGoalNonPrescriptiveGrader,
)
from ._brief_source_faithfulness import (
    BriefSourceFaithfulnessGrader as BriefSourceFaithfulnessGrader,
)
from ._cancellation import CancellationGrader as CancellationGrader
from ._capability_honesty import CapabilityHonestyGrader as CapabilityHonestyGrader
from ._chart_format_compliance import (
    ChartFormatComplianceGrader as ChartFormatComplianceGrader,
)
from ._chart_granularity import ChartGranularityGrader as ChartGranularityGrader
from ._chart_necessity import ChartNecessityGrader as ChartNecessityGrader
from ._chart_purposefulness import (
    ChartPurposefulnessGrader as ChartPurposefulnessGrader,
)
from ._chart_technical_correctness import (
    ChartTechnicalCorrectnessGrader as ChartTechnicalCorrectnessGrader,
)
from ._chart_type_fitness import ChartTypeFitnessGrader as ChartTypeFitnessGrader
from ._chatbot_response_quality import (
    ChatbotResponseQualityGrader as ChatbotResponseQualityGrader,
)
from ._clarification_judgement import (
    ClarificationJudgementGrader as ClarificationJudgementGrader,
)
from ._clarification_precision import (
    ClarificationPrecisionGrader as ClarificationPrecisionGrader,
)
from ._constraint_adherence import (
    ConstraintAdherenceGrader as ConstraintAdherenceGrader,
)
from ._context_reuse import ContextReuseGrader as ContextReuseGrader
from ._correction import CorrectionGrader as CorrectionGrader
from ._cross_agent_context_retention import (
    CrossAgentContextRetentionGrader as CrossAgentContextRetentionGrader,
)
from ._cross_slide_logical_flow import (
    CrossSlideLogicalFlowGrader as CrossSlideLogicalFlowGrader,
)
from ._data_analysis_recovery import (
    DataAnalysisRecoveryGrader as DataAnalysisRecoveryGrader,
)
from ._deck_audience_calibration import (
    DeckAudienceCalibrationGrader as DeckAudienceCalibrationGrader,
)
from ._deck_brief_coverage import DeckBriefCoverageGrader as DeckBriefCoverageGrader
from ._deck_source_faithfulness import (
    DeckSourceFaithfulnessGrader as DeckSourceFaithfulnessGrader,
)
from ._decomposition_quality import (
    DecompositionQualityGrader as DecompositionQualityGrader,
)
from ._delegation_argument_correctness import (
    DelegationArgumentCorrectnessGrader as DelegationArgumentCorrectnessGrader,
)
from ._delegation_quality import DelegationQualityGrader as DelegationQualityGrader
from ._diagnosis_quality import DiagnosisQualityGrader as DiagnosisQualityGrader
from ._direct_handle_recognition import (
    DirectHandleRecognitionGrader as DirectHandleRecognitionGrader,
)
from ._direct_mode_escape import DirectModeEscapeGrader as DirectModeEscapeGrader
from ._failure_report_quality import (
    FailureReportQualityGrader as FailureReportQualityGrader,
)
from ._finding_consistency import FindingConsistencyGrader as FindingConsistencyGrader
from ._finding_deduplication import (
    FindingDeduplicationGrader as FindingDeduplicationGrader,
)
from ._first_look_inspection_cleaning import (
    FirstLookInspectionCleaningGrader as FirstLookInspectionCleaningGrader,
)
from ._follow_up_relevance import FollowUpRelevanceGrader as FollowUpRelevanceGrader
from ._gap_acknowledgement import GapAcknowledgementGrader as GapAcknowledgementGrader
from ._harmful_content_refusal import (
    HarmfulContentRefusalGrader as HarmfulContentRefusalGrader,
)
from ._insight_quality import InsightQualityGrader as InsightQualityGrader
from ._method_appropriateness import (
    MethodAppropriatenessGrader as MethodAppropriatenessGrader,
)
from ._outlier_handling_quality import (
    OutlierHandlingQualityGrader as OutlierHandlingQualityGrader,
)
from ._output_verification import OutputVerificationGrader as OutputVerificationGrader
from ._proceed_with_defaults import (
    ProceedWithDefaultsGrader as ProceedWithDefaultsGrader,
)
from ._redelegation_on_failure import (
    RedelegationOnFailureGrader as RedelegationOnFailureGrader,
)
from ._report_coherence import ReportCoherenceGrader as ReportCoherenceGrader
from ._report_completeness import ReportCompletenessGrader as ReportCompletenessGrader
from ._report_format_and_length import (
    ReportFormatAndLengthGrader as ReportFormatAndLengthGrader,
)
from ._report_format_compliance import (
    ReportFormatComplianceGrader as ReportFormatComplianceGrader,
)
from ._report_length_appropriateness import (
    ReportLengthAppropriatenessGrader as ReportLengthAppropriatenessGrader,
)
from ._reproducible_analysis_script import (
    ReproducibleAnalysisScriptGrader as ReproducibleAnalysisScriptGrader,
)
from ._routing_accuracy import RoutingAccuracyGrader as RoutingAccuracyGrader
from ._scope_correctness import ScopeCorrectnessGrader as ScopeCorrectnessGrader
from ._session_action_honesty import (
    SessionActionHonestyGrader as SessionActionHonestyGrader,
)
from ._session_bounded_troubleshooting import (
    SessionBoundedTroubleshootingGrader as SessionBoundedTroubleshootingGrader,
)
from ._session_completeness import (
    SessionCompletenessGrader as SessionCompletenessGrader,
)
from ._session_context_reuse import (
    SessionContextReuseGrader as SessionContextReuseGrader,
)
from ._session_conversation_faithfulness import (
    SessionConversationFaithfulnessGrader as SessionConversationFaithfulnessGrader,
)
from ._session_cross_agent_context_retention import (
    SessionCrossAgentContextRetentionGrader as SessionCrossAgentContextRetentionGrader,
)
from ._session_step_efficiency import (
    SessionStepEfficiencyGrader as SessionStepEfficiencyGrader,
)
from ._session_synthesis_faithfulness import (
    SessionSynthesisFaithfulnessGrader as SessionSynthesisFaithfulnessGrader,
)
from ._session_task_decomposition_accuracy import (
    SessionTaskDecompositionAccuracyGrader as SessionTaskDecompositionAccuracyGrader,
)
from ._single_prompt_clarification import (
    SinglePromptClarificationGrader as SinglePromptClarificationGrader,
)
from ._slide_protocol_ordering import (
    SlideProtocolOrderingGrader as SlideProtocolOrderingGrader,
)
from ._slide_spec_compliance import (
    SlideSpecComplianceGrader as SlideSpecComplianceGrader,
)
from ._slide_title_quality import SlideTitleQualityGrader as SlideTitleQualityGrader
from ._slide_visual_quality import SlideVisualQualityGrader as SlideVisualQualityGrader
from ._step_efficiency import StepEfficiencyGrader as StepEfficiencyGrader
from ._synthesis_faithfulness import (
    SynthesisFaithfulnessGrader as SynthesisFaithfulnessGrader,
)
from ._trace_budget import TraceBudgetGrader as TraceBudgetGrader
from ._turn_budget import TurnBudgetGrader as TurnBudgetGrader
from ._turns_to_task_start import TurnsToTaskStartGrader as TurnsToTaskStartGrader
from ._types import ConversationalTestCaseMetadata as ConversationalTestCaseMetadata
from ._types import LlmTestCaseMetadata as LlmTestCaseMetadata
from ._types import OrcaChatMetadata as OrcaChatMetadata
from .default import CriterionGEvalGrader as CriterionGEvalGrader
