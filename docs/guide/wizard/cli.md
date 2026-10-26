# Use the Wizard CLI

The CLI runs the Interview in a terminal and writes the specification to local files. It does not
need the API server.

- It saves the Interview state after each turn. You can close the terminal and resume later.
- It accepts documents when the Interview starts. See [Add documents](#add-documents).
- It always uses the End user Perspective. Use the web client or the API for the Engineer,
  Compliance, or Security Perspective.

See the [Wizard overview](../wizard.md) for the shared Interview flow and output concepts.

## Requirements

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- GNU Make
- An OpenAI-compatible model provider, such as Platform AI

## Set up

1. From the repository root, install the workspace or only the Wizard package:

   ```bash
   make install
   # or
   make install-wizard
   ```

2. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

3. Add your provider values:

   | Variable | Required | Purpose |
   |---|---|---|
   | `OPENAI_API_KEY` | Yes | API key of the shared gateway. `INTERVIEW_API_KEY` and `EMBEDDING_API_KEY` override it for one role. |
   | `OPENAI_BASE_URL` | No | Full OpenAI-compatible provider endpoint. Unset uses the default OpenAI endpoint. |
   | `DEFAULT_MODEL` | No | Model of every chat role. Unset uses `gpt-6-luna`. |
   | `INTERVIEW_MODEL` | No | Interview model name. Unset uses `DEFAULT_MODEL`. |
   | `EMBEDDING_MODEL` | No | Embedding model for scorer matching. Unset uses `text-embedding-3-large`. Without an embeddings key, the CLI warns, and each Criterion uses the criterion judge. |
   | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | No | Tracing. Tracing is off unless all three are set. |

   An environment variable has priority over the value in `.env`. The command reads one `.env`
   file and prints its path. See the [model guide](../models.md) for the search and the
   variables of each role. When the run ends, the CLI lists the models that the run needs, where
   each one comes from, and whether its key is set. To change a model, set `USER_AGENT_MODEL` or
   `JUDGE_MODEL` in `.env`, or edit `specification.yaml`.

4. Verify the command:

   ```bash
   metis wizard init --help
   ```

   The package also installs the standalone `metis-wizard` command.

## Start an Interview

1. Give the Wizard a plain description of the target:

   ```bash
   metis wizard init "A research assistant that answers questions from internal documents and cites each source."
   ```

2. Choose the mode: `1` to build a Specification only, or `2` to build it and run evals. In run
   mode, enter the target binding values. See [Connect the target](#connect-the-target).
3. The CLI shows the fixed ARC capability catalogue. Select known capabilities by number, name, or
   ID, separated by commas. Enter a blank line when you know none.
4. Enter one confidence value: `low`, `medium`, or `high`. The value states how complete the full
   selection is.
5. Answer the clarification questions.
6. Review the Features, Behaviours, Criteria, Personas, Scenarios, and Test Cases that the Wizard drafts.

## Go back to an earlier step

Each review step after Clarify has a **← Back** choice. Select its number to open the step
before it with its current content.

- Back from Behaviours shows the Target name, users, description, and detail. Press Enter to
  keep a value, or type a new value. A required field that you leave empty keeps its current
  value.
- Continue with no change returns to the later step. The Wizard drafts nothing again.
- If you change content that later content came from, the Wizard asks what to do with the later
  content. You can keep it, regenerate it, or review it yourself.

Clarify has no Back, because it is the first step. To correct the description, say so in your
answer, for example "The target is for staff only." To change the capabilities, start again with
`init --restart`.

The CLI saves state after each accepted turn in
`experiments/design/YYYYMMDD-HHMMSS-interview/inputs/interview_state.json`. The date and time are local to the
machine when `init` starts. Use `--out-dir` to select an exact experiment root:

```bash
metis wizard init "<description>" --out-dir my-eval
```

## Add documents

Give `init` one `--document` option (short form `-d`) for each file. The Interview reads the text
of each file, in the same way as the web client and the API:

```bash
metis wizard init "<description>" --document policy.pdf --document diagram.png
```

The CLI checks the files before it asks for capabilities or calls the model. It uses the same file
types, limits, and text reader as the web client. It shows one line for each file:

| Line | Meaning |
|---|---|
| `Read: policy.pdf` | The Interview uses the text of the file. |
| `Not read: diagram.png (no text reader for this file type)` | The file type has no text reader. The Interview knows the file by name only. |
| `Could not read: scan.pdf: <reason>` | The file has a text reader, but the CLI could not read the text. |

A file type that the Wizard does not accept stops the command with exit code 1.

When a file could not be read, the CLI asks `Keep unread files without text?` The default is No.
Answer Yes to keep the file by name only. Answer No to stop. Then remove the file from the
command and run `init` again. A run with no terminal, such as a script, stops with exit code 1.

The CLI keeps a copy of each document in `inputs/documents/`. A Test Case can send an opening
document to the target as a fixture file. `resume` uses this copy, so you can move the source
files after `init`.

## Connect the target

In run mode, the Wizard asks for the target binding before the capability questions. Choose how
to give it: fill in the fields in the CLI, or give the path to a binding YAML file. Each secret
field takes the name of an environment variable, never its value. The CLI reads `.env` and the
environment, then checks the binding on your computer:

- It validates the binding fields.
- It reports each named variable as set or not set. It never shows a value.
- For HTTP, it fetches the OpenAPI document. For a browser, it loads the start page.

After the test, choose **test again**, **fix the values**, or **continue**. If the fields are not
valid, fix them. To continue without a binding, run with `--mode spec`.

| Option | Effect |
|---|---|
| `--mode spec` | Write a Specification only. Ask no connection question. |
| `--mode run` | Ask for the binding values. |
| `--binding PATH` | Check the binding in a YAML file. This option implies `--mode run`. |

Without `--mode`, a terminal asks for the mode. When no terminal is available, the mode is
`spec`. With `--binding` and no terminal, the CLI checks the file once and asks nothing.
`--mode run` with no terminal and no `--binding` stops with exit code 1 before the Interview starts.

To add or replace the binding later, run:

```bash
metis wizard connect --out-dir my-eval
metis wizard connect --out-dir my-eval --binding my-binding.yaml
```

For a complete export, `connect` writes the Specification, `review.md`, and the binding again.
For an Interview in progress, it saves the connection, and `resume` writes the binding at the end.

## Resume or restart

Resume requires `--out-dir`, including when the Interview continues on another day. The CLI
prints the complete resume command when an Interview starts.

| To | Command |
|---|---|
| Resume a saved Interview | `metis wizard resume --out-dir my-eval` |
| Discard the Interview in progress and start again | `metis wizard init "<description>" --out-dir my-eval --restart` |

Without `--restart`, `init` does not overwrite an Interview in progress. It directs you to
`resume`.

## Output files

When the Interview is complete, the CLI retains its final state and writes this layout:

| File | Contents |
|---|---|
| `outputs/specification.yaml` | Target, Features, Behaviours, Criteria and Grader settings, Personas, Scenarios, and Tasks |
| `outputs/review.md` | A human-readable review of the specification |
| `outputs/target-binding.yaml` | The target binding, in run mode only. It names environment variables and holds no secret value. |
| `inputs/interview_state.json` | The final state used to compile the Specification |
| `inputs/documents/` | A copy of the documents given to `init` |
| `outputs/fixtures/` | The documents that a Test Case uses. The CLI copies them from `inputs/documents/`. |

When a Test Case uses a file that is not in `inputs/documents/`, the CLI names the file. Put
that file in `outputs/fixtures/` before you run the Experiment.

The CLI removes a file from `outputs/fixtures/` when the file is a copy of a document in
`inputs/documents/` and no Test Case uses it. A copy has the same name and the same bytes as the
document. Other files in `outputs/fixtures/` stay there.

The CLI publishes `outputs/specification.yaml` after the other export files are saved.
Its presence marks a completed export. `resume` reports completion even though the final state
is retained. Use `--restart` to start again in the same directory. If export fails before the
Specification is published, `resume` can retry from the saved final state.

The CLI also shows the total trial count. For an Interview started on 2026-10-16 at 22:30:45, run the result with:

```bash
metis engine run --input-dir experiments/design/20261016-223045-interview/outputs/
```

See the [Engine guide](../engine.md) for the next steps.
