import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  keepReferencedFixtures,
  manualFormProblems,
  replacePersonaReference,
  synthesizeManualProfile,
  type ManualExperiment,
} from "./manual.ts";

const synthesis = {
  id: " manual-research ",
  description: " Check research answers and recovery. ",
  personas: [
    { id: " analyst ", description: " A careful policy analyst. " },
    { id: "director", description: "A time-poor director." },
  ],
  scenarios: [
    {
      id: " supported-answer ",
      description: " Ask for a supported answer. ",
      num_trials: 2,
      persona_refs: ["analyst", "director"],
      fixtures: ["policy.pdf"],
      scorers: [
        {
          fqn: "metis.library.metrics.SynthesisFaithfulnessMetric",
          name: "Synthesis faithfulness",
          description: "Checks that the answer uses its evidence.",
        },
        {
          fqn: "metis.library.metrics.TurnBudgetMetric",
          name: "Turn budget",
          description:
            "Checks that the conversation stays within its turn budget.",
        },
      ],
    },
    {
      id: "short-recovery",
      description: "Recover after a failed search.",
      num_trials: 1,
      persona_refs: ["analyst"],
      fixtures: ["notes.txt"],
      scorers: [
        {
          fqn: "metis.library.metrics.TurnBudgetMetric",
          name: "Turn budget",
          description:
            "Checks that the conversation stays within its turn budget.",
        },
      ],
    },
  ],
} satisfies ManualExperiment;

test("synthesizes the complete deterministic manual Profile", () => {
  const expected = JSON.parse(
    readFileSync(
      new URL(
        "../../../tests/fixtures/wizard/manual_profile.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  assert.deepEqual(synthesizeManualProfile(synthesis), expected);
});

test("the complete-form gate checks every manual row", () => {
  assert.deepEqual(
    manualFormProblems(synthesis, [
      { name: "policy.pdf" },
      { name: "notes.txt" },
    ]),
    [],
  );

  const invalid: ManualExperiment = {
    id: "Not valid",
    description: " ",
    personas: [
      { id: "same", description: "ok" },
      { id: "same", description: " " },
    ],
    scenarios: [
      {
        id: "same",
        description: "",
        num_trials: 21,
        persona_refs: ["missing"],
        scorers: [],
        fixtures: ["missing.pdf"],
      },
      {
        id: "same",
        description: "ok",
        num_trials: 1,
        persona_refs: [],
        scorers: synthesis.scenarios[0]?.scorers ?? [],
        fixtures: [],
      },
    ],
  };
  const problems = manualFormProblems(invalid, []);
  for (const part of [
    "lowercase experiment ID",
    "experiment description",
    "every persona",
    "unique persona IDs",
    "every scenario",
    "unique scenario IDs",
    "1 to 20 trials",
    "current persona",
    "scorer",
    "missing.pdf",
  ]) {
    assert.match(problems.join(" "), new RegExp(part));
  }
});

test("persona references follow a changed or removed persona ID", () => {
  const renamed = replacePersonaReference(
    synthesis.scenarios,
    "analyst",
    "reviewer",
  );
  assert.deepEqual(renamed[0]?.persona_refs, ["reviewer", "director"]);
  assert.deepEqual(
    replacePersonaReference(renamed, "reviewer", "")[0]?.persona_refs,
    ["director"],
  );
});

test("keeps only fixture bytes that a current Scenario uses", () => {
  const files = [
    { name: "policy.pdf", size: 1, blob: new Blob(["p"]) },
    { name: "notes.txt", size: 1, blob: new Blob(["n"]) },
    { name: "removed.csv", size: 1, blob: new Blob(["r"]) },
  ];
  assert.deepEqual(
    keepReferencedFixtures(synthesis.scenarios, files).map((file) => file.name),
    ["policy.pdf", "notes.txt"],
  );
});
