import type {
  InterviewState,
  InterviewStep,
  LocalFixture,
  LocalInterviewRecord,
  TranscriptEntry,
} from "../transport/api.ts";

const DB_NAME = "metis-web";
const STORE_NAME = "interviews";
const DB_VERSION = 2;
const STORAGE_VERSION = 3 as const;
const INTERVIEW_STEPS: readonly InterviewStep[] = [
  "clarify",
  "behaviours",
  "criteria",
  "personas",
  "scenarios",
  "done",
];

export interface LocalStorageProblem {
  id: string;
  message: string;
}

function validRecord(value: unknown): value is LocalInterviewRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<LocalInterviewRecord>;
  return (
    record.storage_version === STORAGE_VERSION &&
    typeof record.id === "string" &&
    typeof record.created_at === "number" &&
    Number.isFinite(record.created_at) &&
    typeof record.updated_at === "number" &&
    Number.isFinite(record.updated_at) &&
    typeof record.title === "string" &&
    typeof record.stage === "string" &&
    INTERVIEW_STEPS.includes(record.stage) &&
    validState(record.state) &&
    Array.isArray(record.transcript) &&
    record.transcript.every(validTranscriptEntry) &&
    Array.isArray(record.fixtures) &&
    record.fixtures.every(validFixture)
  );
}

function validFixture(value: unknown): value is LocalFixture {
  if (!value || typeof value !== "object") return false;
  const fixture = value as Partial<LocalFixture>;
  return (
    typeof fixture.name === "string" &&
    fixture.name.length > 0 &&
    typeof fixture.type === "string" &&
    typeof fixture.size === "number" &&
    Number.isFinite(fixture.size) &&
    fixture.size >= 0 &&
    typeof Blob !== "undefined" &&
    fixture.blob instanceof Blob &&
    fixture.size === fixture.blob.size
  );
}

function validState(value: unknown): value is InterviewState {
  if (!value || typeof value !== "object") return false;
  const state = value as Partial<InterviewState>;
  return (
    !!state.profile &&
    typeof state.profile === "object" &&
    state.profile.schema_version === 1 &&
    Array.isArray(state.profile.tasks) &&
    Array.isArray(state.profile.personas) &&
    Array.isArray(state.profile.scenarios) &&
    Array.isArray(state.history) &&
    Array.isArray(state.user_typed) &&
    Array.isArray(state.issued_ids) &&
    (state.pending === null ||
      (typeof state.pending === "object" && state.pending !== null))
  );
}

function validTranscriptEntry(value: unknown): value is TranscriptEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<TranscriptEntry>;
  if (entry.kind === "initial_description") {
    return (
      typeof entry.id === "string" && typeof entry.description === "string"
    );
  }
  return (
    entry.kind === "interaction" &&
    typeof entry.request_id === "string" &&
    (entry.status === "pending" ||
      entry.status === "answered" ||
      entry.status === "ended_unanswered") &&
    !!entry.request &&
    typeof entry.request === "object"
  );
}

const memory = new Map<string, LocalInterviewRecord>();

export class InterviewRepository {
  private problemsValue: LocalStorageProblem[] = [];

  get problems(): readonly LocalStorageProblem[] {
    return this.problemsValue;
  }

  async list(): Promise<LocalInterviewRecord[]> {
    const rows = await this.allRaw();
    const healthy: LocalInterviewRecord[] = [];
    this.problemsValue = [];
    for (const row of rows) {
      if (validRecord(row)) healthy.push(row);
      else
        this.problemsValue.push({
          id:
            typeof row === "object" && row && "id" in row
              ? String((row as { id?: unknown }).id)
              : "unknown",
          message: "This local Interview cannot be read.",
        });
    }
    return healthy.sort((a, b) => b.updated_at - a.updated_at);
  }

  async read(id: string): Promise<LocalInterviewRecord | undefined> {
    const row = await this.raw(id);
    if (row === undefined) return undefined;
    if (!validRecord(row)) {
      this.problemsValue = [
        { id, message: "This local Interview cannot be read." },
      ];
      return undefined;
    }
    return row;
  }

  async put(record: LocalInterviewRecord): Promise<void> {
    if (!validRecord(record))
      throw new Error("Invalid local Interview record.");
    await this.write(record);
  }

  async delete(id: string): Promise<void> {
    if (!globalThis.indexedDB) {
      memory.delete(id);
      return;
    }
    const db = await this.database();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () =>
        reject(tx.error ?? new Error("Local Interview deletion failed."));
      tx.onabort = () =>
        reject(tx.error ?? new Error("Local Interview deletion failed."));
    });
  }

  private async allRaw(): Promise<unknown[]> {
    if (!globalThis.indexedDB) return [...memory.values()];
    const db = await this.database();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const request = tx.objectStore(STORE_NAME).getAll();
      request.onsuccess = () => resolve(request.result as unknown[]);
      request.onerror = () =>
        reject(
          request.error ?? new Error("Local Interviews could not be read."),
        );
    });
  }

  private async raw(id: string): Promise<unknown> {
    if (!globalThis.indexedDB) return memory.get(id);
    const db = await this.database();
    return new Promise((resolve, reject) => {
      const request = db
        .transaction(STORE_NAME, "readonly")
        .objectStore(STORE_NAME)
        .get(id);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(
          request.error ?? new Error("Local Interview could not be read."),
        );
    });
  }

  private async write(record: LocalInterviewRecord): Promise<void> {
    if (!globalThis.indexedDB) {
      memory.set(record.id, structuredClone(record));
      return;
    }
    const db = await this.database();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () =>
        reject(tx.error ?? new Error("Local Interview could not be saved."));
      tx.onabort = () =>
        reject(tx.error ?? new Error("Local Interview could not be saved."));
    });
  }

  private database(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = (event) => {
        const oldVersion = (event as IDBVersionChangeEvent).oldVersion;
        const store = request.result.objectStoreNames.contains(STORE_NAME)
          ? request.transaction?.objectStore(STORE_NAME)
          : request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
        if (!store || oldVersion >= DB_VERSION) return;
        const cursor = store.openCursor();
        cursor.onsuccess = () => {
          const current = cursor.result;
          if (!current) return;
          const value = current.value as Partial<LocalInterviewRecord>;
          if (
            (value as { storage_version?: number }).storage_version === 2 &&
            !Array.isArray(value.fixtures)
          ) {
            current.update({
              ...value,
              storage_version: STORAGE_VERSION,
              fixtures: [],
            });
          }
          current.continue();
        };
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(
          request.error ?? new Error("Local Interview storage is unavailable."),
        );
    });
  }
}

export function emptyRecord(
  id: string,
  state: InterviewState,
  stage: LocalInterviewRecord["stage"],
  transcript: TranscriptEntry[],
): LocalInterviewRecord {
  const now = Date.now();
  return {
    storage_version: STORAGE_VERSION,
    id,
    created_at: now,
    updated_at: now,
    title: state.profile.product.name.trim() || "Untitled Interview",
    stage,
    state,
    transcript,
    fixtures: [],
  };
}

export function addFixtures(
  record: LocalInterviewRecord,
  files: readonly File[],
): LocalInterviewRecord {
  const fixtures = [...record.fixtures];
  for (const file of files) {
    const next: LocalFixture = {
      name: file.name,
      type: file.type,
      size: file.size,
      blob: file,
    };
    const index = fixtures.findIndex((fixture) => fixture.name === file.name);
    if (index === -1) fixtures.push(next);
    else fixtures[index] = next;
  }
  return { ...record, fixtures };
}

export async function withProvisionalFixtures<T>(
  repository: Pick<InterviewRepository, "put">,
  prior: LocalInterviewRecord,
  files: readonly File[],
  operation: (provisional: LocalInterviewRecord) => Promise<T>,
): Promise<T> {
  if (files.length === 0) return operation(prior);

  const provisional = addFixtures(prior, files);
  await repository.put(provisional);
  try {
    return await operation(provisional);
  } catch (cause) {
    // The fixture must exist before its name crosses the API boundary. If the turn or its final
    // local write fails, restore the exact record that existed before the provisional write.
    await repository.put(prior);
    throw cause;
  }
}

export function removeUnreferencedFixtures(
  record: LocalInterviewRecord,
  names: readonly string[],
): LocalInterviewRecord {
  const references = new Set(
    record.state.profile.scenarios.flatMap((scenario) => scenario.fixtures),
  );
  const removable = new Set(names.filter((name) => !references.has(name)));
  if (removable.size === 0) return record;
  return {
    ...record,
    fixtures: record.fixtures.filter((fixture) => !removable.has(fixture.name)),
  };
}
