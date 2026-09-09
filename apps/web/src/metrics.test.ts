import assert from "node:assert/strict";
import test from "node:test";
import type { ProductProfile } from "./transport/api.ts";
import { profileHasCriteria } from "./metrics.ts";

const profile: ProductProfile = {
  schema_version: 1,
  product: { name: "", users: "", description: "", detail: "" },
  tasks: [
    {
      id: "T-1",
      name: "Task",
      description: "",
      behaviours: [
        {
          id: "B-1",
          name: "Behaviour",
          description: "",
          measured: true,
          criteria: [],
        },
      ],
    },
  ],
  personas: [],
  scenarios: [],
};

test("metric loading waits until the Profile contains a Criterion", () => {
  assert.equal(profileHasCriteria(profile), false);
  const withCriterion: ProductProfile = {
    ...profile,
    tasks: [
      {
        ...profile.tasks[0]!,
        behaviours: [
          {
            ...profile.tasks[0]!.behaviours[0]!,
            criteria: [
              {
                id: "C-1",
                name: "Criterion",
                description: { given: "", when: "", then: "" },
              },
            ],
          },
        ],
      },
    ],
  };
  assert.equal(profileHasCriteria(withCriterion), true);
});
