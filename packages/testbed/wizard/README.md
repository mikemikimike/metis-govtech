# Wizard evaluation examples

The cases in `cases/` contain five mock use cases for reviewing
Wizard's generated Specifications: Orca, Enterprise AI Assistant, a travel planner,
a billing support assistant, and an incident triage assistant.

Each use case has `inputs/prompt.md` for Wizard's first chat message and an
`outputs/specification.yaml` reference. Other files in `inputs/` are supporting
documents for upload. Files in `outputs/fixtures/` describe uploads in the mock
Test Cases. The Specification is the final output under review; these examples
do not run the described products.

The Orca input documents stay local. Its `inputs/` folder keeps a tracked
`.gitkeep`, and its `.gitignore` excludes the local documents. The other use
cases include their inputs in the repository.

The examples include persona and scenario metadata for future testbed use.

## Review the cases locally

From the repository root:

```bash
uv run python packages/testbed/wizard/reviewer/build.py --serve
```

Open `http://127.0.0.1:8765/.reviewer/` to inspect the Behaviour–Test Case matrix,
personas, scenarios, and reference YAML. Supporting documents are available through
the local server. Orca inputs can be absent; the reviewer marks its prompt missing.

Generated pages stay in the ignored `packages/testbed/wizard/.reviewer/` directory. They
can contain local input text. Only the reviewer source files are committed.

## Maintain reference cases

`cases/config.yaml` lists the case folders. Each case README records its sources,
scope, and review decisions. Keep reference material outside `inputs/`; only the
prompt and supporting documents go to Wizard. Store generated Specifications in
`results/`, outside the reference outputs.

Review source coverage, assessable Criteria, and Task links. Different wording and
Feature groupings can be valid. Record missing input as unresolved. A human must
review each product Grader before it is treated as approved. Schema validation
alone does not establish reference quality.

Persona metadata is optional and flat. Use `input_style` for communication style;
optional age, occupation, personality, or background values are plain text. Omit
unspecified fields and gender. Scenario metadata can hold `start_prompt` and
`stop_condition`. Engine support for action triggers is planned.

ASSERT-derived cases include source links and MIT licence notices in their case
READMEs. Their inputs and Scenarios are locally authored examples; no ASSERT
pipeline was run. Upstream judge rubrics use `true` for a violation. Keep that
score direction when implementing a Grader.
