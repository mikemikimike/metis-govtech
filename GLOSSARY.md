| Term | Definition |
|------|------------|
| Target Agentic System | The agentic system under evaluation, considered at a specific version or configuration. |
| Task | A general description of what the **target agentic system** is expected to accomplish. |
| Desired Behaviour | An expected pattern of agent conduct describing how the agent should act while performing a **task**. |
| Baseline Behaviour | A **desired behaviour** expected by default across agentic tasks, unless a task renders it inapplicable. |
| Task-specific Behaviour | A **desired behaviour** arising from the requirements, constraints, or operating context of a particular **task**. |
| Criterion | A specific, assessable property used to determine whether a **desired behaviour** was exhibited in an individual **trial**. |
| Baseline Criterion | A **criterion** used to determine whether a **baseline behaviour** was exhibited. |
| Task-specific Criterion | A **criterion** used to determine whether a **task-specific behaviour** was exhibited. |
| Scenario | A concrete instantiation of a **task**, specifying the particular situation and conditions in which the agent is evaluated. |
| Persona | A concrete simulated user whose characteristics and behaviour are relevant to an evaluation interaction. |
| Fixture | A reusable artefact or piece of environment state used to instantiate or execute a **test case**. It may be supplied by the user or generated dynamically. |
| Test Case | A complete specification of a particular evaluation condition, combining a **scenario**, a **persona** (where applicable), **fixtures**, and any conditions required for execution. |
| Trial | One execution of a **test case** against a **target agentic system**, producing a **trace** and evaluation outputs. |
| Run | A grouping of repeated **trials** of the same **test case**. |
| Experiment | A collection of **runs** used to evaluate one or more **target agentic systems** across a set of **test cases**. |
| Trace | The observable record of what occurred during a **trial**, including interactions, actions, tool calls, observations, and relevant state changes. |
| Scorer | A procedure that evaluates a **trial** against a **criterion** and produces a **trial score**. |
| Trial Score | The value produced by applying a **scorer** to a **trial** for a particular **criterion**. |
| Result | The average **trial score** of a **run**. |
| Passing Threshold | A configurable acceptance rule applied to a **result**. Its value may vary according to the **task** or evaluation context. |
| Test-Time Evals | Evaluations that measure a target model or **target agentic system** against curated datasets before release. |
| Run-Time Evals | Evaluations that continuously measure live traffic and real user interaction as a target model or **target agentic system** runs. |
