# Report Contract

This document defines the product and data contract for the METIS product evaluation
report. The
report is an investigation dashboard for a product owner. It presents evaluation
evidence. It does not make release decisions or set product priorities.

## Reader and purpose

- The primary reader is the product owner.
- The report shows all measured product tasks and lets the product owner decide what to
  investigate or prioritize.
- The report can state direct facts from the evaluation data. It must not add urgency,
  investment, release, or product-priority judgements.
- The report must keep the detailed evidence needed by evaluators.

## Summary facts

The summary shows these facts before the evidence explorer:

1. Trial success, calculated from completed simulation outcomes.
2. Evaluated metric pass rate, calculated from pass and fail results that the report
   can attribute to the product specification.
3. Task results.
4. Coverage gaps and evaluation-data errors.
5. Repeated exact error messages from unsuccessful trials.

Show one templated sentence below the product name. State how many evaluated task scores
are below the pass threshold and name the lowest-scoring task. Generate all values from
report data.

Trial success and evaluated metric pass rate are separate measures. Neither value is an
overall product score. The report must label both measures and show their denominators.

## Temporary pass contract

The aggregator is the future authority for rates, thresholds, counts, statuses, and
aggregation methods. Until it supplies all of that metadata, the report uses this
fallback contract:

1. Use a value supplied by the aggregator when it exists.
2. Calculate a missing rate as `pass / (pass + fail)`.
3. Exclude skipped results from the rate denominator.
4. Use a 70% pass threshold when the aggregator supplies no threshold.
5. Treat exactly 70% as Pass.
6. Show the numeric rate, Pass or Fail status, threshold, and pass/fail/skip counts.

The visible states are:

- Pass
- Fail
- Not evaluated
- Data error

## Hierarchy roll-up

The report uses these aggregation rules:

- A criterion aggregates metric results from different trials with
  `pass / (pass + fail)`.
- A behaviour uses the lowest non-null criterion rate.
- A task uses the lowest non-null behaviour rate.
- A node with no usable evidence is Not evaluated.
- A metric setup or mapping problem is Data error.

The normalized profile gives each criterion a name and a stable ID. Report JSON keeps its
current contract and uses the stable criterion ID as the criterion key and tree title.
The criterion name is part of the profile contract; the report uses the exact metric result
name as the metric title. If a result is missing, it uses the metric class display name as
a fallback. Stable IDs join Tasks, Behaviours, Criteria, Personas, Scenarios, and metric
results. The report JSON Schema remains unchanged.

These rules are report inputs. The report must not replace an aggregator-supplied rate
or aggregation method.

## Failure evidence

- For a selected metric, use one `Individual results` section.
- Use multi-select persona and scenario filters that omit values with no result for the
  selected metric.
- Show the exact evaluator message in each individual result.
- The report shows the recorded failure source. A product-response error is from the
  product. A user-agent LLM failure is from the user agent. A simulation crash is from
  the evaluation runner.
- For old records that do not contain a failure source, the report can use the matching
  simulation log only when the log explicitly names the source.
- The report does not infer a failure source from message text. It does not assign a
  cause.
- The report does not adjust scores or exclude unsuccessful trials.
- It groups unsuccessful trials only when their recorded source and error-message text
  are exactly equal.
- Each error-message group shows its count, scenarios, personas, and trial identifiers.
- The report keeps the recorded message text. It does not rewrite the message into a
  new cause or summary.
- Below the segmented outcome bar, show a table with task, scenario, persona, error
  source, exact recorded message, and evaluation count. Open the table on the `Errors`
  view. If a scenario covers multiple tasks, list the tasks in one cell and count each
  trial once. Expanding a row shows the affected trials. If an abandonment has no error
  message, state that no error message was recorded.

## Information architecture

- Show every task at the first hierarchy level.
- Keep behaviours, criteria, and metrics accessible through expansion.
- Do not require all hierarchy levels to be expanded at the same time.
- Do not impose a product-level limit on the number of result nodes.
- Search and filters can inspect the complete data set.
- Default ordering must not claim to be a product-priority order.
- Put the result explorer in two tabs: `Experiment tree` and `Results table`.
- Keep the tree as the default view.
- In the table, use one row per persona and scenario pair. Group metric columns by task.
- In each metric cell, show the percentage of evaluated trials that pass. Give each
  trial equal weight. Exclude skipped and not-run trials from the denominator. Keep the
  separate status squares for trial outcomes.
- Let the reader expand a row, select a trial tab, and read its user-agent and product
  turns.
- Do not show a separate persona and scenario coverage section. The table shows who and
  what ran.

## Implementation boundary

The report contract belongs in the report generator and its tests. A one-off generated
report file is not a source of truth.

The report must accept future aggregator-owned fields without changing this interface
contract. The aggregator can take full ownership of rates, thresholds, counts, statuses,
and aggregation methods in a later change.
