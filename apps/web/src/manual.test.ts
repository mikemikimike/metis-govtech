import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  emptyManualExperiment,
  emptyManualTestCase,
  keepReferencedFixtures,
  manualFieldErrors,
  replaceTaskReference,
  synthesizeManualSpecification,
  type ManualExperiment,
} from "./manual.ts";

const synthesisScorer = {
  fqn: "tests.unit.engine.graders_for_tests.FixedScoreGrader",
  name: "Synthesis faithfulness",
  description: "Checks that the answer uses its evidence.",
};
const budgetScorer = {
  fqn: "metis.library.graders.TraceBudgetGrader",
  name: "Turn budget",
  description: "Checks that the conversation stays within its turn budget.",
};
const synthesis = {
  id: " manual-research ",
  description: " Check research answers and recovery. ",
  personas: [
    { id: " analyst ", description: " A careful policy analyst. " },
    { id: "director", description: "A time-poor director." },
  ],
  scenarios: [
    { id: " supported-answer ", description: " Ask for a supported answer. " },
    { id: "short-recovery", description: "Recover after a failed search." },
  ],
  tasks: [
    {
      id: "",

      scenario_ref: "supported-answer",
      persona_ref: "analyst",
      num_trials: 2,
      fixtures: ["policy.pdf"],
      scorers: [synthesisScorer, budgetScorer],
    },
    {
      id: "",

      scenario_ref: "supported-answer",
      persona_ref: "director",
      num_trials: 2,
      fixtures: ["policy.pdf"],
      scorers: [synthesisScorer, budgetScorer],
    },
    {
      id: "",

      scenario_ref: "short-recovery",
      persona_ref: "analyst",
      num_trials: 1,
      fixtures: ["notes.txt"],
      scorers: [budgetScorer],
    },
  ],
} satisfies ManualExperiment;

test("explicit test cases produce the complete engine Specification", () => {
  const expected = JSON.parse(
    readFileSync(
      new URL(
        "../../../tests/fixtures/wizard/manual_specification.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  assert.deepEqual(synthesizeManualSpecification(synthesis), expected);
  assert.deepEqual(
    manualFieldErrors(synthesis, [
      { name: "policy.pdf" },
      { name: "notes.txt" },
    ]),
    [],
  );
});

test("each test case selects an existing Persona and Scenario and valid execution settings", () => {
  const invalid: ManualExperiment = {
    id: "Not valid",
    description: " ",
    personas: [
      { id: "same", description: "ok" },
      { id: "same", description: "" },
    ],
    scenarios: [
      { id: "same", description: "" },
      { id: "same", description: "ok" },
    ],
    tasks: [
      {
        ...emptyManualTestCase(),
        num_trials: 21,
        persona_ref: "missing",
        scenario_ref: "missing",
        fixtures: ["missing.pdf"],
      },
    ],
  };
  const fields = manualFieldErrors(invalid, []).map((error) => error.field);
  assert.deepEqual(fields, [
    "experiment.id",
    "experiment.description",
    "persona.1.id",
    "persona.1.description",
    "scenario.0.description",
    "scenario.1.id",
    "scenario.0.tasks",
    "scenario.1.tasks",
    "task.0.persona",
    "task.0.scenario",
    "task.0.trials",
    "task.0.scorers",
    "task.0.files",
  ]);
  assert.deepEqual(
    manualFieldErrors(emptyManualExperiment(), []).map((error) => error.field),
    [
      "experiment.id",
      "experiment.description",
      "personas",
      "scenarios",
      "tasks",
    ],
  );
});

test("renaming and removing definitions preserve test case identity and other settings", () => {
  const tasks = [{ ...synthesis.tasks[0], id: "TC-stable" }];
  const renamed = replaceTaskReference(
    replaceTaskReference(tasks, "persona_ref", "analyst", "reviewer"),
    "scenario_ref",
    "supported-answer",
    "new-situation",
  );
  assert.deepEqual(renamed[0], {
    ...tasks[0],
    persona_ref: "reviewer",
    scenario_ref: "new-situation",
  });
  assert.equal(
    replaceTaskReference(renamed, "persona_ref", "reviewer", "")[0].persona_ref,
    "",
  );
  assert.equal(
    replaceTaskReference(renamed, "scenario_ref", "new-situation", "")[0]
      .scenario_ref,
    "",
  );
  assert.equal(
    replaceTaskReference(renamed, "persona_ref", "", "new-person")[0]
      .persona_ref,
    "reviewer",
  );
});

test("keeps fixture bytes until the last test case that uses them is removed", () => {
  const files = ["policy.pdf", "notes.txt", "unused.csv"].map((name) => ({
    name,
    size: 1,
    blob: new Blob(["x"]),
  }));
  assert.deepEqual(
    keepReferencedFixtures(synthesis.tasks.slice(1), files).map((f) => f.name),
    ["policy.pdf", "notes.txt"],
  );
  assert.deepEqual(
    keepReferencedFixtures(synthesis.tasks.slice(2), files).map((f) => f.name),
    ["notes.txt"],
  );
});

test("the same Persona and Scenario can have separate test cases and scorer settings", () => {
  const experiment: ManualExperiment = structuredClone(synthesis);
  const first = experiment.tasks[0];
  const second = experiment.tasks[1];
  first.id = "TC-first";
  second.id = "TC-second";
  second.persona_ref = first.persona_ref;
  first.grader_args_text = { [budgetScorer.fqn]: '{"max_traces":4}' };
  second.grader_args_text = { [budgetScorer.fqn]: '{"max_traces":10}' };
  const specification = synthesizeManualSpecification(experiment);
  assert.deepEqual(
    specification.tasks.slice(0, 2).map((t) => t.id),
    ["TC-first", "TC-second"],
  );
  assert.equal(specification.tasks.length, 3);
  assert.equal(
    specification.tasks.reduce((total, t) => total + t.num_trials, 0),
    5,
  );
  assert.deepEqual(
    specification.features[0].behaviours[0].criteria[1].grader_args,
    {
      max_traces: 4,
    },
  );
  assert.deepEqual(
    specification.features[0].behaviours[1].criteria[1].grader_args,
    {
      max_traces: 10,
    },
  );
  assert.notDeepEqual(
    specification.tasks[0].behaviour_refs,
    specification.tasks[1].behaviour_refs,
  );
  first.grader_args_text[budgetScorer.fqn] = "[]";
  assert.ok(
    manualFieldErrors(experiment, []).some(
      (error) => error.field === `task.0.settings.${budgetScorer.fqn}`,
    ),
  );
});

test("manual task execution settings survive specification construction", () => {
  const experiment: ManualExperiment = structuredClone(synthesis);
  Object.assign(experiment.tasks[0], {
    max_turns: 7,
    timeout_minutes: 2,
    response_wait_ms: 45000,
    max_run_retries: 0,
  });
  const task = synthesizeManualSpecification(experiment).tasks[0];
  assert.equal(task.max_turns, 7);
  assert.equal(task.timeout_minutes, 2);
  assert.equal(task.response_wait_ms, 45000);
  assert.equal(task.max_run_retries, 0);
});

test("manual metadata preserves text and requires unique nonblank keys", () => {
  const experiment: ManualExperiment = structuredClone(synthesis);
  for (const kind of ["personas", "scenarios"] as const) {
    const item = experiment[kind][0];
    item.metadata = [
      { key: "custom context", value: "  exact text  " },
      { key: "count", value: "001" },
      { key: "optional", value: "" },
    ];
    assert.deepEqual(
      synthesizeManualSpecification(experiment)[kind][0].metadata,
      {
        "custom context": "  exact text  ",
        count: "001",
        optional: "",
      },
    );
    const prefix = kind === "personas" ? "persona" : "scenario";
    item.metadata.push({ key: "count", value: "2" }, { key: " ", value: "x" });
    assert.deepEqual(
      manualFieldErrors(experiment, []).filter((error) =>
        error.field.startsWith(`${prefix}.0.metadata`),
      ),
      [
        { field: `${prefix}.0.metadata.3.key`, message: "Use a unique key." },
        { field: `${prefix}.0.metadata.4.key`, message: "Enter a key." },
      ],
    );
    assert.throws(
      () => synthesizeManualSpecification(experiment),
      /unique key/,
    );
    item.metadata = [];
    assert.equal(
      synthesizeManualSpecification(experiment)[kind][0].metadata,
      undefined,
    );
  }
});
