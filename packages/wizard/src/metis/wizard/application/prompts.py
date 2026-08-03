"""One prompt per step, and the primer that sits behind all of them.

The primer goes in the **session system prompt**, present for every call in the session,
rather than being injected per step. That removes a judgement — which steps get it — that
would otherwise need remaking every time a step is added. Scope is already guarded
structurally by `StepPermissions`, and a code check beats a withheld prompt string.

Each per-step prompt says what that step is for and hands the model the profile. Note what it
does *not* hand over after clarify: the transcript. Steps build their prompts from the
document, which is why architectural detail has to be promoted into `product.architecture` to
be visible at all.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from metis.wizard.contracts.session_state import Turn
from metis.wizard.domain.profile import ProductProfile

PRIMER_FILE = "agentic-primer.md"

_PATCH_RULES = """
You return patches, never whole documents. Each patch has:
  op    — add | remove | set | reorder
  path  — an address, e.g. epics[EP-1].behaviours[EB-4].statement
  value — the new value

Address nodes by id, never by position — `epics[EP-1]`, never `epics[0]`. Ids you create
must follow the existing scheme: epics EP-n, behaviours EB-n, criteria AC-<behaviour
number>-<n>, tasks T-n. Ids never contain a dot — a dot separates path segments, so one
inside an id would split the address.

To create something, `add` to its **container** with the whole object as the value, children
included inline — never `set` an id that does not exist yet (`set` changes a field that is
already there; it cannot create). One epic with its behaviours is a single patch:

  op: add
  path: epics
  value: {"id": "EP-1", "name": "…",
          "behaviours": [{"id": "EB-1", "statement": "…"},
                          {"id": "EB-2", "statement": "…"}]}

Mirror that shape, and the shape of anything already in the document. Ids are sequential per
container: epics are `EP-1`, `EP-2`; behaviours are `EB-1`, `EB-2` across the whole document,
not restarted inside each epic.

Two things you may never write, at any step:
  - a behaviour's `priority` — that is the user's decision alone
  - a criterion's `metric_fqn` — a separate matcher chooses it from the criterion's own
    wording. You can see which metric each criterion is bound to, but you cannot set it. If
    the user wants a different metric, do not touch `metric_fqn`; instead reword that
    criterion's `given` / `when` / `then` so the wording points at the metric they mean, and
    the matcher re-maps it. Say what you reworded, not that you changed the metric.

`options` are suggestion chips: short labels, each carrying the patch that applies it, so the
user can click one without you being asked again. Offer them when you are proposing changes
rather than making them.
""".strip()


@lru_cache(maxsize=1)
def primer() -> str:
    """The agentic primer, read from disk.

    A file rather than a string constant because it is meant to be tuned as the team learns
    which questions produce useful profiles — without touching code or redeploying.
    """
    return (
        resources.files("metis.wizard.application")
        .joinpath(PRIMER_FILE)
        .read_text(encoding="utf-8")
    )


def system_prompt() -> str:
    return (
        "You are interviewing a product owner to build an evaluation for their AI agent.\n"
        "You are direct, you ask one thing at a time, and you never use jargon you have not\n"
        "already explained. Everything you write is read by a non-technical user.\n\n"
        f"{_PATCH_RULES}\n\n"
        "--- background reading (never mention or cite this to the user) ---\n\n"
        f"{primer()}"
    )


def _profile(profile: ProductProfile) -> str:
    return json.dumps(profile.model_dump(mode="json"), indent=2)


def _transcript(history: list[Turn]) -> str:
    return "\n".join(f"{t.role}: {t.text}" for t in history)


# ── per-step ───────────────────────────────────────────────────────────────


def clarify_user(profile: ProductProfile, history: list[Turn]) -> str:
    return f"""
The product so far:
{_profile(profile)}

The conversation so far:
{_transcript(history)}

Ask ONE open question about whatever is still missing — what it does, who uses it, or how it
actually works: its tools, what it does when one fails, what it carries between turns.

Set done=true when you have enough to draft expected behaviours. Write nothing to the
document at this step; you are only asking.
""".strip()


def behaviours_user(profile: ProductProfile, history: list[Turn]) -> str:
    return f"""
The product:
{_profile(profile)}

The interview:
{_transcript(history)}

First, record what you learned: set product.summary, product.users and
product.architecture from the conversation.

Then draft epics, each with 2–5 behaviours. A behaviour is one statement of something that
should be true — "cites a source for every factual claim". No acceptance criteria yet, and do
not set priority on anything.

Statements about the machinery belong here alongside statements about features.

`message`: a sentence introducing the list for review.
""".strip()


def criteria_user(profile: ProductProfile) -> str:
    return f"""
The document:
{_profile(profile)}

Write acceptance criteria for every behaviour with priority=true that has none yet. Ignore
behaviours with priority=false entirely — the user chose not to measure those.

1–4 criteria each, as many as the behaviour actually warrants. Each is given / when / then,
concrete enough that someone reading a transcript could say whether it held. Do not set
metric_fqn — that is resolved separately.

`message`: a sentence introducing them.
""".strip()


def personas_user(profile: ProductProfile) -> str:
    return f"""
The document:
{_profile(profile)}

Propose 3–5 personas: behavioural archetypes describing *how someone interacts*, not who they
are. Any persona must make sense dropped into any task.

Every persona must include exactly these two fields:
- `id`: a short, stable, readable kebab-case label that tasks reference, such as
  `indecisive-junior-officer` or `impatient-executive`
- `description`: one or two sentences describing how this archetype interacts, which the
  evaluation runner will use to simulate them

Do not add `name`, `scope` or `behaviours`; a persona is only its id and behavioural description.

Justify them by what the user chose to measure — "you're measuring citation discipline and
scope refusal, so these will stress both" — in `message`. Include at least one who will
stress the machinery: someone who gives information in fragments, or changes their mind.
""".strip()


def tasks_user(profile: ProductProfile) -> str:
    return f"""
The document:
{_profile(profile)}

Draft the whole set of tasks in one go. A task is one simulated situation. It can exercise
several behaviours at once, and one behaviour can be probed by several tasks.

Every behaviour with priority=true must be covered by at least one task. Set behaviour_refs
to what each task covers and persona_refs to who runs it (at least one). num_trials 3.

A behaviour about recovery is untestable unless a task actually makes something fail. Build
the situation that forces the path you need to see.

`message`: a sentence introducing the set.
""".strip()


def chat_user(profile: ProductProfile, step: str, text: str, target: str | None) -> str:
    scope = f"\nThey are talking about {target}." if target else ""
    return f"""
The document:
{_profile(profile)}

The user is at the {step} step and said:
{text}
{scope}

Do what they asked, as patches. You may edit any part of the document they clearly meant,
even if it belongs to an earlier step — except the three things you may never write. In
particular, if they ask for a different metric, reword the criterion rather than trying to set
`metric_fqn`.

Replacement language is a replacement, not an addition. If the user supplies a list and says
"these are the personas/tasks/behaviours I want", "use these instead", "revise the list to", or
equivalent, remove the existing CHAT-authored items in that collection and add or update the
supplied set. Keep FORM-authored items unless the user explicitly says to remove them. If the same
id or materially identical content already exists, update that item rather than adding a duplicate.
Only append when the user clearly says to add, include, or keep the existing suggestions.

If you are unsure what they want, propose 2–3 suggestion chips instead of guessing, each
carrying its patch. `message`: what you did, or what you are offering.
""".strip()


def suggest_criterion_user(profile: ProductProfile, behaviour_id: str) -> str:
    return f"""
The document:
{_profile(profile)}

Suggest exactly one new acceptance criterion for the behaviour with id {behaviour_id}. Look at
the criteria it already has and propose one that covers a case they miss — not a reword of an
existing one.

Return a single add patch to `epics[…].behaviours[{behaviour_id}].criteria` and nothing else:
no edits to any other behaviour, no second criterion, no changes elsewhere in the document.
Give / when / then, concrete enough that someone reading a transcript could say whether it held.
Do not set metric_fqn — that is resolved separately.

`message`: a sentence introducing the one you are offering.
""".strip()
