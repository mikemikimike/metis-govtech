import type { MetricSpec, ProductProfile } from "./transport/api";

export interface ManualPersona {
  id: string;
  description: string;
}

export interface ManualScenario {
  id: string;
  description: string;
  num_trials: number;
  persona_refs: string[];
  scorers: MetricSpec[];
  fixtures: string[];
}

export interface ManualExperiment {
  id: string;
  description: string;
  personas: ManualPersona[];
  scenarios: ManualScenario[];
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
  };
}

export function emptyManualPersona(): ManualPersona {
  return { id: "", description: "" };
}

export function emptyManualScenario(
  personaRefs: readonly string[] = [],
): ManualScenario {
  return {
    id: "",
    description: "",
    num_trials: 1,
    persona_refs: [...personaRefs],
    scorers: [],
    fixtures: [],
  };
}

export function synthesizeManualProfile(
  experiment: ManualExperiment,
): ProductProfile {
  const description = experiment.description.trim();
  const behaviours = experiment.scenarios.map((scenario, scenarioIndex) => {
    const id = scenario.id.trim();
    return {
      id: `EB-${scenarioIndex + 1}`,
      name: id,
      description: scenario.description.trim(),
      measured: true,
      criteria: scenario.scorers.map((scorer, scorerIndex) => ({
        id: `AC-${scenarioIndex + 1}-${scorerIndex + 1}`,
        name: scorer.name,
        description: {
          given: `the target agent is evaluated in scenario ${id}`,
          when: scenario.description.trim(),
          then: `the result is evaluated by ${scorer.name}: ${scorer.description}`,
        },
        metric_fqn: scorer.fqn,
        metric_args: {},
      })),
    };
  });

  return {
    schema_version: 2,
    product: {
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
      return { id, name: id, description: persona.description.trim() };
    }),
    scenarios: experiment.scenarios.map((scenario, index) => {
      const id = scenario.id.trim();
      return {
        id,
        name: id,
        description: scenario.description.trim(),
        behaviour_refs: [`EB-${index + 1}`],
        persona_refs: scenario.persona_refs,
        fixtures: scenario.fixtures,
        num_trials: scenario.num_trials,
      };
    }),
  };
}

export function manualFormProblems(
  experiment: ManualExperiment,
  fixtures: readonly Pick<ManualFixture, "name">[],
): string[] {
  const problems: string[] = [];
  const experimentId = experiment.id.trim();
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(experimentId)) {
    problems.push("a lowercase experiment ID with words joined by hyphens");
  }
  if (!experiment.description.trim())
    problems.push("an experiment description");

  const personaIds = experiment.personas.map((persona) => persona.id.trim());
  if (experiment.personas.length === 0) problems.push("at least one persona");
  else {
    if (
      experiment.personas.some(
        (persona) => !persona.id.trim() || !persona.description.trim(),
      )
    ) {
      problems.push("an ID and description for every persona");
    }
    if (new Set(personaIds).size !== personaIds.length) {
      problems.push("unique persona IDs");
    }
  }

  if (experiment.scenarios.length === 0) problems.push("at least one scenario");
  else {
    const scenarioIds = experiment.scenarios.map((scenario) =>
      scenario.id.trim(),
    );
    if (
      experiment.scenarios.some(
        (scenario) => !scenario.id.trim() || !scenario.description.trim(),
      )
    ) {
      problems.push("an ID and description for every scenario");
    }
    if (new Set(scenarioIds).size !== scenarioIds.length) {
      problems.push("unique scenario IDs");
    }
    if (
      experiment.scenarios.some(
        (scenario) =>
          !Number.isInteger(scenario.num_trials) ||
          scenario.num_trials < 1 ||
          scenario.num_trials > 20,
      )
    ) {
      problems.push("1 to 20 trials for every scenario");
    }
    const currentPersonas = new Set(personaIds.filter(Boolean));
    if (
      experiment.scenarios.some(
        (scenario) =>
          scenario.persona_refs.length === 0 ||
          scenario.persona_refs.some((id) => !currentPersonas.has(id)),
      )
    ) {
      problems.push("a current persona for every scenario");
    }
    if (
      experiment.scenarios.some((scenario) => scenario.scorers.length === 0)
    ) {
      problems.push("a scorer for every scenario");
    }
  }

  const present = new Set(fixtures.map((fixture) => fixture.name));
  const missing = referencedFixtureNames(experiment.scenarios).filter(
    (name) => !present.has(name),
  );
  if (missing.length > 0) problems.push(`files: ${missing.join(", ")}`);
  return problems;
}

export function replacePersonaReference(
  scenarios: readonly ManualScenario[],
  previousId: string,
  nextId: string,
): ManualScenario[] {
  const previous = previousId.trim();
  const next = nextId.trim();
  if (!previous || previous === next) return [...scenarios];
  return scenarios.map((scenario) => ({
    ...scenario,
    persona_refs: scenario.persona_refs.flatMap((id) => {
      if (id !== previous) return [id];
      return next ? [next] : [];
    }),
  }));
}

export function addPersonaReference(
  scenarios: readonly ManualScenario[],
  personaId: string,
): ManualScenario[] {
  const id = personaId.trim();
  if (!id) return [...scenarios];
  return scenarios.map((scenario) => ({
    ...scenario,
    persona_refs: scenario.persona_refs.includes(id)
      ? [...scenario.persona_refs]
      : [...scenario.persona_refs, id],
  }));
}

export function referencedFixtureNames(
  scenarios: readonly ManualScenario[],
): string[] {
  return [...new Set(scenarios.flatMap((scenario) => scenario.fixtures))];
}

export function keepReferencedFixtures(
  scenarios: readonly ManualScenario[],
  fixtures: readonly ManualFixture[],
): ManualFixture[] {
  const referenced = new Set(referencedFixtureNames(scenarios));
  return fixtures.filter((fixture) => referenced.has(fixture.name));
}
