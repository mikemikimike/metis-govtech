# What a simulator must record

This applies to every target; Orca is used as the example. METIS evaluation scores the
target's own Langfuse traces, not the simulator's copy of the conversation. So a simulator's output is small: enough to find the traces, attribute
them, and supply the few facts that only the simulator knows. Everything beyond that is
for humans reading the results, and its format is up to you.

## Required, one per trial

| Field | Why it is needed |
| --- | --- |
| **Target session ID** (for Orca, its `sessionId`) | Evaluation fetches the trial's traces from Langfuse with it. Without it, the trial cannot be evaluated at all. |
| **Task ID** (for example `TC-005`) | Ties the trial to its scenario and persona, and tells evaluation what to score. |
| **Trial number** | Tells apart the repeated runs of one task. |
| **Persona ID** | The persona is never recorded in the target's traces, so it must come from the simulator. |
| **Scenario ID** | Used for labelling. |
| **Stop reason** | Why the conversation ended. At least one metric (abandonment) scores on this directly. Today's values: `goal_achieved`, `user_abandoned`, `max_turns`, `timeout`, `target_exhausted`, `system_error`, `interrupted`. |
| **Files**, each with: name, whether it was uploaded by the user or delivered by the target, whether it was actually received, the local path to a saved copy, and the turn it appeared on | Metrics that judge the target's outputs (for Orca: reports, charts, slides) read these files. |

## The turn number on files has to line up with the target's traces

Evaluation matches a file to a moment in the conversation by comparing the file's turn
number with the position of each trace in the target's session (traces sorted by time). A
file is visible to the trace at position *i* if its turn number is *i* or less. A file
with no turn number is visible to every trace. This relies on one user turn producing
exactly one trace on the target. That holds for Orca; check it for any new target.

Today the two counts are off by one. Turn numbers start at 1, but trace positions start
at 0, so a file the target delivers on turn 1 becomes visible only from the second trace. A
new simulator should pick a numbering deliberately and state it, rather than copy this.

If your simulator counts turns differently, for example by splitting one user intent
into several API calls, make sure the turn number you record on each file still matches
the target trace it belongs to. Similarly, the turn-budget metric counts the target's traces, not
your turns.

## Strongly recommended

These are not needed for scoring, but every past investigation needed them:

- the full conversation: each user message and the target's reply, in order;
- for each turn, anything that did not happen as intended (an upload that failed, a form
  that was rejected, a reply that never arrived), and whether the simulator itself or
  the target was responsible;
- timings per turn and per trial;
- the exception or error, with a traceback, for any trial that crashed;
- the models used, both for the simulated user and for any other LLM in the loop.

The single most useful addition over today's simulator would be a clear flag for a trial
that stopped being a valid test, such as a file that never arrived or a target that ran
out of allowance, so that it is not mistaken for a real result.
