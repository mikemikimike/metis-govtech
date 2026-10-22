# ORCA

End-to-end evaluation of ORCA's various capabilities.

## Inputs and reference

- `inputs/prompt.md`

The reference Specification is `outputs/specification.yaml`. Its criteria include the ORCA grader assignments. Only files in `inputs/` are supplied to Wizard. This README and the reference are for review.

The four CSV files in `outputs/fixtures/` are user uploads for the ORCA Test Cases. They are copies of the files in `packages/engine/example-experiment/full/fixtures/` and are not Wizard input documents.

ORCA inputs stay Git-ignored. Restore `inputs/prompt.md` locally before running this evaluation. `.gitkeep` preserves the input folder.

## Sources

Source locations used to author the inputs and reference:

- packages/engine/example-experiment/full/specification.yaml
- tests/fixtures/wizard/specifications.py::orca_handover (product text)
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Data Analyst.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Orchestration.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Personas.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Scenarios.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Slide Maker.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - Universal Behaviours.csv
- centralized-evaluation-framework-teams/centralized-evaluation-framework-teams - User Satisfaction.csv

## Scope and review

The reference is a candidate for human review. Grader assignments need human validation.

- The product summary is a test fixture. A complete product requirements document was not found.
- The summary names Text Analyst, Slide Reviewer, and Criteria Evaluator. The reference does not have separate features for these specialists.
- The reference includes detailed rules and execution checks that the product summary does not establish. Humans must supply source requirements or narrow the scored scope.
- The source evaluation CSV files contain expected behaviours, criteria, and grading guidance. Their original locations are listed above; they are not Wizard inputs.
- The grader assignments need human review. The CSV files in `outputs/fixtures/` support the Test Cases that name them.
