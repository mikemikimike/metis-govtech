# User simulation redesign: judgement of proposal 4

This file records stage 1 (Judge) of
[#460](https://github.com/govtech-responsibleai/metis/issues/460): a verdict on each design
element of proposal 4, the runner-agent design for `metis engine simulate`. The design and
its evidence are in the investigation directory `/Volumes/Develop/exp/metis-user-simulation`
(`SR` below). Its brief is `SR/HANDOFF.md`. Other abbreviations follow the brief:
`SP` = `SR/proposals/proposal4/spike`, `V5` = `SP/experiments/orca-api-common-v5`, and
`BL` = `SR/baseline/run/orca-eval-20261017-132140`.

Every "METIS today" claim was checked against this checkout at
`7d2ff7e8142573c885bf1c090dc4a45a089b5409`, not against `d3e1179`. METIS paths are relative
to the repository root unless they start with `simulation/`, which is short for
`packages/engine/src/metis/engine/simulation/`.

Figures are marked **checked** when they were recounted from raw files in `V5` or `BL`, and
**on trust** when they come from `SP/FINDINGS.md` or `SR/HANDOFF.md` alone. The recount
scripts were run from `$TMPDIR` with `python -I` and only read `SR`.

| Element | Verdict |
| --- | --- |
| LLM-call log (Part 2) | **adopt** |
| Transport log (Part 2) | **adapt** |
| Trial record additions: validity and `stop_detail` (Part 2) | **reject for now** (checks move into `gen_2` and #462's `failure_source`) |
| 13. User agent: no target advice, file facts by code, promise list | **adapt** |
| 1. A runner agent instead of hand-written runners | **adapt** |
| 2. Code owns the facts; the LLM only cites logged evidence | **adopt** |
| 3. A file is recorded only from a real download whose bytes match its type | **adopt** |
| 4. Downloads are limited to this conversation | **adopt** |
| 5. The session ID comes only from a submission's answer | **adopt** |
| 6. One open submission at a time, defined by a code rule | **adapt** |
| 7. A closing step, `end_chat()`, after the last turn | **adapt** |
| 8. The YAML target profile | **adapt** |
| 9. Rereading the whole specification every round | **reject** (fix folded into card 1) |
| 10. `BrowserRunner` | **adapt** (taken untested) |
| 11. Turn semantics and `at_simulated_turn` | **adapt** |
| 12. LLM-built map of user-input fields | **reject** |
| Artifact ledger (Part 2) | **adapt** (write path only) |
| Workflow contract (Part 2) | **adapt** (a "run one trial" seam only) |

## Loading the records at this checkout

Every `record.json` in `V5` and `BL` has `schema_version: 2`. This checkout's `TrialRecord`
(`packages/core/src/metis/core/trials.py`) accepts only `1`, since `aea865d` reset the
`next` branch, so `TrialRecord.load_file` rejects all 18 as they stand on disk. For this
judgement each record was read with `json.load`, its `schema_version` was set to `1` in
memory only, and the result was passed to `TrialRecord.model_validate`. After that patch
all 18 validated (9 `V5`, 9 `BL`) (**checked**). Nothing in `SR` was written. The version
number is the only incompatibility. The extra keys in `V5` (`validity`, `stop_detail`,
`turns`, and others) are ignored because the model is `extra="ignore"`, and the baseline's
`conversation` key, which `TrialRecord` no longer has since #461, is ignored the same way.

Trial folders were matched with `trials/TC-*/` only. `V5/trials/` also contains a stray
`.claude/` directory, which is not a trial.

---

## LLM-call log

**Verdict: adopt.**

**Reason.** METIS cannot say today what a simulation cost, or which model actually answered
it. The log in `SR/common/llm-calls.md` writes one row per request with component,
requested model, returned model, tokens and latency, into one file per trial. That answers
both questions, and it doesn't depend on any other card. The `V5` logs show that the shape
is enough to give per-trial, per-component totals and to confirm the returned model, with no
other source. The spec's rules carry over unchanged. Its paths map onto METIS's layout,
which isn't a design change.

**METIS today.**

- The user agent calls `AsyncOpenAI.beta.chat.completions.parse` and logs prompt and
  completion tokens with `logger.debug` (`simulation/user_agent/agent.py`, lines 437–447).
  It doesn't record the requested or returned model, latency or failures, and it keeps no
  per-trial total. This matches the handoff.
- The handoff leaves out a second LLM caller. The artifact summarizer
  (`simulation/artifact_summarizer.py`, `_summarize_via_llm`, line 98) makes its own
  `AsyncOpenAI` call per text artifact, and once per fixture per experiment in
  `resolve_fixture_descriptions`, and **logs no usage at all**. So today's token counts are
  incomplete as well as being debug-only.
- Both clients keep the OpenAI SDK's default `max_retries` (2), so up to two retries per
  call are invisible. The engine's judge client (`packages/engine/src/metis/engine/evaluation/judge.py`,
  lines 95–110) relies on the same default by design.
- One handoff claim is too strong. `SP/FINDINGS.md` says tokens can't be compared with the
  baseline "since today's simulator logs none". The baseline's per-trial logs
  (`BL/logs/simulate-TC-*.log`) do hold the user agent's debug usage lines: 23 calls and
  84,850 prompt tokens over the 9 trials (**checked**). What they lack is the summarizer's
  calls, the returned model and latency.

**Evidence used.**

- Read `SR/common/llm-calls.md` in full, and `SP/p4/llm.py` (the spike's use of
  `LoggingLLMClient` with `max_retries=0`).
- Recounted every `V5/trials/TC-*/evidence/llm_calls.jsonl`:
  - 136 calls: 21 `user_agent`, 115 `runner_agent` (**checked**).
  - Every call requested and returned `bedrock.claude-haiku-4-5` (**checked**).
  - 0 errors, and no row has a `None` token count (**checked**).
  - Totals: user agent 100,264 in and 3,962 out; runner agent 2,101,215 in and 15,187 out
    (**checked**).
  - Per trial: user agent 2–3 calls, runner agent 8–24 (**checked**).
  - `V5/logs/llm_calls.jsonl`, the experiment-level file, is empty (**checked**).
- Per-trial input-token share of the runner agent. The handoff and #460 give **92–96%**,
  which holds only for TC-004 (92.8–95.3%) and TC-013 (95.0–95.6%). The three TC-001
  trials are 98.7–98.9%, and the whole run is 95.4% (**checked**). `SP/FINDINGS.md`'s own
  table gives the TC-001 numbers that contradict its range. This figure belongs to card 9
  rather than to this card, but it should be corrected before card 9 is judged.
- Baseline user-agent usage from `BL/logs/simulate-TC-*.log` debug lines (**checked**).

**Checks not run.**

- I didn't run the shared component's own tests (`SR/common/llm_calls/`).
- Nothing was run against a live gateway. The claim that a gateway can return a different
  model from the one requested is on trust. In `V5` the two always matched.

**Stage 2 note.**

- **Package.** `metis-engine`, as a shared module (`simulation/llm_calls.py`; see "Package
  layout"). The row model (`LLMCallRecord`) stays private to the engine, since nothing
  else reads the file yet. It moves to `metis-core` if `metis-insights` starts reading it.
- **Both paths** (card 1, item 6). On `gen_1` it wraps today's user agent and the
  summarizer, which is one of the two pieces of new work `gen_1` takes. That gives Orca
  runs real cost figures for stage 4 to compare `gen_2` against. On `gen_2` it wraps the new
  user agent and the runner agent from the start.
- **Retries.** Rule 2 allows two ways to keep retries visible: set the SDK's `max_retries`
  to 0, or route every attempt through the wrapper. METIS should take the second. If the
  user agent's call fails, `simulation/orchestrator.py` (lines 515–525) ends the trial as
  `system_error` rather than retrying, so turning SDK retries off would turn every
  transient gateway error into a failed trial.
- **Files.** Per trial: `outputs/trials/<id>/evidence/llm_calls.jsonl`. Calls made once per
  experiment, such as the summarizer's fixture descriptions, go to the experiment's
  `logs/llm_calls.jsonl`.
- **Depends on.** Nothing. Graders call `LLMSettings.client` directly
  (`packages/library/src/metis/library/grader.py`), so logging judge calls is a separate,
  later piece of work.

---

## Transport log

**Verdict: adapt.**

**Reason.** Nothing METIS writes today lets anyone check a record against what actually
crossed the wire. The handoff's main argument, that every prototype fix was found by
reading this log, is about debugging a runner agent, and it rests on runs that were
deleted. That argument still holds for the generic runners, since an LLM decides how they
act, and cards 2–5 need the log: code copies every fact in the record from a logged
entry. The log is also an independent check on the record. The format, the
append-only rule, the action/result pairing and redaction before writing all carry over.
What changes is the scope, where the log hooks in, and how download bytes are stored.

**METIS today.**

- Holds: nothing records the wire. `simulation/runners/orca_api/__init__.py` logs a few
  `INFO` events, such as "Submitting turn..." and "Session minted", but no request or
  response bodies. The baseline's per-trial logs contain no HTTP request lines
  (**checked**: 0 in `BL/logs/simulate-TC-004_domain-expert-perfectionist-01.log`).
- Every Orca API call already passes through one place: `v1_request`
  (`simulation/runners/orca_api/_transport.py`), which calls `send_with_backoff`, and
  `download_to` (`simulation/runners/_http.py`). Both use the `httpx.AsyncClient` from
  `build_client`, which also sets `Authorization`. The generic HTTP runner can reuse
  these helpers, so a request/response hook on its client would log every attempt,
  retries included, and could redact in one place.
- No live browser trial of the spike's design exists (card 10, C only), so the browser
  entry kinds have offline evidence only.

**What changes.**

1. **Scope.** The generic runners (card 1, item 6, `gen_2`): HTTP entries for the
   generic HTTP runner, and `browser_action` and `capture` entries for `BrowserRunner`.
   The Orca runners get no transport log, since they are kept only for reference.
2. **Where it is written.** The log is written at the `httpx` layer, not by each call site,
   so every attempt `send_with_backoff` makes gets its own pair of entries.
3. **Download bytes.** In `V5`, a downloaded file's bytes are stored twice: once as
   `evidence/*.bin` and once under `artifacts/`. For example, TC-004 #1 has 632 KB of
   evidence and 396 KB of artifacts (**checked**, `du`). A response body that is a
   downloaded artifact should point to the artifact's file and digest instead of a copy.

The spec's entry shape, `pairs_with`, code-written `summary`, the 64 KB inline limit and
caller-side redaction apply as written.

**Evidence used.**

- Read `SR/common/transport-log.md` in full.
- Recounted every `V5/trials/TC-*/evidence/log.jsonl`:
  - Requests and responses pair one to one: 7–83 of each per trial (**checked**).
  - All 12 `POST /api/v1/chat` requests carry `X-PlatformAI-Key: ***`, and no request has
    an unredacted `Authorization` or `X-PlatformAI-Key` header (**checked**, by matching
    header fields).
  - Log size is 98–320 KB per trial (**checked**). The OpenAPI fetches are 84–127 KB of
    that, a cost METIS's runners would not pay.
- Used the log to recheck the card 2–5 figures the handoff cites:
  - All 29 `source: target` files in `V5` trace to exactly one `GET .../content` request by
    their `external_id`, and every file's bytes match its type (PNG and OOXML magic bytes,
    JSON, UTF-8 text) (**checked**).
  - All 9 session IDs appear in a `POST /api/v1/chat` response body (**checked**).
  - The six TC-001 and TC-013 records each contain one "not part of this conversation"
    refusal (**checked**).
- "Every prototype fix was found by reading this log" (D9, D12, D14, D16, T19) is **on
  trust**, because those runs were deleted (evidence level B).

**Checks not run.**

- I didn't grep the literal credential values against `V5`, which `SP/FINDINGS.md` reports
  doing, because I didn't load `SR/stage2/.env`. My redaction check covers header fields
  only. A secret in a body or a URL would not have been caught.
- I didn't run the shared component's tests (`SR/common/transport_log/`).
- I didn't prototype a hook on the generic runner's `httpx` client, so it is unconfirmed
  that one hook sees every call. `download_to` streams, so it may need its own handling.

**Stage 2 note.**

- **Package.** `metis-engine`, as a shared module (`simulation/transport_log.py`; see
  "Package layout"), with the `LogEntry` model private to the engine. `gen_2`'s generic
  HTTP runner and `BrowserRunner` use it; `gen_1` could later. The writer, the redaction
  and the `httpx` hook live there too.
- **Depends on.** Nothing. Cards 2–5 depend on it.

---

## Trial validity (trial record additions)

**Verdict: reject for now.** The checks move into `gen_2`, and their result is reported
through #462's `failure_source` and `failure_message`. A `validity` field can be added
later if something comes to need it.

**Reason.** The problem is real. In earlier Orca experiments, 8 trials recorded the user
"giving up" because METIS never uploaded the file, and 29 kept talking to Orca after its
allowance ran out. Each was blamed on Orca. The requirement to catch such trials comes
from the investigation's problem statement (goal 2). But a separate `validity` field would
have no reader in METIS:

| Reader | What it uses from `record.json` | Would it read `validity`? |
| --- | --- | --- |
| `metis engine evaluate` (`packages/engine/src/metis/engine/cli.py`, `_evaluate_records`) | session ID, persona, scenario, task, grader refs, artifacts | No. It grades every trial it finds |
| Graders (`packages/library/src/metis/library/grader.py`) | nothing from the record: only traces and artifacts (`GradingInput`) | No, by design. A grader never sees the stop reason |
| `metis insights report` (`packages/insights/src/metis/insights/_report.py`) | `stop_reason`, and `failure_source` and `failure_message` once #462 writes them | Not today |
| `--resume` (`cli.py`, `_classify_resume_trials`) | `stop_reason`, to redo `system_error` trials | No |

(**checked** against this checkout.) The readers the spec names, the investigation's own
"user-simulation graders" and `AbandonmentGrader`, don't exist in METIS. The #428 redesign
removed graders' access to the record. #462 already gives the report a field for who
caused a failed trial, so "METIS broke this trial" can be one of its values and reach a
reader that exists.

**What is kept, and where.**

1. **The checks, in `gen_2`** (card 1, item 6). The generic runners still detect
   `fixture_never_uploaded` (a fixture whose upload turn is never set) and
   `submission_unresolved` (a submission that never settles). Each ends the trial, or marks
   it, through `failure_source` with a value that names METIS's simulator as the cause,
   and a `failure_message` saying which check fired. The exact value is for #462 to
   settle, together with its existing `target`, `user_agent` and `evaluation_runner`.
2. **`stop_detail`, not taken.** `failure_message` covers a failed trial's one-line
   reason. A sentence for every trial, including successful ones, has no reader either.
3. **`target_degraded`, not taken.** Orca gives no signal for it: once the allowance is
   spent, it "downgrades later turns to a cheaper model … and says so nowhere in the API"
   (`_report_usage` docstring, `simulation/runners/orca_api/__init__.py`). The `GET /usage`
   pre-flight warning stays the only signal.

**What is lost.**

- Marking a trial that ended `goal_achieved` as unfair, for example one where the user
  agent accepted an answer about a file that never arrived. #462's fields describe failed
  trials.
- Evidence pointers into the transport log for each reason.

Nothing reads either one today. If a reader appears (a report view that excludes unfair
trials, or a grader of simulation fidelity), `validity` can be added then, as an optional
field on the core `TrialRecord` with a default, so older records still load.

**METIS today.**

- `TrialRecord`, `TrialOutcome` and `TrialConfig` live in metis-core
  (`packages/core/src/metis/core/trials.py`, moved by `e3e9d0d`), not in
  `simulation/types.py`, where `SR/common/trial-record.md` confirmed them.
  `schema_version` is `1`, there is no `conversation` field (#461), and records are written
  to `outputs/trials/<id>/record.json`.
- `TrialOutcome` has optional `failure_source` and `failure_message` (added in `e3e9d0d`
  for #462), which the report reads. No engine code writes them yet.
- `target_exhausted` (`simulation/orchestrator.py`, lines 322–331) is today's only stop
  reason that blames the target for ending the trial.

**Evidence used.**

- Read `SR/common/trial-record.md`, the problem statement's goal 2 and constraints
  (`SR/user-simulation-problem-statement.md`), and `SP/p4/orchestrator.py`, where the
  spike sets its validity reasons.
- All 9 `V5` records are valid with no reasons (**checked**), so the live run never
  showed a check firing.
- The 8 and 29 earlier trials are **on trust** (from #460 and `SR/HANDOFF.md`).
- The 18-record load check in "Loading the records at this checkout" (**checked**).

**Checks not run.** The offline tests for `fixture_never_uploaded` and
`submission_unresolved` (skipped at review), so both checks are offline only (C).

**Stage 2 note.** The checks land in `metis-engine`, in `gen_2`. The cause value and its
wording are settled on #462, before #462 starts writing `failure_source`. `gen_1` uses the
same value: today's orchestrator writes it for its existing METIS-side failures, such as
the user agent's LLM call failing (decided at review).

## 13. The user agent: no target advice, file facts by code, a promise list

**Verdict: adapt.**

**Reason.** The card bundles four things, which deserve different verdicts.

- **Code-computed file facts: adopt for structured text files.** The baseline itself
  contains a live example of the problem: the summarizer described the 200-row fixture as
  "CSV file with 180 rows" in all six trials that carry it.
- **Removing Orca's model advice from the prompt: adopt.** That knowledge belongs to the
  target or scenario, not to the generic user agent. The advice also isn't reliably obeyed
  today.
- **Inlining file content: not adopted.** Its resend cost grows with every turn and every
  file. The user agent sees each file's facts only (decided at review).
- **The promise list and the ⟦ ⟧ natural-language action: part of `gen_2`.** Both depend
  on the runner agent (cards 1 and 7), and the promise list was never exercised in `V5`.

**METIS today.**

- Holds: the system prompt carries Orca advice, "IMPORTANT: When you see an "AI Model"
  dropdown, ALWAYS select "Fast (Claude Haiku)"" (`simulation/user_agent/prompts.py`,
  lines 80–82). It is unchanged since `d3e1179`, apart from "system" being renamed to
  "target".
- Holds: an LLM writes file descriptions (`simulation/artifact_summarizer.py`). Fixture
  descriptions are resolved once per experiment, and an author-supplied description takes
  precedence (`resolve_fixture_descriptions`). Prompt rules 8 and 9 tell the user agent to
  judge from those descriptions.
- Holds: the user agent emits typed actions (`upload_file`, `button_click`, `form_fill`)
  that name offered slots (`simulation/user_agent/agent.py`, `ActionSlot`).
- **Differs from what the card implies:** the advice doesn't make today's user agent
  choose Fast. In the baseline, TC-004 #1 and #2 filled `model_family` with
  `Detailed (Claude Sonnet)`, and only #3 chose `Fast (Claude Haiku)` (**checked**,
  `conversation[].user_ui_actions` in `BL`). So the card's point that the spike's TC-004
  "ran on a slower model than today's prompt would have chosen" applies to one baseline
  trial in three. Model choice confounds the TC-004 wall-clock figures on both sides: the
  baseline's Fast trial ran 206 s, its Detailed trials 249 s and 299 s (**checked**).

**What changes.**

All of this goes into `gen_2`'s new user agent (card 1, item 6). Today's user agent,
`simulation/user_agent/`, drives the Orca runners kept for reference and is left as it
is, including its Orca model advice and its LLM file descriptions.

1. **Facts.** A code-computed fact block replaces the LLM description for files whose
   structure code can read. For a CSV that is data rows, columns and header, as in
   `SP/p4/files.py` `compute_facts`. Author descriptions still take precedence.
   Binary files degrade to type and size, as both systems already do. Whether to keep an
   LLM summary for free text such as `.md` or `.py`, where code facts say little, is open.
2. **Facts only, no content.** The spike inlined up to 32 KB of every held file's content
   and resent it every turn, which `SR/reconciliation.md` records as growing without
   bound. `gen_2` shows each file as one facts line and never inlines its content, so the
   prompt stays small however many files a trial collects. A persona that would read a
   file in detail, such as the perfectionist in TC-004, works from its facts instead
   (decided at review, over capping or aging content out).
3. **No model advice.** `gen_2`'s prompt carries no target knowledge. If a fast model is
   wanted for an experiment, it should be stated in the scenario or persona text in the
   specification (which #442's metadata would also carry), not in the generic prompt.
4. **The rest belongs to `gen_2`.** The ⟦ ⟧ natural-language action and the promise list
   are part of `gen_2`'s user agent (card 1, item 6), with the promise list's evidence
   level set by card 7.

What still applies from the card's evidence: the code-computed facts are correct where the
LLM's were not. The spike's live rerun of TC-004 #1 after the fix
(`SP/experiments/post-fix-TC-004-tuning/`) records "CSV: 200 data rows, 5 columns" for
`q3_sales.csv` (**checked**), and the fixture really has 200 data rows and 5 columns
(**checked**, by counting `V5/inputs/fixtures/q3_sales.csv`, the same SHA-256 as
`BL/inputs/fixtures/q3_sales.csv`).

**Evidence used.**

- Read `SP/p4/prompts/user_agent.md` (41 lines), `SP/p4/user_agent.py` and `SP/p4/files.py`.
- Compared the TC-004 turns in `V5` and `BL`:
  - `V5`: turn 1 uploads the file and asks; turn 2 answers the model form; turn 3 decides
    `goal_achieved` (**checked**).
  - `BL`: two turns, with the same form answered on turn 2 (**checked**).
  - All three `V5` TC-004 trials chose "Detailed": the actions were "Choose ⟦Detailed
    (Claude Sonnet)⟧" twice and "Choose ⟦Detailed⟧" once (**checked**).
- File disputes:
  - No `V5` user-agent *action* disputes a file's contents (**checked**, by pattern search
    over `turns[].action`).
  - No `BL` user message mentions the wrong row count either (**checked**, by searching for
    "180" and "200" in `conversation[].user_message`).
  - The baseline user agent saw "180 rows" and never argued about it. So the 9 trials in
    either run can't show whether code facts prevent file arguments: the problem didn't
    appear in the baseline either.
- The summarizer's "180 rows" description, in all six `BL` TC-004 and TC-013 records
  (**checked**).
- User-agent input tokens per TC-004 trial: about 22,000 in `V5` against about 13,000 in
  `BL` (**checked**). This is consistent with inlined content costing more.
- `SR/STATUS.md` and `SR/reconciliation.md`, on reopening `files.py` on 2026-10-19.

**Checks not run, and limits.**

- **`V5` was produced by an earlier `files.py`.** The spike's `p4/files.py` and
  `p4/orchestrator.py` were last modified on 2026-10-19, after `V5` ran on 2026-10-17
  (**checked**, file timestamps). `SR/reconciliation.md` says the earlier version
  recomputed facts every turn. `V5`'s records carry no `content_description` at all
  (**checked**). So the facts the `V5` user agent saw can't be recovered from the records,
  and the code in `SP` today isn't the code that produced `V5`.
- **The user agent's reasoning isn't on disk in `V5`** (**checked**: no `reasoning` key in
  any `V5` file). The handoff's "its actions and reasoning searched for disputes; none
  found" is therefore on trust for the reasoning half. Only the actions were rechecked.
- The historical "152 rows" against "200 rows" argument is on trust.
- I didn't run `SP/tests/test_files.py` (offline tests skipped at review).

**Stage 2 note.**

- **Package.** `metis-engine`, as `gen_2`'s own user agent and file-facts code, beside the
  generic runners. `simulation/user_agent/prompts.py` and
  `simulation/artifact_summarizer.py` are not changed.
- **Depends on.** Card 1's `gen_2`. The promise list waits for card 7.
- **#442.** Persona and scenario metadata reach both generations' prompts through one
  shared function, added by whichever of #442 and `gen_2`'s user agent lands first, so
  the same persona is presented identically to both (decided at review).

---

## 1. A runner agent instead of hand-written runners

**Verdict: adapt.**

**Reason.** METIS is meant to simulate any user's app. Orca is the target it was built
against, and a stepping stone, not the limit of what it serves. Today every target needs
its own hand-written runner (`orca_api` is 1,394 code lines, plus a 146-line shared HTTP
helper). That is a cost each new target pays again, and it lands on whoever brings the
app. One generic runner per transport, driven by a short profile and the target's own
API spec, is the design that turns a new target into a configuration file. The prototype
shows that the design can work: on Orca's API it ran 9 of 9 trials with no Orca-specific
Python. It also shows that it works only if code, not the LLM, owns every fact in the
record. So the direction is right. What changes is how it lands in METIS, because the
evidence covers one target, the cost is high, and the six fixes show the generic code
hasn't settled yet.

**What changes.**

1. **Added beside the hand-written runners, not replacing them.** The generic HTTP runner
   becomes a third `RunnerFactory` that a specification selects with
   `runner_factory_ref`. `orca_api` stays the reference and the default for Orca until the
   generic runner matches it on the same 9 trials (stage 4). `orca_playwright` stays as
   the runner for Orca's UI until card 10's `BrowserRunner` has a live run.
2. **HTTP targets with an OpenAPI spec come first.** That is the only case with live
   evidence. Browser UIs follow with card 10's `BrowserRunner`, taken untested. Other
   transports, such as WebSocket, are not covered.
3. **Cost is part of the design, not a later optimisation.** The runner agent took 95.4%
   of input tokens over the run, and 98.7–98.9% on the one-turn task (**checked**),
   because the whole spec is resent on every tool round. For METIS's users, this cost is
   paid on every trial of every target. Card 9's fix, sending each round only the parts
   of the spec it needs, is a requirement for the METIS version, not debt to pay later.
4. **Its record must match the existing runners' record.** It writes the same
   `TrialRecord`, with the round-1 additions (LLM-call log, transport log), so
   `evaluate` and `insights` don't need to know which runner ran.
5. **Its proof needs a second target.** The design's central claim, that a new target
   needs a profile and no code, is still untested. METIS's own users will supply the
   targets. Before the generic runner is presented to users as the way to add a target,
   it should be bound to one non-Orca target with an OpenAPI spec, and the code fixes
   that takes should be counted. A small public or in-house API is enough. This is the
   card's own cheapest check, moved to stage 4.
6. **Two simulation paths, one record: `gen_1` and `gen_2`.** The generic runners don't
   fit today's `Runner` seam. `send_turn(message, actions)` takes typed actions that name
   slots the runner offered (rules I1 and I5 in `docs/runner-contract.md` are written
   against them), while the generic runner takes one plain-language action and offers no
   slots. The two `Observation` types share almost no fields. So `metis engine simulate`
   holds two paths, and the specification's `runner_factory_ref` picks one per
   experiment:

   ```
                        metis engine simulate
                                 │
             specification's runner_factory_ref picks one
                ┌────────────────┴────────────────┐
                ▼                                 ▼
      gen_1 (today, kept for reference)    gen_2 (new, generic)
      today's user agent: typed actions    card 13's user agent: one
      today's orchestrator                   plain-language action
      Runner.send_turn(message, actions)   new turn loop: act() + end_chat()
      orca_api, orca_playwright            generic HTTP runner, BrowserRunner
                └────────────────┬────────────────┘
                                 ▼
                    the same record.json (TrialRecord)
                                 │
                metis engine evaluate, metis insights report
   ```

   `gen_1` is left as it is. Its runners are kept for reference and get no new work
   beyond fixes that keep them running, with two exceptions decided at review: the
   LLM-call log wraps today's user agent and summarizer, and today's orchestrator writes
   #462's `failure_source` for METIS-side failures, using the same cause value `gen_2`
   uses. Neither changes how `gen_1` behaves. `gen_2` is new, with its own user agent and
   turn loop. Both write the same `TrialRecord`, so nothing after simulation can tell which
   path ran. What they share is `RunnerFactory` (`start`, `create`, `close`), the
   experiment's retry loop and the record. The factory named in `runner_factory_ref`
   decides the path, through the "run one trial" seam (see "Workflow contract"). When the
   Orca runners are retired, `gen_1` is deleted as a whole. The names and the files
   behind them are in "Package layout".

   Two other ways were considered and not taken. Wrapping the generic runner in today's
   typed-action interface would make it invent slots for every target, which is the kind
   of LLM-built map card 12 shows failing. Giving the Orca runners an `act()` adapter
   would need an LLM to turn plain language into typed actions, which is new work on
   runners kept only for reference.

**What still applies from the card's evidence.**

- The 9 of 9 Orca API trials with no Orca-specific Python, bound by a 23-line profile
  (**checked**: `SP/targets/orca-api.yaml` is 23 lines; outcomes from `V5` records).
- The split of work: code owns submissions, the session ID and file bytes. 29 of 29 files
  traced to a real download, and 9 of 9 session IDs matched a chat response
  (**checked**).
- The six live-failure fixes are the list of things the METIS version must not get wrong.
  They are cards 3–6 and 7. The failures behind them are **on trust** (evidence level B).

**METIS today.**

- Holds: two hand-written Orca runners. `simulation/runners/orca_api` is 2,331 raw lines
  and `simulation/runners/orca_playwright` is 2,189 (**checked**; `orca_api` is unchanged
  since `d3e1179`, and `orca_playwright` differs by one line). Every
  `runner_factory_ref` outside the tests names `OrcaApiRunnerFactory`.
- `docs/guide/engine.md`, "Adapting to Your Target", tells a user with a new target to
  write their own `Runner` and `RunnerFactory` in Python. That is the cost this card
  removes.
- **The line counts the handoff compares aren't like for like.** The spike's 2,293 is
  pygount code lines. The runners' 2,331 and 2,189 are raw lines. Counted the same way
  (code lines only: no blanks, comment-only lines or docstrings), it comes out as
  follows (**checked**, my own counter, which gives 2,534 for the spike's 13 files where
  pygount gave 2,293):

  | What | Code lines |
  | --- | --- |
  | Spike generic code without `browser_runner.py` (the HTTP path) | 2,104 |
  | Shared components it imports (`SR/common/*/_*.py`) | 1,476 |
  | `simulation/runners/orca_api` | 1,394 |
  | `simulation/runners/_http.py` (used by `orca_api`) | 146 |
  | `simulation/runners/orca_playwright` | 1,707 |

  For one target, the generic path is larger. Its size is paid once, though, while a
  hand-written runner's is paid for every target. From about the second HTTP target
  onward, the generic path is smaller in total.
- Orca's own changes have already forced runner changes in METIS: #338 (aligning with
  Orca's v1 spec), #337 (Vega-Lite charts missing from Orca's digest) and #374 (poll-lane
  digest failures). All 21 commits touching `orca_api` since 2026-08-01 are by METIS
  maintainers. Every new target would add the same upkeep.

**Evidence used.**

- Read `SP/p4/http_runner.py`, `SP/p4/runner.py` and `SP/p4/orchestrator.py` beside
  `simulation/runners/orca_api/__init__.py` and `simulation/runner.py`, and read
  `SP/targets/orca-api.yaml`.
- `V5` outcomes and the round-1 recounts (**checked**).
- Wall-clock (**checked**, `outcome.duration_seconds`):

  | Task | `V5` | `BL` |
  | --- | --- | --- |
  | TC-001 | 58–65 s | 22–32 s |
  | TC-004 | 221–259 s | 206–299 s |
  | TC-013 | 59–75 s | 36–169 s |

  TC-004 is confounded by model choice on both sides (see card 13).
- Agent behaviour code still had to refuse in `V5`:
  - The account-wide file listing was tried in 6 of 9 trials (**checked**, the records'
    refusals).
  - 26 of the 27 lines in `V5/logs/simulate.log` are `refused …` entries (**checked**).
    Among them are form answers sent under an invented field name or for an option the
    user didn't choose, and ledger appends citing a JSON path that doesn't exist.
  - These show that the agent's mistakes keep recurring and the code rules keep catching
    them. That is the reason cards 3–6 are needed, not a reason against the card.
- The six live-failure fixes (D9, D12, D14, D16, T19, T20) are **on trust**.
- The code-line counts above (**checked**).

**Checks not run.**

- **The card's deciding check, binding a second HTTP target from a profile alone.** No
  second target was available. It moves to stage 4 (item 5 above), so this verdict rests
  on Orca evidence and on reasoning about future targets.
- I didn't run the offline tests (skipped at review).
- No live run of any kind. Whether the spike's behaviour holds on a model other than
  `bedrock.claude-haiku-4-5` is unmeasured.

**Stage 2 note.**

- **Package.** The generic HTTP runner, its runner-agent loop and its tools go in
  `metis-engine`, under `simulation/gen_2/` (see "Package layout"), as a new
  `RunnerFactory`. The target profile is a user-written file contract, so its model and
  published schema go in `metis-core` (`packages/core/schemas/`), registered in
  `packages/core/scripts/generate_schema.py`.
- **Depends on.**
  - The round-1 transport log and LLM-call log. Code-owned facts cite transport entries,
    and cost must be measurable.
  - The validity checks, reported through #462's `failure_source` (see "Trial validity").
  - Card 13's user-agent changes, so no target advice remains in the prompt.
  - Cards 2–9 as round 3 judges them, especially cards 3–6 and 9.
  - Card 7's closing step, owned by the generic runner (no change to `gen_1`'s seam).

**Effect on round 3.** Card 1 is adapted, so cards 2–9 are judged on their merits, not
rejected together. Cards 3–6 are where the prototype paid for its lessons, so dropping
any of them needs a stated reason.

## 2. Code owns the facts; the LLM only cites logged evidence

**Verdict: adopt.**

**Reason.** This is the principle that made card 1 work, and it is what lets METIS trust
a record written by a runner agent for an app nobody at METIS has seen. The runner agent
decides *how* to act. Every fact in the record is copied by code from a logged transport
entry: what was sent, the reply, the session ID, each file and its bytes. Each time the
prototype let the LLM state a fact directly, it failed live (D14, D16, T19). In `V5`,
where code owned the facts, every fact checked out. It costs a pointer-based tool design
(the agent passes entry IDs and JSON paths, never values), which the spike already
shows is workable on a small model.

**METIS today.** Hand-written runners write their own facts in code, so the rule is met
by construction for `orca_api` and `orca_playwright`. The handoff's description holds. It
matters only for the generic runner from card 1.

**Evidence used.**

- Read `SP/p4/runner.py`, where every base tool takes pointers
  (`artifact_ledger_append`, `session_id_from`, `report.reply_from`) and copies values
  through `resolve()`.
- `V5` (**checked**): 29 of 29 files trace to exactly one `GET .../content` request, with
  bytes that match their type; 9 of 9 session IDs first appear in a `POST /api/v1/chat`
  response that the record lists as a submission's answer.
- The three live failures without the rule are **on trust** (evidence level B).

**Checks not run.** No offline tests (skipped at review).

**Stage 2 note.** `metis-engine`, inside the generic runner's tool layer. It depends on
the transport log (round 1), because the pointers resolve into it.

## 3. A file is recorded only from a real download whose bytes match its type

**Verdict: adopt.**

**Reason.** Without this rule, the runner agent recorded Orca's JSON chat reply as every
"delivered" file: 57 fake files in three runs, with no download made. A record that
holds a chat reply under a `.docx` name would mislead every grader that reads it. The
rule is small: one download per file, and a check of the first bytes against the
extension (`bytes_problem()` in `SP/p4/runner.py`). It knows nothing about any target,
so it carries to any app.

**What it covers and doesn't.** The check catches wrong *kinds* of content: JSON instead
of a file, or a file that doesn't start with its type's signature. It can't catch a file
of the right type with the wrong content, and it says nothing for extensions outside its
list (`.csv`, `.txt`), except that they must not be a JSON document. That is enough for
the failure it was built for.

**METIS today.** `simulation/runners/orca_api/_artifacts.py` streams each file from
`GET /files/{fileId}/content` and doesn't check its bytes. As the handoff says, a
hand-written runner doesn't need the check because it never mistakes a listing for a
file. The generic runner does.

**Evidence used.**

- Read `bytes_problem()`, `_tool_artifact_ledger_append` and `_tool_fetch_files`
  (`SP/p4/runner.py`, `SP/p4/http_runner.py`).
- `V5` (**checked**): every PNG starts with the PNG signature, every `.docx` with the
  OOXML (zip) signature, every `.vl.json` parses as JSON with a `$schema`, and every other
  text file decodes as UTF-8.
- The 57 fake files (D14) are **on trust**.

**Checks not run.** `SP/tests/test_http_trial.py::test_bytes_must_match_the_name` (offline
tests skipped).

**Stage 2 note.** `metis-engine`, in the generic runner's download tool. It could also be
used by `orca_api`'s download path at little cost, as a defence against a target that
answers a download with an error page.

## 4. Downloads are limited to this conversation

**Verdict: adopt.**

**Reason.** Most real apps will have some "list everything this account owns" endpoint,
and the runner agent reached for Orca's in 6 of 9 `V5` trials. Without the rule, one
trial recorded about 1,850 files from other sessions as its own deliverables. That both
corrupts the record and copies other users' files into METIS's output. The rule
(`is_this_trials()`) accepts a listing only if it answers one of this trial's
submissions, or answers a request whose URL names an ID this trial was given. That is
target-agnostic. The 100-files-per-fetch cap behind it is a second guard.

**METIS today.** `orca_api` lists only `GET /sessions/{id}` for its own session, so the
question doesn't arise. The handoff holds.

**Evidence used.**

- Read `is_this_trials()`, `trial_ids()` and `MAX_FILES_PER_FETCH` (`SP/p4/runner.py`,
  `SP/p4/http_runner.py`).
- `V5` (**checked**): the six TC-001 and TC-013 records each contain one
  "not part of this conversation" refusal, from the closing step, and none of those
  trials recorded a target file.
- The ~1,850-file run (D16) is **on trust**.

**What to watch.** The rule trusts that an ID this trial was given (any string of 8 or
more characters in a submission's answer) appears only in this trial's URLs. A target
that reuses long IDs across sessions would weaken it. That is untested.

**Checks not run.** `test_account_wide_listing_is_refused` (offline tests skipped).

**Stage 2 note.** `metis-engine`, in the generic runner's download tool. It depends on
the transport log.

## 5. The session ID comes only from a submission's answer

**Verdict: adopt.**

**Reason.** The session ID is how `evaluate` finds the trial's Langfuse traces, so a
wrong one makes the whole trial ungradable, or worse, graded against another session.
In one earlier run the agent took a file ID from an upload response as the session ID.
The rule (`_tool_session_id_from`) accepts only a value from the target's answer to a
submission, refuses a value that is a held file's ID, and refuses a second, different
ID. Those checks name no target.

**METIS today.** Each hand-written runner implements `get_session_id()` in code
(`simulation/runner.py`). The handoff holds.

**Evidence used.**

- Read `_tool_session_id_from` and `_answers_submission` (`SP/p4/runner.py`).
- `V5` (**checked**): in all 9 trials, the session ID first appears in the body of the
  trial's first `POST /api/v1/chat` response, and that response is recorded as a
  submission's answer.
- The earlier wrong ID (T19) is **on trust**.

**What to watch.** `_answers_submission` also accepts any entry logged after the first
submission, such as a poll. That is looser than the card's wording. It held in `V5`,
but the METIS version should state which entries count.

**Checks not run.** `test_session_id_is_not_taken_from_an_upload` (offline tests skipped).

**Stage 2 note.** `metis-engine`, generic runner. Its `get_session_id()` returns the
value code recorded.

## 6. One open submission at a time, defined by a code rule

**Verdict: adapt.**

**Reason.** Keeping one submission open at a time is needed. Two overlapping messages
would make turn counting meaningless and could make the target answer twice. Defining a
submission by a code rule instead of an LLM-built map is also right, since the map was
wrong 3 of 3 times (card 12). What needs adapting is the rule itself: "any POST, PUT or
PATCH with a JSON body" fits Orca, but not every app. Some apps take a chat message as
a form or multipart post, and many have JSON writes that aren't messages (settings,
renames). For Orca the rule worked: the only non-JSON write was the file upload, which
is correctly not a submission.

**What changes.** The code rule stays the default. The target profile can name a
target's submission endpoints exactly, for example `submissions: ["POST /api/v1/chat"]`,
and when it does, the profile wins. That keeps the decision in code and configuration,
never in the LLM. The settle-only-by-polling rule stays.

**METIS today.** Runner contract I4 (`docs/runner-contract.md`) limits the *caller* to one
`send_turn` per turn and leaves the inside to each runner. The handoff holds.

**What still applies from the card's evidence.**

- `V5` (**checked**): 12 submissions across the 9 trials, all accepted, all settled, and
  none sent before the previous one settled. Every write request was either a chat
  submission or the `POST /api/v1/files` upload (multipart, so not a submission).
- The refusal path (a second submission while one is open) is offline only, C.

**Checks not run.**
`test_second_submission_refused_while_open_and_poll_404_is_unresolved` (offline tests
skipped).

**Stage 2 note.** `metis-engine` (generic runner) for the rule. The profile field goes in
the profile model in `metis-core` (card 8).

## 7. A closing step, `end_chat()`, after the last turn

**Verdict: adapt.**

**Reason.** Any target that produces files can make some available without naming them
in its reply, and a generic runner can't know each target's quirks in advance. A
closing step that lists what the session holds and fetches what's missing is the
generic answer. The `V5` evidence is narrower than the card suggests, though: all 8 files
the closing step fetched in the three TC-004 trials were Vega-Lite `.vl.json` chart
specs (**checked**), which is exactly the gap `orca_api` already closes per target
(#337). So the evidence shows the step solves the one known case, not a broader one.

**What changes.**

1. **It isn't added to every runner.** The card's cost is that every runner would have
   to implement `end_chat()`, even as a no-op. Instead, the generic runner owns it,
   called from the end of its own last turn or from `teardown()`. The `Runner` seam in
   `simulation/runner.py` stays as it is. `orca_api` keeps its per-turn reconciliation.
2. **The promise list waits.** It was never exercised in `V5`: no trial recorded a
   promised file (**checked**, `promised` is empty in all 9 records). It is kept as part
   of the generic runner's design, with evidence D.

**METIS today.** `_artifacts.py` reconciles each settled turn against `GET /sessions/{id}`,
because the digest omits Vega-Lite specs (its module docstring cites #337). The handoff
holds.

**Evidence used.**

- Read `end_chat()` and `CLOSING` (`SP/p4/runner.py`) and `SP/p4/orchestrator.py`.
- `V5` (**checked**): the closing step fetched 2, 3 and 3 files in the TC-004 trials,
  all `.vl.json`, and 0 elsewhere. In TC-001 and TC-013 it tried the account-wide
  listing and was refused (card 4).

**Checks not run.**
`test_fetch_files_then_end_chat_collects_late_files_and_records_unmet_promise` (offline
tests skipped).

**Stage 2 note.** `metis-engine`, inside the generic runner. No change to the `Runner`
ABC or `docs/runner-contract.md`.

## 8. The YAML target profile

**Verdict: adapt.**

**Reason.** For a user to add their own app, the profile *is* the product surface: it is
what they write instead of a runner. So it needs to be a validated, documented file
contract, not a loose YAML file the code reads. The prototype's profile is short (23
lines for Orca) and covered what Orca needed. But four of the eleven corrections
(A2 server URL, A3 secret headers, A4 TLS, A11 preflight reads) needed new generic
code because the profile couldn't express them. A second app will likely need more of
the same. So the fields need to be designed for growth, and each new field documented.

**What changes.**

1. **A core model with a published schema.** The profile becomes a Pydantic model in
   `metis-core`, published as a `*.schema.json` in `packages/core/schemas/`, so users get
   validation and editor help. The shared-schema rule in `AGENTS.md` requires this.
2. **Only fields code checks.** The prototype mixes fields code enforces
   (`forbidden_calls`, `secret_headers`, `tls_verify`) with advice (`limits`, `notes`).
   Advice is fine, but should be marked as advice in the schema.
3. **A submissions field** for card 6.
4. **Where the profile is referenced.** Today a specification names a runner with
   `runner_factory_ref`. The generic runner needs that plus a profile path. Two ways to
   write it:

   ```yaml
   # 1. A named field of the specification (preferred)
   runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
   target_binding: targets/my-app.yaml

   # 2. Inside the factory's own settings, as orca_api's config.yaml does today
   runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
   runner_config: targets/my-app.yaml
   ```

   The first is preferred, because the profile is what a user writes for their app, so
   it reads better as a named field than as hidden runner settings. It is a change to
   `Specification` in `metis-core`. Decided in stage 2. The model is named
   `TargetBinding`, and the field `target_binding`, because `TargetProfile` already
   names the Target and its Features (#478).

**METIS today.** As the handoff says: `simulation/runners/orca_api/config.yaml` holds
Orca's runner settings, validated by the Pydantic model in `_config.py` (112 lines), and
the rest of Orca's knowledge is code.

**What still applies from the card's evidence.** The Orca profile and its corrections,
A1–A11 (`SP/plan.md`, section 3), as the first worked example. 23 lines (**checked**).

**Checks not run.** Writing a second target's profile. There is no second target (see
card 1, item 5).

**Stage 2 note.** The model and schema in `metis-core`, registered in
`packages/core/scripts/generate_schema.py`. Loading and use in `metis-engine`. Until stage
4 has bound a second app, writing a profile is documented only in a developer README beside
the code (`simulation/gen_2/README.md`), stating that it has been tested on Orca's API
only. After that, the user guide (`docs/guide/engine.md`, "Adapting to Your Target")
gains a "write a profile" path beside "write a runner" (decided at review).

## 9. Rereading the whole specification every round

**Verdict: reject** (as designed). The fix goes in card 1's adapt.

**Reason.** This is the design choice behind the cost: every tool round resends the
runner agent's whole conversation, which starts with about 16,000 input tokens before
the agent has done anything. Each act's first round took 16,232–18,457 tokens
(**checked**), and on average a runner call took about 18,000. For a user, that is paid
on every round of every trial of their app, and grows with the size of their API's
spec. Rejecting the "whole spec every round" part doesn't reject the idea of working
from the live spec. It means sending each round only the parts it needs.

**What should replace it** (stage 2, inside the generic runner):

- an index of the spec's operations up front (method, path, summary), with a tool to
  fetch one operation's full schema when needed;
- fetching the spec once per trial, not once per act. `V5` fetched it 2–3 times per trial
  (**checked**), which costs little in tokens but adds wall-clock;
- trimming old tool results from the conversation once they're cited.

The handoff's own recommendation agrees: trimming what is resent matters more than
caching the fetch.

**METIS today.** Not applicable: hand-written runners send no spec to an LLM.

**Evidence used.**

- `V5` `llm_calls.jsonl` (**checked**): 115 runner-agent calls, 2,101,215 input tokens,
  95.4% of the run's input tokens; per trial 92.8–98.9%; each act's first round
  16,232–18,457 tokens.
- Wall-clock against the baseline (**checked**, card 1).
- The spec file the fake Orca uses, `SP/reference/orca-openapi.json`, is 42 KB.

**Checks not run.** No measurement of a trimmed design. Its saving is reasoned, not
measured.

## 10. `BrowserRunner`

**Verdict: adapt** (taken untested, by the maintainer's decision at review).

**Reason.** METIS's users will bring apps that only have a web UI, so the generic design
needs a browser runner as well as an HTTP one. `SP/p4/browser_runner.py` is that runner
for the same design: it shares the runner base, so code still owns every fact, and it
records files through the same write path and byte check as the HTTP runner. It is taken
as the starting point, with its evidence level stated plainly: offline only (C). It has
never met a live page, and its login note predates Orca's login change. Taking it now
keeps the design whole for both transports, instead of designing the HTTP side alone and
fitting a browser runner to it later.

**What changes.**

1. **Built after the generic HTTP runner**, on the same base, so the parts both
   transports share (the tool loop, code-owned facts, the artifact write path, the
   validity checks) land once.
2. **Login is redone** for Orca's current flow before any live run. The spike's
   `login()` and `SP/targets/orca-web.yaml` (W1–W4) are known to be stale.
3. **Its proof is a live browser run in stage 4**, on `orca-web` or a user's app. Until
   then it is documented as untested, and `orca_playwright` stays the runner for Orca's
   UI.
4. **The transport log covers it.** Its `browser_action` and `capture` entries come with
   it (see "Transport log").

**METIS today.** `simulation/runners/orca_playwright` (2,189 raw lines) drives Orca's UI
with Orca-specific selectors. The maintainers have treated it as legacy since the API
runner became the default for Orca (a team decision, not written down in the
repository), so it is not a base to grow a generic browser runner from.

**What still applies from the card's evidence.** Only the offline tests' coverage, as
listed in `SP/FINDINGS.md` (Build state): login through a secret, an upload check, a
submission settled by `wait_for`, a session ID cut from the URL, and a download recorded
from the logged event. All of it is **on trust**.

**Evidence used.** Read the module docstring and size of `SP/p4/browser_runner.py` (523
lines) and its download path (lines 497–511), and `SP/FINDINGS.md`'s `orca-web` section
(on trust).

**Checks not run.** No live run exists. The offline tests were skipped at review, and
they need Chromium outside the macOS sandbox anyway (`SP/FINDINGS.md`, D3).

**Stage 2 note.** `metis-engine`, under `simulation/gen_2/runners/`, as a second generic
`RunnerFactory`. It depends on the generic HTTP runner's base, the transport log's
browser entry kinds, and the artifact write path. Playwright is already a dependency of
`orca_playwright`.

## 11. Turn semantics and `at_simulated_turn`

**Verdict: adapt.**

**Reason.** "One user action per turn, however many tool rounds it takes" is the right
definition for a generic runner, and it matches what METIS counts today: one user-agent
decision, one `send_turn`. A turn doing more target work than before (TC-004 turn 2
answered a form and fetched 6–8 files, **checked**) is by design and harmless. The
part to adapt is `at_simulated_turn`, which the spike numbers differently from METIS.

**What changes.**

- **`at_simulated_turn` follows METIS's numbering.** METIS stamps `at_simulated_turn` with the 1-based turn
  number on which the file moved (`simulation/orchestrator.py`, lines 591 and 594). The
  spike stamps `turn - 1`, so its first turn's upload is `0` and turn 2's downloads are
  `1` (**checked**, `V5` TC-004 #1). The same trial would put the same file on different
  numbers depending on the runner. The generic runner must use METIS's convention.
- **The closing step's files keep the last turn's `at_simulated_turn`**, as in the spike, and the
  closing step isn't counted in `total_turns`.

**METIS today.** `TrialOutcome.total_turns` counts completed turns, and `Artifact.at_simulated_turn`
is the 1-based turn (see above). No reader of `at_simulated_turn` exists outside the simulation
package (**checked**, by grepping `packages/` and `apps/`).

**Evidence used.** `V5` `turns[].gestures` (**checked**): 12 turns, 3 doing more than one
thing, all TC-004 turn 2.

**Known limit.** Keeping METIS's numbering also keeps #427's mismatch: evaluation compares
`at_simulated_turn` with a trace's position in the session, which is a different count, so a file
can attach to the wrong turn. `gen_2` is no worse than `gen_1` here. #427 is fixed once,
for both, outside #460 (decided at review).

**Checks not run.** Alignment of turns with Langfuse traces, which needs #469.

**Stage 2 note.** `metis-engine`, generic runner. No contract change.

## 12. Rejected: an LLM-built map of user-input fields

**Verdict: reject.**

**Reason.** It was wrong 3 of 3 times, in three different ways, and a wrong map blocked
a valid upload and produced a wrongly blamed trial. Its job is now done by a code rule
(card 6), and by measuring per turn whether the user's words reached the target verbatim
instead of enforcing it. That measurement is cheap and worth keeping in the generic
runner's record.

**METIS today.** Nothing like it exists.

**Evidence used.** `SP/FINDINGS.md` D9 and D12 (**on trust**; those runs were deleted).
`V5` `turns[].verbatim` (**checked**): `true` on every free-text turn, and `false` only on
the three form-answer turns where a label was correctly sent as its value.

## Artifact ledger

**Verdict: adapt.** Take the ledger's write path. Keep METIS's record shape.

**Reason.** The ledger has two parts, and they deserve different verdicts:

```
 ArtifactLedger
 ├─ data: a list of Artifact entries       METIS already has this (TrialRecord.artifacts);
 │                                          the ledger cloned METIS's Artifact class
 └─ write path: one add() that every        METIS has no single equivalent
    transfer goes through
      • saves the bytes under a safe name in this trial's folder
      • never overwrites a file or an entry
      • sets path, digest, hash and state itself
```

The data part adds nothing. Its one change, recording an upload as a second entry, is
what makes each fixture appear twice in every `V5` record. The write path is what METIS
lacks: today each runner records files its own way. With cards 1 and 10 adapted, both
generic runners, HTTP and browser, need one place where a file is recorded and where
cards 2 and 3's checks run, so the checks aren't rebuilt per runner.

**What changes.**

1. **The record keeps METIS's shape.** `Artifact` stays in `metis-core` unchanged. There
   is one entry per fixture, with the upload turn stamped on it, so nothing is listed
   twice. Earlier re-uploads, which today's record loses, don't need a second entry,
   because the transport log records every upload request.
2. **One write path for the generic runners.** Append-only, safe file names that never
   overwrite, digest and state set by code, partial downloads never kept, and the byte
   check from card 3. The generic HTTP runner and `BrowserRunner` use it from the start.
   `orca_api` and `orca_playwright` stay on their own code, since they are kept only for
   reference (card 1, item 6). `orca_playwright`'s overwrite risk stays covered by
   moving old files aside before a retry.

**METIS today.**

- `orca_api` picks safe, unused names itself (`_local_name` and `_unused_path` in
  `simulation/runners/orca_api/_artifacts.py`), and `download_to`
  (`simulation/runners/_http.py`) never leaves a half-written file.
- `orca_playwright` saves with `download.save_as()` under the page's suggested filename
  (`simulation/runners/orca_playwright/__init__.py`, around lines 430 and 454), with no
  check for a clash. `simulation/_artifact_store.py` records that it used to overwrite
  attempt 1's file. That is now prevented only by moving old files aside before a retry.
- The orchestrator changes the fixture's entry in place when it is uploaded
  (`simulation/orchestrator.py`, lines 574–592), so only the last upload of each fixture
  survives in the record.

**What still applies from the card's evidence.** The write path's guarantees held in
`V5`: 29 of 29 target files saved, each traced to one download, with no overwrites
(**checked**).

**Evidence used.**

- Read `SR/common/artifact-ledger.md`, and `SP/p4/runner.py`'s `_record_upload` and
  `_record_download`, which both transports call.
- `V5` (**checked**): each TC-004 and TC-013 record lists `q3_sales.csv` twice, once with
  `at_simulated_turn` unset and once with `at_simulated_turn` 0 and Orca's file ID.

**Checks not run.** The shared component's own tests (`SR/common/artifact_ledger/`).

**Stage 2 note.** `metis-engine`, as a shared module (`simulation/artifacts.py`; see
"Package layout"), used by `gen_2`'s runners and available to `gen_1`. It writes METIS's
own `Artifact` from `metis-core`, which is unchanged, so nothing new goes in
`metis-core`. It depends on nothing new.

## Workflow contract

**Verdict: adapt.** Take only a "run one trial" seam. Keep the existing retry loop and
`RunnerFactory`.

**Reason.** The contract exists so that different ways of running simulations can sit
side by side, and card 1's two paths (item 6) are exactly that. Today
`simulation/experiment.py` always builds today's orchestrator for every trial, so naming a
generic runner's factory in `runner_factory_ref` would still run `gen_1`'s user agent and
turn loop around it. The experiment's retry loop needs one seam it calls per trial, with
one implementation per path. That is the core of the contract's `create_trial` and
`Trial.execute()`. The rest of the contract isn't needed: METIS already has its own
lifecycle (`RunnerFactory`'s `start`, `create`, `close`), its own retry loop, and its own
selection by `runner_factory_ref`.

**What changes.**

1. **One seam, chosen by the factory.** A runner factory says which path its runners
   belong to, and hands the experiment the matching trial runner: today's orchestrator
   for `gen_1`, `gen_2`'s turn loop for `gen_2`. The user never picks a path directly. It
   follows from the runner the specification names:

   ```
    runner_factory_ref names…                      → generation
    ──────────────────────────────────────────────   ─────────────────────────────────
    …orca_api.OrcaApiRunnerFactory                   gen_1 (today's user agent and loop)
    …orca_playwright.OrcaPlaywrightRunnerFactory     gen_1
    …<generic HTTP runner factory>                   gen_2 (new user agent and loop)
    …<BrowserRunner factory>                         gen_2
   ```

2. **The retry loop stays.** `simulation/experiment.py` keeps its attempts,
   `prior_failures`, delays and partial records. It calls the seam instead of building
   the orchestrator directly. Both paths return a `TrialRecord`.
3. **Not taken:** the contract's own lifecycle, its `check()` pre-run step, its retry and
   deadline caller, and its `trials/<id>/attempt-<k>/` layout. METIS's existing pieces
   cover them, or the round-1 logs do (one LLM-call log and one transport log per
   attempt).

**METIS today.** `RunnerFactory` and `Runner` (`simulation/runner.py`),
`runner_factory_ref`, which the specification requires (`docs/guide/engine.md`), and the
retry loop in `simulation/experiment.py`. The handoff's "`RunnerFactory` plus the
orchestrator" holds.

**Evidence used.** Read `SR/common/workflow-contract.md` and `simulation/experiment.py`'s
retry loop. The `V5` trials ran with no retries, so the contract's retry paths are offline
only (C).

**Stage 2 note.** `metis-engine`: the seam in `simulation/experiment.py`, with today's
orchestrator as `gen_1`'s implementation. `gen_2`'s implementation comes with card 1. It
depends on nothing else.

## Package layout

This section draws the verdicts together into one layout, decided at review. It is the
starting point for stage 2's sub-issues, not a final design.

### Two generations, one difference

The two simulation paths in card 1, item 6, are called **`gen_1`** (today's) and
**`gen_2`** (the runner agent). They differ in one thing: the interface between the user
agent and the runner.

```
 gen_1:  user agent ──(message, typed actions on offered slots)──▶ runner.send_turn() ──▶ Observation (slots, action_results)
 gen_2:  user agent ──(one plain-language action)─────────────────▶ runner.act()       ──▶ Observation (reply, reading) + end_chat()
```

What depends on that interface is per generation. Everything else is shared:

| Part | Depends on the interface? | Where |
| --- | --- | --- |
| `Runner` ABC, `Observation`, action types | yes, they are the interface | one per generation |
| user agent (prompt and output shape) | yes: typed actions, or one action | one per generation |
| turn loop (orchestrator) | yes: calls `send_turn`, or `act` and `end_chat` | one per generation |
| runners | yes: each implements one interface | under its generation |
| `RunnerFactory`, the seam, the retry loop | no | shared |
| record building, #462's failure cause, the LLM-call log | no | shared |
| artifact write path, file facts, transport log | no | shared, usable by either |

### Files

```
packages/engine/src/metis/engine/simulation/
├── experiment.py      retry loop                    shared
├── trial.py           "run one trial" seam          shared
├── factory.py         RunnerFactory                 shared
├── record.py          building the TrialRecord      shared
├── llm_calls.py       LLM-call log                  shared
├── transport_log.py   transport log (LogEntry)      shared
├── artifacts.py       artifact write path, facts    shared
├── types.py, exceptions.py, _hashing.py, _fixture_artifacts.py
│
├── gen_1/             the interface that exists today
│   ├── runner.py        Runner ABC: send_turn(message, actions) → Observation
│   ├── types.py         typed actions, slots, Observation, ActionResult
│   ├── orchestrator.py, user_agent/, artifact_summarizer.py, _contract.py
│   └── runners/  orca_api/, orca_playwright/, _http.py
│
└── gen_2/             the runner-agent interface
    ├── runner.py        Runner ABC: act(action) → Observation; end_chat()
    ├── types.py         Observation (reply, reading, pending, …)
    ├── orchestrator.py, user_agent/
    └── runners/  http.py, browser.py (+ their shared agent base)
```

Notes on the layout:

- **Retiring `gen_1`** means deleting its folder and its seam implementation. Nothing in
  `gen_2` imports from `gen_1`, and a one-line import check enforces that.
- **The artifact summarizer stays in `gen_1`.** Its LLM descriptions are what `gen_2`
  replaces with code facts, so it belongs to how `gen_1`'s user agent is told about
  files.
- **Old import paths keep working.** Specifications on disk, including the baseline's,
  name `metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory`. Re-exports under
  the old names stay until `gen_1` is retired.

### What goes in `metis-core`

The rule (`packages/core/schemas/README.md`): "New shared file models belong in core …
Private runtime and API models stay in their owning packages." A model goes in core when
a package other than its writer reads it.

| Model | Written by | Read by | Where |
| --- | --- | --- | --- |
| `TargetBinding` | the user, by hand | the engine; perhaps the wizard or web client later | **`metis-core`**, with a published schema, since users edit it |
| `LLMCallRecord` | the engine | only the engine | `metis-engine` (`simulation/llm_calls.py`). Move to core if insights starts reading it |
| `LogEntry` | the engine | only the engine | `metis-engine` (`simulation/transport_log.py`). Private |
| `TrialRecord` | the engine | engine, insights | `metis-core`, as today, plus #462's cause value |

The investigation's specs call the LLM-call log and the transport log "shared". They were
shared between that project's proposal lanes. In METIS, nothing outside the engine reads
them yet, and keeping them private avoids freezing their row shapes while `gen_2` is still
changing.

## Stage 2: proposed sub-issues

Each item is one sub-issue of #460 and one PR into `next`, which stays working after each
merge, because `gen_1`'s behaviour never changes.

| # | Sub-issue | Verdicts it carries | Package | Needs first |
| --- | --- | --- | --- | --- |
| 1 | #462's "simulator" cause value (a comment on #462, not a new issue) | validity checks' reporting; `gen_1` writes it too | core, engine, insights | nothing |
| 2 | Move today's code into `gen_1`, behind the "run one trial" seam | workflow contract | engine | nothing |
| 3 | LLM-call log, wrapping `gen_1`'s user agent and summarizer | LLM-call log | engine | 2 |
| 4 | Transport log | transport log | engine | 2 |
| 5 | Target binding model and schema, and the specification's `target_binding` field | card 8, card 6's submissions field | core | nothing |
| 6 | Artifact write path and file facts | artifact ledger, card 3's byte check, card 13's file facts | engine | 2 |
| 7 | `gen_2` interface, user agent and turn loop | card 13, card 11, card 7's promise list | engine | 2, 3 |
| 8a | `gen_2` generic HTTP runner, with code-owned facts | card 1, cards 2, 4, 5, 6 | engine | 4, 5, 6, 7 |
| 8b | Send only what each round needs | card 9 | engine | 8a |
| 8c | Closing step and the validity checks | card 7, validity checks | engine | 1, 8a |
| 9 | `BrowserRunner` | card 10 | engine | 8a |

```
 1 #462 cause ─────────────────────────────────────────────────────────┐
 5 profile model (core) ─────────────────────────┐                     │
 2 gen_1 behind the seam ─┬─▶ 3 LLM-call log ─┬──┼─▶ 8a generic HTTP ──┼─▶ 8c closing + checks
                          ├─▶ 4 transport log ┼──┤    runner ─┬────────┘
                          ├─▶ 6 write path ───┼──┤            ├─▶ 8b round trimming
                          └───────────────────┴─▶ 7 gen_2 UA + loop    └─▶ 9 BrowserRunner
```

Stage 4 (comparison with `V5` and the baseline, the second target, and `BrowserRunner`'s
live run) is tracked on #460 directly, not as sub-issues.
