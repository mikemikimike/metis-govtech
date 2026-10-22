# Report Contract

This document defines the target and data contract for the METIS target evaluation
report. The
report is an investigation dashboard for a target owner. It presents evaluation
evidence. It does not make release decisions or set target priorities.

## File contract and current input support

The insights [Report model](../../packages/insights/src/metis/insights/_models.py) defines `report.json`.
The report writer validates data through this model. Saved reports contain `"schema_version": 1`.
The model defaults a missing version to `1` and rejects other explicit values.
The version remains `1` during the `next` pre-release phase.

The Insights CLI reads `metis.core.reporting.EvaluationResults` from
`outputs/reports/results.json`. Each `GraderRecord` in its `records` list is one grader run
on one session, with one or more `RecordedResult` entries. The command joins records to the
frozen `inputs/specification.yaml` and to the saved `outputs/trials/*/record.json` files.
Trial conversations come from the traces in `outputs/traces/` that `evaluate` saved.
It writes `report.json` and an offline `report.html` beside the results file. A results
file in the format from before the grader redesign has `turn_results` or `session_results`.
The CLI rejects that file and writes no report. Insights does not create graders.

## Reader and purpose

- The primary reader is the target owner.
- The report shows all measured target features and lets the target owner decide what to
  investigate or prioritize.
- The report can state direct facts from the evaluation data. It must not add urgency,
  investment, release, or target-priority judgements.
- The report must keep the detailed evidence needed by evaluators.

## Summary facts

The summary shows these facts before the evidence explorer:

1. Trial success, calculated from completed simulation outcomes.
2. Evaluated grader pass rate and mean score, calculated from grader runs that the report
   can attribute to the target specification.
3. Feature results.
4. Coverage gaps and evaluation-data errors.
5. Repeated exact error messages from unsuccessful trials.

Show one templated sentence below the target name. State how many features have evaluated
runs and name the feature with the lowest pass rate. Generate all values from report data.

Trial success and evaluated grader pass rate are separate measures. Neither value is an
overall target score. The report must label both measures and show their denominators.

## Temporary pass contract

A grader returns one result for each scope item, such as one trace or the whole session.
Each result is already combined inside the grader by its declared aggregation. See the
[grader guide](library/graders.md). The report reads only the recorded results. It does
not inspect the grader. How the results of one record combine into one run score is not
decided yet. Until then, the report uses this contract:

1. Each `GraderRecord` is one grader run. Its combined score is the equal-weight mean of
   its scored results.
2. Compare the combined score with the recorded `grader_args.threshold`. A score at or above
   the threshold passes. A lower score fails.
3. A scored run needs a finite numeric threshold from 0 to 1. A missing or invalid threshold
   stops report generation, and the error names the run.
4. A run with no scored results is errored if any result errored. Otherwise, it is skipped.
5. Exclude skipped and errored runs from rates and mean scores. Show their counts beside
   every rate and mean score.
6. Show the numeric rate, mean score, status, recorded threshold, judge model, and
   passed/failed/skipped/errored counts.

Partial skipped or errored results stay visible as raw evidence when a run has scored
results. They do not add extra run verdicts. Original result outcomes and scores stay
unchanged.

The visible states are:

- No failed runs
- Has failed runs
- Not evaluated
- Grader error: a grader run errored. This says something about the grader, not the target.
- Data error: a grader setup or mapping problem.

## Hierarchy roll-up

Each item shows two numbers:

- **Pass rate:** the share of grader runs that passed. A run passes when its score is at or
  above the recorded threshold.
- **Mean score:** the average score from 0 to 1, before the threshold.

The two numbers can differ. Runs that score just below the threshold give a low pass rate
and a high mean score.

The table shows how each item calculates both numbers, from the most detailed item to the
least detailed. A grader run is one `GraderRecord`.

| Item | How it is averaged |
| --- | --- |
| Grader run | Equal-weight mean of its scored results. The run passes or fails by the [temporary pass contract](#temporary-pass-contract). A trial tab shows one grader run for each criterion. |
| Grader runs across all trials of one test case | Mean of the grader runs of one criterion, over all trials in one test case. The results table shows this number in each cell. |
| Criterion | Mean of all its grader runs, over all test cases. |
| Behaviour | Mean of its evaluated criteria. |
| Feature | Mean of its evaluated behaviours. |
| Headline result | Mean of the evaluated features. |

Every mean is unweighted, so each item in it counts once. For a pass rate, a passed run
counts as 1 and a failed run as 0. The mean of a criterion's runs is therefore passed runs /
evaluated runs. A behaviour takes the mean of its criteria and not of their runs. A
criterion with many runs then has the same weight as a criterion with few runs.

`report.json` also has persona and scenario rows in `axes`. Each row is the mean of the
evaluated criteria, each calculated over the runs for that persona or scenario. These rows
have a pass rate only. The HTML page does not show them.

The terminal summary has one row per criterion and grader, which uses the criterion rule.
Its last row is the mean of the criterion rows.

These rules apply to every item:

- An evaluated run passed or failed. Skipped and errored runs are left out of rates and mean
  scores.
- A child counts only when it has at least one scored run. A node with no usable evidence
  is Not evaluated.
- A grader setup or mapping problem is Data error.
- Counts beside a rate are the totals of the runs below it. They show coverage. They do not
  weight the mean. Calculate from unrounded values.

The normalized profile gives each criterion a name and an ID. Report JSON uses the criterion
ID as the criterion key and tree title. A criterion names one grader. Criteria, table
columns, and unmapped entries use `grader_fqn` for the full grader path and `grader_name`
for its display label. The display label never identifies a criterion or a recorded
result. Scores retain Task, Trial, Session, Criterion, Grader FQN, and arguments.
IDs join Features, Behaviours, Criteria, Personas, Scenarios, Tasks, and
grader records. The insights [Report model](../../packages/insights/src/metis/insights/_models.py)
defines these fields.

A record joins to a criterion through its task and criterion IDs. The recorded scenario must
match the task scenario, and the task must select the criterion's behaviour. When trial
records are available, a record joins to a trial through its task ID, trial index, and
session ID. A different session cannot inherit that trial's persona or outcome. The report
rejects two grader records for the same task, trial index, session, and criterion.

The terminal summary includes all stored grader runs, with one row per criterion and grader.
It has no specification, so its last row is the unweighted mean of the criterion rows. The
report's hierarchy, axes, and headline use runs that match the specification. Unmatched runs
stay in `unmapped` with a reason and their original grader records. Distinct reasons stay in
separate groups. The top-level `results` count includes every raw result, including
unmatched results.

These rules are report inputs. The report must not replace an aggregator-supplied rate
or aggregation method.

## Failure evidence

- For a selected criterion, use one `Raw results` section.
- Use multi-select persona and scenario filters that omit values with no result for the
  selected criterion.
- Show the exact grader reason in each raw result.
- Each raw result keeps its task, trial index, session, criterion, grader FQN, recorded grader
  arguments, outcome, score, reason, and position within its grader record. It also shows
  the run's combined score, threshold, and verdict. Core results do not store a trace ID or
  a conversation position, and the report does not infer either value.
- Each raw result has an expandable `Recorded grader settings` section with the grader FQN
  and the recorded grader arguments of that run.
- Show results that match no Task and Criterion in a separate `Results without a matching
  criterion` section. Group them by criterion ID, grader FQN, and reason. These results are
  excluded from the target pass rate.
- The report shows the recorded failure source. A target-response error is from the
  target. A user-agent LLM failure is from the user agent. A simulation crash is from
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
- Below the segmented outcome bar, show a table with feature, scenario, persona, error
  source, exact recorded message, and evaluation count. Open the table on the `Errors`
  view. If a scenario covers multiple features, list the features in one cell and count each
  trial once. Expanding a row shows the affected trials. If an abandonment has no error
  message, state that no error message was recorded.

## Information architecture

- Show every feature at the first hierarchy level.
- Keep behaviours, criteria, and graders accessible through expansion.
- Do not require all hierarchy levels to be expanded at the same time.
- Do not impose a target-level limit on the number of result nodes.
- Search and filters can inspect the complete data set.
- Default ordering must not claim to be a target-priority order.
- Put the result explorer in two tabs: `Experiment tree` and `Results table`.
- Keep the tree as the default view.
- In the table, use one row per Task, identified by its ID. Group grader columns by feature.
- In each grader cell, pool the grader runs of all trials in that Task for that criterion.
  Show the pass rate, mean score, and run counts. Exclude skipped and errored runs from the
  rate. Keep the separate status squares for trial outcomes.
- Let the reader expand a row and select a trial tab. The tab shows that trial's result for
  each criterion and its user-agent and target turns. Trial data keeps the engine's
  `total_turns` value.
- Do not show a separate persona and scenario coverage section. The table shows who and
  what ran.

## Implementation boundary

The report file contract, report generation, and its content rules belong in
`metis-insights`. A generated report file is not a source of truth.

The report must accept future aggregator-owned fields without changing this interface
contract. The aggregator can take full ownership of rates, thresholds, counts, statuses,
and aggregation methods in a later change.
