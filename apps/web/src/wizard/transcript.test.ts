import assert from "node:assert/strict";
import test from "node:test";
import type {
  ChoiceRequest,
  InterviewState,
  InterviewSuccess,
} from "../transport/api.ts";
import { emptyRecord } from "../storage/repository.ts";
import {
  applyEnd,
  applyTurn,
  startTranscript,
  toPresentation,
} from "./transcript.ts";

const pending = {
  type: "chat" as const,
  prompt: "What does it do?",
  title: "Clarify",
  step: 1,
  steps: 5,
  state: "pending" as const,
  request_id: "req-1",
  stage: "clarify" as const,
  multiline: true,
  answer: "",
};
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
  pending,
};
const success = (next: InterviewState): InterviewSuccess => ({
  type: "success",
  state: next,
  stage: next.pending?.stage ?? "done",
  missing: [],
  outcome: next.pending ? "awaiting_response" : "done",
});

test("transcript projects start and one answered turn without changing API state", () => {
  const record = emptyRecord(
    "transcript-test",
    state,
    "clarify",
    startTranscript("A product", state),
  );
  const nextState = {
    ...state,
    pending: { ...pending, request_id: "req-2", prompt: "Who uses it?" },
  };
  const next = applyTurn(record, success(nextState), {
    type: "chat",
    text: "A product",
  });
  assert.equal(
    next.transcript.filter((entry) => entry.kind === "interaction").length,
    2,
  );
  const answered = next.transcript.find(
    (entry) => entry.kind === "interaction" && entry.request_id === "req-1",
  );
  assert.equal(
    answered?.kind === "interaction" ? answered.status : undefined,
    "answered",
  );
  assert.equal(toPresentation(next).requests.length, 3);
  assert.equal(record.state.pending?.request_id, "req-1");
});

test("choice toggles update the current transcript screen in place", () => {
  const behaviourScreen = (
    requestId: string,
    selected: boolean,
  ): ChoiceRequest => ({
    type: "choice",
    prompt: "Choose behaviours",
    title: "Behaviours",
    step: 2,
    steps: 5,
    state: "pending",
    request_id: requestId,
    stage: "behaviours",
    options: [],
    multi: true,
    cards: [
      {
        kind: "standard",
        id: "EB-1",
        title: "Cite sources",
        selected,
        components: [],
        options: [
          {
            id: { action: "tick", target: "EB-1" },
            label: "Measure this",
            patch: {
              op: "set",
              path: "features[F-1].behaviours[EB-1].measured",
              value: !selected,
              origin: "wizard",
            },
            selected,
            primary: false,
            enabled: true,
          },
        ],
        blocking: false,
      },
    ],
    warnings: [],
    footer: null,
    instruction: null,
  });
  const first = behaviourScreen("choice-1", true);
  const second = behaviourScreen("choice-2", false);
  const initialState = { ...state, pending: first };
  const record = emptyRecord("toggle-test", initialState, "behaviours", [
    {
      kind: "interaction",
      request_id: first.request_id,
      request: first,
      status: "pending",
    },
  ]);

  const next = applyTurn(
    record,
    success({ ...initialState, pending: second }),
    { type: "choice", selected: ["tick:EB-1"] },
  );

  assert.equal(next.transcript.length, 1);
  const current = next.transcript[0];
  assert.equal(
    current?.kind === "interaction" ? current.request_id : undefined,
    "choice-2",
  );
  assert.equal(
    current?.kind === "interaction" ? current.status : undefined,
    "pending",
  );
  assert.equal(
    current?.kind === "interaction" && current.request.type === "choice"
      ? current.request.cards[0]?.selected
      : undefined,
    false,
  );
});

test("failed end leaves the pending display entry available", () => {
  const record = emptyRecord(
    "end-test",
    state,
    "clarify",
    startTranscript("A product", state),
  );
  const failed = {
    type: "failure" as const,
    code: "completion_failed" as const,
    message: "Try again",
    retryable: true,
    state,
    missing: [],
  };
  assert.equal(applyEnd(record, failed), record);
});

test("choice and form receipts keep the offered fields and selections", () => {
  const choiceRequest = {
    type: "choice" as const,
    prompt: "Choose a goal",
    title: "Behaviours",
    step: 2,
    steps: 5,
    state: "pending" as const,
    request_id: "choice-1",
    stage: "behaviours" as const,
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
  const formRequest = {
    type: "form" as const,
    prompt: "Name the behaviour",
    title: "Behaviours",
    step: 2,
    steps: 5,
    state: "pending" as const,
    request_id: "form-1",
    stage: "behaviours" as const,
    fields: [{ id: "name", label: "Name", placeholder: "", multiline: false }],
    target: "B-1",
    answer: {},
  };
  const record = emptyRecord(
    "receipt-test",
    { ...state, pending: choiceRequest },
    "behaviours",
    [
      { kind: "initial_description", id: "initial", description: "A product" },
      {
        kind: "interaction",
        request_id: "choice-1",
        request: choiceRequest,
        status: "pending",
      },
    ],
  );
  const afterChoice = applyTurn(
    record,
    success({ ...state, pending: formRequest }),
    { type: "choice", selected: ["continue"] },
  );
  const answeredChoice = afterChoice.transcript[1];
  assert.equal(
    answeredChoice?.kind === "interaction" ? answeredChoice.status : undefined,
    "answered",
  );
  assert.deepEqual(
    answeredChoice?.kind === "interaction"
      ? answeredChoice.response
      : undefined,
    { type: "choice", selected: ["continue"] },
  );

  const formRecord = {
    ...afterChoice,
    state: { ...afterChoice.state, pending: formRequest },
    transcript: [
      ...afterChoice.transcript,
      {
        kind: "interaction" as const,
        request_id: "form-1",
        request: formRequest,
        status: "pending" as const,
      },
    ],
  };
  const afterForm = applyTurn(
    formRecord,
    success({ ...state, pending: null, confirmed: true }),
    { type: "form", values: { name: "Reviewer" } },
  );
  const answeredForm = afterForm.transcript.find(
    (entry) => entry.kind === "interaction" && entry.request_id === "form-1",
  );
  assert.deepEqual(
    answeredForm?.kind === "interaction" ? answeredForm.response : undefined,
    { type: "form", values: { name: "Reviewer" } },
  );
});

test("replaying a response does not duplicate a request ID", () => {
  const record = emptyRecord(
    "duplicate-test",
    state,
    "clarify",
    startTranscript("A product", state),
  );
  const nextState = { ...state, pending: { ...pending, request_id: "req-2" } };
  const response = { type: "chat" as const, text: "A product" };
  const once = applyTurn(record, success(nextState), response);
  const twice = applyTurn(once, success(nextState), response);
  assert.deepEqual(twice.transcript, once.transcript);
});
