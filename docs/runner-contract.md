# The Runner Contract

**Status:** normative. RFC 2119 keywords (MUST, MUST NOT, SHOULD, MAY) carry
their usual force. This document is a peer of [architecture.md](architecture.md).
The how-to for writing a runner is [guide/engine.md](guide/engine.md), which is
explanatory and cites the identifiers below rather than restating the
obligations.

**Applies to:** every implementation of `metis.engine.simulation.runner.Runner`,
in this repository or outside it.

## 1. What a runner is for

A runner is the only component that touches the target system. It receives one
persona turn — prose plus a list of chosen actions — translates it into
whatever transport the target speaks, and returns an `Observation`: a
first-hand, mechanical account of what happened.

Two principles govern every rule below.

**P1 — Decompose only what the persona named.** The `Observation` reports on the
actions the runner was given, one row each. It does not describe the runner's
internal steps. A runner that resolves an element three times, uploads two
files and polls eleven times still reports one row per action it received,
because the persona chose actions, not HTTP requests.

**P2 — Report facts, never interpretations.** A runner says what it observed
mechanically: the click landed, the upload came back 413, no reply arrived
inside the window. It does not judge whether the target's answer is good,
complete, on-topic or safe. That is what metrics are for, and a runner that
editorialises puts its opinion into the evidence the evaluation is built on.

## 2. Definitions and authority

| Term | Meaning | Whose obligation |
| --- | --- | --- |
| **caller** | The `Orchestrator`, which owns the persona, the scenario and the run | validating the scenario; calling `send_turn` at most once per turn |
| **callee** | The `Runner` implementation | the transport; the `Observation` |
| **received actions** | The list the callee was passed, which may be shorter than the persona's because the caller may withhold an action | `action_index` is relative to this list |

A question answerable from the scenario definition alone belongs to the caller.
A question answerable only by touching the target belongs to the callee.
Whether `report.pdf` is a fixture this scenario staged is the caller's business;
whether Orca accepted it is the callee's.

## 3. Invariants

### I1 — Completeness

If `send_turn` returns, `Observation.action_results` MUST contain exactly one
`ActionResult` per action in the list the callee received, ordered by ascending
`action_index`, such that `action_results[i].action_index == i`.

A runner MUST NOT drop an action silently. This is the invariant that makes
issue #320 — a failed DOM click logged at warning level and otherwise
forgotten — impossible to express.

Correlation uses action position. `ChosenAction.slot_id` is advisory: the persona
is an LLM and may emit an ID that was never offered. Every built-in runner routes
uploads by `filename`.

I1 binds the callee. The caller satisfies the same shape voluntarily when it
synthesises an `Observation` of its own, so that every downstream consumer sees
one uniform shape.

### I2 — Minimal verdict

`succeeded` is mandatory on every row and reports **transport-level** delivery
only: the action reached the target and the target accepted it.

When `succeeded` is `False`, `detail` MUST be non-empty. A bare failure with no
evidence is not a report.

`retryable` is an optional hint, valid on failure rows only, and MUST be `None`
when `succeeded` is `True`. `None` means the runner has no opinion. Only the
persona consumes it; the caller MUST NOT act on it, because acting on it would
be the caller reading delivery state off the callee's internals.

### I3 — Session post-condition

After `send_turn` returns, and after it raises any `RunRecoverableError`
subclass that the run layer recovers from, the target session MUST be usable on
the next turn.

A runner that knows its session is dead MUST raise rather than return, even
when it holds a perfectly good account of the turn. The account is lost; that
is the accepted cost of never handing the caller a session it cannot use.

How a runner keeps this promise is its own business. The contract states the
post-condition, not the mechanism.

### I4 — Delivery multiplicity

A `Runner` MUST NOT be required to tolerate a re-sent turn. A second `send_turn`
call carrying the same `message` MUST be assumed to deliver that message to the
target a second time; no runner is obliged to detect the repetition or to
suppress its effect.

Correspondingly, the caller MUST call `send_turn` at most once per persona turn.
When `send_turn` raises, the caller MUST NOT call it again for that turn,
whatever the exception type: a raise carries no information the caller may use
to conclude that the turn was not delivered.

How many transport operations a runner performs inside a single `send_turn`
call — retries, re-resolutions, polls, uploads — is the runner's own business
and is not observable to the caller. This invariant constrains only the number
of `send_turn` calls the caller makes.

### I5 — Delivery disclosure

`Observation.delivered` reports whether this turn was actually submitted to
the target and accepted by it, as opposed to being declined by the runner or
rejected by the target — the same meaning I2 gives `succeeded`, but for the
turn as a whole rather than per action. Like I3, this is a post-condition on
the outcome, not a claim about mechanism: how many transport operations a
runner needs to submit a turn — one request, several, a multi-step handshake
— is the runner's own business (P1), same as the internal calls it makes to
resolve or upload an attachment before `action_results` ever sees them.
`True` says nothing about whether the target liked the reply; `False` says
the runner chose, or was forced by a check it can run without touching the
transport, not to submit anything this turn.

A runner MUST NOT set `delivered=False` merely because part of the turn could
not be honoured, when a different valid request still exists. A malformed
form answer, an attachment that failed to resolve, an invented button — none
of these make every possible request for the turn invalid; they cost only
their own `ActionResult` row (I2), and the runner MUST submit whatever
request is still valid rather than discarding the turn. `delivered=False` is
for the turn that has no valid request left to send at all — an empty
message with no form answer to send in its place, for instance, which Orca's
own schema rejects outright (`## 6`).

`delivered` defaults to `True`, matching the common case where nothing about
the turn is in question. A runner that declines MUST set it to `False`
explicitly at the point of decline; relying on the default there would
silently misreport a turn nothing was ever sent for as delivered.

## 4. Return or raise

Returning an `Observation` asserts two things: *I have a first-hand account of
this turn*, and *the session is usable next turn* (I3). Raising asserts *I
cannot tell you what happened*.

Severity does not define the line. A turn in which every action failed and the
target answered nothing is still a return, because the runner watched it
happen. A turn that went perfectly but left the browser page crashed is still a
raise, because I3 cannot be met.

A return in which every row failed MUST NOT increment the caller's
consecutive-failure counter. Only a raise counts towards escalation, because
the counter exists to detect a runner that has stopped being able to report,
not a target that keeps saying no. A severity-based line — escalate once the
failures look bad enough — was considered and rejected: "how bad is it" is not
observable across transports, whereas "do I still have a usable session" is.

## 5. The channels

One `Observation` carries four kinds of report, each with exactly one owner.
Mixing them is what a single free-text `errors` list got wrong: the persona
could not tell its own rejected upload from the target's outage.

| Channel | Reports on | Granularity owner |
| --- | --- | --- |
| `action_results` | each action the callee received | the persona, which chose the actions |
| `text`, `artifacts` | what the target said and produced | the target |
| `response_notices` | problems with this turn's reply that no submitted action accounts for | the turn |
| `available_actions` | what the target offers next | the target |
| `delivered` | whether this turn was actually submitted to the target and accepted (I5) | the turn |
| raise-or-return | whether a first-hand account exists at all | the runner |

An `ActionResult` row is five fields:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `action_index` | `int` | required | position in the list the callee received (I1) |
| `succeeded` | `bool` | required | transport-level delivery, not the target's approval |
| `detail` | `str` | `""` | evidence; MUST be non-empty when `succeeded` is `False` (I2) |
| `retryable` | `bool \| None` | `None` | optional hint on failure rows only; `None` means no opinion |
| `withheld` | `bool` | `False` | the caller rejected this action before dispatch |

There is deliberately no `action_type` and no `slot_id` on a row. Correlation is
positional, for the reason given under I1, and a copy of `slot_id` here would
invite readers to treat an advisory label as an identity.

`response_notices` covers target-reported problems, the absence of a reply, and
failures in METIS's own handling of a reply that did arrive. Anything
attributable to a submitted action MUST go in `action_results` instead.

`available_actions` is three-state, and the distinction is load-bearing:

- a list of slots — the runner looked, and the target offers these;
- `[]` — the runner looked, and the target offers nothing;
- `None` — nobody looked.

Reporting `[]` when nobody looked tells the persona its controls were
withdrawn, which is a claim about the target that the runner never observed.

`withheld=True` on an `ActionResult` marks an action the **caller** rejected
before dispatch, which the callee therefore never saw. A callee MUST NOT set
`withheld`; it can have no opinion about an action it was never given, and a
runner that sets it is claiming the caller's authority. A withheld row is always
a failure row — `succeeded` is `False` and `detail` carries the caller's reason —
but it is not a product failure and MUST NOT be attributed to the target. The
consumers that count product evidence, the persona prompt and the HTML report,
both exclude withheld rows.

## 6. Edge cases

**The reply that is itself an error message.** A target answering "I cannot
process that file" has replied. `text` carries the reply and `succeeded` stays
`True` on the upload row, because the file arrived. The target's unhappiness is
content, and a runner that demoted it to a failure would be interpreting (P2).

**`text` contradicting `action_results`.** A reply that ignores an action the
runner delivered successfully is not a contradiction and MUST NOT be reconciled.
The two channels describe different things: one what the transport did, the
other what the target said. Reconciling them is a metric's job.

**A shape mismatch.** A runner that cannot produce one row per received action
MUST raise rather than return a best-effort `Observation`. The caller enforces
I1 on every return and raises `RunnerContractError` on a mismatch, so a
best-effort return is not quietly accepted — it is an engine error either way,
and raising from the runner puts the failure where the defect is.

**Every action failed but the target replied.** A return. See `## 4`.

**A good account of a dead session.** A raise, and the account is lost. I3 is a
post-condition on the session, not on the quality of the report, and a runner
holding both MUST prefer the post-condition.

**A message is always valid while a form is pending.** Orca's schema accepts
`message` alone or `formAnswers` alone, never both and never neither — a form
left pending does not narrow that requirement, and Orca leaves the question
open and may ask it again rather than rejecting a plain message in its place
*(Orca API v1 spec, `POST /api/v1/chat`)*. A runner whose typed form answer
fails validation locally therefore has one lawful move: discard the answer
and fall through to the message, never abandon the turn — the same request
Orca would have accepted had the persona sent prose to begin with.

**Nobody looked at what is on offer.** `available_actions` is `None`, never `[]`.
A runner whose transport exposes no notion of offered actions reports `None`
every turn; that is accurate, not a deficiency.

**A persona's repeated message is not a caller-directed retry.** I4 forbids the
*caller* from re-sending a turn, but nothing stops the *persona* from choosing,
as an ordinary next turn, a message that repeats or resembles the one that just
failed — that arrives at the callee as a plain `send_turn` call, indistinguishable
from any other. A runner's I3 recovery MUST NOT be conditioned on recognising
such a repeat: the contract gives a runner no standing to infer persona intent
from `message`, so a runner's own housekeeping between turns MUST trigger on the
fact that a next `send_turn` call arrived, not on what it contains. A runner
that defers a fix from a failing `send_turn` call to the start of the next one
— reloading a page lazily, say — MUST apply that fix on every next call
unconditionally, whether or not that call happens to look like a retry.

## 7. Conformance

I1 is machine-checked at run time: the orchestrator validates every returned
`Observation` against the list it passed, and a violation raises
`RunnerContractError`. That exception sits deliberately outside both the
`TurnRecoverableError` and `RunRecoverableError` families, so no recovery
ladder can catch a runner bug and retry it into the record; it surfaces as a
`system_error` outcome.

I2 is partly machine-checked: the `ActionResult` model validators enforce
"failure implies detail" and "`retryable` is `None` on success" at
construction time.

I3, I4 and I5 are reviewer-enforced. An executable conformance suite a
third-party runner can run against itself is issue #358. The precedents are
PEP 3333 with `wsgiref.validate`, SQLAlchemy's dialect contract with
`sqlalchemy.testing.suite`, and the Container Storage Interface with
`csi-sanity`. Until that suite exists, a new runner is reviewed against this
document by hand.

## 8. References

- Issue #329 — this contract
- Issue #320 — the silently dropped DOM action, subsumed by I1
- Issue #315 — wired turn errors into the persona prompt
- Issue #358 — the executable conformance suite
- Issue #361 — removes `Runner.recover()`, which I4 orphans
- Issue #365 — I5, delivery disclosure
