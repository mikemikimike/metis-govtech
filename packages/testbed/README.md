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

[Issue #436](https://github.com/govtech-responsibleai/metis/issues/436) tracks
the Wizard evaluation runtime and comparison metrics. The examples include
persona and scenario metadata ahead of the shared model work in
[issue #441](https://github.com/govtech-responsibleai/metis/issues/441).
