import type {
  InterviewResult,
  InterviewState,
  LocalInterviewRecord,
  PresentationView,
  TranscriptEntry,
  UserResponse,
  WizardRequest,
} from "../transport/api.ts";
import { optionKey, titleFor } from "../transport/api.ts";

function clone<T>(value: T): T {
  return structuredClone(value);
}
function localId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `local-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

export function startTranscript(
  description: string,
  state: InterviewState,
): TranscriptEntry[] {
  const pending = state.pending;
  return [
    { kind: "initial_description", id: localId(), description },
    ...(pending
      ? [
          {
            kind: "interaction" as const,
            request_id: pending.request_id ?? "",
            request: clone(pending),
            status: "pending" as const,
          },
        ]
      : []),
  ];
}

function resolvedRequest(
  request: WizardRequest,
  response: UserResponse,
): WizardRequest {
  const next = clone(request);
  next.state = "resolved";
  if (next.type === "chat" && response.type === "chat")
    next.answer = response.text;
  if (next.type === "form" && response.type === "form")
    next.answer = response.values ?? {};
  if (next.type === "choice" && response.type === "choice") {
    const selected = new Set(response.selected ?? []);
    const mark = (option: {
      id: Parameters<typeof optionKey>[0];
      selected?: boolean | null;
    }) => {
      option.selected = selected.has(optionKey(option.id));
    };
    next.options.forEach(mark);
    next.warnings.forEach((warning) => warning.options.forEach(mark));
    next.cards.forEach((card) => {
      card.options.forEach(mark);
      card.components.forEach((component) => {
        if (component.type === "options") component.options.forEach(mark);
      });
    });
  }
  return next;
}

export function applyTurn(
  record: LocalInterviewRecord,
  result: InterviewResult,
  response: UserResponse,
): LocalInterviewRecord {
  if (result.type === "failure" || !result.state) return record;
  const nextState = result.state;
  const transcript = clone(record.transcript);
  const pending = transcript.find(
    (entry) =>
      entry.kind === "interaction" &&
      entry.status === "pending" &&
      entry.request_id === record.state.pending?.request_id,
  );
  const responseAdvancesRequest =
    nextState.pending?.request_id !== record.state.pending?.request_id;
  if (pending && pending.kind === "interaction" && responseAdvancesRequest) {
    pending.request = resolvedRequest(pending.request, response);
    pending.response = response;
    pending.status = "answered";
  }
  if (
    nextState.pending &&
    !transcript.some(
      (entry) =>
        entry.kind === "interaction" &&
        entry.request_id === nextState.pending?.request_id,
    )
  )
    transcript.push({
      kind: "interaction" as const,
      request_id: nextState.pending.request_id ?? "",
      request: clone(nextState.pending),
      status: "pending",
    });
  return {
    ...record,
    updated_at: Date.now(),
    title: titleFor(nextState.profile),
    stage: result.stage,
    state: nextState,
    transcript,
  };
}

export function applyEnd(
  record: LocalInterviewRecord,
  result: InterviewResult,
): LocalInterviewRecord {
  if (result.type === "failure" || !result.state) return record;
  const transcript = clone(record.transcript);
  const pending = transcript.find(
    (entry) => entry.kind === "interaction" && entry.status === "pending",
  );
  if (pending && pending.kind === "interaction")
    pending.status = "ended_unanswered";
  return {
    ...record,
    updated_at: Date.now(),
    title: titleFor(result.state.profile),
    stage: result.stage,
    state: result.state,
    transcript,
  };
}

export function toPresentation(record: LocalInterviewRecord): PresentationView {
  const requests: WizardRequest[] = record.transcript.map((entry) => {
    if (entry.kind === "interaction") return entry.request;
    return {
      type: "chat",
      prompt: "",
      title: null,
      step: null,
      steps: null,
      state: "resolved",
      request_id: entry.id,
      stage: "clarify",
      multiline: true,
      answer: entry.description,
    };
  });
  return {
    id: record.id,
    stage: record.stage,
    done: record.state.pending === null && record.state.confirmed,
    requests,
    profile: record.state.profile,
  };
}
