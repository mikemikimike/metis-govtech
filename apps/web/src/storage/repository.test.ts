import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { indexedDB as fakeIndexedDB } from "fake-indexeddb";
import type { InterviewState } from "../transport/api.ts";
import { InterviewRepository, emptyRecord } from "./repository.ts";

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
    schema_version: 1,
    product: { name: "", users: "", description: "", detail: "" },
    tasks: [],
    personas: [],
    scenarios: [],
  },
  behaviours_confirmed: false,
  confirmed: false,
  history: [],
  user_typed: [],
  issued_ids: [],
  pending: null,
};

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
  assert.equal((await repository.read("storage-test-a"))?.storage_version, 2);
  await repository.delete("storage-test-a");
  assert.equal(await repository.read("storage-test-a"), undefined);
  await repository.delete("storage-test-b");
});

test("isolates unsupported and corrupt records while keeping healthy records", async () => {
  const repository = new InterviewRepository();
  const healthy = emptyRecord("healthy-record", state, "clarify", []);
  await repository.put(healthy);
  await new Promise<void>((resolve, reject) => {
    const request = fakeIndexedDB.open("metis-web", 1);
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
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    };
    request.onerror = () => reject(request.error);
  });

  assert.deepEqual(
    (await repository.list()).map((record) => record.id),
    ["healthy-record"],
  );
  assert.equal(repository.problems.length, 2);
  assert.equal(await repository.read("bad-record"), undefined);
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
