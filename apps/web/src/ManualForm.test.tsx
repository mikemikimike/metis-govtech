import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { focusManualInput, itemHeading, ManualForm } from "./ManualForm";
import {
  emptyManualTestCase,
  emptyManualExperiment,
  emptyManualScenario,
} from "./manual";

test("the new manual form presents its Experiment sections in order", () => {
  const markup = renderToStaticMarkup(<ManualForm onBack={() => undefined} />);
  assert.match(markup, /Return to the opening screen/);
  assert.match(markup, /aria-label="Experiment ID"/);
  assert.doesNotMatch(markup, />New Persona<\/h4>/);
  assert.doesNotMatch(markup, />New Scenario<\/h4>/);
  assert.match(markup, />Add Persona<\/button>/);
  assert.match(markup, />Add Scenario<\/button>/);
  assert.match(markup, /No Personas yet/);
  assert.match(markup, />Add test case<\/button>/);
  assert.match(markup, />ID<\/span>/);
  assert.match(markup, />Description<\/span>/);
  assert.match(markup, /Download specification/);
  assert.doesNotMatch(markup, /Still needs/);
  assert.doesNotMatch(markup, />Feature</);
  assert.doesNotMatch(markup, />Behaviour</);
  assert.doesNotMatch(markup, />Criterion</);

  const experiment = markup.indexOf('id="manual-experiment"');
  const details = markup.indexOf('id="manual-experiment-details"');
  const personas = markup.indexOf('id="manual-personas"');
  const scenarios = markup.indexOf('id="manual-scenarios"');
  assert.ok(experiment < details);
  assert.ok(details < personas);
  assert.ok(personas < scenarios);
  assert.ok(scenarios < markup.indexOf('id="manual-tasks"'));
});

test("new definitions and test cases start with explicit empty selections", () => {
  const experiment = emptyManualExperiment();
  assert.deepEqual(experiment.personas, []);
  assert.deepEqual(experiment.scenarios, []);
  assert.deepEqual(experiment.tasks, []);
  assert.deepEqual(emptyManualScenario(), { id: "", description: "" });
  assert.equal(emptyManualTestCase().persona_ref, "");
  assert.equal(emptyManualTestCase().scenario_ref, "");
});

test("manual item headings describe blank and entered IDs", () => {
  assert.equal(itemHeading("Persona", ""), "New Persona");
  assert.equal(
    itemHeading("Scenario", " supported-answer "),
    "supported-answer",
  );
});

test("manual item addition can focus the new ID control", () => {
  const focused: string[] = [];
  const persona = { focus: () => focused.push("persona") };
  const scenario = { focus: () => focused.push("scenario") };
  const task = { focus: () => focused.push("task") };
  assert.equal(
    focusManualInput({ kind: "task", index: 0 }, [], [], [task]),
    true,
  );

  assert.equal(
    focusManualInput({ kind: "persona", index: 0 }, [persona], []),
    true,
  );
  assert.equal(
    focusManualInput({ kind: "scenario", index: 0 }, [], [scenario]),
    true,
  );
  assert.equal(
    focusManualInput({ kind: "persona", index: 1 }, [persona], []),
    false,
  );
  assert.deepEqual(focused, ["task", "persona", "scenario"]);
});
