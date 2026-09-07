import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { ProductProfile } from "./api";
import { Transcript } from "./Conversation";
import { Profile } from "./Profile";

function profile(product: Partial<ProductProfile["product"]> = {}): ProductProfile {
  return {
    product: {
      name: "",
      users: "",
      description: "",
      detail: "",
      ...product,
    },
    tasks: [],
    personas: [],
    scenarios: [],
  };
}

function render(
  value: ProductProfile,
  state: { busy?: boolean; interviewStep?: string } = {},
): string {
  return renderToStaticMarkup(
    <Profile
      profile={value}
      interviewStep={state.interviewStep}
      busy={state.busy}
      showMetrics={false}
      onShowMetricsChange={() => undefined}
      metricByFqn={new Map()}
      metricsLoading={false}
      metricsError={false}
      interviewId="wizard-test"
    />,
  );
}

function section(markup: string, title: string, nextTitle: string): string {
  const start = markup.indexOf(`<h2 class="min-w-0 text-base font-semibold tracking-tight text-foreground">${title}</h2>`);
  const end = markup.indexOf(`<h2 class="min-w-0 text-base font-semibold tracking-tight text-foreground">${nextTitle}</h2>`);
  assert.notEqual(start, -1, `${title} heading is present`);
  assert.notEqual(end, -1, `${nextTitle} heading is present`);
  return markup.slice(start, end);
}

function occurrences(value: string, part: string): number {
  return value.split(part).length - 1;
}

test("the empty document scaffolds all four Product fields", () => {
  const markup = render(profile());
  const product = section(markup, "Product", "Behaviours");

  assert.match(product, />Name<\/h3>/);
  assert.match(product, />Description<\/h3>/);
  assert.match(product, />Users<\/h3>/);
  assert.match(product, />Details<\/h3>/);
  assert.equal(occurrences(product, "placeholder-rule"), 12);
});

test("each written Product value replaces only its own placeholder", () => {
  const markup = render(profile({ users: "policy analysts" }));
  const product = section(markup, "Product", "Behaviours");

  assert.match(product, /policy analysts/);
  assert.equal(occurrences(product, "placeholder-rule"), 9);
});

test("resumed values are complete and preserve paragraphs and line lists", () => {
  const markup = render(
    profile({
      name: "Research assistant",
      description: "Answers research questions.",
      users: "People\n- policy analysts\n- reviewers",
      detail: "Searches the library.\nReturns cited answers.",
    }),
  );
  const product = section(markup, "Product", "Behaviours");

  assert.match(product, /People\n- policy analysts\n- reviewers/);
  assert.match(product, /Searches the library\.\nReturns cited answers\./);
  assert.equal(occurrences(product, "placeholder-rule"), 0);
});

test("clarify marks only Product and leaves its document content read-only", () => {
  const markup = render(profile(), { busy: true, interviewStep: "clarify" });
  const product = section(markup, "Product", "Behaviours");

  assert.equal(occurrences(markup, "is-writing"), 1);
  assert.equal(occurrences(markup, "section-writing-marker"), 1);
  assert.doesNotMatch(product, /<(?:input|textarea|button)\b/);
});

test("the document keeps node names and descriptions in their presentation roles", () => {
  const value: ProductProfile = {
    ...profile({ name: "Research assistant", description: "Answers questions." }),
    tasks: [
      {
        id: "T-1",
        name: "Answer quality",
        description: "Answer accurately and cite useful evidence.",
        behaviours: [
          {
            id: "EB-1",
            name: "Cite sources",
            description: "Cites every factual claim.",
            measured: true,
            criteria: [
              {
                id: "AC-1-1",
                name: "Supported answer",
                description: {
                  given: "a question",
                  when: "the answer returns",
                  then: "each claim cites its source",
                },
              },
            ],
          },
        ],
      },
    ],
    personas: [
      { id: "careful-reviewer", name: "Careful reviewer", description: "Checks outputs." },
    ],
    scenarios: [
      {
        id: "S-1",
        name: "Supported question",
        description: "Ask a question the library covers.",
        behaviour_refs: ["EB-1"],
        persona_refs: ["careful-reviewer"],
        fixtures: [],
        num_trials: 1,
      },
    ],
  };
  const markup = render(value);

  assert.match(markup, /Answer quality/);
  assert.match(markup, /Answer accurately and cite useful evidence\./);
  assert.match(markup, /Cite sources/);
  assert.match(markup, /Cites every factual claim\./);
  assert.match(markup, /Supported answer/);
  assert.match(markup, /the answer returns/);
  assert.match(markup, /each claim cites its source/);
  assert.match(markup, /Careful reviewer/);
  assert.match(markup, /Checks outputs\./);
  assert.match(markup, /Supported question/);
  assert.match(markup, /Ask a question the library covers\./);
  assert.doesNotMatch(markup, />analyst<\/span>/);
});

test("the generic form renderer transports names, descriptions, and opaque targets", () => {
  const markup = renderToStaticMarkup(
    <Transcript
      requests={[
        {
          type: "form",
          prompt: "Add a Behaviour",
          state: "pending",
          fields: [
            { id: "name", label: "Name", placeholder: "", multiline: false },
            { id: "description", label: "Description", placeholder: "", multiline: true },
          ],
          target: "T-2",
          answer: {},
        },
      ]}
      busy={false}
      onRespond={() => undefined}
      fixtureActions={{ onUpload: async () => [] }}
    />,
  );

  assert.match(markup, /Add a Behaviour/);
  assert.match(markup, />Name<\/span>/);
  assert.match(markup, />Description<\/span>/);
  assert.match(markup, /<textarea/);
  assert.match(markup, /<input/);
  assert.doesNotMatch(markup, /T-2/);
});
