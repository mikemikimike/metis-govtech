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
evidence as `errored`, with a reason that says what is missing.

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
| `aggregations` | Rules that a multi-rule grader can use to combine its rules. |

A tuple with one value records a fixed capability. A tuple with several values records
several implemented capabilities. The declaration itself does not select a value for
one grading request.

A taxonomy value is a named enum member, such as `Scope.TRACE` or
`JudgmentForm.BINARY`. A taxonomy definition can hold shared behavior for one value.
This behavior can include evidence preparation, prompt text, response validation, or
aggregation logic.

The enums define the accepted vocabulary for future grader implementations. An enum
member alone does not provide runtime support.

Three shared definition registries hold this behavior. Each holds only the values that
a grader uses:

| Registry | Module | Values | What a definition holds |
|---|---|---|---|
| `SCOPE_DEFINITIONS` | `metis.library.scope` | `TRACE`, `SUBSESSION`, `SESSION`, `ARTIFACT` | The judge instructions for the scope, the trace processor function that selects what to judge, and the one that renders it. |
| `JUDGMENT_FORM_DEFINITIONS` | `metis.library.judgment_form` | `BINARY` | The output instructions and the reply model (`BinaryJudgment`: status, score, reason). |
| `AGGREGATION_DEFINITIONS` | `metis.library.aggregation` | `NONE_SINGLE_SCORE`, `PASS_IF_ALL`, `PASS_IF_ANY` | The function that combines a multi-rule grader's per-rule results into one result. |

Each scope pairs a select function with a render function, both in
`metis.core.trace_processing`. The select function returns what to judge, under the label
of its result. The render function turns one of them into what the judge reads:

| Scope | Select | One entry | Render | The judge reads |
|---|---|---|---|---|
| `TRACE` | `select_by_turn` | `"turn:3"`: one turn | `render_session` | that turn only |
| `SUBSESSION` | `select_by_window` | `"turns:2-4"`: a run of turns | `render_session` | those turns |
| `SESSION` | `select_session` | `"session"`: every turn | `render_session` | every turn |
| `ARTIFACT` | `select_by_artifact` | `"artifact:a.pdf"`: the latest revision of a file | `render_artifact` | the file only |

A subsession ends at a turn and holds up to `window` turns. A `window` that is not set
holds every turn before the end turn, so a grader that judges one turn with the
conversation so far as context declares `SUBSESSION`. A grader that needs another view of
the same turns, such as `render_dialogue`, calls that render function itself.

`metis.library.judge.judge` judges one rendered piece against one criterion. It builds the
prompt from the grader's criteria and the scope and judgment form definitions, and returns
the judge's reply as one result. A `Problem` from a select or render function is errored
without a judge call, and so is a reply that the criterion does not apply.

A multi-rule grader, such as `TaskConstraintAdherenceGrader`, loops over its rules in its
own `grade()`. It calls `judge` once for each rule, then combines the rule results with
`AGGREGATION_DEFINITIONS[self.aggregation]`. Under `pass_if_all`, a failed rule makes the
piece fail, even when another rule errored. Otherwise an errored rule makes the piece
errored, and otherwise it passes. Under `pass_if_any`, a passing rule makes the piece pass,
even when another rule errored.

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
budget and `0` when the count exceeds it. An empty session produces an errored result.
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

`GraderArgs` defines three taxonomy settings once for every grader: `scope`,
`judgment_form`, and `aggregation`. A grader's own args model does not declare them. A
setting that is not set means the grader's first declared value. `Grader.scope`,
`Grader.judgment_form`, and `Grader.aggregation` give the value in use. When a grader is
built, it rejects a value that its taxonomy does not declare, and the engine reports the
error before the run. A spec author sets one only on a grader that declares more than one
value, and the wizard shows it only there.

A scope's own settings come from a template class in `metis.library.scope`: `TraceArgs`
gives `turn` (`each` or `last`), `SubsessionArgs` gives `turn` and `window` (how many turns end at that turn), and
`ArtifactArgs` gives `artifact` (the file name). A grader's args model inherits the class
for each scope it declares, and `Grader` checks this when the class is defined.
`metis.library.judge.TaskArgs` gives the optional `task_description`. The taxonomy records
support. The argument model records a selection for one criterion.

The current Criterion Judge has no measure mapping and fixed values in
the other five groups. Its arguments contain its criterion text, model, input limit,
and passing threshold. The criterion text defines the check. The args model has no
taxonomy selection fields.

## Results and evidence

`GradingInput` contains the recorded traces and artifact records for one session. A
grader does not receive the scenario, persona, or stop reason.

A grader returns `GradingOutput` with one result for each thing it judged, and at least one
result. Use:

- `scored` when the grader made an assessment;
- `errored` when the assessment cannot complete.

Before any judge call, a grader checks that the session has the evidence its measure
needs. For example, a tool argument grader needs recorded tool calls. When the evidence
is absent, the grader returns one `errored` result that says what is missing. When the
evidence is present but the event that the measure looks for did not happen, such as a
correction grader on a session with no correction, the result is also `errored` with the
reason. Errored results have no score. The engine applies the criterion threshold to
scored results.

`GraderResult.scope` names what the result is about: `"session"`, `"turn:3"`, or
`"artifact:report.pdf"`. A multi-rule grader returns one result for each thing it judged, combined
from its rules. The engine records the aggregation rule on `GraderRecord.aggregation`.

Evidence requirements are part of the declared support. Recorded state can support a
judgment. Unobserved live state cannot. At `ARTIFACT` scope, the judge call attaches
the file and the judge model reads it. METIS does not extract text from files. A model
or gateway that rejects a file type gives an errored result with its reason. Missing
required evidence cannot produce a passing result.

## Current limits

The taxonomy is library metadata. The base `Grader` contract does not require it. The
engine reads only the aggregation rule, which it records on `GraderRecord.aggregation`.
The wizard, insights, and reports do not inspect the taxonomy.

Scope, judgment form, and aggregation values have shared runtime behavior. Grader type,
reference type, and measure values are descriptive declarations.

A multi-rule grader combines its rules itself. Insights combines the
results of one grader run with an equal-weight mean.

The taxonomy does not test validity, reliability, calibration, or agreement with
human assessors. Those properties need a separate evaluation method.

## Decisions needed for further implementations

The following work is outside this foundation:

- A grader with several capabilities needs explicit selection arguments and validation
  of supported combinations. Tuple membership does not establish every combination.
- Subsession graders need rules for trace membership, ordering, and the context visible
  to each judgment. Their results need a way to identify the selected evidence.
- Internal aggregation combines the rules within one judgment's scope. Cross-trial
  aggregation belongs to reporting. Each new aggregation rule needs to define its score
  meaning and required settings, such as weights.
- Shared definitions for grader type, reference type, and measure need concrete consumers
  before they become registries.

## Author a grader

1. Define an arguments model that extends `GraderArgs`. For an LLM judge, extend
   `JudgeArgs`. Declare reference values and selection arguments in that model.
2. Subclass `Grader[YourArgs]`. Set `args_model = YourArgs` to the same class.
3. Declare a `GraderTaxonomy` that describes the behavior you implement. Start with
   fixed capabilities when the grader needs only one combination.
4. Implement `async grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput`.
   Apply the evidence and result rules in this guide. An LLM grader selects what to judge
   with its scope's select function, checks any evidence its measure needs, renders each
   selected piece, and calls `metis.library.judge.judge` once for each:

   ```python
   async def grade(self, input, llm):
       scope = SCOPE_DEFINITIONS[self.scope]
       selected = scope.select(input, self.args)
       if isinstance(selected, Problem):
           return GradingOutput.errored(selected.detail)
       return GradingOutput(
           results=[
               await judge(self, llm, label, scope.render(thing), self.criteria())
               for label, thing in selected.items()
           ]
       )
   ```

   `judge` adds the scope instructions, the untrusted-evidence rule, and the output
   instructions to the criteria, checks `input_budget_error`, and uses `llm.client`.
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
first. The select functions choose what to judge, and the render functions show it to the
judge. `render_session` shows everything the trace records, in time order: the user's
message, each agent's system prompt (once), what each model call wrote, sub-agent handoffs,
tool calls, errors at the observation where they happened, and the reply. With
`tool_results=True`, it adds each tool call's status and result, and `max_chars` cuts long
payloads. `render_dialogue` shows only what the user and the agent said to each other.

Readers return a value or a `Problem`. A `Problem` means that METIS could not read the
evidence. Map every `Problem` to `errored`, with its detail in the reason. Never score a
`Problem`.
A recorded target error is evidence about the target and can support an assessment.

`find_artifacts` returns the records of the files the target produced, and `find_fixtures`
returns the records of the files the user gave the target. Neither opens a file. Langfuse media
references are unavailable to these readers. For a judgment of one trace, provide
only the context permitted by the grader's contract. Exclude later traces when the
judgment must use only information available at that point.

Treat grading input as read-only. A grader instance can grade several sessions
concurrently. Keep only immutable arguments on the grader instance. Send LLM calls
through the shared `llm.client`.
