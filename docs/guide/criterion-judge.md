# Edit the criterion fallback judge

The guided Interview selects `metis.library.graders.CriterionJudgeGrader` when no specific
scorer matches a criterion. It also uses this judge when the embedding provider fails.
The manual form does not offer this judge because that form has no criterion description field.

1. Export the Interview specification.
2. Find the criterion under `features[].behaviours[].criteria[]` in `specification.yaml`.
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

Each description clause must contain text. The engine joins the clauses as
`Given ..., when ..., then ... .` and supplies that text to the judge at run time.
Do not add `criterion` under `grader_args`. The engine rejects a second instruction source.

You can set `grader_args.model` to select a judge model for this criterion. If you omit it,
the engine uses `defaults.judge_model`, then `JUDGE_MODEL`, then its package default.
The result record contains the resolved model, threshold, and criterion instructions.

An experiment copies its specification into `inputs/specification.yaml`. Evaluation reads
that copy. To evaluate an existing experiment with new instructions, edit the description
in that copy before you run evaluation again. Keep the previous result file if you need
to compare the assessments.

The judge returns one result for the whole session. A score of `1` means that the recorded
evidence satisfies the criterion. A score of `0` means that it does not. The engine marks
a score as passed when it is at least the threshold. Keep the default threshold of `0.5`
for this binary score rule. A threshold of `0` also passes a score of `0`.

The judge receives observation IDs, parent IDs, types, names, inputs, and outputs, grouped
by trace. It does not receive trace metadata or timing fields. It does not read artifact files.
A file path or a recorded claim about a file cannot establish the file's contents.
Use a specific grader when the criterion requires evidence outside the supported trace fields.

A session with no recorded input or output is skipped without a model call. The model can
also skip a criterion when the session has no applicable evidence. Provider failures and
invalid replies produce errored results. Skipped and errored results do not count as failures.

## Test the fallback judge

Run these offline checks from the repository root:

```bash
uv run pytest tests/unit/library/test_criterion_judge.py tests/unit/wizard/application/test_matcher.py tests/integration/wizard/test_matching.py -q
uv run pytest tests/integration/wizard/test_compile.py -k 'edited_yaml_description or invalid_fallback' -q
uv run pytest tests/unit/wizard/application/test_driver.py -k fallback_parameter -q
npm --prefix apps/web test
```

The judge tests use the real OpenAI client with an in-memory HTTP transport and a dummy key.
They make no provider requests. The YAML test writes the exported specification, edits only
its description, loads it through the engine, and checks the request and result record.

Run `make ci` for the complete repository checks. If the unrelated user-agent tests need an
OpenAI key to construct their offline client, use `OPENAI_API_KEY=test-only make ci`.
Do not use that dummy key for a provider check.

For a provider check, configure `JUDGE_API_KEY`, `JUDGE_BASE_URL`, and `JUDGE_MODEL` for your
supported gateway. Use a completed experiment with available traces. Edit its
`inputs/specification.yaml` description, then run:

```bash
uv run metis engine evaluate --experiment-dir path/to/completed-experiment
```

Check `outputs/reports/results.json`. Find the criterion's record. Confirm that
`grader_args.criterion` contains the edited description and that `grader_args.model` is correct.
Check the result's reason and outcome against the recorded evidence. This check confirms
provider compatibility. It does not establish grading accuracy.

For code review, check the shared argument preparation function, the engine's reference
construction, and the wizard's validation calls. Each must use the current description.
Check that unknown settings fail before execution and that invalid form edits preserve the
prior settings. Review the fixed response validation and the evidence sent to the model.
The fallback must stay outside similarity matching and the manual form's scorer choices.
