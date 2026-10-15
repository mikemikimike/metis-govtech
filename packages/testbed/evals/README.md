# Shared evaluations

These mock use cases provide shared inputs and reference outputs for Wizard review. Each
case has an input set and a reference `specification.yaml`. A human has reviewed
the Test Cases in all five use cases. The reference Specifications and graders
can receive further review. A schema check does not establish their quality.

| Case | Input | Test Case status |
| --- | --- | --- |
| ORCA | Local product summary | Human-validated |
| Enterprise AI assistant | Prompt and five capability documents | Human-validated |
| LangGraph travel planner | System-level product brief | Human-validated |
| Billing support | System-level product brief | Human-validated |
| Incident triage | System-level product brief | Human-validated |

## Files and boundaries

`config.yaml` lists use case folder names. Each use case contains:

- `README.md`: the use case description, source locations, scope, and review notes.
- `inputs/`: `prompt.md` for the first chat message, plus optional supporting documents uploaded to Wizard. Files are discovered recursively; hidden files such as `.gitkeep` are excluded.
- `outputs/`: the reference `specification.yaml` and any supporting reference fixtures.

Inputs and outputs are tracked except for ORCA inputs. `orca/inputs/.gitkeep`
preserves the folder. Restore ORCA documents locally before starting an evaluation.
Only the prompt and supporting input documents are sent to Wizard. Keep reference material and evaluation
rubrics outside `inputs/`. A system comparison must use the same inputs and the
same policy for answering Interview questions.

The graders inside `specification.yaml` assess the described product. Wizard's
generated Specification is reviewed against the reference. An Assert judge
setting is not a METIS grader class.

## Use a case

1. Read the use case README and resolve its known limits before a scored run.
2. Start a fresh Wizard Interview. Paste `inputs/prompt.md` into the first chat and upload any other input files. Record the Wizard
   version, model settings, operator answers, and full Interview transcript.
3. Answer follow-up questions from the input material. Record missing information
   as unknown. Do not use the reference to supply answers.
4. Save the generated `specification.yaml` outside the outputs directory.
5. Review the result against the reference. Record evidence and unresolved items.
6. Have a human check each product grader and record the decision in the use case README.

Different feature groupings and wording can be valid. Do not use YAML equality
as the quality score. Check source coverage, assessable criteria, and grader fit.
Do not count criteria that need missing input as failures until the case is resolved.

The reference Specifications are the final outputs under review. Their Tasks
describe mock product interactions. The described products are not run here.
The Assert references leave `runner_factory_ref` empty because an Assert callable
does not implement the METIS runner interface.

## Check the files

### Persona metadata

Keep the main persona description separate from its optional `metadata` object.
Use one natural-language `input_style` statement to describe how the user communicates,
such as brief, casual, everyday, or formal. Keep metadata one level deep. Optional
`age`, `occupation`, and `personality` fields are natural-language text. If a general
`background` field is used, write one natural-language statement in it. Do not include
a gender field. Omit fields when their values are not specified.
Existing personas can omit metadata entirely.

```yaml
metadata:
  input_style: Gives specific, detailed instructions and clear preferences.
  personality: Highly organised, detail-focused, and Type A.
```

### Scenario metadata

Scenarios can include an optional, one-level `metadata` object. The travel cases use
`start_prompt` for the opening user message and `stop_condition` for a natural-language
completion rule. The Europe scenario omits the start prompt. The incident triage
scenario describes the selected-alert action and upload in plain text; it does
not use metadata. Engine support for action triggers is planned for a
later iteration.

### Review

Check each reference against its inputs, scenario descriptions, and review notes.
The separate testbed runtime and automated checks are tracked in issue #436.

## Assert source conversion

The ASSERT use case READMEs link to source material on the `main` branch
of `responsibleai/ASSERT`.
Each adapted use case README includes the ASSERT attribution and full MIT licence notice.

Each ASSERT input is a locally authored system-level product brief. It describes
users, functions, workflow, environment, and product constraints. The reference
Specifications also incorporate human review decisions documented in each README.
They need human review before they can serve as complete system-level references.

Scenarios are locally authored review examples, not generated ASSERT run outputs.
The upstream judge rubrics use `true` for a violation; preserve that direction
when implementing a METIS grader. No ASSERT agent or evaluation pipeline was run
to build these use cases.
