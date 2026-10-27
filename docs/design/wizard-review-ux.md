# Wizard review UX proposal

Status: local prototype for issues [353](https://github.com/govtech-responsibleai/metis/issues/353)
and [489](https://github.com/govtech-responsibleai/metis/issues/489). It is built on the opening,
Back, document, model-role, and target-connection work from issue
[547](https://github.com/govtech-responsibleai/metis/issues/547) and the branches below it.
The design is not final.

## Current scope

Keep the implemented Interview stages. Use two work areas. The chat provides short instructions
and always shows the feedback field. The Profile is the main reading and editing area.
It shows the current Specification and places the active review inside its matching section.
Previous sections stay available with their current content.

### Behaviour review

- Title the step and its Profile section "Features / Expected Behaviours".
- Group Behaviours under their Feature. The group header shows the Feature name only. Section
  and group headings show no item counts.
- The instruction is "Select max 5 key behaviours only." More than five is allowed and shows a
  warning that does not block Continue.
- Keep each review instruction to one short sentence. Do not use " · " in any text.
- Show a labelled checkbox, the Behaviour name, and a short description for each Behaviour.
- Keep Behaviour names and descriptions concise. Show their complete current wording in the review.
- Keep Feature groups open initially. Users can collapse them without losing their selections.
- Show the total selected count beside Continue. Selection does not advance the Interview.
- Do not add recommendation explanations under each Behaviour.
- Keep the full Profile visible beside chat. Avoid repeating the full review in chat.
- Keep the user's position and open groups after a correction.

### Corrections

Apply a submitted correction immediately. Update the affected content in place.
Return a short result message. Do not ask keep-or-regenerate questions. Preserve unrelated content
and selections. A Target edit after Back follows the same rule: a changed description or detail
updates the derived content, and a form with no change drafts nothing again.

The feedback field shows a placeholder for each step. The placeholder is an example of what the
user can type, with a real item name when one exists: "Add a new feature that describes…",
"Add a new criterion to <Behaviour>…", "Make <Persona> more…", "Add a scenario where the user…". Sending feedback applies one correction in one turn. A correction
from the user's own message can also select Behaviours and set Trials. A drafting call cannot.

Every item has Create, Edit, and Delete. A "+" on a heading opens a typed form for a new item: on
the Behaviours heading it adds a Feature, on a Feature heading a Behaviour, on a Behaviour a
Criterion, and on the Personas, Scenarios, and Test Cases headings an item of that kind. A pen
opens a typed form with the current values, in place: a Criterion edits in its own row and a
Test Case in its table cells. There is no modal. Save uses the exact text. Cancel returns to review.
Model suggestions come from the chat, not from a form. A typed Criterion gets a Grader from the
matcher. Keep item IDs, Behaviour selections, and Test Case references through edits.

Delete removes the item and its dependants together. The door asks first and names them:

- A Feature takes its Behaviours, their Criteria, and their references in Test Cases.
- A Behaviour takes its Criteria and its references in Test Cases.
- A Persona or Scenario takes the Test Cases that use it.

The last Feature, Persona, or Scenario cannot be deleted, because that step drafts a new set when
it is empty. The last Criterion of a selected Behaviour cannot be deleted.

The primary button to go to the next step says "Continue" on every step. Forms say "Save" and
"Cancel". The Target form after Back says "Continue".

Criterion review keeps the same Feature groups and Behaviour names, with no checkboxes. A
selected Behaviour supplies all its Criteria. Show each Criterion name and its assessment. Show
a concise Grader summary in quiet text. Expand that summary to inspect the Grader identifier.
The Criterion pen edits the assessment and the Grader parameters. Personas have no checkboxes.
The Test Case table chooses which Personas run. A card shows a checkbox only when one of its
options changes it. A card shows its ID only when the ID carries meaning (`show_id`): Behaviours,
Criteria and Test Cases show it, and Personas and Scenarios, whose IDs repeat their names, do not.

Scenarios and Test Cases are two steps, so the user approves the situations before the model
matches them with Personas. The Scenarios step is a card list. The model drafts Scenarios only.
Continue on Scenarios starts a separate model call for each Scenario that has no Test Case yet.
That call picks the existing Personas that the Scenario runs with, usually one or two, and the
measured Behaviours that each pair really tests. It returns one Task draft for each pick. Each
new Test Case is selected and uses the default Trials. Code drops a second Test Case for a pair
and a Test Case for a Scenario that already has one. It leaves out an unmeasured Behaviour with
a warning, and a Test Case left with none covers all measured Behaviours. A measured Behaviour
that no selected Test Case covers is not added anywhere by itself: the Test Case review shows the
coverage gap, and the user fixes it with a chip or the chat. Behaviours Continue after Back
follows the same rule. It removes unmeasured references, and a Test Case left with none covers
the measured set. A Scenario that already has a Test Case is not matched again, so a Test Case
that the user deleted does not come back. A Scenario that the user adds later, by form or chat,
is matched when the user selects Continue on Scenarios again, or the user adds its Test Cases
with "+".

The Test Cases step is a table with Persona, Scenario, Behaviours, Trials, and Files columns. Behaviours
show as ID chips, with the description as hover text. The row checkbox means "include in the
evaluation". The selection is Interview state, so the shared Specification schema does not
change. Only selected Test Cases count in the footer total, take part in readiness, and go into
the export. A Scenario that no selected Test Case uses is left out of the export. Continue with
none selected shows "Select at least one Test Case." There is no bulk removal.

The Test Case edit form fills the row cells: Persona and Scenario dropdowns, Behaviour ID chips,
Trials, and Files. Each field names its column. A Test Case is unique by its Persona and
Scenario pair. Readiness, the form, and model patch validation each refuse a pair that is in
use. Persona and Scenario forms have Name, Description, and More information, written as
`key: value` lines.
Persistent change tracking and repeated acceptance of affected items are deferred.

### Back

Back works from every step after Clarify, and also while a form is open: one turn closes the form
with no change, then goes back. Back on Run settings and on a completed Interview reopens the
Test Case review. An earlier screen shows its drafting message again after Back. When the user
changes the selected Behaviours after Back, Behaviours Continue updates the Test Cases: a Test
Case drops an unselected Behaviour, and a newly selected Behaviour gets Criteria. The Test Case
review names it until the user covers it with a chip or the chat. Then the review can continue.

### Generation limits

Limit the number of generated Behaviours and Criteria. Keep names and descriptions concise as
a separate writing rule. Preserve complete Given, When, and Then clauses.

Default generation budgets are five Behaviours across the full Specification and three Criteria
per selected Behaviour. These values are defaults for testbed review. They are ceilings, not
minimums. Do not pad the result to reach them. If a budget would leave a stated requirement or
an important safety concern uncovered, identify the gap and allow deliberate expansion.

Generate new Criteria only for selected Behaviours. Preserve existing Criteria when a user
clears a Behaviour selection.

### Perspective and capability context

Use the selected Perspective consistently in questions, generated content, and explanations.
Use plain language for End user. Use technical terms where useful for Engineer.

Carry supplied capability evidence through the relevant Interview stages. Capability evidence
describes known abilities. It does not establish new product requirements or prove that other
abilities are absent. Do not repeat capability identifiers throughout the review.

The API must allow callers to omit capability selection and capability confidence together.
Omitted evidence means unspecified. Do not invent a confidence value or infer that the product
has no capabilities. Validate capability IDs and confidence when callers supply them.
In the web opening, Capabilities is an optional control. If the user selects no capability and
no confidence, the browser sends no evidence. A selection with no confidence is sent as low
confidence, because the selection may be incomplete. In the CLI, `skip` omits the evidence.

## CLI opening

`metis wizard init` asks for the description when the argument is not given:

```console
$ metis wizard init

Tell me about your product. What does it do, and who uses it?
> A billing assistant that answers account questions and handles billing changes.

Which Perspective should guide this evaluation?
  1. End user
  2. Engineer
  3. Compliance
  4. Security
```

The description argument stays as a shortcut. With it, the CLI does not ask the description
question:

```bash
metis wizard init "A billing assistant that answers account questions."
```

The opening order is description, Perspective, mode and target connection, then optional
capability evidence. Ask for confidence only when the user supplies capability evidence.
Treat skipped evidence as unspecified. Use the shared opening question and Perspective
explanations in CLI and web.

Without a terminal and with no description argument, `init` stops before any model call and
tells the user to pass the description as an argument.

## Deferred work

- Persistent affected-content review tracking and change history.
- Broader changes to the Interview stage sequence.

The browser tab, draft, reply, and retry behaviour delivered in PR 393 remains part of the
existing contract. Shared flow rules and copy belong in the wizard package. The clients own
presentation and input handling.
