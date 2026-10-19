# Edit the criterion fallback judge

The guided Interview selects `metis.library.graders.CriterionJudgeGrader` for a criterion when
no specific grader matches it. The Interview also selects this judge when the embedding provider
fails. The judge uses the criterion description as its instructions. The manual form does not
offer this judge, because the form has no criterion description field.

## Edit the instructions

To change what the judge checks, edit the criterion description:

1. Export the Interview specification.
2. In `specification.yaml`, find the criterion under `features[].behaviours[].criteria[]`.
3. Edit its `description.given`, `description.when`, and `description.then` clauses.
4. Save the file before you start the next simulation.

For example, a criterion can contain these fields:

```yaml
id: AC-1-1
name: Cite sources
description:
  given: a question that needs evidence
  when: the target returns an answer
  then: each factual claim has a source citation
grader_fqn: metis.library.graders.CriterionJudgeGrader
grader_args:
  threshold: 0.5
```

Each description clause must contain text. At run time, the engine joins the clauses as
`Given ..., when ..., then ... .` and gives that text to the judge as `grader_args.criterion`.
Do not set `criterion` under `grader_args` yourself. The engine reports it as a setup error
before the run starts.

An experiment copies its specification into `inputs/specification.yaml`, and evaluation reads
that copy. To evaluate an existing experiment with new instructions, edit the description in
that copy, then run evaluation again. To compare the old and new assessments, keep a copy of
the previous result file first.

## Settings

| Setting | Default | Description |
|---|---|---|
| `threshold` | `0.5` | A score passes when it is at least this value. Keep `0.5` for the binary score. A threshold of `0` also passes a score of `0`. |
| `model` | See the next paragraph. | The judge model for this criterion. |
| `max_input_tokens` | `128000` | The largest estimated request that the judge sends. |

If you omit `model`, the engine uses `defaults.judge_model`, then `JUDGE_MODEL`, then its
package default. If you omit `max_input_tokens`, the engine uses `JUDGE_MAX_INPUT_TOKENS`, then
`128000`. If the value from either source is not a positive integer, the engine logs a warning
and uses `128000`. The result record contains the resolved model, threshold, input limit, and
criterion instructions.

Before each model call, the judge estimates the size of the request as one token for each
UTF-8 byte, plus 4,096. If the estimate is more than `max_input_tokens`, the judge records an
errored result and does not call the model. The reason gives the estimate and the limit. The
estimate is conservative, so a model with a large context window can accept a request that is
above the default. To judge such a session, raise the limit.

## Results

The judge returns one result for the whole session:

- A score of `1` means that the recorded evidence satisfies the criterion.
- A score of `0` means that the recorded evidence does not satisfy the criterion.
- A skipped result means that the session has no applicable evidence. A session with no recorded
  input or output is skipped without a model call.
- An errored result means that the request was above the input limit, that the provider failed,
  or that the reply was not valid.

Skipped and errored results do not count as failures.

## Evidence that the judge reads

The judge receives these fields of each observation, grouped by trace: the ID, the parent ID,
the type, the name, the input, and the output. It does not receive trace metadata or timing
fields. It does not read artifact files, so a file path or a recorded claim about a file does
not show what the file contains. If the criterion needs other evidence, select a specific
grader.

## Check the judge with a provider

The offline tests do not call a provider. To confirm that your gateway accepts the judge
request, use a completed experiment with available traces:

1. Set `JUDGE_API_KEY`, `JUDGE_BASE_URL`, and `JUDGE_MODEL` for your gateway.
2. Edit the criterion description in the experiment's `inputs/specification.yaml`.
3. Run the evaluation:

   ```bash
   uv run metis engine evaluate --experiment-dir path/to/completed-experiment
   ```

4. In `outputs/reports/results.json`, find the record for the criterion.
5. Confirm that `grader_args.criterion` contains the edited description and that
   `grader_args.model` names the model that you set.
6. Compare the reason and the outcome of the result with the recorded evidence.

This check shows that the provider accepts the request. It does not measure grading accuracy.
