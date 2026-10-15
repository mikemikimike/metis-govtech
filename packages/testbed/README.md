# Wizard evaluation examples

The [shared evaluations](evals/README.md) contain five mock use cases for reviewing
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
uv run python packages/testbed/reviewer/build.py --serve
```

Open `http://127.0.0.1:8765/.reviewer/` to inspect the Behaviour–Test Case matrix,
personas, scenarios, and reference YAML. Supporting documents are available through
the local server. Orca inputs can be absent; the reviewer marks its prompt missing.

Generated pages stay in the ignored `packages/testbed/.reviewer/` directory. They
can contain local input text. Only the reviewer source files are committed.
