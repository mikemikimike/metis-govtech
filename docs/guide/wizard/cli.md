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

1. Give the Wizard a plain description of the target system:

   ```bash
   metis wizard init "A research assistant that answers questions from internal documents and cites each source."
   ```

2. The CLI shows the fixed ARC capability catalogue. Select known capabilities by number, name, or
   stable ID, separated by commas. Enter a blank line when you know none.
3. Enter one confidence value: `low`, `medium`, or `high`. The value states how complete the full
   selection is.
4. Answer the clarification questions.
5. Review the Tasks, Behaviours, Criteria, Personas, and Scenarios that the Wizard drafts.

The CLI saves state to `evaluation/interview_state.json` after each accepted turn. Use another
directory with `--out-dir`:

```bash
metis wizard init "<description>" --out-dir my-eval
```

## Resume or restart

| To | Command |
|---|---|
| Resume the latest saved state | `metis wizard resume` (add `--out-dir my-eval` for another directory) |
| Discard the Interview in progress and start again | `metis wizard init "<description>" --restart` |

Without `--restart`, `init` does not overwrite an Interview in progress. It directs you to
`resume`.

## Output files

When the Interview is complete, the CLI writes these files and removes `interview_state.json`:

| File | Contents |
|---|---|
| `experiment.yaml` | Personas, Scenarios, trial counts, fixtures, and scorers |
| `profile.yaml` | Product, Tasks, Behaviours, Criteria and their scorers, Personas, and Scenarios |
| `review.md` | A human-readable review of the specification |

The CLI also shows the total trial count. Run the result with:

```bash
metis engine run --input-dir evaluation/
```

See the [Engine guide](../engine.md) for the next steps.
