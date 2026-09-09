import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import type {
  ChoiceRequest,
  FormRequest,
  InterviewState,
  InterviewSuccess,
} from "../transport/api.ts";
import { api } from "../transport/api.ts";
import { downloadCompileResult } from "../download.ts";
import { InterviewRepository, emptyRecord } from "../storage/repository.ts";
import { applyEnd, applyTurn, startTranscript } from "./transcript.ts";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const baseState = (): InterviewState => ({
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
  pending: {
    type: "chat",
    prompt: "What does it do?",
    title: "Clarify",
    step: 1,
    steps: 5,
    state: "pending",
    request_id: "chat-1",
    stage: "clarify",
    multiline: true,
    answer: "",
  },
});

function success(
  state: InterviewState,
  outcome: InterviewSuccess["outcome"],
): InterviewSuccess {
  return {
    type: "success",
    state,
    stage: state.pending?.stage ?? "done",
    missing: [],
    outcome,
  };
}

test("runs an offline start, chat, choice, form, reload, end and compile flow", async () => {
  const startState = baseState();
  const choice: ChoiceRequest = {
    type: "choice",
    prompt: "Choose a goal",
    title: "Behaviours",
    step: 2,
    steps: 5,
    state: "pending",
    request_id: "choice-1",
    stage: "behaviours",
    options: [
      {
        id: { action: "continue" },
        label: "Continue",
        primary: true,
        enabled: true,
      },
    ],
    multi: false,
    cards: [],
    warnings: [],
    footer: null,
    instruction: null,
  };
  const form: FormRequest = {
    type: "form",
    prompt: "Name the behaviour",
    title: "Behaviours",
    step: 2,
    steps: 5,
    state: "pending",
    request_id: "form-1",
    stage: "behaviours",
    fields: [{ id: "name", label: "Name", placeholder: "", multiline: false }],
    target: "B-1",
    answer: {},
  };
  const finalState = { ...startState, pending: null, confirmed: true };

  globalThis.fetch = async (input, init) => {
    const path = String(input);
    if (path.endsWith("/start"))
      return new Response(
        JSON.stringify(success(startState, "awaiting_response")),
        { status: 200 },
      );
    if (path.endsWith("/turn")) {
      const body = JSON.parse(String(init?.body)) as { request_id: string };
      const next =
        body.request_id === "chat-1"
          ? { ...startState, pending: choice }
          : body.request_id === "choice-1"
            ? { ...startState, pending: form }
            : finalState;
      return new Response(
        JSON.stringify(
          success(next, next.pending ? "awaiting_response" : "done"),
        ),
        { status: 200 },
      );
    }
    if (path.endsWith("/end"))
      return new Response(JSON.stringify(success(finalState, "done")), {
        status: 200,
      });
    return new Response(
      JSON.stringify({
        "profile.yaml": "profile: {}\n",
        "experiment.yaml": "scenarios: []\n",
      }),
      { status: 200 },
    );
  };

  const repository = new InterviewRepository();
  const started = await api.start("A support assistant");
  let record = emptyRecord(
    "offline-flow",
    started.state,
    started.stage,
    startTranscript("A support assistant", started.state),
  );
  await repository.put(record);
  record = applyTurn(
    record,
    await api.respond(record.state, "chat-1", {
      type: "chat",
      text: "It answers questions",
    }),
    { type: "chat", text: "It answers questions" },
  );
  record = applyTurn(
    record,
    await api.respond(record.state, "choice-1", {
      type: "choice",
      selected: ["continue"],
    }),
    { type: "choice", selected: ["continue"] },
  );
  record = applyTurn(
    record,
    await api.respond(record.state, "form-1", {
      type: "form",
      values: { name: "Reviewer" },
    }),
    { type: "form", values: { name: "Reviewer" } },
  );
  await repository.put(record);

  const reloaded = await new InterviewRepository().read("offline-flow");
  assert.equal(reloaded?.transcript.length, 4);
  const ended = applyEnd(reloaded!, await api.end(reloaded!.state));
  await repository.put(ended);
  const compiled = await api.compile(ended.state.profile);
  assert.match(compiled["profile.yaml"], /profile/);
  assert.match(compiled["experiment.yaml"], /scenarios/);
  const downloads: string[] = [];
  downloadCompileResult(
    compiled,
    {
      createElement: () => ({
        href: "",
        download: "",
        click() {
          downloads.push(this.download);
        },
        remove() {},
      }),
    } as unknown as Document,
    { createObjectURL: () => "blob:offline", revokeObjectURL: () => {} },
  );
  assert.deepEqual(downloads, ["profile.yaml", "experiment.yaml"]);
  assert.equal(ended.state.confirmed, true);
  assert.equal(ended.transcript.at(-1)?.kind, "interaction");
});
