import assert from "node:assert/strict";
import test from "node:test";
import {
  ACCEPTED_FIXTURE_EXTENSIONS,
  FIXTURE_MAX_BYTES,
  FIXTURE_MAX_FILES,
  fixtureNames,
  normalizeFixtureName,
  validateFixtureSelection,
} from "./fixture-policy.ts";

const file = (name: string, size = 1) => ({ name, size });

test("accepts every advertised extension case-insensitively", () => {
  const names = validateFixtureSelection(
    ACCEPTED_FIXTURE_EXTENSIONS.map((extension) => file(`sample.${extension.toUpperCase()}`)),
    [],
  );
  assert.equal(names.length, ACCEPTED_FIXTURE_EXTENSIONS.length);
});

test("rejects unsupported types, unsafe names and collisions before upload", () => {
  for (const name of ["sample.exe", "../sample.csv", "report.csv", "CON.txt"]) {
    assert.throws(
      () => validateFixtureSelection([file(name)], name === "report.csv" ? [{ name, size: 1 }] : []),
      /Unsupported|portable|reserved|already (exists|uploaded|in)/,
    );
  }
  assert.equal(normalizeFixtureName("  résumé.md  "), "résumé.md");
});

test("enforces experiment-wide file and byte limits", () => {
  const twenty = Array.from({ length: FIXTURE_MAX_FILES }, (_, i) => file(`f-${i}.txt`));
  assert.doesNotThrow(() => validateFixtureSelection(twenty, []));
  assert.throws(() => validateFixtureSelection([file("overflow.txt")], twenty.map((item) => item)), /at most 20/);
  assert.throws(() => validateFixtureSelection([file("large.txt", FIXTURE_MAX_BYTES + 1)], []), /100 MB/);
});

test("returns filename references without copying library files", () => {
  const library = [{ name: "policy.md", size: 20 }];
  assert.deepEqual(fixtureNames([file("notes.html")]), ["notes.html"]);
  assert.deepEqual(library, [{ name: "policy.md", size: 20 }]);
});
