import assert from "node:assert/strict";
import test from "node:test";
import {
  ACCEPTED_FIXTURE_EXTENSIONS,
  FIXTURE_MAX_BYTES,
  FIXTURE_MAX_FILES,
  normalizeFixtureName,
  validateFixtureSelection,
} from "./fixture-policy.ts";

const file = (name: string, size = 1) => ({ name, size });

test("accepts each supported fixture extension without case sensitivity", () => {
  assert.equal(
    validateFixtureSelection(
      ACCEPTED_FIXTURE_EXTENSIONS.map((value) =>
        file(`sample.${value.toUpperCase()}`),
      ),
      [],
    ).length,
    ACCEPTED_FIXTURE_EXTENSIONS.length,
  );
});

test("rejects unsafe, unsupported, and duplicate fixture names", () => {
  for (const name of ["../sample.csv", "CON.txt", "sample.exe"]) {
    assert.throws(() => validateFixtureSelection([file(name)], []));
  }
  assert.throws(() =>
    validateFixtureSelection([file("STRASSE.csv")], [file("straße.csv")]),
  );
  assert.equal(normalizeFixtureName("  résumé.md  "), "résumé.md");
});

test("enforces the fixture count and total byte limits", () => {
  const full = Array.from({ length: FIXTURE_MAX_FILES }, (_, index) =>
    file(`f-${index}.txt`),
  );
  assert.doesNotThrow(() => validateFixtureSelection(full, []));
  assert.throws(() => validateFixtureSelection([file("extra.txt")], full));
  assert.throws(() =>
    validateFixtureSelection([file("large.txt", FIXTURE_MAX_BYTES + 1)], []),
  );
});
