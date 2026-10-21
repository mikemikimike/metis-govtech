| Term | Definition |
|------|------------|
| Target | The agentic system under evaluation, considered at a specific version or configuration. |
| Profile | The context and requirements for a **target**: its **features**, **expected behaviours**, and **criteria**, including the selected **graders** and their settings. |
| Specification | The evaluation document containing a **profile** and the configuration needed to conduct an **experiment**. |
| Interview | The wizard's guided process that builds a **specification** by asking the user a sequence of questions. |
| Document | A user-supplied file that can inform **evaluation planning** and may be sent to the **target** as a **fixture** for a **task**. |
| Perspective | The point of view the user answers the **Interview** from (who the evaluation is for), distinct from a **Persona**. |
| Capability | An ability a **target** can have, drawn from the ARC framework and distinct from an **Expected Behaviour** or **Feature**. |
| Feature | A function or user workflow that the **target** is expected to perform, such as creating slide decks. |
| Baseline | A scope qualifier for an **expected behaviour**, **criterion**, or **grader** that can be applied to every **target**. Baseline graders are provided by the library. |
| Feature-specific | A scope qualifier for an **expected behaviour**, **criterion**, or **grader** arising from the requirements, constraints, or operating context of a particular **feature**. A feature-specific grader is provided by the library where one exists, or otherwise authored directly from its **criterion** as a *custom* grader. |
| Expected Behaviour | An expected behaviour describing how the agent should act while performing a **feature**. |
| Criterion | A specific, assessable property used to determine whether an **expected behaviour** was exhibited in an individual **trial**. |
| Scenario | A concrete instantiation of a **feature**, specifying the particular situation and conditions in which the agent is evaluated. |
| Persona | A concrete simulated user whose characteristics and behaviour are relevant to an evaluation interaction. |
| Fixture | An artefact or piece of environment state selected by a **task** to execute its **scenario**. It may be supplied by the user or generated dynamically. A fixture is an input, not an expected answer or scoring rule. |
| Test Case / Task | A complete specification of a particular evaluation problem, combining a **scenario**, a **persona**, **fixtures**, a Trial count, and references to **expected behaviours**. Each selected Behaviour supplies all its Criteria. Each Task has an ID. **Test case** and **task** are interchangeable terms. |
| Trial | One execution of a **test case** against a **target**, producing a **trace** and evaluation outputs. |
| Run | A grouping of repeated **trials** of the same **test case**. |
| Experiment | A collection of **runs** used to evaluate one or more **targets** across a set of **test cases**. |
| Grader | A procedure that evaluates a **trial** against one or more **criteria** and produces a **trial score**. |
| Scope | The evidence unit that a **grader** assesses, such as tool arguments, an artefact, a turn, or a complete trajectory. A grader declares its supported scopes. One judgment selects one attribute within one Scope subdimension. See [Scope](#scope). The **baseline** and **feature-specific** qualifiers describe which **targets** a grader applies to. |
| Trial Score | The value produced by applying a **grader** to a **trial** for a particular **criterion**. |
| Grader Passing Threshold | A configurable rule applied to the **trial score** from the **grader** to mark it as pass or fail. |
| Result | The pass rate of a set of **trial scores**. |
| Test-Time Evals | Evaluations that measure a target model or **target** against curated datasets before release. |
| Run-Time Evals | Evaluations that continuously measure live traffic and real user interaction as a target model or **target** runs. |

Note: **Expected Behaviour** corresponds to the `Behaviour` data models.

## Scope

Scope is one of the three top-level taxonomy groups, with Measure and Mechanism.
It describes the evidence unit to assess. Choose one subdimension, then one
attribute within it.

| Subdimension | Attributes |
|--------------|------------|
| Atomic | Model decision generation, model reasoning, artefact, tool selection, tool arguments, tool execution, environment action. |
| Interaction | Turn, sub-trajectory, complete trajectory episode. |

The `Scope` enum defines these attributes. `GraderTaxonomy.scopes` lists the values
that a grader supports. The grader's configuration selects a supported value when
several values are available. See the [grader taxonomy guide](docs/guide/library/graders.md).

Graders assess recorded evidence. The current result model has no structured field
that identifies a scope item.

### Evidence records

The following terms describe the records that supply evidence for a scope.
They are listed from largest to smallest.

| Term | Definition |
|------|------------|
| Session | A collection of **traces** corresponding to exactly one **trial**, including references to where artefacts can be retrieved. METIS assumes a one-to-one correspondence between a session and a trial: the **target**'s conversation for a trial produces the traces that make up its session. |
| Subsession | A group of **traces** that is a subset of one **session** and covers part of one **trial**. A subsession is a subset of steps from the full **session** of the **target**, evaluated as a local segment. |
| Trace | The observable record of what occurred during a **trial**: a group of **observations** that contain the interactions, actions, tool calls, relevant state changes, and references to where artefacts can be retrieved. |
| Observation | One recorded step of the **target**, such as a model call or a tool call, with its input, output, and timing. Each observation belongs to exactly one **trace** and can be nested under another observation in the same trace. |

Note: Artefact references in **traces** and **sessions** identify where the artefacts can be retrieved. They do not contain the artefacts themselves.

## Baseline and Feature-specific

**Baseline** — applies to any **target**, whatever the feature. Baseline expected behaviour should include baseline criteria and graders. Baseline graders should come from the library.

- fluency — is the response grammatically correct and natural?
- instruction following — did the agent do what the user asked?

**Feature-specific** — exists only because of the feature. Feature-specific expected behaviour should include feature-specific criteria and graders. These may or may not come from the library.

Example: a slide-making agent.

- from the library (a grader with a parameter): minimum font size, colour contrast, number of slides
- *custom* (no library grader, written from the **criterion**): concise slide language, specific to the user's use case

## Grader Types

A **grader** is one of two kinds:

- **Code-based grader** — a program checks the **trace** against the **criterion**. Best when the criterion is exact and measurable.
  - slide count equals the requested number
  - font size at least the minimum
  - response is valid JSON
- **Model-based grader** — a language model judges the **trace** against the **criterion**. Best when the criterion needs judgement.
  - output tone
  - instruction following
  - summary faithful to the source
