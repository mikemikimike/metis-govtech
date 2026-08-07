# metis-wizard

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

IMPORTANT: Always talk in ASD-STE100 Simplified Technical English.

## Package Purpose

Interactive wizard that turns a prose description of a product into a runnable `experiment.yaml`.
Depends on metis-core and metis-library.

Design lives in `packages/wizard/docs/`:
- `wizard-mvp-design.md` — the models and behaviour, single source of truth
- `wizard-agentic-primer-design.md` — amends the above to make the interview agentic
- `wizard-mvp-userflow.html` — the flow, the dependency graph, the door contract
- `wizard-mvp-mockup.html` — the interaction, clickable

The two HTML companions are illustrative flow and mockup artefacts. Where they disagree with
`wizard-mvp-design.md`, the markdown wins.

## Working style

**Build the service before the frontend.** The interview lives in the application/contracts/domain
layers, and the web UI is a demo over it. When a change touches both, land the service behaviour —
models, driver, session, door contract — first and get it right, then wire the frontend to it. Do
not shape the service around what is convenient for the current UI.

**Never use a term you haven't already shown the user.** Jargon, internal names, and concepts from
the design have to be introduced before they are used — with a concrete example, not a definition
in passing. If a term appears for the first time in an explanation or a question, stop and explain
it there. This applies to vocabulary invented for this project just as much as to standard
technical terms.

**Design data models with OOP where possible.** Prefer a shared base class over repeating the same
fields across several models. Prefer inheritance and composition over flags and optional fields
that are only meaningful in some cases — if a class has fields that sit empty most of the time,
that is a signal it should be several classes.

```python
# a base holds what every request shares
class WizardRequest(BaseModel):
    prompt: str


# each kind adds only what it actually needs
class ChatRequest(WizardRequest):
    type: Literal["chat"] = "chat"


class FormRequest(WizardRequest):
    type: Literal["form"] = "form"
    fields: list[FormField]
```

**Name a model after what it belongs to.** A nested model or enum carries its owner's name, so the
link is visible without having to look anything up:

```python
Patch.op            → PatchOp
Card.lines          → CardLine
FormRequest.fields  → FormField
```

The exception is a genuinely shared type used by several owners — `Option` appears on
`ChoiceRequest`, on `Card` and on `Warning`, so tying it to any one of them would be misleading.

**Leave light comments in the code.** Enough to follow what something does and why it exists,
especially where the reasoning is not obvious from the code itself. Comment the decision, not the
syntax.

```python
# criteria are kept when a behaviour is unticked — they go dormant rather than being
# deleted, and the compiler filters on `priority` at the end. this is what lets the
# tick stay live without needing any staleness tracking.
behaviour.priority = False
```

## Module layout

The package is split by ownership so the CLI can later move to a web application without moving
the interview itself:

```
src/metis/wizard/
├── domain/       profile, patches, path resolution, permissions and edit impacts
├── contracts/    requests, responses, cards, warnings, model outputs and session persistence
├── application/  Session, driver, prompts, screens, compiler, matcher and primer
├── adapters/
│   ├── cli/      Typer commands, Rich renderer and terminal input
│   ├── llm/      PlatformAI structured-output and embedding gateway
│   └── web/      HTTP server, per-session store and the built React bundle in static/
├── bootstrap.py  the only adapter composition root
└── __init__.py   stable headless facade
```

Dependencies point inward: adapters depend on application/contracts/domain, application depends
on contracts/domain, and contracts depend on domain. Adapter siblings never import one another;
`bootstrap.py` is the sole exception because it composes the production CLI.

## Testing

`make test` runs `packages/*/tests`. The wizard tests are grouped by ownership, with shared
fixtures under `tests/fixtures/`.

Keep the suite organised around the wizard's stable contracts, not around the sequence of fixes
that produced them:

- Every new wizard capability needs regression coverage for its intended user outcome. A new
  control, for example, needs a test showing that activating it performs its promised action.
- Give each behaviour cluster one authoritative application/domain test module. Extend an existing
  parametrized workflow matrix before creating another narrowly named test.
- A change to labels, actions, request context, or door behaviour should update the current
  contract test and remove superseded assertions; do not retain tests as change archaeology.
- Test shared interview behaviour at the driver/session layer. Door tests should prove that the CLI
  and HTTP adapters preserve that behaviour, using representative or parametrized cases instead of
  repeating every driver example.
- Keep frontend tests light while the wizard web UI is a demo: cover critical interaction wiring
  and shared-door contracts, not every visual detail or microinteraction.
- Exact copy deserves a direct assertion only when the wording is a normative part of the user
  contract. Constants deserve direct tests only when their identity or location is an architectural
  constraint; otherwise test their observable behaviour.
- Multiple OpenSpec scenarios can be covered by one table-driven test. Implementation tasks do not
  each require their own test.

When fixing layered behaviour, modify the authoritative test, add a parameter row if needed, and
delete obsolete coverage in the same change. Do not add separate tests for every incidental failure
found while building the feature, such as an unwanted popup or double-click effect. Add a new test
function when the behaviour is a distinct part of the intended final contract, a safety invariant,
or a boundary risk.

Two integration tests are gates rather than unit tests:

- **`tests/integration/test_slice_a_gate.py`** — a hand-written profile compiles to an experiment the engine
  actually loads, via the engine's own `_validate_inputs`. No model call anywhere in it.
- **`tests/integration/test_slice_b_gate.py`** — the whole interview walks to DONE on `ScriptedInterviewer`,
  with no network. That stand-in in `tests/fixtures/scripted.py` is **not a throwaway**: it is
  the regression suite for the prompts and the matcher, and the only way to exercise the
  corridor without paying per test run. Keep it working.

`tests/fixtures/golden_experiment.yaml` is a golden file. Regenerate with
`uv run python packages/wizard/tests/regenerate_golden.py` — and read the diff before
committing it, or it stops buying anything.

`tests/integration/test_cli_happy_path.py` drives the actual Typer app through `CliRunner` with
the scripted interviewer. It is the offline full happy-path check for both output files.

## Optional Langfuse tracing

The model gateway can record prompts, raw replies, retries, token counts and latency in a
self-hosted Langfuse server. The target server release is `v3.153.0`, using the Python SDK v3
line.

Install the optional dependency with `uv sync --package metis-wizard --extra observability`. Set
these three environment variables before starting the wizard:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

Tracing is disabled when any variable is missing. There is no default host. The core wizard does
not import or initialise Langfuse until the optional dependency is installed and all three values
are present. The CLI and web doors use the same session id for all model-call traces.

## Things that look like bugs and are not

- **Ticks toggle.** Each option's patch flips that behaviour's *current* value, so sending the
  same tick twice turns it off. Correct, and a trap when scripting a walk.
- **Ids must not contain a dot.** A dot separates path segments, so `AC-1.1` would split
  `criteria[AC-1.1]` into two segments. Criterion ids are `AC-<behaviour>-<n>` for that
  reason. `paths.parse` scans segment-by-segment rather than splitting, so a model that
  ignores the rule still produces an addressable path — but the naming rule is the fix, and
  it is stated in the system prompt.
- **Paths resolve by real id only.** Paths address by id (`behaviours[EB-1]`); a numeric bracket
  such as `behaviours[0]` is rejected rather than treated as a positional fallback. This keeps
  edits and references stable when lists are reordered.
- **`ADD` addresses the container** (`tasks`, `scenarios`), `SET`/`REMOVE` an element
  (`tasks[T-1]`). `StepPermissions` must list both or half the operations are silently
  forbidden.
- **Strict drafts own the boundary.** Provider JSON is parsed into strict, model-only draft
  models (`extra="forbid"`) before any persisted profile object exists. The application
  materializer then assigns ids, authorship, defaults and references. The old recursive value
  filter was only a compatibility guard for hand-built runtime patches; it never protected the
  real typed provider path.

## Package-Specific Notes

The metric catalogue now reads from **metis-library** (`metis.library.metrics.*`), so
`application/matching/library_catalogue.py` is back on the DAG. It enumerates the classes
re-exported flat from `metis.library.metrics.__init__` and emits canonical FQNs
`metis.library.metrics.<Class>`; the `MetricSpec`/`MetricParam` types it returns live in
`contracts/metric_spec.py`.

The wizard still depends on **metis-engine** in one place, breaking the DAG: `application/compile/experiment.py`
locates the experiment schema on disk relative to the installed `metis.engine` module (the schema
lives beside the engine package, not inside it). This is temporary and deliberate — it is one
`importlib.util.find_spec("metis.engine")` call, not an import of engine code. See `CHANGELOG.md`
for what closes it.
