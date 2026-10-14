# METIS Wizard

The METIS Wizard turns a description of a target into an evaluation specification.
The METIS Engine runs that specification.

## Choose an interface

| Interface | Best for | Who saves Interview state? | Finished output |
|---|---|---|---|
| [CLI](wizard/cli.md) | A person working in a terminal | The CLI saves a local JSON file | Files in an output directory |
| [Web](wizard/web.md) | A person who wants a guided browser flow | The browser saves data in IndexedDB | `specification.zip` download |
| [API](wizard/api.md) | A service or custom client | Your client saves the returned JSON state | YAML strings or `specification.zip` |

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

The CLI writes the files to `evaluation/` by default. From the web client or the API, extract
`specification.zip` into a directory, such as `evaluation/`. Then run the specification with the
Engine:

```bash
metis engine run --input-dir evaluation/
```

See the [Engine guide](engine.md) for the evaluation run and the [Report guide](report.md) for the
results.
