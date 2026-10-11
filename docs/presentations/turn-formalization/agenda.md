# The Simulation "Turn" — Presentation Agenda

Diagrams referenced below are the four interactive HTML files in this
directory: `turn-roles.html`, `turn-workflow.html`, `turn-example.html`,
`turn-outcomes.html`.

1. **The three roles.** User Agent decides what to do; Orchestrator manages
   the run and enforces the rules; Runner is the only one that touches the
   real target system. A "turn" is what happens between the User Agent
   deciding and the Runner reporting back. *(Diagram: `turn-roles.html`)*

2. **What a turn is.** One round of observe → decide → act. The User
   Agent's decision isn't limited to one thing — it can be several actions
   at once (e.g., filling in a form field and sending a message), which is
   exactly the part that needs a rule. *(Diagram: `turn-workflow.html`)*

3. **The invariants.** The rules that never bend, no matter which target
   system is involved:
   - Actions in a turn execute in the order the User Agent chose — never
     reordered, never run in parallel.
   - At most one action in a turn is terminal ("final"); if one is
     present, it must come last.
   - A turn can end with no terminal action at all — e.g. a turn that only
     attaches files.
   - Once one action stops the chain — it fails, is withheld, or comes
     back unknown — every action still queued after it is skipped, never
     attempted.
   - Every action gets exactly one outcome, from a fixed set: went
     through, failed, skipped, withheld, or unknown. There is no single
     pass/fail flag for the whole turn.

   Everything from here on is these five rules, one at a time, with a
   worked example. *(Diagrams: `turn-workflow.html`, `turn-outcomes.html`)*

4. **Why order matters.** Concrete, code-free examples: a five-field form
   should cost one turn, not five; "attach a file, then ask about it" only
   makes sense if the attach happens first. Without an explicit order,
   different target systems have ended up guessing differently about how a
   message and a batch of actions relate, and disagreeing with each other.

5. **Who decides what actions are possible.** Different target systems
   support different things — a plain chat box only lets you type, a web
   form lets you click and fill fields, an API might accept structured
   answers. Each system defines its own menu of actions. The framework
   itself only needs to recognize two kinds across every system — "send a
   message" and "attach a file" — because those are the only two that
   matter for reading the conversation back afterward; everything else is
   specific to how that one system works.

6. **Ending a turn, in practice.** The terminal-action rule from the
   invariants, shown on the diagram: hitting send or submit ends the turn,
   and it must come last when it's present. *(Diagram: `turn-workflow.html`)*

7. **What can happen to an action, in practice.** The outcome rule from the
   invariants, shown on the diagram: went through, failed, skipped,
   withheld, or unknown — and once one action fails, everything after it
   in that turn is skipped. *(Diagram: `turn-outcomes.html`)*

8. **Worked example.** The five-field form, narrated in plain terms: fill
   field 1, fill field 2, ..., submit — one round-trip to the target system
   for the whole turn, with one outcome recorded per field, so it's clear
   afterward exactly which field (if any) the target rejected.
   *(Diagram: `turn-example.html`)*

9. **Why this matters for evaluation.** Data scientists reading a report
   get a clean, per-action account of what happened instead of one
   ambiguous "did the turn succeed" flag; project managers get a design
   that scales predictably as new target systems are added, instead of
   every new integration inventing its own rules.

10. **Worth flagging.** Whether the User Agent (an LLM) reliably produces
    well-ordered, dependent action sequences in practice is untested — an
    empirical question for early runs, not a settled one. A couple of
    related loose ends are already tracked separately and don't need
    solving today. One added risk worth naming: a cost-control instruction
    that currently lives inside the framework needs to move into each
    experiment's own configuration — if a future experiment forgets to
    carry it over, it could silently run on a more expensive model.

11. **The ask.** Sign off on this direction before the team scopes the
    implementation work.
