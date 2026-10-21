# Grader taxonomy and authoring guide

The grader taxonomy gives grader authors one vocabulary for describing a grader.
It has three top-level groups:

| Group | Meaning | Selection for one judgment |
|---|---|---|
| Measure | The property to assess. | Choose one subdimension, then one attribute within it. |
| Scope | The evidence unit to assess. | Choose one subdimension, then one attribute within it. |
| Mechanism | The method used for the assessment. | Choose one attribute from each subdimension. |

The Mechanism subdimensions are grader type, reference type, judgment form, and
aggregation. Measure and Scope subdimensions appear as group comments in their
enums. The capability declaration stores supported attributes as flat enum values.
A catch-all judge has no Measure mapping and declares `measure=None`.

The Interaction subdimension of Scope contains `TRACE`, `SUBSESSION`, and `SESSION`.
A trace contains recorded observations. A subsession contains a subset of the traces
in one session. A session contains all traces for one trial.

The taxonomy is a capability declaration. A supported value means that the grader
accepts that value and implements the behavior that it names. The declaration does
not show that the grader is accurate. Grader quality needs separate validation with
representative, human-labeled examples.

## Author responsibility

Some taxonomy categories overlap. Some values also constrain the values that make
sense in another group. The five capability tuples do not permit every possible
combination of their values.

The human who defines a grader class must understand the grading method and the
evidence that it needs. The author must declare a sensible set of supported values.
If the grader declares several values in more than one group, the author must define
and validate the combinations that the grader implements. The author must test each
declared path.

For example, an `EXPECTED_OUTPUT` reference needs an expected output. A
`TOOL_ARGUMENTS` scope needs recorded tool arguments. A weighted aggregation needs
weights. Validate required settings before a run. During grading, report missing
evidence as `skipped` or `errored`, according to the documented evidence contract.

The taxonomy does not select a method. Grader code and validated arguments determine
the method for each request. A taxonomy declaration does not establish grading accuracy.

## Taxonomy contract

`GraderTaxonomy` contains one required measure field and five nonempty tuples.
A specialized grader declares one measure. A catch-all grader explicitly sets
`measure=None` because it has no category mapping:

| Field | Meaning |
|---|---|
| `measure` | One evaluation property, or `None` for a catch-all grader with no category mapping. |
| `scopes` | Evidence units that the grader can assess. |
| `grader_types` | Procedures that the grader implements. |
| `reference_types` | Reference categories that the grader can use. |
| `judgment_forms` | Result forms that the grader can produce. |
| `aggregations` | Rules that the grader can use to combine internal checks. |

A tuple with one value records a fixed capability. A tuple with several values records
several implemented capabilities. The declaration itself does not select a value for
one grading request.

A taxonomy value is a named enum member, such as `Scope.TRACE` or
`JudgmentForm.BINARY`. A taxonomy definition can hold shared behavior for one value.
This behavior can include evidence preparation, prompt text, response validation, or
aggregation logic.

The enums define the accepted vocabulary for future grader implementations. An enum
member alone does not provide runtime support.

The current shared definition registry, `JUDGMENT_FORM_DEFINITIONS` in
`metis.library.judgment`, contains only `JudgmentForm.BINARY`. Its definition owns the
output instructions and the `BinaryJudgment` response model. A judge uses the same
definition for its prompt, response schema, and response validation.

## Criterion Judge example

`CriterionJudgeGrader` is the LLM reference grader in the public catalog.
It is a catch-all judge with no measure mapping. The other five groups each
have one fixed value:

| Group | Declared value | Reason |
|---|---|---|
| Measure | `None` | The catch-all judge has no category mapping. |
| Scope | `SESSION` | It assesses all supplied traces and returns one result. |
| Grader type | `LLM` | It uses the configured language model. |
| Reference type | `RUBRIC_BASED` | The criterion description supplies the assessment rule. |
| Judgment form | `BINARY` | A scored result is `1` or `0`. |
| Aggregation | `NONE_SINGLE_SCORE` | It makes one assessment and returns one score. |

The declaration has this shape:

```python
taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
    measure=None,
    scopes=(Scope.SESSION,),
    grader_types=(GraderType.LLM,),
    reference_types=(ReferenceType.RUBRIC_BASED,),
    judgment_forms=(JudgmentForm.BINARY,),
    aggregations=(Aggregation.NONE_SINGLE_SCORE,),
)
```

The criterion text defines the check for each assessment. `None` means that the judge
has no measure mapping. It does not declare support for every measure.
The judge can assess only the evidence that it receives.

The judge uses the shared binary output instructions and response validation. Its
fixed declaration describes that implementation. It has no per-request form selector.

See [the Criterion Judge guide](criterionjudge.md) for its settings and evidence
limits.

## Deterministic reference grader

`metis.library.graders.demo.DemoTraceBudgetGrader` checks a trace budget for a session.
It declares `Measure.TASK_CONSTRAINT_ADHERENCE`, `Scope.SESSION`,
`GraderType.DETERMINISTIC`, `ReferenceType.POLICY_RULE`, `JudgmentForm.BINARY`, and
`Aggregation.NONE_SINGLE_SCORE`.

The `max_traces` argument supplies the policy rule. The grader counts all traces,
including traces with target errors. It returns `1` when the count is within the
budget and `0` when the count exceeds it. An empty session produces a skipped result.
It makes no LLM call. This example checks one task constraint. It does not assess
all task constraints.

A criterion can select the demo with these settings:

```yaml
grader_fqn: metis.library.graders.demo.DemoTraceBudgetGrader
grader_args:
  max_traces: 4
```

The demo is exported only from `metis.library.graders.demo`. The wizard does not offer
demo graders in its catalog.

## Grader arguments

Each grader defines an `args_model`. The model validates the settings stored under
`grader_args`. Unknown keys fail validation.

A grader with several supported values can use a typed argument to select one value.
The argument model or `check_setup()` must reject unsupported combinations. The
taxonomy records support. The argument model records a selection for one criterion.

The current Criterion Judge has no measure mapping and fixed values in
the other five groups. Its arguments contain its criterion text, model, input limit,
and passing threshold. The criterion text defines the check. The args model has no
taxonomy selection fields.

## Results and evidence

`GradingInput` contains the recorded traces and artifact records for one session. A
grader does not receive the scenario, persona, or stop reason.

A grader returns `GradingOutput` with at least one result. Use:

- `scored` when the grader made an assessment;
- `skipped` when there is no applicable evidence;
- `errored` when the assessment cannot complete.

Skipped and errored results have no score. The engine applies the criterion threshold
to scored results.

Evidence requirements are part of the declared support. Recorded state can support a
judgment. Unobserved live state cannot. An artifact path does not give a grader the
artifact contents. The grader or a shared helper must load available content when the
method needs it. Missing required evidence cannot produce a passing result.

## Current limits

The taxonomy is library metadata. The base `Grader` contract does not require it. The
engine, wizard, insights, and reports do not inspect it.

Criterion Judge and DemoTraceBudget are the working reference graders. Each has one
fixed value in each capability tuple. Other graders need their own declarations and
behavior tests before they claim taxonomy support.

Only the binary judgment definition has shared runtime behavior. Scope, grader type,
reference type, measure, and aggregation values are descriptive declarations.
Their shared definition registries and runtime routing are not implemented.

The current result model has no structured scope-item or evidence-source identifier.
Both reference graders return one result for the complete session. Graders that
return results for individual evidence items need a defined way to identify those items.

The taxonomy does not test validity, reliability, calibration, or agreement with
human assessors. Those properties need a separate evaluation method.

## Decisions needed for further implementations

The following work is outside this foundation:

- A grader with several capabilities needs explicit selection arguments and validation
  of supported combinations. Tuple membership does not establish every combination.
- Subsession graders need rules for trace membership, ordering, and the context visible
  to each judgment. Their results need a way to identify the selected evidence.
- Internal aggregation combines checks within one judgment's scope. Cross-trial
  aggregation belongs to reporting. Each implementation needs to define its score
  meaning and required settings, such as weights.
- Shared definitions for other taxonomy groups need concrete consumers before they
  become registries. Generic method selection and runtime routing are not implemented.

## Author a grader

1. Define an arguments model that extends `GraderArgs`. For an LLM judge, extend
   `JudgeArgs`. Declare reference values and selection arguments in that model.
2. Subclass `Grader[YourArgs]`. Set `args_model = YourArgs` to the same class.
3. Declare a `GraderTaxonomy` that describes the behavior you implement. Start with
   fixed capabilities when the grader needs only one combination.
4. Implement `async grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput`.
   Apply the evidence and result rules in this guide. For an LLM call, check
   `input_budget_error` first and use `llm.client`.
5. Validate settings in the arguments model. Use `check_setup()` for checks that need
   the specification, such as whether a named fixture exists.
6. Export the grader from `metis.library.graders`. Export demos only from
   `metis.library.graders.demo`.
7. Add tests under `tests/unit/library/` for each supported behavior, invalid settings,
   absent evidence, and assessment failures. Mock external providers in offline tests.
8. Evaluate grading quality against representative examples with human labels. Record
   the dataset, model settings, and results separately from capability tests.

## Reading traces

Use `metis.core.trace_processing` when a grader needs normalized turns, tool calls,
target errors, or artifact records. `turns(input.traces)` returns one turn per trace, oldest
first. Use `select_all`, `select_final`, or `select_where` to select evidence.
`render_transcript` prepares a shared text view for LLM judges.

Readers return a value or a `Problem`. A `Problem` means that METIS could not read the
evidence. Map `no_match` and `artifact_unavailable` to `skipped`. Document whether
`unsupported` and `missing` produce `skipped` or `errored`. Never score a `Problem`.
A recorded target error is evidence about the target and can support an assessment.

`find_artifacts` returns artifact records. It does not open files. Langfuse media
references are unavailable to these readers. For a judgment of one trace, provide
only the context permitted by the grader's contract. Exclude later traces when the
judgment must use only information available at that point.

The Criterion Judge is a specific exception. It serializes the supported observation
fields directly. It sends observation IDs, parent IDs, types, names, inputs, and
outputs. This behavior is part of its documented evidence contract.

Treat grading input as read-only. A grader instance can grade several sessions
concurrently. Keep only immutable arguments on the grader instance. Send LLM calls
through the shared `llm.client`.
