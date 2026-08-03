# Metrics

Metrics are organised by what they measure, not by which agent produced the trace. Any metric can be listed under `metric_refs` in `experiment.yaml` — the evaluator instantiates them dynamically from their FQN and routes them automatically to the right test case type:

- **Session metrics** (`BaseConversationalMetric` subclasses) run against the full multi-turn `ConversationalTestCase` for each session.
- **Per-turn metrics** run against each individual `LLMTestCase` (one per trace/turn).

---

## Session (`metrics.session`)

Run once per session on a `ConversationalTestCase`. Covers multi-turn properties that per-turn metrics cannot see — e.g. whether context was retained across agent switches, or whether the user's goal was ultimately achieved.

| Name | FQN | How it is implemented |
|------|-----|-----------------------|
| Step Efficiency | `metis.library.metrics.session.SessionStepEfficiencyMetric` | **Code.** Annotation-dependent — skips without `expected_minimum_steps`. Counts total tool calls across the session and checks against the annotated minimum. |
| Bounded Troubleshooting | `metis.library.metrics.session.SessionBoundedTroubleshootingMetric` | **Code.** Detects consecutive calls to the same tool where every output contains an error signal. Fails if any streak exceeds `max_retries=3`. |
| Action Honesty | `metis.library.metrics.session.SessionActionHonestyMetric` | **ConversationalGEval.** Checks whether the assistant's final response claims actions or artefacts that no tool call actually produced. |
| Conversation Faithfulness | `metis.library.metrics.session.SessionConversationFaithfulnessMetric` | **ConversationalGEval.** Checks whether any later assistant response contradicts factual claims from earlier turns. |
| Context Reuse | `metis.library.metrics.session.SessionContextReuseMetric` | **ConversationalGEval.** Checks whether the agent re-asks for information the user already provided in a prior turn. |
| Synthesis Faithfulness | `metis.library.metrics.session.SessionSynthesisFaithfulnessMetric` | **ConversationalGEval.** Skips if no `delegate_task_to_member` call present. Checks that the final response preserves key facts from delegated outputs without fabrication. |
| Session Completeness | `metis.library.metrics.session.SessionCompletenessMetric` | **DeepEval built-in `ConversationCompletenessMetric`.** Infers the expected outcome from the conversation and scores whether it was achieved. |
| Cross-Agent Context Retention | `metis.library.metrics.session.SessionCrossAgentContextRetentionMetric` | **ConversationalGEval.** Checks whether context from earlier agent turns is correctly forwarded across agent switches. |
| Task Decomposition Accuracy | `metis.library.metrics.session.SessionTaskDecompositionAccuracyMetric` | **ConversationalGEval.** Skips if no `delegate_task_to_member` call present. Checks that the right subagents were chosen and invoked in a logical order. |

---

## Orchestration (`metrics.orchestration`)

Measures how well the orchestrator routes, delegates, and synthesises.

| Name | FQN | How it is implemented |
|------|-----|-----------------------|
| Routing Accuracy | `metis.library.metrics.orchestration.RoutingAccuracyMetric` | **GEval.** Skips if no delegation and no tool calls. Checks whether the routing choice was correct given the user's query. |
| Direct Handle Recognition | `metis.library.metrics.orchestration.DirectHandleRecognitionMetric` | **Code.** Checks that the orchestrator does not route to a subagent when the request can be answered directly. |
| Clarification Judgement | `metis.library.metrics.orchestration.ClarificationJudgementMetric` | **GEval.** Checks whether the orchestrator's decision to ask for clarification (or not) was appropriate. |
| Delegation Quality | `metis.library.metrics.orchestration.DelegationQualityMetric` | **GEval.** Checks whether the delegation instruction to the subagent was complete and accurate. |
| Redelegation On Failure | `metis.library.metrics.orchestration.RedelegationOnFailureMetric` | **GEval.** Condition-gated — fires only when a subagent reports failure. Checks whether the orchestrator retried or escalated appropriately. |
| Gap Acknowledgement | `metis.library.metrics.orchestration.GapAcknowledgementMetric` | **GEval.** Checks whether the orchestrator acknowledged information gaps rather than fabricating. |
| Chatbot Response Quality | `metis.library.metrics.orchestration.ChatbotResponseQualityMetric` | **GEval.** For direct-handle traces: checks response quality, helpfulness, and tone. |
| Decomposition Quality | `metis.library.metrics.orchestration.DecompositionQualityMetric` | **GEval.** Checks whether complex tasks were broken down into appropriate subtasks for each subagent. |
| Agent Status Communication | `metis.library.metrics.orchestration.AgentStatusCommunicationMetric` | **GEval.** Checks whether the orchestrator communicated subagent progress or failures to the user. |
| Finding Deduplication | `metis.library.metrics.orchestration.FindingDeduplicationMetric` | **GEval.** Requires multi-agent trace. Checks that duplicate findings from different subagents are not surfaced to the user. |
| Finding Consistency | `metis.library.metrics.orchestration.FindingConsistencyMetric` | **GEval.** Skips on single-agent traces. Checks for contradictions between findings from different agents in the final response. |
| Capability Honesty | `metis.library.metrics.orchestration.CapabilityHonestyMetric` | **GEval.** Checks that the orchestrator does not claim capabilities it does not have. |
| Follow-Up Relevance | `metis.library.metrics.orchestration.FollowUpRelevanceMetric` | **GEval.** Checks that follow-up questions or suggestions are relevant to the completed task. |
| Delegation Argument Correctness | `metis.library.metrics.orchestration.DelegationArgumentCorrectnessMetric` | **GEval.** Checks that arguments passed to `delegate_task_to_member` are correctly formed. |
| Cross-Agent Context Retention | `metis.library.metrics.orchestration.CrossAgentContextRetentionMetric` | **Code.** Checks whether context from earlier agent turns (via `spoke_context`) is forwarded and not redundantly re-asked in later turns. |

---

## Analysis (`metrics.analysis`)

Measures analytical quality: correctness, scope, chart accuracy, and report quality.

| Name | FQN | How it is implemented |
|------|-----|-----------------------|
| Data Ingestion Accuracy | `metis.library.metrics.analysis.DataIngestionAccuracyMetric` | **Code.** Checks that uploaded files were read without corruption. |
| Scope Correctness | `metis.library.metrics.analysis.ScopeCorrectnessMetric` | **GEval.** Checks whether the agent analysed exactly the quantities asked for — no scope creep, no omissions. |
| Analytical Correctness | `metis.library.metrics.analysis.AnalyticalCorrectnessMetric` | **Code (annotation-dependent).** Skips unless `annotations.expected_values` present. Compares numerical results against ground truth within 1% tolerance. |
| Method Appropriateness | `metis.library.metrics.analysis.MethodAppropriatenessMetric` | **GEval.** Checks that the chosen statistical method was appropriate for the data and question. |
| Insight Quality | `metis.library.metrics.analysis.InsightQualityMetric` | **GEval.** Checks that findings go beyond restating the data. |
| Chart Purposefulness | `metis.library.metrics.analysis.ChartPurposefulnessMetric` | **GEval.** Checks that each chart adds analytical value. |
| Chart Necessity | `metis.library.metrics.analysis.ChartNecessityMetric` | **GEval.** Checks that charts were included only when they aid understanding. |
| Chart Type Fitness | `metis.library.metrics.analysis.ChartTypeFitnessMetric` | **Code (annotation-dependent).** Skips unless `annotations.data_pattern` or `annotations.acceptable_chart_types` present. Checks chart type against acceptable set for the annotated data pattern. |
| Chart Granularity | `metis.library.metrics.analysis.ChartGranularityMetric` | **Code.** Checks that chart data granularity matches what was requested. |
| Report Format Compliance | `metis.library.metrics.analysis.ReportFormatComplianceMetric` | **Code.** Checks that the report matches any explicit format requirements. |
| Report Coherence | `metis.library.metrics.analysis.ReportCoherenceMetric` | **GEval.** Checks that the report flows logically and sections are internally consistent. |
| Report Completeness | `metis.library.metrics.analysis.ReportCompletenessMetric` | **GEval.** Skips if output is under 500 chars. Decomposes the user's request into sub-questions and checks each is addressed. |
| Chart Format Compliance | `metis.library.metrics.analysis.ChartFormatComplianceMetric` | **Code.** Checks chart formatting against any explicit requirements. |
| Analytical Assumption Transparency | `metis.library.metrics.analysis.AnalyticalAssumptionTransparencyMetric` | **GEval.** Checks that assumptions made during analysis are stated explicitly. |
| Outlier Handling Quality | `metis.library.metrics.analysis.OutlierHandlingQualityMetric` | **GEval.** Checks that outliers were handled appropriately and transparently. |
| Report Length Appropriateness | `metis.library.metrics.analysis.ReportLengthAppropriatenessMetric` | **GEval.** Checks that report length is proportionate to the complexity of the request. |

---

## Presentation (`metrics.presentation`)

Measures slide deck quality: spec compliance, narrative flow, and source faithfulness.

| Name | FQN | How it is implemented |
|------|-----|-----------------------|
| Slide Spec Compliance | `metis.library.metrics.presentation.SlideSpecComplianceMetric` | **Extract + GEval.** Skips if no deck properties extractable. Reads slide count, theme, and titles from `deck_metadata`, then checks each explicit user requirement. |
| Cross-Slide Logical Flow | `metis.library.metrics.presentation.CrossSlideLogicalFlowMetric` | **Extract + GEval.** Skips if no slide titles extractable. Judges whether the title sequence forms a coherent narrative arc. |
| Deck Source Faithfulness | `metis.library.metrics.presentation.DeckSourceFaithfulnessMetric` | **Extract + DeepEval built-in `FaithfulnessMetric`.** Skips if no source material found. Reads source file contents from `read_source_file` tool outputs and checks each claim in the output is grounded. |

---

## Universal (`metrics.universal`)

Applies across all task types.

| Name | FQN | How it is implemented |
|------|-----|-----------------------|
| Single-Prompt Clarification | `metis.library.metrics.universal.SinglePromptClarificationMetric` | **Code.** Counts `request_user_input` tool calls. Fails if count > 1. |
| Turns to Task Start | `metis.library.metrics.universal.TurnsToTaskStartMetric` | **Code.** Counts clarification round-trips before the agent proceeds to execution. Fails if count > `max_turns` (default 2). |
| Step Efficiency | `metis.library.metrics.universal.StepEfficiencyMetric` | **Code.** Annotation-dependent — skips without `expected_minimum_steps`. Checks that actual tool call count doesn't exceed the annotated minimum by more than `max_ratio` (default 1.3×). |
| Context Reuse | `metis.library.metrics.universal.ContextReuseMetric` | **Code.** Skips if no `spoke_context` present. Checks that `request_user_input` calls don't ask for keys already in `spoke_context`. |
| Bounded Troubleshooting | `metis.library.metrics.universal.BoundedTroubleshootingMetric` | **Code.** Checks that no single tool is called more than `max_retries` times (default 5) in total. |
| Diagnosis Quality | `metis.library.metrics.universal.DiagnosisQualityMetric` | **Condition-gated GEval.** Skips if no error signal in the trace. When present, checks whether root cause was described before the first fix attempt. |
| Open-Ended Scope Quality | `metis.library.metrics.universal.OpenEndedScopeQualityMetric` | **GEval.** Checks that the agent's self-chosen scope is comprehensive, relevant, and proportionate for an open-ended request. |
| Clarification Precision | `metis.library.metrics.universal.ClarificationPrecisionMetric` | **Extract + GEval.** Skips if no `request_user_input` calls. Checks whether each question was necessary and no critical question was omitted. |
| Failure Report Quality | `metis.library.metrics.universal.FailureReportQualityMetric` | **Condition-gated GEval.** Skips unless `chat_metadata.had_error=True`. Checks that the failure report contains what failed, what was attempted, and at least one actionable next step. |
| Assumption Transparency | `metis.library.metrics.universal.AssumptionTransparencyMetric` | **GEval.** Checks that scope/interpretation assumptions are explicitly stated. Normal operations (delegating, reading files) are excluded from counting as assumptions. |
| Constraint Adherence | `metis.library.metrics.universal.ConstraintAdherenceMetric` | **GEval.** Checks that explicit constraints in the user's request (method, format, scope) were respected. |
| Turn Budget | `metis.library.metrics.universal.TurnBudgetMetric` | **Code.** Fails if the session exceeds `max_turns` (configurable). Use `TurnBudgetMetric: {max_turns: N}` in `experiment.yaml`. |

---

## Skip behaviour

All metrics use the same skip convention: `score=1.0`, `skipped=True`, `success=True`. Skipped metrics are excluded from pass-rate aggregation in the report.
