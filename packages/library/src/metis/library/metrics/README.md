# Metrics

All metrics live in `metis.library.metrics` and are imported by their class name:

```python
from metis.library.metrics import RoutingAccuracyMetric
```

In `experiment.yaml`, use the package-level FQN:

```yaml
metric_refs:
  - metis.library.metrics.RoutingAccuracyMetric
  - metis.library.metrics.TurnBudgetMetric:
      max_turns: 8
```

## Classification via tags

Each metric class carries a `tags: ClassVar[tuple[str, ...]]` for multi-dimensional classification. File layout is a developer ergonomics concern only — it carries no semantic weight.

| Dimension | Values |
|-----------|--------|
| Component | `orchestration`, `analysis`, `presentation`, `universal` |
| Granularity | `per-turn`, `session-level` |
| Grading | `code-graded`, `judge-graded` |

Example:

```python
class RoutingAccuracyMetric(SyncBaseMetric):
    tags: ClassVar[tuple[str, ...]] = ("orchestration", "per-turn", "judge-graded")
```

## Evaluation routing

The engine routes metrics automatically by type:

- **Session metrics** (`BaseConversationalMetric` subclasses, tagged `"session-level"`) run against the full multi-turn `ConversationalTestCase` for each session.
- **Per-turn metrics** (tagged `"per-turn"`) run against each individual `LLMTestCase`.

Both can be listed together in `experiment.yaml` — no annotation needed.

## File layout

One file per metric, named `_<snake_case>.py`. Shared infrastructure lives in:

- `_base.py` — `SyncBaseMetric`, `_ContextAwareGEval`, `_ContextAwareConversationalGEval`, helpers
- `_types.py` — `TraceMetadata`, `OrcaChatMetadata`, `ClarificationRequest`
- `_judge.py` — `_get_judge_model()`
- `_constants.py` — `SYSTEM_PROMPT_SUMMARY`, `TOOL_MANIFEST`

Maintenance rule: **new metric = new file**. No judgment call about which file to put it in.

## Skip behaviour

All metrics use the same skip convention: `score=1.0`, `skipped=True`, `success=True`. Skipped metrics are excluded from pass-rate aggregation in the report.
