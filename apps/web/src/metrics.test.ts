import assert from "node:assert/strict";
import test from "node:test";
import type { ProductProfile } from "./transport/api.ts";
import { profileHasCriteria } from "./metrics.ts";

const profile: ProductProfile = {
  schema_version: 2,
  product: { name: "", users: "", description: "", detail: "" },
  features: [
    {
      id: "F-1",
      name: "Feature",
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
    features: [
      {
        ...profile.features[0]!,
        behaviours: [
          {
            ...profile.features[0]!.behaviours[0]!,
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
