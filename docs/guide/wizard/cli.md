# Use the Wizard CLI

The CLI runs the Interview in a terminal and writes the specification to local files. It does not
need the API server.

- It saves the Interview state after each turn. You can close the terminal and resume later.
- It does not accept documents. Use the [web client](web.md) or the [API](api.md) to add documents.
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
   cp packages/wizard/.env.example .env
   ```

3. Add your provider values:

   | Variable | Required | Purpose |
   |---|---|---|
   | `OPENAI_API_KEY` | Yes | API key for the Interview model |
   | `OPENAI_BASE_URL` | Yes | Full OpenAI-compatible provider endpoint |
   | `INTERVIEW_MODEL` | No | Interview model name; a provider default applies when unset |
   | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | No | Tracing. Tracing is off unless all three are set. |

   An environment variable has priority over the value in `.env`.

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

2. The CLI shows the fixed ARC capability catalogue. Select known capabilities by number, name, or
   ID, separated by commas. Enter a blank line when you know none.
3. Enter one confidence value: `low`, `medium`, or `high`. The value states how complete the full
   selection is.
4. Answer the clarification questions.
5. Review the Features, Behaviours, Criteria, Personas, Scenarios, and Test Cases that the Wizard drafts.

The CLI saves state after each accepted turn in
`experiments/design/YYYYMMDD-HHMMSS-interview/inputs/interview_state.json`. The date and time are local to the
machine when `init` starts. Use `--out-dir` to select an exact experiment root:

```bash
metis wizard init "<description>" --out-dir my-eval
```

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
| `inputs/interview_state.json` | The final state used to compile the Specification |
| `outputs/fixtures/` | Fixture files referenced by Tasks |

The CLI publishes `outputs/specification.yaml` after the other export files are saved.
Its presence marks a completed export. `resume` reports completion even though the final state
is retained. Use `--restart` to start again in the same directory. If export fails before the
Specification is published, `resume` can retry from the saved final state.

The CLI also shows the total trial count. For an Interview started on 2026-10-16 at 22:30:45, run the result with:

```bash
metis engine run --input-dir experiments/design/20261016-223045-interview/outputs/
```

See the [Engine guide](../engine.md) for the next steps.
