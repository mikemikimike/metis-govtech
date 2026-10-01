import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { indexedDB as fakeIndexedDB } from "fake-indexeddb";
import type { InterviewState } from "../transport/api.ts";
import {
  addFixtures,
  InterviewRepository,
  emptyRecord,
  removeUnreferencedFixtures,
} from "./repository.ts";

before(async () => {
  globalThis.indexedDB = fakeIndexedDB;
  await new Promise<void>((resolve, reject) => {
    const request = fakeIndexedDB.deleteDatabase("metis-web");
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
});

after(() => {
  (globalThis as { indexedDB?: IDBFactory }).indexedDB = undefined;
});

const state: InterviewState = {
  profile: {
    schema_version: 2,
    product: { name: "", users: "", description: "", detail: "" },
    features: [],
    personas: [],
    scenarios: [],
  },
  behaviours_confirmed: false,
  confirmed: false,
  context: {
    perspective: "end_user",
    opening_description: "",
    capability_evidence: { known_capability_ids: [], confidence: "low" },
  },
  history: [],
  user_typed: [],
  issued_ids: [],
  pending: null,
};

test("migrates saved Interviews with their description and fixture bytes", async () => {
  const request = fakeIndexedDB.open("metis-web", 2);
  const database = await new Promise<IDBDatabase>((resolve, reject) => {
    request.onupgradeneeded = () =>
      request.result.createObjectStore("interviews", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const bytes = new Blob(["policy bytes"], { type: "text/markdown" });
  const oldRecord = {
    ...emptyRecord("legacy-opening-files", state, "clarify", []),
    storage_version: 3,
    transcript: [
      {
        kind: "initial_description",
        id: "initial-message",
        description: "The opening explanation.",
      },
    ],
    state: {
      ...state,
      context: {
        perspective: "end_user",
        capability_evidence: {
          known_capability_ids: [],
          confidence: "low",
        },
      },
    },
    fixtures: [
      {
        name: "policy.md",
        type: "text/markdown",
        size: bytes.size,
        blob: bytes,
      },
    ],
  };
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction("interviews", "readwrite");
    transaction.objectStore("interviews").put(oldRecord);
    transaction
      .objectStore("interviews")
      .put({ ...oldRecord, id: "version-four", storage_version: 4 });
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();

  const migrated = await new InterviewRepository().read("legacy-opening-files");

  assert.equal(migrated?.storage_version, 5);
  assert.equal(
    migrated?.state.context.opening_description,
    "The opening explanation.",
  );
  assert.deepEqual(migrated?.state.context.documents, []);
  assert.equal(await migrated?.fixtures[0]?.blob.text(), "policy bytes");
  const versionFour = await new InterviewRepository().read("version-four");
  assert.equal(versionFour?.storage_version, 5);
  assert.equal(await versionFour?.fixtures[0]?.blob.text(), "policy bytes");
  await new InterviewRepository().delete("version-four");
  await new InterviewRepository().delete("legacy-opening-files");
});

test("local repository creates, orders, reads and deletes browser records", async () => {
  const repository = new InterviewRepository();
  const first = emptyRecord("storage-test-a", state, "clarify", []);
  await repository.put(first);
  await new Promise((resolve) => setTimeout(resolve, 1));
  const second = {
    ...emptyRecord("storage-test-b", state, "clarify", []),
    updated_at: Date.now() + 1,
  };
  await repository.put(second);

  assert.deepEqual(
    (await repository.list()).map((record) => record.id),
    ["storage-test-b", "storage-test-a"],
  );
  assert.equal((await repository.read("storage-test-a"))?.storage_version, 5);
  await repository.delete("storage-test-a");
  assert.equal(await repository.read("storage-test-a"), undefined);
  await repository.delete("storage-test-b");
});

test("isolates unsupported and corrupt records while keeping healthy records", async () => {
  const repository = new InterviewRepository();
  const healthy = emptyRecord("healthy-record", state, "clarify", []);
  await repository.put(healthy);
  await new Promise<void>((resolve, reject) => {
    const request = fakeIndexedDB.open("metis-web", 4);
    request.onsuccess = () => {
      const tx = request.result.transaction("interviews", "readwrite");
      tx.objectStore("interviews").put({
        storage_version: 99,
        id: "old-record",
      });
      tx.objectStore("interviews").put({
        storage_version: 2,
        id: "bad-record",
        state: {},
      });
      tx.objectStore("interviews").put({
        ...healthy,
        id: "missing-capability-evidence",
        state: { ...state, context: { perspective: "end_user" } },
      });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    };
    request.onerror = () => reject(request.error);
  });

  assert.deepEqual(
    (await repository.list()).map((record) => record.id),
    ["healthy-record"],
  );
  assert.equal(repository.problems.length, 3);
  assert.equal(await repository.read("bad-record"), undefined);
  assert.equal(await repository.read("missing-capability-evidence"), undefined);
});

test("rejects an invalid update before it can replace a healthy record", async () => {
  const repository = new InterviewRepository();
  const healthy = emptyRecord("atomic-record", state, "clarify", []);
  await repository.put(healthy);
  await assert.rejects(
    repository.put({
      ...healthy,
      storage_version: 1,
    } as unknown as typeof healthy),
  );
  assert.deepEqual(await repository.read("atomic-record"), healthy);
});

test("stores fixture Blobs with one local Interview and restores them", async () => {
  const repository = new InterviewRepository();
  const record = emptyRecord("fixture-record", state, "scenarios", []);
  const file = new File(["fixture bytes"], "policy.pdf", {
    type: "application/pdf",
  });

  await repository.put(addFixtures(record, [file]));
  const restored = await repository.read("fixture-record");

  assert.equal(restored?.fixtures[0]?.name, "policy.pdf");
  assert.equal(await restored?.fixtures[0]?.blob.text(), "fixture bytes");
  await repository.delete("fixture-record");
});

test("later uploads cannot replace an opening original with the same name", () => {
  const started = emptyRecord(
    "initial-name-conflict",
    {
      ...state,
      context: {
        ...state.context,
        documents: [{ name: "policy.md" }],
      },
    },
    "clarify",
    [],
  );
  const initial = addFixtures(started, [new File(["original"], "policy.md")]);

  assert.throws(
    () => addFixtures(initial, [new File(["replacement"], "policy.md")]),
    /cannot be replaced/,
  );
});

test("fixture Blobs are isolated between local Interviews", async () => {
  const repository = new InterviewRepository();
  const first = addFixtures(
    emptyRecord("fixture-one", state, "scenarios", []),
    [new File(["one"], "shared.pdf")],
  );
  const second = addFixtures(
    emptyRecord("fixture-two", state, "scenarios", []),
    [new File(["two"], "shared.pdf")],
  );

  await repository.put(first);
  await repository.put(second);

  assert.equal(
    await (await repository.read("fixture-one"))?.fixtures[0]?.blob.text(),
    "one",
  );
  assert.equal(
    await (await repository.read("fixture-two"))?.fixtures[0]?.blob.text(),
    "two",
  );
  await repository.delete("fixture-one");
  await repository.delete("fixture-two");
});

test("removing a fixture reference keeps a Blob used by another scenario", () => {
  const fixture = new File(["shared"], "shared.txt");
  const profile = {
    ...state.profile,
    scenarios: [
      {
        id: "S-1",
        name: "First",
        description: "First scenario",
        behaviour_refs: [],
        persona_refs: [],
        fixtures: ["shared.txt"],
        num_trials: 1,
      },
      {
        id: "S-2",
        name: "Second",
        description: "Second scenario",
        behaviour_refs: [],
        persona_refs: [],
        fixtures: ["shared.txt"],
        num_trials: 1,
      },
    ],
  };
  const record = addFixtures(
    emptyRecord("fixture-reference", { ...state, profile }, "scenarios", []),
    [fixture],
  );

  const stillUsed = removeUnreferencedFixtures(record, ["shared.txt"]);
  assert.equal(stillUsed.fixtures.length, 1);

  const noLongerUsed = removeUnreferencedFixtures(
    {
      ...record,
      state: {
        ...record.state,
        profile: {
          ...record.state.profile,
          scenarios: record.state.profile.scenarios.map((scenario) => ({
            ...scenario,
            fixtures: [],
          })),
        },
      },
    },
    ["shared.txt"],
  );
  assert.equal(noLongerUsed.fixtures.length, 0);
});
