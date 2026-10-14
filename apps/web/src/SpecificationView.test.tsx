import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { Specification } from "./transport/api";
import { Composer, Transcript } from "./Conversation";
import { Done } from "./Done";
import { SpecificationView } from "./SpecificationView";

function specification(
  target: Partial<Specification["target"]> = {},
): Specification {
  return {
    schema_version: 2,
    id: "test",
    runner_factory_ref:
      "metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory",
    tasks: [],
    target: {
      name: "",
      users: "",
      description: "",
      detail: "",
      ...target,
    },
    features: [],
    personas: [],
    scenarios: [],
  };
}

function render(
  value: Specification,
  state: { busy?: boolean; interviewStep?: string } = {},
): string {
  return renderToStaticMarkup(
    <SpecificationView
      specification={value}
      interviewStep={state.interviewStep}
      busy={state.busy}
      showGraders={false}
      onShowGradersChange={() => undefined}
      graderByFqn={new Map()}
      gradersLoading={false}
      gradersError={false}
    />,
  );
}

function section(markup: string, title: string, nextTitle: string): string {
  const start = markup.indexOf(
    `<h2 class="min-w-0 text-base font-semibold tracking-tight text-foreground">${title}</h2>`,
  );
  const end = markup.indexOf(
    `<h2 class="min-w-0 text-base font-semibold tracking-tight text-foreground">${nextTitle}</h2>`,
  );
  assert.notEqual(start, -1, `${title} heading is present`);
  assert.notEqual(end, -1, `${nextTitle} heading is present`);
  return markup.slice(start, end);
}

function occurrences(value: string, part: string): number {
  return value.split(part).length - 1;
}

test("the empty document scaffolds all four Target fields", () => {
  const markup = render(specification());
  const target = section(markup, "Target", "Behaviours");

  assert.match(target, />Name<\/h3>/);
  assert.match(target, />Description<\/h3>/);
  assert.match(target, />Users<\/h3>/);
  assert.match(target, />Details<\/h3>/);
  assert.equal(occurrences(target, "placeholder-rule"), 12);
});

test("each written Target value replaces only its own placeholder", () => {
  const markup = render(specification({ users: "policy analysts" }));
  const target = section(markup, "Target", "Behaviours");

  assert.match(target, /policy analysts/);
  assert.equal(occurrences(target, "placeholder-rule"), 9);
});

test("resumed values are complete and preserve paragraphs and line lists", () => {
  const markup = render(
    specification({
      name: "Research assistant",
      description: "Answers research questions.",
      users: "People\n- policy analysts\n- reviewers",
      detail: "Searches the library.\nReturns cited answers.",
    }),
  );
  const target = section(markup, "Target", "Behaviours");

  assert.match(target, /People\n- policy analysts\n- reviewers/);
  assert.match(target, /Searches the library\.\nReturns cited answers\./);
  assert.equal(occurrences(target, "placeholder-rule"), 0);
});

test("clarify marks only Target and leaves its document content read-only", () => {
  const markup = render(specification(), {
    busy: true,
    interviewStep: "clarify",
  });
  const target = section(markup, "Target", "Behaviours");

  assert.equal(occurrences(markup, "is-writing"), 1);
  assert.equal(occurrences(markup, "section-writing-marker"), 1);
  assert.doesNotMatch(target, /<(?:input|textarea|button)\b/);
});

test("the document keeps node names and descriptions in their presentation roles", () => {
  const value: Specification = {
    ...specification({
      name: "Research assistant",
      description: "Answers questions.",
    }),
    features: [
      {
        id: "F-1",
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
                grader_fqn: "metis.graders.answer_quality",
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
      {
        id: "careful-reviewer",
        name: "Careful reviewer",
        description: "Checks outputs.",
      },
    ],
    tasks: [
      {
        id: "TC-001",

        scenario_ref: "S-1",
        persona_ref: "careful-reviewer",
        fixtures: [],
        num_trials: 3,
        max_turns: 20,
        timeout_minutes: 15,
        response_wait_ms: 300000,
        max_run_retries: null,
        behaviour_refs: ["EB-1"],
      },
    ],
    scenarios: [
      {
        id: "S-1",
        name: "Supported question",
        description: "Ask a question the library covers.",
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

test("hides grader identifiers and shows only the human summary when enabled", () => {
  const value = specification();
  value.features = [
    {
      id: "F-1",
      name: "Answer quality",
      description: "Answer accurately.",
      behaviours: [
        {
          id: "EB-1",
          name: "Cite sources",
          description: "Cites claims.",
          measured: true,
          criteria: [
            {
              id: "AC-1-1",
              name: "Supported answer",
              grader_fqn: "metis.graders.answer_quality",
              description: {
                given: "a question",
                when: "it answers",
                then: "claims cite sources",
              },
            },
          ],
        },
      ],
    },
  ];
  const hidden = render(value);
  assert.doesNotMatch(hidden, /Answer quality grader/);
  const visible = renderToStaticMarkup(
    <SpecificationView
      specification={value}
      showGraders
      onShowGradersChange={() => undefined}
      graderByFqn={
        new Map([
          [
            "metis.graders.answer_quality",
            {
              fqn: "metis.graders.answer_quality",
              name: "Answer quality grader",
              description: "Checks supported answers.",
            },
          ],
        ])
      }
      gradersLoading={false}
      gradersError={false}
    />,
  );
  assert.match(visible, /Answer quality grader/);
  assert.doesNotMatch(visible, /metis\.graders\.answer_quality/);
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
            {
              id: "description",
              label: "Description",
              placeholder: "",
              multiline: true,
            },
          ],
          target: "F-2",
          answer: {},
          request_id: "form-1",
          stage: "behaviours",
        },
      ]}
      busy={false}
      onRespond={() => undefined}
    />,
  );

  assert.match(markup, /Add a Behaviour/);
  assert.match(markup, />Name<\/span>/);
  assert.match(markup, />Description<\/span>/);
  assert.match(markup, /<textarea/);
  assert.match(markup, /<input/);
  assert.doesNotMatch(markup, /F-2/);
});

test("wizard upload fields render a working local file control", () => {
  const markup = renderToStaticMarkup(
    <Transcript
      requests={[
        {
          type: "choice",
          prompt: "Add scenario files",
          title: "Scenarios",
          step: 5,
          steps: 5,
          state: "pending",
          request_id: "choice-upload",
          stage: "scenarios",
          options: [],
          multi: false,
          cards: [
            {
              kind: "scenario",
              id: "S-1",
              title: "Support case",
              section: "Scenarios",
              selected: null,
              components: [
                {
                  type: "upload",
                  id: { action: "files", target: "S-1" },
                  label: "Files",
                  value: ["policy.pdf"],
                },
              ],
              options: [],
              note: null,
              blocking: false,
              trials: 1,
            },
          ],
          warnings: [],
          footer: null,
          instruction: null,
        },
      ]}
      busy={false}
      onRespond={() => undefined}
    />,
  );

  assert.match(markup, /type="file"/);
  assert.match(markup, /policy\.pdf/);
  assert.doesNotMatch(markup, /File attachments are not available/);
});

test("the docked composer fills the conversation column", () => {
  const markup = renderToStaticMarkup(
    <Composer
      request={{
        type: "chat",
        prompt: "What should change?",
        title: "Scenarios",
        step: 5,
        steps: 5,
        state: "pending",
        request_id: "chat-1",
        stage: "scenarios",
        multiline: true,
        answer: "",
      }}
      busy={false}
      onSend={() => undefined}
    />,
  );

  assert.match(markup, /class="w-full pb-6 pt-2"/);
});

test("the Specification output action follows Interview completion", () => {
  const shared = {
    specification: specification(),
    showGraders: false,
    onShowGradersChange: () => undefined,
    graderByFqn: new Map(),
    gradersLoading: false,
    gradersError: false,
    onFinish: () => undefined,
    onDownload: () => undefined,
  };
  const pending = renderToStaticMarkup(<SpecificationView {...shared} />);
  const complete = renderToStaticMarkup(<SpecificationView {...shared} done />);

  assert.match(pending, /Skip interview and download specification/);
  assert.doesNotMatch(pending, />Download specification</);
  assert.match(complete, />Download specification</);
  assert.doesNotMatch(complete, /Skip interview/);
});

test("a completed Interview reports that its specification is ready", () => {
  const markup = renderToStaticMarkup(<Done />);

  assert.match(markup, /Your specification is ready/);
  assert.doesNotMatch(markup, /Your evaluation is ready/);
});
