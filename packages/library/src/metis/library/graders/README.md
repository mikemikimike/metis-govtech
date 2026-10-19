# Graders

A grader judges one session of the target. It sees only what the target left behind (the
session's Langfuse traces and the artifacts the run produced, as a `GradingInput`), returns a
score for each grading scope it chooses, and never decides pass or fail. The engine applies the
criterion's `threshold` (`score >= threshold` passes).

The contract lives in `metis.library.grader`; this package holds the graders built on it. It
exports none yet: the only graders so far are the demos in `metis.library.graders.demo`, which
the wizard never offers (#470).

## Writing one

```python
class DemoTraceBudgetArgs(GraderArgs):
    max_traces: int = Field(default=10, ge=1, strict=True)


class DemoTraceBudgetGrader(Grader[DemoTraceBudgetArgs]):
    args_model = DemoTraceBudgetArgs  # must name the same class as the type argument

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput: ...
```

Then export it from `__init__.py` (a demo, from `demo/__init__.py` only). A criterion uses it
as:

```yaml
grader_fqn: metis.library.graders.demo.DemoTraceBudgetGrader
grader_args:
  max_traces: 4
```

## Reading traces

Read a session through `metis.core.trace_processing`, never through an observation's `input`,
`output` or `metadata`. Those hold whatever the target's application sent; the processor knows
which shapes it can read and says so when it can't.

- **Units.** `turns(input)` gives one `Turn` per trace, oldest first: `user` and `reply` as text,
  every `tool_calls` entry at any depth with the agent that made it, and `target_errors`. Pick
  units with `select_all`, `select_final` or `select_where`, then read them.
- **Problems.** A reader returns a value or a `Problem`. A `Problem` is METIS failing to read
  something, never the target failing: map `no_match` and `artifact_unavailable` to `skipped`,
  and `unsupported` and `missing` to `errored` or `skipped`. Never score it.
- **Target errors.** `Turn.target_errors` (no reply, or an observation Langfuse marked
  `ERROR`/`WARNING`) is evidence about the target. Grade it: a turn with a target error is
  judged even when its reply is a `Problem`, since the missing reply is the target's failure.
- **Judges.** Give an LLM judge `render_transcript(...)`, the same view every judge sees. A
  per-turn judge passes `turns[: i + 1]` so it never sees what came after.
- **Files.** `find_artifacts(input, name)` returns every received file with that name; the
  processor never opens them. Media a target uploaded to Langfuse (an image in a message, say)
  is not available: text holding a Langfuse media reference reads as an `unsupported` problem.

The demos in `metis.library.graders.demo` show each of these on a real captured session.

## Rules

- **Args.** Every key under `grader_args` is a field of `args_model`. Unknown keys are
  rejected before the run. A model-based grader's args extend `JudgeArgs`, whose `model` the
  engine fills in.
- **Scope.** Return one result per thing you judge: per turn, per session, or per retry chain.
  A per-turn grader should judge turn `i` against `turns[: i + 1]` only, so it cannot see what
  came after.
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
