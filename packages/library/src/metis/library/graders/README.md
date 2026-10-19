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
