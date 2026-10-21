# METIS Wizard

The METIS Wizard turns a description of a target into an evaluation specification.
The METIS Engine runs that specification.

## Choose an interface

| Interface | Best for | Who saves Interview state? | Finished output |
|---|---|---|---|
| [CLI](wizard/cli.md) | A person working in a terminal | The CLI saves a local JSON file | Files in an output directory |
| [Web](wizard/web.md) | A person who wants a guided browser flow | The browser saves data in IndexedDB | `YYYYMMDD-HHMMSS-interview.zip` download |
| [API](wizard/api.md) | A service or custom client | Your client saves the returned JSON state | YAML strings or `YYYYMMDD-HHMMSS-interview.zip` |

- The CLI runs the Wizard logic on your computer. It does not need the API server.
- The web client uses the Wizard API.
- The API does not save an Interview between requests. A custom client must save each returned
  `state` object and send the whole object with the next request.

## What the Interview builds

Example evaluation details for a research assistant:

| Term | Example |
|---|---|
| Feature | Answer policy questions. |
| Behaviour | Cite sources in each answer. |
| Criterion | Each citation supports the answer. |
| Persona | A policy analyst who needs to check a new rule. |
| Scenario | Ask how a new leave policy applies to a part-time employee. |
| Scorer | A check that compares the answer with its cited sources. |

The Interview produces one Specification with these related concepts:

| Concept | Contents |
|---|---|
| Profile | The target and its users, Features, Behaviours, Criteria, and their scorer settings |
| Specification | The Profile and the configuration needed to conduct an Experiment |
| Experiment | A collection of Runs used to evaluate one or more targets across a set of Test Cases |

The interface guides give the exact files or archive that each interface produces.

## Interview flow

1. Describe the target. In the web client and the API, you can also add documents.
2. Select the evaluation Perspective (who the evaluation is for, such as an end user or an
   engineer). Web and API only. The CLI always uses End user.
3. Select the known ARC capabilities and a confidence value.
4. Answer clarification questions.
5. Review the Behaviours to measure and their Criteria.
6. Review the Personas, Scenarios, and Test Cases.
7. Finish and validate the specification.
8. Compile or package the result.

Other paths:

- The web client and the API can finish early. See [web](wizard/web.md#finish-and-download) and
  [API](wizard/api.md#finish-early).
- The web client has a manual path for a user who already knows the Experiment to run. It does
  not use the Interview. See [Write the Experiment directly](wizard/web.md#write-the-experiment-directly).

The Wizard saves the description, Perspective, capabilities, and documents in the Interview state.
This context is separate from the Specification.

## ARC capability catalogue

- 12 capabilities in three groups: Cognitive, Interaction, and Operational.
- METIS owns a fixed copy. It does not fetch the catalogue at run time.
- Source: the GovTech Singapore Agentic Risk & Capability Framework, with Apache-2.0 attribution.

## How the Interview uses your answers

- Clarification covers the main things the target does first, then asks for detail where needed.
  It does not ask again about what the description or documents already explain.
- Features are grouped by the work the target does for its users.
- The Perspective sets which Behaviours matter most. The capabilities show what the target can do
  in each Feature.

## Run the evaluation

The CLI writes files to `experiments/design/YYYYMMDD-HHMMSS-interview/` by default. The timestamp uses the machine's local date and 24-hour time, including seconds.
Extract browser or API downloads into `experiments/design/`.
Each ZIP contains its dated experiment folder. For an Interview created on 2026-10-16 at 22:30:45, run the specification with the
Engine:

```bash
metis engine run --input-dir experiments/design/20261016-223045-interview/outputs/
```

See the [Engine guide](engine.md) for the evaluation run and the [Report guide](report.md) for the
results.

## Review and edit Criteria

Each Criterion has one non-empty description that states one assessable requirement.
Keep any necessary condition in the sentence, such as "After a tool call fails, the agent reports the failure."
The description appears by default. Expand the grader details to inspect the selected
grader and its exact settings. Criterion names and IDs remain in the specification.

Ask the Wizard to change a Criterion when you want it to update the assessment as a whole.
The matcher uses the complete description to select a grader. The Wizard then configures
the description and arguments for that grader. It validates the result before it saves
the Criterion. A failed edit keeps the previous Criterion.

The description identifies what the Criterion assesses. A parameter-based grader keeps
its exact values in its arguments. The description can include those values when useful.
A criterion judge needs the complete rule in the description, including any required limit.
Slide count and concise language need separate Criteria. A count grader cannot assess language.

You can edit the description and grader settings directly with typed fields. Raw JSON
is not required. Keep the fields consistent when you edit them directly. The Wizard checks
required fields and argument types and limits. It does not rewrite manually edited fields
or block export because their meanings differ. Export and results keep the Criterion ID
and grader settings used for the run.

For older saved data, see [Convert Criterion descriptions](../../MIGRATION.md#convert-criterion-descriptions).

## Edit fallback grading instructions

When no specific grader matches a criterion, the Interview selects the criterion fallback judge.
The judge uses the criterion description as its instructions. To change what the judge checks,
edit the Criterion in the Interview or change its description in the exported YAML before the next run. For the settings and the
evidence that the judge reads, see [Edit the criterion fallback judge](library/criterionjudge.md).
