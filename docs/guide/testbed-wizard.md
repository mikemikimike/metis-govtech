# Evaluate Wizard Specifications

The METIS testbed measures the Specifications that a Wizard Target produces from
product information. It runs every Test Case listed in
`packages/testbed/wizard/cases/config.yaml`, compares each generated Specification with
its human-reviewed reference, and saves one immutable result.

The initial interaction is one-shot. The testbed starts the Interview, leaves the
first clarification request unanswered, and asks Wizard to finish. This checks the
quality of the opening prompt and Wizard's best-effort completion path. If Wizard
returns a ready Scenario review, the testbed accepts its enabled Continue option
once and records that response. It does not answer clarification questions or
change the generated content. A remaining request is recorded as `incomplete`.
Scores can be saved for an incomplete Interview; they do not mean it finished.
The command exits with status 1 if any case fails or remains incomplete.

Each Test Case uses `inputs/prompt.md` as the first chat message. The prompt can be
plain product information. All other files in `inputs/` are uploaded as supporting
documents. The same rule applies to every Target version.

## Prepare the environment

Install the workspace and configure the same OpenAI-compatible endpoint used by
Wizard:

```bash
make install
export OPENAI_BASE_URL="https://example.invalid/v1"
export OPENAI_API_KEY="..."
export INTERVIEW_MODEL="gpt-5.6-luna"
```

The testbed uses the endpoint for Wizard calls and semantic similarity embeddings.
Use a chat model that the API key can access. Set `INTERVIEW_CONTEXT_TOKENS` to
its supported context limit and `INTERVIEW_OUTPUT_TOKENS` to the output reserve
(defaults: 128,000 and 16,384). Wizard checks a conservative UTF-8 byte-based token
bound before every chat request, including its schema and retry history. The
bound can reject input that a model-specific tokenizer could fit. No input is
truncated. A context error states the budget and the required bound.

Document text can contain up to 500,000 characters per file and 1,000,000 in total.
The API config supplies the same limits to clients. TXT, Markdown, YAML, JSON,
CSV, PDF, and DOCX support text extraction.

Langfuse remains optional and follows the Wizard configuration.

Orca product input files stay local. Restore the product documents described in
`packages/testbed/wizard/cases/orca/README.md` before a complete run. A missing Orca input produces an
`input_missing` Test Case result. It does not stop the other Test Cases.

## Run the evaluation

From the repository root:

```bash
uv run metis-testbed wizard
```

The command uses an exact `metis-wizard/v*` Git tag as the Target version when the
current commit has one. It otherwise uses the current branch name. Supply a version
when testing a deployment or another named build:

```bash
uv run metis-testbed wizard --target-version v1.0.1
```

Use another configuration or result directory when needed:

```bash
uv run metis-testbed wizard \
  --config packages/testbed/wizard/cases/config.yaml \
  --results packages/testbed/results
```

## Saved results

Results are grouped by Target and Target version. A timestamp permits repeated
immutable executions of one version:

```text
packages/testbed/results/
└── metis-wizard/
    └── v1.0.1/
        └── 20261015T023000Z/
            ├── run.json
            ├── report.md
            └── cases/
                └── travel-planner-langgraph/
                    ├── result.json
                    └── generated-specification.yaml
```

`run.json` is the machine-readable aggregate. `report.md` shows the scores,
alignments, missing items, and additional items. Each Test Case keeps its own result
and generated Specification. Each result records `completed` and
`lifecycle_outcome` separately from scores. Wizard failures retain their code,
retryable flag, missing requirements, safe retry state, and available diagnostic
state. The report includes these details. A failed completion can save a draft
Specification for inspection; this does not certify that it is runnable.
The reference Specification remains in its case
directory and never enters the Wizard Interview.

The saved metadata is intentionally small:

- execution ID and creation time;
- Target name and Target version;
- interaction mode;
- configuration ID and version;
- Test Case outcomes and scores.

## Understand the scores

Generated IDs and order can change. The scorer uses semantic embeddings to build a
similarity matrix. It then finds a maximum-weight, one-to-one alignment. The level
score is:

```text
sum of aligned similarities / max(reference count, generated count)
```

This formula lowers the score when generated content is missing or extra. Reports
also show structural coverage and precision.

The scorer reports these levels:

| Level | Compared information |
|---|---|
| Feature | Name and description |
| Expected Behaviour | Name, description, parent Feature, and measurement selection |
| Criterion | Name and Given/When/Then text within its aligned Expected Behaviour |
| Grader | Exact Grader FQN and arguments for aligned Criteria that have a reference Grader |
| Task | Scenario, Persona, Expected Behaviour references, fixtures, and execution settings |

Grader similarity is unavailable when the reference contains no selected Graders.
The report uses `—` for this state.

The aggregate includes two views:

- Case average gives every scored Test Case equal weight.
- Item weighted gives larger Specifications more influence.

There is no pass threshold in this first version. Use the first results to establish
a useful baseline before setting a gate.

## Compare Target versions

Compare the latest saved execution for two versions:

```bash
uv run metis-testbed compare v1.0.0 v1.0.1
```

The command reports the change in the case-average score at each curation level. It
reads saved results and makes no model calls.

Use `--target` when the results belong to another Wizard Target:

```bash
uv run metis-testbed compare release-11 release-12 --target internal-wizard
```

## Add a Test Case

Create a directory under `packages/testbed/wizard/cases/` with the existing case layout.
Add its folder name to `config.yaml`. The next command execution discovers it
without a code change.

The runner discovers all non-hidden files in `inputs/`. Put the first chat message
in `inputs/prompt.md` and supporting documents beside it. Put source links and
review notes in `README.md`, and the reference in `outputs/specification.yaml`.
Only the prompt and supporting input documents are supplied to Wizard.

## Add another Wizard Target

A Target adapter implements the `WizardTarget` interface in
`metis.testbed.contracts`. It translates its system state into `WizardState` and
supports start, response, and end operations. The evaluator and scorer consume this
common state. The adapter owns conversion of the system output into a METIS
Specification.

The built-in `MetisWizardTarget` adapter uses the headless METIS Interview interface.
A future internal or search-based Wizard can add another adapter without changing
the result contract or scorer.

## Add a full interaction

An interaction driver implements the `InteractionDriver` interface. It receives a
Target adapter and one Test Case input. It returns a `Candidate` with the generated
Specification and interaction events.

The first driver is `OneShotInteraction`. A simulated driver can answer pending
requests with a user agent. A manual driver can display each pending request and
collect a person's response. Both drivers must return the same `Candidate` shape so
their results remain comparable with one-shot results.

## Verify the implementation

The offline tests use fake Target and similarity adapters. They make no model calls:

```bash
uv run pytest tests/unit/testbed
```

Run the repository checks before review:

```bash
make check
```
