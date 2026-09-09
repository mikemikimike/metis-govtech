import assert from "node:assert/strict";
import test from "node:test";
import { transitionFrames, wordFrames } from "./reveal.ts";

test("keeps unchanged text still", () => {
  assert.deepEqual(
    transitionFrames({
      displayed: "Already written",
      previous: "Already written",
      next: "Already written",
      reducedMotion: false,
    }),
    [],
  );
});

test("reveals a first value by word while preserving its exact whitespace", () => {
  const value = "First line\nsecond  line";
  assert.deepEqual(wordFrames(value), [
    "First ",
    "First line\n",
    "First line\nsecond  ",
    value,
  ]);
  assert.deepEqual(
    transitionFrames({
      displayed: "",
      previous: "",
      next: value,
      reducedMotion: false,
    }),
    ["First ", "First line\n", "First line\nsecond  ", value],
  );
});

test("animates only a replaced word", () => {
  assert.deepEqual(
    transitionFrames({
      displayed: "Orca coordinates five specialists",
      previous: "Orca coordinates five specialists",
      next: "Orca coordinates four specialists",
      reducedMotion: false,
    }),
    ["Orca coordinates specialists", "Orca coordinates four specialists"],
  );
});

test("animates an insertion without restarting the field", () => {
  const frames = transitionFrames({
    displayed: "Orca coordinates specialists",
    previous: "Orca coordinates specialists",
    next: "Orca coordinates five specialists",
    reducedMotion: false,
  });
  assert.deepEqual(frames, ["Orca coordinates five specialists"]);
  assert(
    frames.every(
      (frame) => frame.includes("Orca") && frame.includes("specialists"),
    ),
  );
});

test("animates a deletion without restarting the field", () => {
  const frames = transitionFrames({
    displayed: "Orca coordinates five specialists",
    previous: "Orca coordinates five specialists",
    next: "Orca coordinates specialists",
    reducedMotion: false,
  });
  assert.deepEqual(frames, ["Orca coordinates specialists"]);
  assert(
    frames.every(
      (frame) => frame.includes("Orca") && frame.includes("specialists"),
    ),
  );
});

test("keeps matching words between separated changes visible", () => {
  const frames = transitionFrames({
    displayed: "Orca coordinates five specialists today",
    previous: "Orca coordinates five specialists today",
    next: "Orca routes four specialists securely",
    reducedMotion: false,
  });
  assert(
    frames.some(
      (frame) => frame.includes("Orca") && frame.includes("specialists"),
    ),
  );
  assert(
    frames.every(
      (frame) => frame.includes("Orca") && frame.includes("specialists"),
    ),
  );
  assert.equal(frames.at(-1), "Orca routes four specialists securely");
});

test("treats punctuation and capitalisation as part of a changed word", () => {
  const frames = transitionFrames({
    displayed: "Orca helps officers.",
    previous: "Orca helps officers.",
    next: "Orca helps Officers!",
    reducedMotion: false,
  });
  assert(frames.some((frame) => frame === "Orca helps"));
  assert.equal(frames.at(-1), "Orca helps Officers!");
});

test("restores exact whitespace and line breaks after a correction", () => {
  const next = "Orca supports officers!\nToday";
  const frames = transitionFrames({
    displayed: "Orca helps officers.\nToday",
    previous: "Orca helps officers.\nToday",
    next,
    reducedMotion: false,
  });
  assert.equal(frames.at(-1), next);
});

test("shows the complete value immediately for reduced motion", () => {
  assert.deepEqual(
    transitionFrames({
      displayed: "Old text",
      previous: "Old text",
      next: "Complete new text",
      reducedMotion: true,
    }),
    ["Complete new text"],
  );
});

test("a newer value supersedes the visible frame of an in-flight reveal", () => {
  assert.deepEqual(
    transitionFrames({
      displayed: "Partly ",
      previous: "Partly revealed old value",
      next: "Newest value",
      reducedMotion: false,
    }),
    ["", "Newest", "Newest value"],
  );
});
