# Graders

A grader judges one session of the target. It sees only what the target left behind (the
session's Langfuse traces and the artifacts the run produced, as a `GradingInput`), returns a
score for each grading scope it chooses, and never decides pass or fail. The engine applies the
criterion's `threshold` (`score >= threshold` passes).

The contract lives in `metis.library.grader`; this package holds the graders built on it.

## Writing one

```python
class TraceBudgetArgs(GraderArgs):
    max_traces: int = Field(default=10, ge=1, strict=True)


class TraceBudgetGrader(Grader[TraceBudgetArgs]):
    args_model = TraceBudgetArgs  # must name the same class as the type argument

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput: ...
```

Then export it from `__init__.py`. A criterion uses it as:

```yaml
grader_fqn: metis.library.graders.TraceBudgetGrader
grader_args:
  max_traces: 4
```

## Judge output instructions

Shared output instructions live in [`metis.library.judgment`](../judgment.py).
Edit `OUTPUT_INSTRUCTIONS[JudgmentShape.BINARY]` there to change the binary prompt for all
judges that use it. This configuration map uses the judgment shape enum as its key.
Keep the instructions consistent with the `BinaryJudgment` response model in the same module.

Select the judgment shape once, then use its instructions and response model:

```python
from metis.library.judgment import OUTPUT_INSTRUCTIONS, JudgmentShape

shape = JudgmentShape.BINARY
prompt = assessment_prompt + "\n\nOutput instructions:\n" + OUTPUT_INSTRUCTIONS[shape]
response_schema = shape.response_model.model_json_schema()
result = shape.response_model.model_validate_json(response_text)
```

Only binary output is supported. To add another judgment shape, follow the same pattern in
`judgment.py`: add a `JudgmentShape` enum member, its text in `OUTPUT_INSTRUCTIONS`, and a
response model with matching validation. Add the model to `JudgmentShape.response_model`,
then select the new enum member in your grader. The prompt construction code above stays
the same.

## Rules

- **Args.** Every key under `grader_args` is a field of `args_model`. Unknown keys are
  rejected before the run. A model-based grader's args extend `JudgeArgs`, whose `model` the
  engine fills in.
- **Scope.** Return one result per thing you judge: per trace, per session, or per retry chain.
  A per-trace grader should judge trace `i` against `input.traces[: i + 1]` only, so it
  cannot see what came after.
- **Nothing to judge** → one `GraderResult(status="skipped", reason=...)`. Never `[]`, never a
  pass.
- **Could not judge** (an LLM call failed after retries, or the reply was unparseable) →
  `status="errored"` for that part, then carry on. Never a score of 0.
- **No state.** One instance grades every session of its criterion concurrently. Keep nothing
  on `self` except `self.args`, and treat `input` as read-only.
- **LLM calls** go through `llm.client` (a shared `AsyncOpenAI`). Never read env vars or build
  your own client.
- **No harness metadata.** A grader never sees the scenario, persona or stop reason. Pass a
  reference value through args instead.
