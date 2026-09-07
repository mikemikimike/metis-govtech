| Term | Definition |
|------|------------|
| Target Agentic System | The agentic system under evaluation, considered at a specific version or configuration. |
| Profile | The complete evaluation specification for a **target agentic system**, comprising its **tasks** and their **behaviours**, **personas**, and **scenarios**. |
| Task | A general description of what the **target agentic system** is expected to accomplish. |
| Baseline | A scope qualifier for a **behaviour**, **criterion**, or **scorer** that can be applied to every **target agentic system**. Baseline scorers are provided by the library. |
| Task-specific | A scope qualifier for a **behaviour**, **criterion**, or **scorer** arising from the requirements, constraints, or operating context of a particular **task**. A task-specific scorer is provided by the library where one exists, or otherwise authored directly from its **criterion** as a *custom* scorer. |
| Behaviour | An expected **behaviour** describing how the agent should act while performing a **task**. |
| Criterion | A specific, assessable property used to determine whether a **behaviour** was exhibited in an individual **trial**. |
| Scenario | A concrete instantiation of a **task**, specifying the particular situation and conditions in which the agent is evaluated. |
| Persona | A concrete simulated user whose characteristics and behaviour are relevant to an evaluation interaction. |
| Fixture | A reusable artefact or piece of environment state used to instantiate or execute a **test case**. It may be supplied by the user or generated dynamically. |
| Test Case | A complete specification of a particular evaluation condition, combining a **scenario**, a **persona** (where applicable), **fixtures**, and any conditions required for execution. |
| Trial | One execution of a **test case** against a **target agentic system**, producing a **trace** and evaluation outputs. |
| Run | A grouping of repeated **trials** of the same **test case**. |
| Experiment | A collection of **runs** used to evaluate one or more **target agentic systems** across a set of **test cases**. |
| Trace | The observable record of what occurred during a **trial**, including interactions, actions, tool calls, observations, and relevant state changes. |
| Session | A collection of **traces**. |
| Scorer | A procedure that evaluates a **trial** against a **criterion** and produces a **trial score**. |
| Trial Score | The value produced by applying a **scorer** to a **trial** for a particular **criterion**. |
| Scorer Passing Threshold | A configurable rule applied to the **trial score** from the **scorer** to mark it as pass or fail. |
| Result | The pass rate of a set of **trial scores**. |
| Test-Time Evals | Evaluations that measure a target model or **target agentic system** against curated datasets before release. |
| Run-Time Evals | Evaluations that continuously measure live traffic and real user interaction as a target model or **target agentic system** runs. |

## Baseline vs Task-specific

**Baseline** — applies to any **target agentic system**, whatever the task. Baseline behaviour should include baseline criterion and scorers. Baseline scorers should come from the library.

- fluency — is the response grammatically correct and natural?
- instruction following — did the agent do what the user asked?

**Task-specific** — exists only because of the task. Task-specific Behaviour should include task-specific criterion and scorers. These may or may not come from the library.

Example: a slide-making agent.

- from the library (a scorer with a parameter): minimum font size, colour contrast, number of slides
- *custom* (no library scorer, written from the **criterion**): concise slide language, specific to the user's use case

## Scorer Types

A **scorer** is one of two kinds:

- **Code scorer** — a program checks the **trace** against the **criterion**. Best when the criterion is exact and measurable.
  - slide count equals the requested number
  - font size at least the minimum
  - response is valid JSON
- **LLM-as-a-judge scorer** — a language model judges the **trace** against the **criterion**. Best when the criterion needs judgement.
  - output tone
  - instruction following
  - summary faithful to the source
