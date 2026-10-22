# Example Experiment

This directory is a ready-to-run experiment input for `metis engine run`.

**Everything here is written for Orca** — the personas, scenario descriptions, fixture
files, and Grader selections assume Orca's specific multi-agent architecture
(orchestrator → data-analyst / slide-maker subagents). Evaluating a
different system will require writing your own specification from scratch.

> **Graders are being rewritten (#428).** The METIS grader library was rebuilt without
> DeepEval. In `full/specification.yaml`, Criterion `AC-EXEC-3` names the demo
> `DemoTraceBudgetGrader`, and every other Criterion names the generic
> `CriterionJudgeGrader`, which judges the session against the Criterion's own description.
> Purpose-built graders will replace these as they are written. For a quick first run, use
> the [simple specification](simple/specification.yaml).

The [full specification](full/specification.yaml) defines 18 Tasks and 54 Trials for Orca. Each Task
selects one Scenario, one Persona, fixtures, and Criteria. Each Criterion owns
its Grader and parameters.

## Structure

```
example-experiment/
├── simple/                  # Quick check: one Task, one Trial, one Grader, no uploaded files
│   ├── specification.yaml
│   └── fixtures/
└── full/                    # The complete Orca experiment
    ├── specification.yaml   # Target, features, behaviours, criteria, personas, scenarios, and tasks
    ├── reports/
    └── fixtures/            # Files uploaded to Orca during simulation
        ├── q3_sales.csv
        ├── q3_sales_corrupted.csv
        ├── q3_sales_v1.csv
        ├── q3_sales_v2.csv
        └── policy_document_adversarial.txt
```

## Quick check

The [simple specification](simple/specification.yaml) runs one direct question through
Orca's API. It uses one Persona, one Scenario, one Task, and one Trial. Its Grader,
`DemoTraceBudgetGrader`, checks that the session used at most four traces (persona–target
exchanges). The Task shows the optional execution settings, including the separate turn
limit and retry count.

From the repository root, with the same credentials as the full example:

```bash
uv run metis engine run --input-dir packages/engine/example-experiment/simple/
```

No uploaded files are needed. Results are written under
`experiments/execute/orca-simple-<timestamp>/`.

## Running

From the repository root, with Orca, user-agent model, and Langfuse credentials set:

```bash
# Simulate, evaluate, and write results.
uv run metis engine run --input-dir packages/engine/example-experiment/full/

# Separate phases: simulate prints the evaluate command for the output it wrote.
# The --experiment-dir value is that output directory. Its real name holds the
# experiment id and the start time of the run.
uv run metis engine simulate --input-dir packages/engine/example-experiment/full/
uv run metis engine evaluate --experiment-dir experiments/execute/orca-eval-20260820-143000/
```

`run` writes `outputs/reports/results.json` (holding one GraderRecord per grader per session) under the new `experiments/execute/orca-eval-<timestamp>/` directory and prints the `metis insights report` command that builds a report from it.

Simulation uses the live TUI in a terminal. Use `--no-tui` to turn it off. Evaluation uses a normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in the named output.

## What it covers

| Scenario | Tests |
|------|-------|
| direct-question | Direct-handle routing, response quality |
| constrained-analysis | Constraint adherence, analytical correctness, chart & report quality |
| multi-agent-pipeline | Decomposition, synthesis, cross-agent handoff, full Slide Maker suite |
| corrupted-data | Error diagnosis, bounded retries, failure reporting, data recovery |
| impossible-request | Capability honesty, limitation acknowledgement |
| harmful-request | Safety refusal (dedicated refusal metric) |
| conflicting-sources | Contradiction flagging, gap acknowledgement |
| evolving-brief | Context retention across agent switches, full Slide Maker suite |

## Graders not yet in the library

Every Criterion except `AC-EXEC-3` uses the generic `CriterionJudgeGrader` until a grader
written against `metis.library.grader.Grader` replaces it (#428). The framework items below never had one:
prompt-injection resistance (no metric ID), `M-DA-21` (ML rigour), `M-DA-24`
(uploaded-data injection), `M-DA-25` (egress & filesystem containment).

## Persona × Scenario matrix

Each Scenario has Tasks for the 2–3 Personas that best test its Criteria. Every
Persona is used at least once. Each Task is one Persona × Scenario pair. The number of Trials is the sum of `num_trials` over all Tasks.

| Scenario | Personas |
|------|-------|
| direct-question | cooperative-delegator, impatient-executive, uncertain-explorer |
| constrained-analysis | domain-expert-perfectionist, skeptical-auditor |
| multi-agent-pipeline | cooperative-delegator, impatient-executive, skeptical-auditor |
| corrupted-data | impatient-executive, uncertain-explorer |
| impossible-request | skeptical-auditor, impatient-executive |
| harmful-request | cooperative-delegator, domain-expert-perfectionist |
| conflicting-sources | skeptical-auditor, domain-expert-perfectionist |
| evolving-brief | cooperative-delegator, domain-expert-perfectionist |

With `num_trials: 3` on each of the 18 Tasks, this is 54 Trials.

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
