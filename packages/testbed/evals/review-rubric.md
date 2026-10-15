# Review a Wizard specification

Record the case ID, candidate path, source revision, Wizard revision, model,
Interview transcript path, reviewer, and date. Review the input coverage limits
before assigning results.

For each row below, record `pass`, `fail`, or `unresolved`, with source and candidate
locations. Use `unresolved` when the input or human decision is missing. Keep that
status separate from a failure. Do not compute an overall pass rate until humans
agree on the required checks and acceptable alternatives.

| Check | Pass condition |
| --- | --- |
| Product context | The product, users, available tools, and limits agree with the input. |
| Features | Features describe user functions. Their combined scope covers the selected input requirements. |
| Expected behaviours | Behaviours state distinct expected actions or outcomes within each feature. |
| Criteria | Each criterion is assessable from a trial and preserves the requirement's conditions and exceptions. |
| Coverage | Required source statements have a candidate location; omissions have an explicit scope decision. |
| Unsupported requirements | Added requirements have a source or a recorded user decision. |
| Grader fit | A human confirms that each selected grader measures its criterion with the available evidence. |
| Experiment links | Task, scenario, persona, and behaviour references resolve. Fixture and runner gaps are recorded. |

## Product grader review

Record criterion review decisions in the use case README. Existing Orca
assignments are imported choices. They have no new human approval in this suite.
All other grader assignments are pending.

For each criterion, a human must select or define a grader and record:

- The grader class and parameters, or a precise rule for a custom grader.
- Required evidence, such as tool arguments, retrieved content, or file contents.
- The score direction and passing threshold.
- A passing trial and a failing trial that the grader distinguishes correctly.
- Exceptions, including permitted refusals and permitted actions.
- Reviewer, review date, decision, and evidence for that decision.

Record the decision as `approved`, `revise`, or `pending`. For an approved choice,
update the reference criterion's `grader_fqn` and `grader_args` as well. Keep a
missing implementation pending. Do not insert a class name that cannot be loaded.

## Compare systems

Use the same case version, input files, Interview answer policy, and review checks
for every system. Record human assistance and missing information. Evaluate the
meaning of the output even if another system uses a different file format.
Keep repeated trials separate so variation remains visible.
