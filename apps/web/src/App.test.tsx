import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import {
  CapabilityConfidencePicker,
  CapabilityPicker,
  conversationScrollRevision,
  InitialDocumentPicker,
  OpeningConfigurationState,
  OpeningRoute,
  OpeningScreen,
  PerspectivePicker,
  type CapabilityEvidenceDraft,
} from "./App";
import { Composer, FixtureField, Transcript } from "./Conversation";
import { InterviewRail } from "./InterviewRail";
import { api, type InterviewState, type Perspective } from "./transport/api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

type TestElement = ReactElement<Record<string, unknown>>;

function findElement(
  node: ReactNode,
  predicate: (element: TestElement) => boolean,
): TestElement {
  if (isValidElement(node)) {
    const element = node as TestElement;
    if (predicate(element)) return element;
    for (const child of Children.toArray(element.props.children as ReactNode)) {
      try {
        return findElement(child, predicate);
      } catch (cause) {
        if (!(
          cause instanceof Error && cause.message === "Element not found"
        )) {
          throw cause;
        }
      }
    }
  }
  throw new Error("Element not found");
}

function findElements(
  node: ReactNode,
  predicate: (element: TestElement) => boolean,
): TestElement[] {
  if (!isValidElement(node)) return [];
  const element = node as TestElement;
  const nested = Children.toArray(element.props.children as ReactNode).flatMap(
    (child) => findElements(child, predicate),
  );
  return predicate(element) ? [element, ...nested] : nested;
}

const state = {
  profile: {
    schema_version: 1,
    product: { name: "", users: "", description: "", detail: "" },
    tasks: [],
    personas: [],
    scenarios: [],
  },
  behaviours_confirmed: false,
  confirmed: false,
  context: {
    perspective: "security",
    opening_description: "",
    capability_evidence: {
      known_capability_ids: ["tool_use"],
      confidence: "medium",
    },
  },
  history: [],
  user_typed: [],
  issued_ids: [],
  pending: null,
} as InterviewState;

test("changes the conversation scroll revision only for new content", () => {
  const current = conversationScrollRevision("interview-1", 3, false);

  assert.notEqual(current, conversationScrollRevision("interview-2", 3, false));
  assert.notEqual(current, conversationScrollRevision("interview-1", 4, false));
  assert.notEqual(current, conversationScrollRevision("interview-1", 3, true));

  assert.notEqual(
    current,
    conversationScrollRevision("interview-1", 3, false, "1"),
  );

  // An in-place request replacement keeps the presented request count and completion state.
  assert.equal(current, conversationScrollRevision("interview-1", 3, false));
});

test("blocks the opening form until configuration is ready and offers retry", () => {
  let retries = 0;
  const openingProps = {
    busy: false,
    phase: "describe" as const,
    description: "",
    perspective: "end_user" as const,
    onPerspective: () => undefined,
    onContinue: () => undefined,
    onBack: () => undefined,
    documents: [],
    documentTrayOpen: false,
    onDocumentTrayOpen: () => undefined,
    documentReads: {},
    onAddDocuments: () => undefined,
    onRemoveDocument: () => undefined,
    onKeepDocumentUnread: () => undefined,
    onManualOpen: () => undefined,
    capabilityEvidence: {
      known_capability_ids: [],
      confidence: null,
    } satisfies CapabilityEvidenceDraft,
    onCapabilityEvidence: () => undefined,
    onBegin: () => undefined,
  };

  const loadingRoute = OpeningRoute({
    ...openingProps,
    configState: { status: "loading" },
    onRetry: () => {
      retries += 1;
    },
  });
  const loading = OpeningConfigurationState(
    loadingRoute.props as React.ComponentProps<
      typeof OpeningConfigurationState
    >,
  );
  assert.equal(
    findElement(loading, (element) => element.props.role === "status").props
      .children,
    "Loading interview options…",
  );

  const errorRoute = OpeningRoute({
    ...openingProps,
    configState: { status: "error", message: "The service is unavailable." },
    onRetry: () => {
      retries += 1;
    },
  });
  const failure = OpeningConfigurationState(
    errorRoute.props as React.ComponentProps<typeof OpeningConfigurationState>,
  );
  const retry = findElement(
    failure,
    (element) =>
      element.type === "button" && element.props.children === "Try again",
  );
  (retry.props.onClick as () => void)();
  assert.equal(retries, 1);
});

test("loads opening choices and sends complete start evidence on begin", async () => {
  const calls: Array<{ path: string; body?: unknown }> = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    calls.push({
      path,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    if (path.endsWith("/config")) {
      return new Response(
        JSON.stringify({
          opening_question: "What are you building?",
          working_status: "Working…",
          perspectives: [
            {
              id: "end_user",
              label: "End user",
              question: "Does it help the person who uses it?",
            },
            {
              id: "security",
              label: "Security",
              question: "Does it resist misuse?",
            },
          ],
          capability_categories: [
            {
              id: "cognitive",
              name: "Cognitive",
              capabilities: [
                {
                  id: "tool_use",
                  name: "Tool Use",
                  description:
                    "Selects and sequences suitable tools for a task.",
                },
              ],
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (path.endsWith("/start")) {
      return new Response(
        JSON.stringify({
          type: "success",
          state,
          stage: "clarify",
          missing: [],
          outcome: "awaiting_response",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`Unexpected API path: ${path}`);
  };

  const config = await api.config();
  let selected: Perspective = "end_user";
  let phase: "describe" | "capabilities" = "describe";
  let description = "";
  let evidence: CapabilityEvidenceDraft = {
    known_capability_ids: [],
    confidence: null,
  };
  let startRequest: Promise<unknown> | undefined;
  const renderOpening = () => {
    const route = OpeningRoute({
      configState: { status: "ready", config },
      onRetry: () => undefined,
      busy: false,
      phase,
      description,
      perspective: selected,
      onPerspective: (perspective) => {
        selected = perspective;
      },
      onContinue: (nextDescription) => {
        description = nextDescription;
        phase = "capabilities";
      },
      onBack: () => {
        phase = "describe";
      },
      documents: [],
      documentTrayOpen: false,
      onDocumentTrayOpen: () => undefined,
      documentReads: {},
      onAddDocuments: () => undefined,
      onRemoveDocument: () => undefined,
      onKeepDocumentUnread: () => undefined,
      onManualOpen: () => undefined,
      capabilityEvidence: evidence,
      onCapabilityEvidence: (next) => {
        evidence = next;
      },
      onBegin: (description, perspective, selectedEvidence) => {
        if (selectedEvidence === null) {
          throw new Error(
            "The interaction must select confidence before start.",
          );
        }
        startRequest = api.start(description, selectedEvidence, perspective);
      },
    });
    return OpeningScreen(
      route.props as React.ComponentProps<typeof OpeningScreen>,
    );
  };

  let opening = renderOpening();
  const pickerElement = findElement(
    opening,
    (element) => element.type === PerspectivePicker,
  );
  const picker = PerspectivePicker(
    pickerElement.props as React.ComponentProps<typeof PerspectivePicker>,
  );
  const security = findElement(
    picker,
    (element) =>
      element.type === "button" &&
      element.props["aria-label"] === "Security: Does it resist misuse?",
  );
  const hoverQuestion = findElement(
    security,
    (element) =>
      element.type === "span" &&
      element.props.children === "Does it resist misuse?",
  );

  assert.match(
    String(hoverQuestion.props.className),
    /group-hover:translate-y-0/,
  );
  (security.props.onClick as () => void)();
  assert.equal(selected, "security");

  opening = renderOpening();
  const composer = findElement(opening, (element) => element.type === Composer);
  (composer.props.onSend as (description: string) => void)(
    "A support assistant",
  );
  assert.equal(phase, "capabilities");

  opening = renderOpening();
  const editProduct = findElement(opening, (element) =>
    Children.toArray(element.props.children as ReactNode).includes(
      "Edit product",
    ),
  );
  (editProduct.props.onClick as () => void)();
  assert.equal(phase, "describe");
  opening = renderOpening();
  const restoredComposer = findElement(
    opening,
    (element) => element.type === Composer,
  );
  assert.equal(restoredComposer.props.initialText, "A support assistant");
  (restoredComposer.props.onSend as (description: string) => void)(description);

  opening = renderOpening();
  const capabilityElement = findElement(
    opening,
    (element) => element.type === CapabilityPicker,
  );
  const capabilityPicker = CapabilityPicker(
    capabilityElement.props as React.ComponentProps<typeof CapabilityPicker>,
  );
  const toolUse = findElement(
    capabilityPicker,
    (element) =>
      element.type === "button" &&
      element.props["aria-label"] ===
        "Tool Use: Selects and sequences suitable tools for a task.",
  );
  assert.equal(toolUse.props.role, "checkbox");
  assert.equal(toolUse.props["aria-checked"], false);
  (toolUse.props.onClick as () => void)();
  assert.deepEqual(evidence.known_capability_ids, ["tool_use"]);

  opening = renderOpening();
  const confidenceElement = findElement(
    opening,
    (element) => element.type === CapabilityConfidencePicker,
  );
  const confidencePicker = CapabilityConfidencePicker(
    confidenceElement.props as React.ComponentProps<
      typeof CapabilityConfidencePicker
    >,
  );
  const medium = findElement(
    confidencePicker,
    (element) =>
      element.type === "button" &&
      Children.toArray(element.props.children as ReactNode).includes("Medium"),
  );
  (medium.props.onClick as () => void)();
  assert.equal(evidence.confidence, "medium");

  opening = renderOpening();
  const start = findElement(
    opening,
    (element) => element.props.children === "Start interview",
  );
  assert.equal(start.props.disabled, false);
  (start.props.onClick as () => void)();
  await startRequest;

  assert.deepEqual(calls, [
    { path: "/api/v1/wizard/config", body: undefined },
    {
      path: "/api/v1/wizard/interview/start",
      body: {
        description: "A support assistant",
        perspective: "security",
        known_capability_ids: ["tool_use"],
        capability_confidence: "medium",
        documents: [],
      },
    },
  ]);
});

test("opening documents show unread status and let users keep a file unread", () => {
  const config = {
    opening_question: "What are you building?",
    working_status: "Working…",
    perspectives: [],
    capability_categories: [],
    document_limits: {
      max_documents: 20,
      max_initial_bytes: 100_000_000,
      max_extraction_file_bytes: 10_000_000,
      max_extraction_request_bytes: 20_000_000,
      max_text_characters_per_document: 40_000,
      max_text_characters_total: 80_000,
      max_docx_expanded_bytes: 50_000_000,
      max_docx_archive_entries: 2_000,
      max_pdf_expanded_bytes: 50_000_000,
      fixture_extensions: ["txt", "pdf"],
      extraction_extensions: ["txt", "md", "pdf", "docx"],
    },
  } satisfies React.ComponentProps<typeof InitialDocumentPicker>["config"];
  const file = new File(["evidence"], "policy.txt", { type: "text/plain" });
  let keptName: string | undefined;
  const picker = InitialDocumentPicker({
    config,
    documents: [file],
    documentReads: {
      "policy.txt": {
        status: "failed",
        message: "The file could not be read.",
      },
    },
    disabled: false,
    onAdd: () => undefined,
    onRemove: () => undefined,
    onKeepWithoutReading: (name) => {
      keptName = name;
    },
  });
  const keepButton = findElement(
    picker,
    (element) => element.props.children === "Keep without reading",
  );

  assert.match(JSON.stringify(picker), /Could not read/);
  (keepButton.props.onClick as () => void)();
  assert.equal(keptName, "policy.txt");
});

test("Scenario review exposes early fixture suggestions for user selection", () => {
  let submitted: { names: string[]; removed: readonly string[] } | undefined;
  const field = FixtureField({
    component: {
      type: "upload",
      id: { action: "files", target: "S-1" },
      label: "Files sent to your system",
      value: ["policy.pdf"],
      available: ["policy.pdf", "terms.pdf"],
    },
    disabled: false,
    onChange: (names, _files, removed) => {
      submitted = { names, removed };
    },
  });
  const boxes = findElements(
    field,
    (element) => element.type === "input" && element.props.type === "checkbox",
  );

  assert.deepEqual(
    boxes.map((box) => box.props.checked),
    [true, false],
  );
  (
    boxes[1]?.props.onChange as (event: {
      currentTarget: { checked: boolean };
    }) => void
  )({ currentTarget: { checked: true } });
  assert.deepEqual(submitted, {
    names: ["policy.pdf", "terms.pdf"],
    removed: [],
  });
});

test("History stays usable while the sending Interview is protected from deletion", () => {
  let opened = "";
  const rail = InterviewRail({
    interviews: [
      { id: "a", title: "A", updated: Date.now() },
      { id: "b", title: "B", updated: Date.now() },
    ],
    problems: [],
    currentId: "a",
    activeIds: new Set(["a"]),
    onOpen: (id) => {
      opened = id;
    },
    onNew: () => {},
    onDelete: () => {},
  });
  assert.equal(
    findElement(rail, (element) => element.props["aria-label"] === "Delete A")
      .props.disabled,
    true,
  );
  assert.equal(
    findElement(rail, (element) => element.props["aria-label"] === "Delete B")
      .props.disabled,
    false,
  );
  const buttons = findElements(
    rail,
    (element) =>
      element.type === "button" &&
      !!element.props.onClick &&
      !element.props["aria-label"],
  );
  (buttons[1]!.props.onClick as () => void)();
  assert.equal(opened, "b");
});

test("failed reply feedback routes retry through its Interview", () => {
  let retries = 0;
  const request = {
    type: "chat" as const,
    prompt: "Question",
    request_id: "req",
    stage: "clarify" as const,
    state: "resolved" as const,
    multiline: true,
    answer: "Reply",
  };
  const transcript = Transcript({
    requests: [request],
    entries: [
      {
        kind: "interaction",
        request_id: "req",
        request,
        status: "failed",
        response: { type: "chat", text: "Reply" },
        outbound: { files: [], removedFixtures: [], attempt: 1 },
        failure: {
          message: "Service unavailable",
          retryable: true,
          kind: "request",
        },
      },
    ],
    busy: false,
    onRespond: () => {},
    onRetry: () => {
      retries++;
    },
  });
  const retry = findElement(
    transcript,
    (element) => element.props.children === "Retry",
  );
  (retry.props.onClick as () => void)();
  assert.equal(retries, 1);
});
