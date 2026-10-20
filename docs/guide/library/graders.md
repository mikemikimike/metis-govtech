# Grader taxonomy and authoring guide

The grader taxonomy gives grader authors one vocabulary for describing a grader.
It covers six groups:

- evaluation subdimension;
- grader scope;
- grader type;
- reference type;
- judgment form;
- aggregation.

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
weights. A grader must reject a configuration when its required evidence or settings
are absent.

The taxonomy guides the grader to the best supported method. It does not prevent an
LLM judge from making an incorrect assessment.

## Taxonomy contract

`GraderTaxonomy` contains one required subdimension field and five nonempty tuples.
A specialized grader declares one subdimension. A catch-all grader explicitly sets
`subdimension=None` because it has no category mapping:

| Field | Meaning |
|---|---|
| `subdimension` | One evaluation property, or `None` for a catch-all grader with no category mapping. |
| `scopes` | Evidence units that the grader can assess. |
| `grader_types` | Procedures that the grader implements. |
| `reference_types` | Reference categories that the grader can use. |
| `judgment_forms` | Result forms that the grader can produce. |
| `aggregations` | Rules that the grader can use to combine internal checks. |

A tuple with one value records a fixed capability. A tuple with several values records
several implemented capabilities. The declaration itself does not select a value for
one grading request.

A taxonomy value is a named enum member, such as `GraderScope.TURN` or
`JudgmentForm.BINARY`. A taxonomy definition can hold shared behavior for one value.
This behavior can include evidence preparation, prompt text, response validation, or
aggregation logic.

The current shared definition registry contains the binary judgment form. Its
definition owns the output instructions and the `BinaryJudgment` response model.

## Criterion Judge example

`CriterionJudgeGrader` is the public example of a complete taxonomy declaration.
It is a catch-all judge with no subdimension mapping. The other five groups each
have one fixed value:

| Group | Declared value | Reason |
|---|---|---|
| Evaluation subdimension | `None` | The catch-all judge has no category mapping. |
| Grader scope | `COMPLETE_TRAJECTORY_EPISODE` | It assesses all supplied traces and returns one result. |
| Grader type | `LLM` | It uses the configured language model. |
| Reference type | `RUBRIC_BASED` | The criterion description supplies the assessment rule. |
| Judgment form | `BINARY` | A scored result is `1` or `0`. |
| Aggregation | `NONE_SINGLE_SCORE` | It makes one assessment and returns one score. |

The declaration has this shape:

```python
taxonomy: ClassVar[GraderTaxonomy] = GraderTaxonomy(
    subdimension=None,
    scopes=(GraderScope.COMPLETE_TRAJECTORY_EPISODE,),
    grader_types=(GraderType.LLM,),
    reference_types=(ReferenceType.RUBRIC_BASED,),
    judgment_forms=(JudgmentForm.BINARY,),
    aggregations=(Aggregation.NONE_SINGLE_SCORE,),
)
```

The criterion text defines the check for each assessment. `None` means that the judge
has no subdimension mapping. It does not declare support for every subdimension.
The judge can assess only the evidence that it receives.

The judge resolves its binary output instructions and response validation from the
declared judgment form. This keeps the taxonomy declaration and the implemented
judgment behavior aligned.

See [the Criterion Judge guide](criterionjudge.md) for its settings and evidence
limits.

## Grader arguments

Each grader defines an `args_model`. The model validates the settings stored under
`grader_args`. Unknown keys fail validation.

A grader with several supported values can use a typed argument to select one value.
The argument model or `check_setup()` must reject unsupported combinations. The
taxonomy records support. The argument model records a selection for one criterion.

The current Criterion Judge has no subdimension mapping and fixed values in
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

Only the Criterion Judge is documented as the complete public example in this work.
Other graders do not gain taxonomy support through this example.

Only the binary judgment definition has shared runtime behavior. Scope, grader type,
reference type, subdimension, and aggregation values are descriptive declarations.
Their shared definition registries and runtime routing are not implemented.

The current result model has no structured scope-item or evidence-source identifier.
This is sufficient for the Criterion Judge because it returns one result for the
complete session.

The taxonomy does not test validity, reliability, calibration, or agreement with
human assessors. Those properties need a separate evaluation method.

## Checks for grader authors

Before an author declares a value as supported, the author must confirm that the
grader:

1. receives the evidence and reference data that the method needs;
2. implements the declared scope, procedure, judgment, and aggregation behavior;
3. rejects unsupported value combinations and missing required data;
4. returns a result with the documented meaning;
5. has tests for every declared behavior path;
6. has separate quality checks against representative examples.

## Reading traces

Use `metis.core.trace_processing` when a grader needs normalized turns, tool calls,
target errors, or artifact records. Its readers return a value or a `Problem`. Never
score a `Problem` as evidence.

The Criterion Judge is a specific exception. It serializes the supported observation
fields directly. It sends observation IDs, parent IDs, types, names, inputs, and
outputs. This behavior is part of its documented evidence contract.

Treat grading input as read-only. A grader instance can grade several sessions
concurrently. Keep only immutable arguments on the grader instance. Send LLM calls
through the shared `llm.client`.
