# Example Experiment

This directory is a ready-to-run experiment input for `metis engine run`.

**Everything here is written for Orca** — the personas, task descriptions, fixture
files, and metric selections assume Orca's specific multi-agent architecture
(orchestrator → data-analyst / slide-maker subagents). Evaluating a
different system will require writing your own experiment from scratch.

## Structure

```
example-experiment/
├── experiment.yaml      # Personas, tasks, metrics, and configuration
└── fixtures/            # Files uploaded to Orca during simulation
    ├── q3_sales.csv
    ├── q3_sales_corrupted.csv
    ├── q3_sales_v1.csv
    ├── q3_sales_v2.csv
    └── policy_document_adversarial.txt
```

## Running

```bash
# One command: simulate, evaluate, and write the report.
metis engine run --input-dir example-experiment/

# Separate phases: simulate prints the evaluate command for the output it wrote.
# The --experiment-dir value is that output directory. Its real name holds the
# experiment id and the start time of the run.
metis engine simulate --input-dir example-experiment/
metis engine evaluate --experiment-dir experiments/orca-eval-20260820-143000/
```

Simulation uses the live TUI in a terminal. Evaluation uses a normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in the named output.

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

## Metrics not yet in the library

The following framework metrics have no implementation yet and are omitted:

- Universal: `M-UNI-12` (prompt-injection resistance).
- Data Analyst: `M-DA-21` (ML rigour), `M-DA-24` (uploaded-data injection), `M-DA-25` (egress & filesystem containment).

## Persona × Scenario matrix

Rather than a full 5 × 8 cross-product, each scenario selects the 2–3 personas that
best stress its metrics (every persona is used at least once). The number of test
cases is the sum of `personas × num_trials` over all scenarios.

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

With `num_trials: 3` throughout (18 persona × scenario pairs), this is 54 runs.
