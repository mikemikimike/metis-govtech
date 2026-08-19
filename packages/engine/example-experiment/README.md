# Example Experiment

This directory is a ready-to-run experiment input for `metis engine simulate` and `metis engine run`.

**Everything here is written for Orca** — the personas, task descriptions, fixture
files, and metric selections assume Orca's specific multi-agent architecture
(orchestrator → data-analyst / slide-maker subagents).Evaluating a
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

# Separate phases: evaluate selects the latest simulation output.
metis engine simulate --input-dir example-experiment/
metis engine evaluate --input-dir example-experiment/
```

Simulation uses the live TUI in a terminal. Evaluation uses a normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in the selected output.

## What it covers

| Task | Tests |
|------|-------|
| direct-question | Direct-handle routing, response quality |
| ambiguous-request | Clarification behaviour, routing |
| constrained-analysis | Constraint adherence, analytical correctness |
| multi-agent-pipeline | Decomposition, synthesis, cross-agent handoff |
| adversarial-slides | Injection resistance, source faithfulness |
| corrupted-data | Error diagnosis, bounded retries, failure reporting |
| impossible-request | Capability honesty, limitation acknowledgement |
| harmful-request | Safety refusal |
| conflicting-sources | Contradiction flagging, gap acknowledgement |
| evolving-brief | Context retention across agent switches |

## Persona × task matrix

Each task runs once per listed persona (total sessions = sum of checkmarks).

| Task | cooperative | impatient | uncertain | skeptical | perfectionist | scope-creeper | boundary |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| direct-question | ✓ | | | | | | |
| ambiguous-request | | | ✓ | | | | |
| constrained-analysis | ✓ | ✓ | | | | | |
| multi-agent-pipeline | ✓ | ✓ | | | | | |
| adversarial-slides | ✓ | | | | | | |
| corrupted-data | ✓ | | | | | | |
| impossible-request | ✓ | | | ✓ | | | |
| harmful-request | | ✓ | | | | | ✓ |
| conflicting-sources | ✓ | | | ✓ | | | |
| evolving-brief | | | | | ✓ | ✓ | |
