import type { GraderSpec, Specification } from "./transport/api";

export interface ManualMetadataEntry {
  key: string;
  value: string;
}

export interface ManualPersona {
  metadata?: ManualMetadataEntry[];
  id: string;
  description: string;
}

export interface ManualScenario {
  metadata?: ManualMetadataEntry[];
  id: string;
  description: string;
}

export interface ManualTestCase {
  id: string;

  scenario_ref: string;
  persona_ref: string;
  num_trials: number;
  max_turns?: number;
  timeout_minutes?: number;
  response_wait_ms?: number;
  max_run_retries?: number | null;
  scorers: GraderSpec[];
  fixtures: string[];
  grader_args_text?: Record<string, string>;
  grader_args?: Record<string, Record<string, unknown>>;
}

export interface ManualExperiment {
  id: string;
  description: string;
  personas: ManualPersona[];
  scenarios: ManualScenario[];
  tasks: ManualTestCase[];
}

export interface ManualFixture {
  name: string;
  size: number;
  blob: Blob;
}

export function emptyManualExperiment(): ManualExperiment {
  return {
    id: "",
    description: "",
    personas: [],
    scenarios: [],
    tasks: [],
  };
}

export function emptyManualPersona(): ManualPersona {
  return { id: "", description: "" };
}

export function emptyManualScenario(): ManualScenario {
  return { id: "", description: "" };
}

export function emptyManualTestCase(): ManualTestCase {
  return {
    id: "",

    scenario_ref: "",
    persona_ref: "",
    num_trials: 1,
    scorers: [],
    fixtures: [],
  };
}

export function scorerParameters(
  task: ManualTestCase,
  fqn: string,
): Record<string, unknown> {
  const text = task.grader_args_text?.[fqn];
  const value: unknown =
    text === undefined ? (task.grader_args?.[fqn] ?? {}) : JSON.parse(text);
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new Error("Scorer settings must be a JSON object.");
  return value as Record<string, unknown>;
}

function metadataKeyError(
  entries: readonly ManualMetadataEntry[],
  index: number,
): string | undefined {
  const key = entries[index].key;
  if (!key.trim()) return "Enter a key.";
  if (entries.slice(0, index).some((entry) => entry.key === key))
    return "Use a unique key.";
  return undefined;
}

function metadataFields(entries: readonly ManualMetadataEntry[] = []): {
  metadata?: Record<string, string>;
} {
  if (!entries.length) return {};
  entries.forEach((_, index) => {
    const error = metadataKeyError(entries, index);
    if (error) throw new Error(error);
  });
  return {
    metadata: Object.fromEntries(entries.map(({ key, value }) => [key, value])),
  };
}

export function synthesizeManualSpecification(
  experiment: ManualExperiment,
): Specification {
  const description = experiment.description.trim();
  const behaviours = experiment.tasks.map((task, taskIndex) => {
    const scenario = experiment.scenarios.find(
      (s) => s.id.trim() === task.scenario_ref,
    );
    const label = `${task.scenario_ref}: ${task.persona_ref}`;
    return {
      id: `EB-${taskIndex + 1}`,
      name: label,
      description: scenario?.description.trim() ?? "",
      measured: true,
      criteria: task.scorers.map((scorer, scorerIndex) => ({
        id: `AC-${taskIndex + 1}-${scorerIndex + 1}`,
        name: scorer.name,
        description: {
          given: `the target agent is evaluated in scenario ${task.scenario_ref} with persona ${task.persona_ref}`,
          when: scenario?.description.trim() ?? "",
          then: `the result is evaluated by ${scorer.name}: ${scorer.description}`,
        },
        grader_fqn: scorer.fqn,
        grader_args: scorerParameters(task, scorer.fqn),
      })),
    };
  });

  return {
    schema_version: 1,
    id: experiment.id.trim(),
    runner_factory_ref:
      "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory",
    target: {
      name: experiment.id.trim(),
      description,
      users: "The personas defined in this manual experiment.",
      detail: "",
    },
    features: [
      {
        id: "EP-1",
        name: "Manual experiment",
        description,
        behaviours,
      },
    ],
    personas: experiment.personas.map((persona) => {
      const id = persona.id.trim();
      return {
        id,
        name: id,
        description: persona.description.trim(),
        ...metadataFields(persona.metadata),
      };
    }),
    tasks: experiment.tasks.map((task, index) => ({
      id: task.id,

      scenario_ref: task.scenario_ref,
      persona_ref: task.persona_ref,
      fixtures: [...task.fixtures],
      num_trials: task.num_trials,
      max_turns: task.max_turns ?? 20,
      timeout_minutes: task.timeout_minutes ?? 15,
      response_wait_ms: task.response_wait_ms ?? 300000,
      max_run_retries: task.max_run_retries ?? null,
      behaviour_refs: [behaviours[index].id],
    })),
    scenarios: experiment.scenarios.map((scenario) => {
      const id = scenario.id.trim();
      return {
        id,
        name: id,
        description: scenario.description.trim(),
        ...metadataFields(scenario.metadata),
      };
    }),
  };
}

/**
 * One incomplete field in the manual form. `field` names the control that shows the
 * message: `experiment.id`, `persona.0.description`, `task.1.scorers`, and so on.
 * Collection keys (`personas`, `scenarios`, `tasks`) mark an empty collection.
 */
export interface ManualFieldError {
  field: string;
  message: string;
}

function definitionErrors(
  kind: "persona" | "scenario",
  label: string,
  items: readonly (ManualPersona | ManualScenario)[],
): ManualFieldError[] {
  const errors: ManualFieldError[] = [];
  const ids = items.map((item) => item.id.trim());
  items.forEach((item, index) => {
    const entries = item.metadata ?? [];
    entries.forEach((_, row) => {
      const message = metadataKeyError(entries, row);
      if (message)
        errors.push({ field: `${kind}.${index}.metadata.${row}.key`, message });
    });
    const id = ids[index];
    if (!id)
      errors.push({ field: `${kind}.${index}.id`, message: "Enter an ID." });
    else if (ids.indexOf(id) !== index)
      errors.push({
        field: `${kind}.${index}.id`,
        message: `Use an ID that no other ${label} uses.`,
      });
    if (!item.description.trim())
      errors.push({
        field: `${kind}.${index}.description`,
        message: "Enter a description.",
      });
  });
  return errors;
}

export function manualFieldErrors(
  experiment: ManualExperiment,
  fixtures: readonly Pick<ManualFixture, "name">[],
): ManualFieldError[] {
  const errors: ManualFieldError[] = [];
  const add = (field: string, message: string) =>
    errors.push({ field, message });

  const experimentId = experiment.id.trim();
  if (!experimentId) add("experiment.id", "Enter an ID.");
  else if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(experimentId))
    add(
      "experiment.id",
      "Use lowercase words joined by hyphens, such as research-assistant.",
    );
  if (!experiment.description.trim())
    add("experiment.description", "Enter a description.");

  if (!experiment.personas.length) add("personas", "Add at least one Persona.");
  errors.push(...definitionErrors("persona", "Persona", experiment.personas));

  if (!experiment.scenarios.length)
    add("scenarios", "Add at least one Scenario.");
  errors.push(
    ...definitionErrors("scenario", "Scenario", experiment.scenarios),
  );
  experiment.scenarios.forEach((scenario, index) => {
    const id = scenario.id.trim();
    if (id && !experiment.tasks.some((task) => task.scenario_ref === id))
      add(
        `scenario.${index}.tasks`,
        "Select this Scenario in at least one test case.",
      );
  });

  if (!experiment.tasks.length) add("tasks", "Add at least one test case.");
  const scenarioIds = new Set(
    experiment.scenarios.map((s) => s.id.trim()).filter(Boolean),
  );
  const personaIds = new Set(
    experiment.personas.map((p) => p.id.trim()).filter(Boolean),
  );
  const present = new Set(fixtures.map((fixture) => fixture.name));
  experiment.tasks.forEach((task, index) => {
    if (!personaIds.has(task.persona_ref))
      add(`task.${index}.persona`, "Select a Persona.");
    if (!scenarioIds.has(task.scenario_ref))
      add(`task.${index}.scenario`, "Select a Scenario.");
    if (
      !Number.isInteger(task.num_trials) ||
      task.num_trials < 1 ||
      task.num_trials > 20
    )
      add(`task.${index}.trials`, "Enter 1 to 20 Trials.");
    if (!task.scorers.length)
      add(`task.${index}.scorers`, "Select at least one scorer.");
    for (const scorer of task.scorers) {
      try {
        scorerParameters(task, scorer.fqn);
      } catch {
        add(
          `task.${index}.settings.${scorer.fqn}`,
          "Enter the settings as a JSON object, such as {}.",
        );
      }
    }
    const missing = task.fixtures.filter((name) => !present.has(name));
    if (missing.length)
      add(`task.${index}.files`, `Choose ${missing.join(", ")} again.`);
  });
  return errors;
}

export function replaceTaskReference(
  tasks: readonly ManualTestCase[],
  field: "persona_ref" | "scenario_ref",
  previousId: string,
  nextId: string,
): ManualTestCase[] {
  const previous = previousId.trim();
  if (!previous) return [...tasks];
  return tasks.map((task) =>
    task[field] === previous ? { ...task, [field]: nextId.trim() } : task,
  );
}

export function referencedFixtureNames(
  tasks: readonly ManualTestCase[],
): string[] {
  return [...new Set(tasks.flatMap((task) => task.fixtures))];
}

export function keepReferencedFixtures(
  tasks: readonly ManualTestCase[],
  fixtures: readonly ManualFixture[],
): ManualFixture[] {
  const referenced = new Set(referencedFixtureNames(tasks));
  return fixtures.filter((fixture) => referenced.has(fixture.name));
}

export function manualScorers(graders: GraderSpec[]): GraderSpec[] {
  // The manual form has no criterion description to give these graders their instructions.
  return graders.filter((grader) => !grader.uses_criterion_description);
}
