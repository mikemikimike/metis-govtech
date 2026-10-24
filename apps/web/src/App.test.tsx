import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
  type OpeningControl,
} from "./App";
import { AddDocuments } from "./DocumentTray";
import { FooterChip } from "./OpeningControls";
import { Composer, FixtureField, Transcript } from "./Conversation";
import { InterviewRail } from "./InterviewRail";
import {
  api,
  type CapabilityEvidence,
  type InterviewState,
  type Perspective,
} from "./transport/api";

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
  specification: {
    schema_version: 1,
    id: "test",
    runner_factory_ref:
      "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory",
    tasks: [],
    target: { name: "", users: "", description: "", detail: "" },
    features: [],
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
    description: "",
    perspective: "end_user" as const,
    onPerspective: () => undefined,
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
    openControl: null,
    onOpenControl: () => undefined,
    perspectiveSeen: false,
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

const openingConfigBody = {
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
          description: "Selects and sequences suitable tools for a feature.",
        },
      ],
    },
  ],
};

type OpeningHarness = {
  render: () => ReactElement;
  readonly control: OpeningControl | null;
  readonly perspective: Perspective;
  readonly perspectiveSeen: boolean;
  readonly evidence: CapabilityEvidenceDraft;
  readonly description: string;
  readonly begins: Array<{
    description: string;
    perspective: Perspective;
    evidence: CapabilityEvidence;
  }>;
};

// Holds the opening state the way App does, and renders OpeningScreen as a plain element tree.
function openingHarness(
  config: React.ComponentProps<typeof OpeningScreen>["config"],
  onBegin?: (
    description: string,
    perspective: Perspective,
    evidence: CapabilityEvidence,
  ) => void,
): OpeningHarness {
  let control: OpeningControl | null = null;
  let perspective: Perspective = "end_user";
  let perspectiveSeen = false;
  let description = "";
  let evidence: CapabilityEvidenceDraft = {
    known_capability_ids: [],
    confidence: null,
  };
  const begins: OpeningHarness["begins"] = [];
  return {
    render: () => {
      const route = OpeningRoute({
        configState: { status: "ready", config },
        onRetry: () => undefined,
        busy: false,
        description,
        onDescription: (value) => {
          description = value;
        },
        perspective,
        onPerspective: (next) => {
          perspective = next;
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
        openControl: control,
        onOpenControl: (next) => {
          if (next === "perspective") perspectiveSeen = true;
          control = next;
        },
        perspectiveSeen,
        onBegin: (text, selected, startEvidence) => {
          begins.push({
            description: text,
            perspective: selected,
            evidence: startEvidence,
          });
          onBegin?.(text, selected, startEvidence);
        },
      });
      return OpeningScreen(
        route.props as React.ComponentProps<typeof OpeningScreen>,
      );
    },
    get control() {
      return control;
    },
    get perspective() {
      return perspective;
    },
    get perspectiveSeen() {
      return perspectiveSeen;
    },
    get evidence() {
      return evidence;
    },
    get description() {
      return description;
    },
    begins,
  };
}

const testConfig = () =>
  openingConfigBody as React.ComponentProps<typeof OpeningScreen>["config"];

function composerOf(opening: ReactElement): TestElement {
  return findElement(opening, (element) => element.type === Composer);
}

// The footer controls are passed to the Composer, so they are found in its footer slot.
function chip(opening: ReactElement, controls: string): TestElement {
  const element = findElement(
    composerOf(opening).props.sourceControl as ReactNode,
    (item) => item.type === FooterChip && item.props.controls === controls,
  );
  return FooterChip(
    element.props as React.ComponentProps<typeof FooterChip>,
  ) as TestElement;
}

test("the opening box marks End user as the default until the user opens the Perspective control", () => {
  const opening = openingHarness(testConfig());
  const perspective = chip(opening.render(), "opening-perspective");

  assert.equal(perspective.props["aria-label"], "Perspective: End user");
  assert.match(String(perspective.props.className), /perspective-default/);

  (perspective.props.onClick as () => void)();
  assert.equal(opening.control, "perspective");
  assert.equal(opening.perspectiveSeen, true);

  const reopened = chip(opening.render(), "opening-perspective");
  assert.doesNotMatch(String(reopened.props.className), /perspective-default/);
  assert.equal(reopened.props["aria-expanded"], true);
});

test("the default marker has a one-shot animation and none with reduced motion", () => {
  // npm test runs in apps/web; the bundled test does not sit next to its source.
  const css = readFileSync("src/globals.css", "utf8");
  const rule = /\.perspective-default\s*{[^}]*animation:\s*[^;]*;/.exec(css);
  assert.ok(rule, "The default marker has an animation.");
  assert.doesNotMatch(rule[0], /infinite/);
  assert.match(
    css,
    /@media \(prefers-reduced-motion: reduce\)\s*{[^@]*\.perspective-default\s*{\s*animation:\s*none/,
  );
});

test("the Perspective panel shows each question as text and keeps radio semantics", () => {
  const opening = openingHarness(testConfig());
  (chip(opening.render(), "opening-perspective").props.onClick as () => void)();
  const pickerElement = findElement(
    opening.render(),
    (element) => element.type === PerspectivePicker,
  );
  const picker = PerspectivePicker(
    pickerElement.props as React.ComponentProps<typeof PerspectivePicker>,
  );
  const radios = findElements(
    picker,
    (element) => element.props.role === "radio",
  );
  assert.deepEqual(
    radios.map((radio) => radio.props["aria-checked"]),
    [true, false],
  );
  assert.deepEqual(
    radios.map((radio) => radio.props.tabIndex),
    [0, -1],
  );
  const security = radios[1];
  assert.ok(security);
  findElement(
    security,
    (element) =>
      element.type === "span" &&
      element.props.children === "Does it resist misuse?",
  );
  (security.props.onClick as () => void)();
  assert.equal(opening.perspective, "security");
});

test("the capability chip shows only its label, with no count", () => {
  const opening = openingHarness(testConfig());
  const label = (rendered: ReturnType<typeof opening.render>) => {
    const spans = findElements(
      chip(rendered, "opening-capabilities"),
      (element) => element.type === "span",
    );
    assert.equal(spans.length, 1);
    assert.equal(spans[0]?.props.children, "Capabilities");
  };
  label(opening.render());

  const capabilities = findElement(
    (() => {
      (
        chip(opening.render(), "opening-capabilities").props
          .onClick as () => void
      )();
      return opening.render();
    })(),
    (element) => element.type === CapabilityPicker,
  );
  (capabilities.props.onChange as (ids: string[]) => void)(["tool_use"]);
  label(opening.render());
});

test("the user can start with no capabilities and no confidence", () => {
  const opening = openingHarness(testConfig());
  (composerOf(opening.render()).props.onSend as (text: string) => void)(
    "A support assistant",
  );
  // With no confidence, the selection may be incomplete, which is what "low" tells the Interview.
  assert.deepEqual(opening.begins.at(-1)?.evidence, {
    known_capability_ids: [],
    confidence: "low",
  });
});

test("the opening controls are inside the Composer box", () => {
  const opening = openingHarness(testConfig());
  const footer = composerOf(opening.render()).props.sourceControl as ReactNode;
  const controls = findElements(
    footer,
    (element) => element.type === FooterChip || element.type === AddDocuments,
  );
  assert.deepEqual(
    controls.map((element) =>
      element.type === AddDocuments ? "documents" : element.props.controls,
    ),
    ["documents", "opening-perspective", "opening-capabilities"],
  );
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
      return new Response(JSON.stringify(openingConfigBody), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
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
  let startRequest: Promise<unknown> | undefined;
  const opening = openingHarness(
    config,
    (description, perspective, evidence) => {
      startRequest = api.start(description, evidence, perspective);
    },
  );

  (chip(opening.render(), "opening-perspective").props.onClick as () => void)();
  const picker = findElement(
    opening.render(),
    (element) => element.type === PerspectivePicker,
  );
  (picker.props.onSelect as (perspective: Perspective) => void)("security");

  (
    chip(opening.render(), "opening-capabilities").props.onClick as () => void
  )();
  const capabilities = findElement(
    opening.render(),
    (element) => element.type === CapabilityPicker,
  );
  (capabilities.props.onChange as (ids: string[]) => void)(["tool_use"]);
  const confidence = findElement(
    opening.render(),
    (element) => element.type === CapabilityConfidencePicker,
  );
  (confidence.props.onSelect as (value: "medium") => void)("medium");

  const composer = composerOf(opening.render());
  (composer.props.onSend as (text: string) => void)("A support assistant");
  await startRequest;

  assert.equal(opening.description, "A support assistant");
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
      label: "Files sent to your target",
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
