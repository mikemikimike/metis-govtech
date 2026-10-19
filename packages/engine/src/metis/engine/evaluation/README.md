# Evaluation

Runs each criterion's grader on every session it applies to and records the results as
`results.json`. The CLI loop that drives this is `_evaluate_records` in
`../cli.py`; this package holds the pieces it uses.

## Flow

```
specification.yaml criteria ──▶ build_criterion_grader (once per criterion)
                                   resolve FQN → Grader subclass
                                   resolve judge model (JudgeArgs only)
                                   validate grader_args against args_model
trial record ──▶ fetch_session ──▶ GradingInput (every trace + artifacts)
                                   │
                 grade_session ◀───┘  every grader once, concurrently
                    grader.grade(input, llm) → GradingOutput (scores per grading scope)
                    record_results: passed iff score ≥ threshold; [] or raise → errored
                 ──▶ one GraderRecord per grader per session ──▶ EvaluationResults
```

## Judge settings (`judge.py`)

| Setting | Where it comes from |
|---|---|
| Judge model | `grader_args.model` → `defaults.judge_model` in the spec → `JUDGE_MODEL` → `gemini-3.5-flash-lite`. Written into the args before validation, so every record names its model. |
| Input limit | `grader_args.max_input_tokens` → `JUDGE_MAX_INPUT_TOKENS` → 128,000. A grader checks it with `input_budget_error` before each model call. An invalid value logs a warning and uses the default. |
| Criterion instructions | A `CriterionJudgeArgs` grader gets `criterion` from the criterion description, carried on `GraderRef.description`. A `criterion` key under `grader_args` is a setup error. |
| Gateway | `JUDGE_API_KEY` / `JUDGE_BASE_URL`, falling back to `OPENAI_API_KEY` / `OPENAI_BASE_URL`. Required only if some criterion's grader extends `JudgeArgs`. |
| Concurrency cap | One shared `AsyncOpenAI` client, at most 50 connections, every grader LLM call from every grader run queues for one. |
| Timeout | 300 s per request once sent; no timeout on waiting for a connection (`pool=None`), so queued calls are never recorded as errored. |

Retries are the OpenAI SDK's own (`max_retries=2`). There is no per-grader-run timeout.

## Outcomes

A grader returns a score; it never decides pass or fail.

| Grader returns | Recorded as |
|---|---|
| `scored`, `score >= threshold` | `passed` |
| `scored`, `score < threshold` | `failed` |
| `skipped` | `skipped` (nothing to judge; never a pass) |
| `errored` | `errored` (could not judge; never a fail) |
| no results, wrong type, or raises | one `errored` result for the grader run |

## Structure

```
evaluation/
├── judge.py         — judge-model resolution, JudgeGateway, build_llm_settings
└── orchestrator.py  — build_criterion_grader, grade_session, record_results
```

The Langfuse fetch lives in `../extractor/`; the grader contract in `metis.library.grader`.
