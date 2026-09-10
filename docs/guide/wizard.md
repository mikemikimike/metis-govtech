# Wizard User Guide

## Introduction

metis-wizard turns a prose description of your product into an evaluation specification. You answer
an interview about what the product does and how it must behave. The wizard then writes three files:

- `experiment.yaml` — personas, scenarios, and metrics.
- `profile.yaml` — tasks, behaviours, criteria, and metrics.
- `review.md` — a human-readable summary of the specification.

You can run the wizard two ways:

- **As a CLI tool** — an interactive terminal interview. This guide covers it.
- **In the browser** — the same interview over the `metis-api` service. See the
  [web client guide](web.md).

Both doors drive the same interview. The interview state is client-held, so nothing is stored on a
server between turns.

By the end of this guide you will have:

- A working local installation.
- A completed evaluation specification produced by an interview.
- The knowledge to run the wizard against your own product.

For the overall METIS architecture and other packages, see the [project README](../../README.md).

---

## Prerequisites & Setup

### Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (workspace and package manager)
- GNU Make
- An OpenAI-wire-compatible model provider (for example, Platform AI)

### Install

From the monorepo root:

```bash
make install
```

This installs all workspace dependencies.

### Environment Configuration

The interview calls a model, so it needs provider credentials. Copy the example environment file
and fill in your credentials:

```bash
cp packages/wizard/.env.example .env
```

The wizard requires these variables:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | Provider API key for the interview model |
| `OPENAI_BASE_URL` | Yes | Full OpenAI-compatible endpoint of your provider |
| `INTERVIEW_MODEL` | No | The wizard's model on that provider (a provider default applies if unset) |

Optional tracing variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | _(unset)_ | Self-hosted Langfuse tracing. Tracing stays off unless all three are set. |

The wizard reads `.env` files only inside the project, and an existing environment variable always
wins over the file.

### Verify Installation

```bash
metis wizard init --help
```

You should see the `init` command's help text. `metis wizard` composes into the unified CLI; the
package also installs a standalone `metis-wizard` entry point.

---

## Run an Interview

### Start

Give the wizard a plain description of the product to evaluate:

```bash
metis wizard init "A research assistant that answers questions from a company's internal documents and always cites its sources."
```

The wizard opens an interview in the terminal. It asks about the product's behaviours, the personas
and scenarios to test, and the criteria that decide a pass. You answer one screen at a time. The
wizard saves the interview state to `evaluation/interview_state.json` after each turn, so an
interrupted run is never lost.

By default the wizard writes to the `evaluation/` directory. Use `--out-dir` to choose another
location:

```bash
metis wizard init "<description>" --out-dir my-eval
```

### Resume

If you close the terminal mid-interview, continue from the saved state:

```bash
metis wizard resume            # reads evaluation/interview_state.json
metis wizard resume --out-dir my-eval
```

### Restart

To discard an interview already in progress and start over:

```bash
metis wizard init "<description>" --restart
```

Without `--restart`, `init` refuses to overwrite an interview in progress and points you to
`resume`.

---

## Outputs

When the interview finishes, the wizard writes three files beside each other in the output
directory and removes `interview_state.json` (the interview is done, so there is nothing to
resume):

```
evaluation/
├── experiment.yaml    # Personas, scenarios, and metrics
├── profile.yaml       # Tasks, behaviours, criteria, and metrics
└── review.md          # A human-readable summary of the specification
```

The wizard also prints how many trials the specification runs, so you know the size of the
evaluation before you start it.

To run the specification, pass the output directory to the engine:

```bash
metis engine run --input-dir evaluation/
```

See the [engine guide](engine.md) for the evaluation run and the [report guide](report.md) for the
results.

---

## Next Steps

- Run the specification and read the results — see the [engine guide](engine.md).
- Use the same interview in the browser — see the [web client guide](web.md).
