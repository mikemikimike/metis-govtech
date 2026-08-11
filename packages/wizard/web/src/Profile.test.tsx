import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { ProductProfile } from "./api";
import { Profile } from "./Profile";

function profile(product: Partial<ProductProfile["product"]> = {}): ProductProfile {
  return {
    product: {
      name: "",
      users: "",
      summary: "",
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
  state: { busy?: boolean; sessionStep?: string } = {},
): string {
  return renderToStaticMarkup(
    <Profile
      profile={value}
      sessionStep={state.sessionStep}
      busy={state.busy}
      showMetrics={false}
      onShowMetricsChange={() => undefined}
      metricByFqn={new Map()}
      metricsLoading={false}
      metricsError={false}
      sessionId="wizard-test"
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

test("the empty document scaffolds all three Product fields", () => {
  const markup = render(profile());
  const product = section(markup, "Product", "Behaviours");

  assert.match(product, />Name<\/h3>/);
  assert.match(product, />Users<\/h3>/);
  assert.match(product, />Details<\/h3>/);
  assert.equal(occurrences(product, "placeholder-rule"), 9);
});

test("each written Product value replaces only its own placeholder", () => {
  const markup = render(profile({ users: "policy analysts" }));
  const product = section(markup, "Product", "Behaviours");

  assert.match(product, /policy analysts/);
  assert.equal(occurrences(product, "placeholder-rule"), 6);
});

test("resumed values are complete and preserve paragraphs and line lists", () => {
  const markup = render(
    profile({
      name: "Research assistant",
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
  const markup = render(profile(), { busy: true, sessionStep: "clarify" });
  const product = section(markup, "Product", "Behaviours");

  assert.equal(occurrences(markup, "is-writing"), 1);
  assert.equal(occurrences(markup, "section-writing-marker"), 1);
  assert.doesNotMatch(product, /<(?:input|textarea|button)\b/);
});
