# Graders

All graders live in `metis.library.graders` and are imported by their class name:

```python
from metis.library.graders import RoutingAccuracyGrader
```

On each Criterion in `specification.yaml`, use the package-level FQN and arguments:

```yaml
grader_fqn: metis.library.graders.TurnBudgetGrader
grader_args:
  max_turns: 8
```

## Classification via tags

Each grader class carries a `tags: ClassVar[tuple[str, ...]]` for multi-dimensional classification. File layout is a developer ergonomics concern only — it carries no semantic weight.

| Dimension | Values |
|-----------|--------|
| Component | `orchestration`, `analysis`, `presentation`, `universal` |
| Granularity | `per-turn`, `session-level` |
| Grading | `code-graded`, `judge-graded` |

Example:

```python
class RoutingAccuracyGrader(MetisTurnGrader):
    tags: ClassVar[tuple[str, ...]] = ("orchestration", "per-turn", "judge-graded")
```

## Evaluation routing

The engine routes graders automatically by type:

- **Session graders** (`BaseConversationalMetric` subclasses, tagged `"session-level"`) run against the full multi-turn `ConversationalTestCase` for each session.
- **Per-turn graders** (tagged `"per-turn"`) run against each individual `LLMTestCase`.

Both can be listed together in `specification.yaml` — no annotation needed.

## File layout

One file per grader, named `_<snake_case>.py`. Shared infrastructure lives in:

- `_base.py` — `MetisTurnGrader`, `mark_skipped`, `_ContextAwareGEval`, `_ContextAwareConversationalGEval`, helpers
- `_types.py` — `LlmTestCaseMetadata`, `OrcaChatMetadata`, `ClarificationRequest`
- `_judge.py` — `_get_judge_model()`
- `_constants.py` — `SYSTEM_PROMPT_SUMMARY`, `TOOL_MANIFEST`

Maintenance rule: **new grader = new file**. No judgment call about which file to put it in.

## Skip behaviour

All graders use the same skip convention: `score=1.0`, `skipped=True`, `success=True`. Skipped graders are excluded from pass-rate aggregation in the report.
