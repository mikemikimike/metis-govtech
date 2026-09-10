import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
import { OpeningScreen, PerspectivePicker } from "./App";
import { Composer } from "./Conversation";
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
  context: { perspective: "security" },
  history: [],
  user_typed: [],
  issued_ids: [],
  pending: null,
} as InterviewState;

test("loads perspective choices and sends the selected perspective on begin", async () => {
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
  let startRequest: Promise<unknown> | undefined;
  const renderOpening = () =>
    OpeningScreen({
      config,
      busy: false,
      perspective: selected,
      onPerspective: (perspective) => {
        selected = perspective;
      },
      onBegin: (description, perspective) => {
        startRequest = api.start(description, perspective);
      },
    });

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
  await startRequest;

  assert.deepEqual(calls, [
    { path: "/api/v1/wizard/config", body: undefined },
    {
      path: "/api/v1/wizard/interview/start",
      body: {
        description: "A support assistant",
        perspective: "security",
      },
    },
  ]);
});
