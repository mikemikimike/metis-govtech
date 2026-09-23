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
make install          # install everything

make install-wizard   # install only wizard dependencies
```

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

Before the first model question, `init` shows the fixed ARC capability catalogue. It has three
groups (Cognitive, Interaction, and Operational) and 12 package-owned capabilities. Select known
capabilities with comma-separated numbers, names, or stable ids. Submit a blank line when you know
none. The command then asks for one confidence value: `low`, `medium`, or `high`. This value means
how confident you are that the selection covers all capabilities the system has; it is not a value
for each capability.

The catalogue is owned by `metis-wizard` in
`packages/wizard/src/metis/wizard/capabilities.yaml`. Its source is the GovTech Singapore Agentic
Risk & Capability Framework, with Apache-2.0 attribution. The wizard does not fetch this source at
run time.

`init` does not ask who the evaluation is for. It always uses the End user perspective. To evaluate
from the Engineer, Compliance, or Security perspective, use the web client, or send `perspective` in
a headless start request (see [Headless start and state](#headless-start-and-state)).

The opening description, the perspective, and the capability evidence give the Interview its
initial view of the product. During Clarify, the model silently identifies the distinct things the
product does from that evidence and the conversation. It covers those things widely before it
examines one closely. A part that the opening evidence explains clearly enough for a provisional
evaluation map already counts as covered; the wizard does not ask a redundant question only to mark
it as covered. A question about how something the product does works, including its tools, failures,
memory, delegation, coordination, or control, can come at any point when it is the most important
unclear part. These are examples, not a checklist.

Clarify questions are direct. They do not normally explain why the question was selected. When a
brief understanding check would widen or deepen what it knows, the model may state what it takes
the product to be and invite one correction. The check is brief and is not a formal Task list;
Clarify owns the Product, while the later Behaviours step owns Tasks and Behaviours. Clarify ends
when every established part of what the product does is covered or when the question limit is
reached.

After Clarify, the wizard groups Tasks by product workflow or user job and drafts a focused set of
observable Behaviours that are important to evaluate. It does not use ARC categories,
perspectives, capabilities, or system components as Task groups. Perspective changes emphasis, and
capability evidence refines what can happen inside a workflow.

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

### Headless start and state

The stateless start operation carries all opening evidence:

```json
{
  "description": "A research assistant",
  "perspective": "end_user",
  "known_capability_ids": ["internet_search_access"],
  "capability_confidence": "medium"
}
```

`known_capability_ids` and `capability_confidence` are required. `known_capability_ids` can be an
empty list, but it must be present. The operation rejects unknown or duplicate ids.

`perspective` is optional. If you do not send it, the Interview uses `end_user`. The other values
are `engineer`, `compliance`, and `security`. Read the labels and questions for all four from
`GET /api/v1/wizard/config`.

The returned `InterviewState` always contains `context.perspective` and
`context.capability_evidence` with the values from the start request. This context belongs to the
Interview, not to `ProductProfile`, and it must be sent unchanged on later turns. Capability
evidence is opening context, not a separate Interview step.

### Finish

The interview ends when you answer the review screens for the behaviours, personas, scenarios, and
criteria. The wizard checks that the specification is runnable, then writes the output files (see
below).

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
