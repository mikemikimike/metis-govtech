// The document view. This is the component in the door that reads `ProductProfile` and knows
// its shape — tasks hold behaviours hold criteria; personas and scenarios are flat lists. The
// conversation stays shape-only so this can hold all of the interview's domain knowledge in one
// place. There is one other domain-aware component, deliberately: the hand-authoring form
// (`ManualForm.tsx`), which names the experiment schema's own fields; its header comment
// explains why that exception is allowed. Neither of those names leaks into the shape-only
// conversation renderer, which remains the rule.
//
// It is read-only where it counts: no control here changes the profile — every edit still
// originates in the conversation. The only controls are presentation: disclosures that fold a
// task open or closed, and a control to collapse the whole pane — both view state, not document
// state.
//
// The pane is scaffold first and document second. Every section it will ever hold is drawn from
// the first turn, blank ones as ruled placeholders, so the shape of what the interview produces is
// visible before any of it exists and the boundary between written and unwritten reads as the
// interview's frontier. This is also where the interview's progress is expressed — the segmented
// bar above the sheet, and the rules of the section being written — because the document and the interview are
// the same six things in the same order, and a second stepper in the conversation would be a
// second drawing of what is already on screen.
//
// It is a live mirror of the profile the package built, drawn fresh each time the payload arrives.
// It holds no persistent change history and no whole-profile diff. Each product value remembers
// only the string it last received while mounted, which is enough to mark an arrival or correction;
// once that reveal has finished, the text looks like content that arrived ten turns ago.

import { useState } from "react";
import type {
  Behaviour,
  MetricSpec,
  ProductProfile,
  Task,
  WizardRequest,
} from "./api";
import { api } from "./api";
import { PanelRight } from "lucide-react";
import { RevealText } from "./RevealText";
import { Button, Chevron, Chip, cn, countTrials, formatTrials, Mono, Tooltip } from "./ui";

// ── where the interview has got to ───────────────────────────────────────────

// The package stamps a title, a one-based position and a total onto every request it composes.
// This is the door reading them, and it is the whole of the door's knowledge of the interview's
// shape: it holds no list of steps, counts no sections, and derives no position of its own, so it
// cannot drift from the package the way a second copy of the step order would.
export interface StepPosition {
  title: string | null;
  step: number;
  steps: number;
}

// The newest request carrying step metadata. Searched from the end because the pending request is
// the one that says where the interview is now, and older requests keep their own — stale —
// positions in the scrollback. Requests carrying none yield null: the terminal step is stamped
// with nothing, and a session persisted before the metadata existed has nothing either, so both
// draw no position rather than a wrong one.
export function stepPosition(requests: WizardRequest[]): StepPosition | null {
  for (let i = requests.length - 1; i >= 0; i--) {
    const request = requests[i];
    if (request.step != null && request.steps != null) {
      return {
        title: request.title ?? null,
        step: request.step,
        steps: request.steps,
      };
    }
  }
  return null;
}

// Which section-level placeholder an in-flight model call is writing into.
//
// `statuses.yaml` is offset by one on purpose — the status for a step names the work that
// continuing *from* it starts. That offset is what lets the session's current step alone identify
// the target, with no new field on the wire and no guessing.
//
// Prioritise is deliberately absent even though continuing from it drafts criteria. Criteria land
// *inside* the Behaviours section as per-behaviour blanks, not as a section-level placeholder, and
// those blanks are suppressed for the whole of the prioritise step (see `selecting`), which is
// exactly the window a `prioritise → criteria` mark would cover. So the mark had nothing to attach
// to: it would fire only while the one placeholder it targets is hidden. The criteria the Continue
// generates land inside already-populated behaviours, so there is no empty section to shimmer for
// it, and the arrival animation still fires on each criterion as it mounts.
//
// Clarify now writes the Product section on every useful answer, so it follows the same rule as the
// later drafting steps instead of being a special case.
type WritingTarget = "product" | "behaviours" | "personas" | "scenarios";

const WRITING_TARGET: Record<string, WritingTarget> = {
  clarify: "product",
  behaviours: "behaviours",
  criteria: "personas",
  personas: "scenarios",
};

export function Profile({
  profile,
  position,
  sessionStep,
  statusText,
  busy,
  showMetrics,
  onShowMetricsChange,
  metricByFqn,
  metricsLoading,
  metricsError,
  onCollapse,
  sessionId,
  done,
}: {
  profile: ProductProfile;
  position?: StepPosition | null;
  sessionStep?: string;
  // The package-owned status line for the session's current step, from interview.yaml. It is the
  // progress caption; when absent the caption falls back to the step's own title.
  statusText?: string;
  busy?: boolean;
  showMetrics: boolean;
  onShowMetricsChange: (show: boolean) => void;
  metricByFqn: ReadonlyMap<string, MetricSpec>;
  metricsLoading: boolean;
  metricsError: boolean;
  onCollapse?: () => void;
  // The session the document belongs to, and whether the interview has reached its end. The
  // download link is built from the id; `done` is what unlocks it. Both are the shell's to know —
  // the pane maps them onto the footer the same way it maps `position` onto the segments.
  sessionId: string;
  done?: boolean;
}) {
  const { product } = profile;
  const { tasks } = profile;
  const writing = busy && sessionStep ? WRITING_TARGET[sessionStep] : undefined;
  const hasCriteria = tasks.some((task) =>
    task.behaviours.some((behaviour) => behaviour.criteria.length > 0),
  );
  const metricsAvailable = !metricsLoading && !metricsError;

  // The user is choosing which behaviours to measure for the whole of the prioritise step, and a
  // criteria blank must not appear until that choice is committed with Continue. The commit signal
  // is the *step*, not `busy`: a tick is a live server round-trip that recomposes prioritise and
  // stays on it, so keying on `busy` would flash the blank on during every tick and off again when
  // the recomposed screen arrives. Keying on the step alone, the blank is suppressed for the whole
  // prioritise step — idle or mid-tick — and appears only once Continue advances the session off
  // it. (Continue is also what generates the criteria, so by the time the session reports a later
  // step the blanks are usually already filled; one that remains is a behaviour whose criteria did
  // not draft, which is exactly what the blank should report.)
  const selecting = sessionStep === "prioritise";

  const behaviourCount = tasks.reduce(
    (total, task) => total + task.behaviours.length,
    0,
  );

  return (
    <div className="flex h-full flex-col p-4">
      {/* The strip above the sheet carries the pane's chrome — things that belong to the pane, not
          to the document. Progress sits on the left as six segments, one per interview step,
          filling left to right; the collapse control sits at the right. Both are outside the sheet
          so its corner stays free for the document header, and the segments read as a header for the
          page below rather than floating inside it. */}
      {(position || onCollapse) && (
        <div className="mb-2 flex shrink-0 items-center gap-3">
          {position && (
            <ProgressSegments
              step={position.step}
              steps={position.steps}
              title={position.title}
              statusText={statusText}
            />
          )}
          {onCollapse && (
            <button
              type="button"
              aria-label="Hide document"
              title="Hide document"
              onClick={onCollapse}
              className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <PanelRight size={16} strokeWidth={1.75} aria-hidden />
            </button>
          )}
        </div>
      )}

      {/* The document is a produced artifact, not an editable field, and it reads that way: a white
          sheet floating on the grey pane, carrying a single soft shadow. That shadow is the one
          exception the house style grants — depth is a border everywhere else — because "this is a
          finished page" is exactly what a sheet-with-shadow says and a border cannot. Nothing here
          is an input; the shadow's job is to say so. */}
      {/* The sheet, not the pane, is the scroll container. Section headings stick to the top of
          the document as you scroll past them, and sticking is measured from the scrollport's
          edge — so the sheet has to be the thing that scrolls, or the headings would pin to the
          pane and float free of the page they belong to. The sheet's own padding moves inside,
          onto the content wrapper, leaving the scrollport's edge flush with the sheet's edge for
          the headings to meet. */}
      <div className="quiet-scrollbar flex-1 overflow-y-auto overflow-x-hidden rounded-[12px] bg-card text-sm text-card-foreground shadow-sm">
        <div className="flex flex-col gap-8 px-5 pb-5">
          {/* The header carries only the pane's metric controls, pinned to the right. It draws
              nothing until there is a control to hold, so an early document opens straight onto
              Product rather than onto an empty strip. */}
          {(hasCriteria || metricsError) && (
            <header className="flex flex-wrap items-center justify-end gap-2 pt-5">
              {hasCriteria && (
                <Button
                  type="button"
                  variant="ghost"
                  active={showMetrics}
                  disabled={!metricsAvailable}
                  aria-pressed={showMetrics}
                  title={metricsError ? "Metric details unavailable" : "Show metrics"}
                  onClick={() => onShowMetricsChange(!showMetrics)}
                  className="px-2 py-1 text-xs"
                >
                  Show metrics
                </Button>
              )}
              {metricsError && (
                <span role="alert" className="text-xs text-destructive">
                  Metric details unavailable
                </span>
              )}
            </header>
          )}

          <Section title="Product" writing={writing === "product"}>
            <div className="flex flex-col gap-4">
              <ProductField label="Name" value={product.name} />
              <ProductField label="Description" value={product.description} preserveLines />
              <ProductField label="Users" value={product.users} preserveLines />
              <ProductField label="Details" value={product.detail} preserveLines />
            </div>
          </Section>

        {/* Sections run in the order the interview fills them, and every one of them is drawn
            whether or not it holds anything yet.

            Each heading is the package's own name for the step that fills it — "Behaviours",
            "Personas", "Scenarios" — so the document and the conversation use one vocabulary and the
            sheet reads as the interview's output section by section. They are entity names, all
            three of the same kind; "What should be true" was a sentence sitting between two nouns,
            which is what made it read as the odd one out. */}
        <Section
          title="Behaviours"
          count={behaviourCount}
          writing={writing === "behaviours"}
        >
          {tasks.length > 0 ? (
            // Groups are set well apart from one another, so the section reads as a handful of
            // named groups rather than one long run of behaviours. The gap is the largest inside
            // the sheet: it is the boundary the eye chunks the list on.
            <div className="flex flex-col gap-6">
              {tasks.map((task) => (
                <TaskView
                  key={task.id}
                  task={task}
                  selecting={selecting}
                  showMetrics={showMetrics}
                  metricByFqn={metricByFqn}
                />
              ))}
            </div>
          ) : (
            <Placeholder boxed />
          )}
        </Section>

        <Section
          title="Personas"
          count={profile.personas.length}
          writing={writing === "personas"}
        >
          {profile.personas.length > 0 ? (
            // Each persona leads with its name and is anchored by a marker at the left edge, so a
            // run of them is countable at a glance rather than read to be counted. The two were
            // previously the same weight — a muted id above a full-strength paragraph — which put
            // the emphasis on the description and let three personas run together into one block.
            // The name now carries the foreground and the description recedes behind it. The
            // description stays whole: a persona is judged on what it says, not on its name.
            <ul className="flex flex-col gap-4">
              {profile.personas.map((p) => (
                <li key={p.id} className="animate-arrive flex gap-3">
                  <span
                    aria-hidden
                    className="mt-[0.4rem] h-1.5 w-1.5 shrink-0 rounded-full bg-border"
                  />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <Mono className="text-foreground">{p.name}</Mono>
                    <span className="text-muted-foreground">{p.description}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Placeholder boxed />
          )}
        </Section>

        <Section
          title="Scenarios"
          count={profile.scenarios.length}
          writing={writing === "scenarios"}
        >
          {profile.scenarios.length > 0 ? (
            <div className="flex flex-col gap-3">
              <ul className="flex flex-col gap-4">
                {profile.scenarios.map((s) => (
                  <li key={s.id} className="animate-arrive flex flex-col gap-2">
                    {/* No visible id. A behaviour's id is referenced — a scenario says which
                        behaviours it covers — but nothing in the pane ever points at a scenario,
                        so drawing `S-1` beside each one spent a column on a handle no reader
                        needs. It is still stamped on the compiled experiment, where it is what
                        results are traced back through. */}
                    <h3 className="font-medium text-foreground">{s.name}</h3>
                    <p className="text-foreground">{s.description}</p>
                    {/* A scenario's metadata answers three separate questions — what it checks,
                        who runs it, and how much of it there is — so each is a labelled row, with
                        the labels lined up in a fixed left column and the values reading down a
                        single column beside them. The three-column grid that stood here spread the
                        same three answers across the full pane width, which left each value marooned
                        under a header far from the others; stacked as rows they stay close to the
                        description they belong to and the labels form one edge to read down.

                        The label column is `auto`, so it sizes to the longest label and the values
                        share one left edge regardless of pane width — no fixed width to re-tune when
                        a label is renamed. On a pane dragged narrow the value cell wraps under its
                        own label rather than under the description. */}
                    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-xs">
                      <ScenarioRow label="Behaviours">
                        {s.behaviour_refs.length > 0 ? (
                          s.behaviour_refs.map((ref) => <Chip key={ref}>{ref}</Chip>)
                        ) : (
                          <span className="text-muted-foreground">None</span>
                        )}
                      </ScenarioRow>
                      <ScenarioRow label="Personas">
                        {s.persona_refs.length > 0 ? (
                          s.persona_refs.map((ref) => <Chip key={ref}>{ref}</Chip>)
                        ) : (
                          <span className="text-muted-foreground">None</span>
                        )}
                      </ScenarioRow>
                      {/* The trial total is the whole of the count worth stating. The per-persona
                          trial count was shown alongside it and said nothing extra: the total *is*
                          that per-persona count times personas, and the personas are named in the
                          row directly above, so "3 per persona, 3 total" was the same fact written
                          twice.

                          The total is plain text, not a chip: a chip marks something the profile
                          refers to by name — a behaviour, a persona, a file — and a total refers to
                          nothing, so bordering it would imply it could be looked up. Files stay chips
                          for exactly that reason, and share the row with the total behind a faint dot
                          separator; they simply do not appear when there are none. */}
                      <ScenarioRow label="Experiment configuration">
                        {/* py-0.5 matches the chip's own vertical padding so the trial total and the
                            file chips sit on one line under `items-start` — without it the padding-
                            less text rode above the chip. */}
                        <span className="py-0.5 text-muted-foreground">
                          {formatTrials(countTrials(s.persona_refs.length, s.num_trials))}
                        </span>
                        {s.fixtures.length > 0 && (
                          <>
                            <span aria-hidden className="py-0.5 text-muted-foreground/40">
                              ·
                            </span>
                            {s.fixtures.map((file) => (
                              <Chip key={file}>{file}</Chip>
                            ))}
                          </>
                        )}
                      </ScenarioRow>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="flex justify-end border-t border-border pt-2 text-sm text-muted-foreground">
                Total: {formatTrials(
                  profile.scenarios.reduce(
                    (total, scenario) =>
                      total + countTrials(scenario.persona_refs.length, scenario.num_trials),
                    0,
                  ),
                )}
              </div>
            </div>
          ) : (
            <Placeholder boxed />
          )}
        </Section>
        </div>
      </div>

      <ProfileFooter sessionId={sessionId} done={done} />
    </div>
  );
}

// The pane's foot: the two things you do with a finished experiment, held below the sheet rather
// than inside it, because they act on the produced artifact — they are not part of it. Both are
// pinned to the right, the download near-black as the one action the user takes here and Run
// evaluation the disabled placeholder beside it.
//
// The download is disabled until the interview reaches its end. A half-written profile still
// compiles to a file, but it is not the file the user came for, so the control that hands it over
// stays inert — and says why on hover — until `done`. It carries the accent while it waits: an
// armed-but-not-yet action is a live state, which is what the accent marks, and it turns near-black
// the moment it becomes pressable. Run evaluation belongs to the engine, which this door is
// forbidden to import, so it ships disabled and labelled as such, exactly as it did in the chat.
function ProfileFooter({
  sessionId,
  done,
}: {
  sessionId: string;
  done?: boolean;
}) {
  return (
    <div className="mt-3 flex shrink-0 flex-wrap items-center justify-end gap-2">
      {done ? (
        <a
          href={api.experimentUrl(sessionId)}
          download
          className={cn(
            "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5",
            "border border-primary bg-primary text-sm font-medium text-primary-foreground",
            "transition-colors duration-150 hover:opacity-90 active:opacity-80",
          )}
        >
          Download experiment.yaml
        </a>
      ) : (
        <Tooltip label="Available once the interview is complete" focusable>
          <span
            aria-disabled
            className={cn(
              "inline-flex cursor-not-allowed items-center justify-center gap-2 rounded-md px-3 py-1.5",
              "border border-accent bg-accent/12 text-sm font-medium text-foreground opacity-60",
            )}
          >
            Download experiment.yaml
          </span>
        </Tooltip>
      )}

      {/* Wired to the engine later — the wizard package must not depend on it, so the control
          ships disabled rather than absent. */}
      <Button variant="secondary" disabled title="Coming soon">
        Run evaluation
      </Button>
    </div>
  );
}

// ── the scaffold ─────────────────────────────────────────────────────────────

// What an unwritten section shows: ruled lines, framed for a list, bare for prose.
//
// The frame is the part that makes the lines work for a list. On its own a run of hairlines read as
// rules under the heading and debris below it — the lines looked like structure that had broken
// rather than space waiting to be filled. Enclosed, they are unambiguously the contents of a
// reserved region, and the dotted edge carries that message rather than the lines themselves.
//
// The frame specifically means "a list will grow here": Behaviours, Personas and Scenarios all fill
// with lists of items, so all three get the identical framed placeholder. A Product field is one
// piece of prose, not a list, so it takes the same lines without the frame — framing a single line
// would promise a growing region that never arrives.
//
// Every framed section is given the same lines at the same widths. Shaping each placeholder after
// the row it would hold was tried and dropped: it made an empty page busier than a written one, and
// the document's own headings already say what each section holds. Identical blanks read as one
// consistent kind of thing — space reserved — which is all the empty state needs to say.
//
// `aria-hidden` throughout: the section heading above already carries the meaning, and a screen
// reader should not hear a description of furniture.
const PLACEHOLDER_WIDTHS = ["w-full", "w-4/5", "w-3/5"];

function Placeholder({
  writing = false,
  boxed = false,
  widths = PLACEHOLDER_WIDTHS,
}: {
  writing?: boolean;
  boxed?: boolean;
  widths?: string[];
}) {
  // The lines carry `placeholder-rule`, so they take the travelling teal crest while the model is
  // writing into this section (`is-writing`, in globals.css). The frame stays still — it is
  // structure, and animating it would make the reserved region itself look unsettled.
  const rules = (
    <div className={cn("flex flex-col gap-2", writing && "is-writing")}>
      {widths.map((width, i) => (
        <span
          key={i}
          className={cn("placeholder-rule block h-px bg-border", width)}
        />
      ))}
    </div>
  );

  if (!boxed) return <div aria-hidden>{rules}</div>;
  return (
    <div
      aria-hidden
      className="rounded-lg border border-dotted border-border px-3 py-3"
    >
      {rules}
    </div>
  );
}

// The interview's position, as a row of segments — one per step, the document's six sections in
// their order. It draws the package's own numbers and computes neither: six steps is what the
// package says six steps is. Segments up to and including the current step carry the accent; the
// rest stay on the border grey. The fill colour transitions rather than snapping, which marks the
// step advancing — the only reason a segment ever changes at all. It reads as a header for the page
// below: a full-width strip, not a puck floating in a corner.
function ProgressSegments({
  step,
  steps,
  title,
  statusText,
}: {
  step: number;
  steps: number;
  title?: string | null;
  statusText?: string;
}) {
  // The caption is the package's own status line for the current step, from interview.yaml
  // ("Shaping expected behaviours…"). It falls back to the step title, then to nothing, so a
  // session with no status still draws a caption rather than an empty row. The whole widget carries
  // one accessible label, so a screen reader hears "Behaviours, step 2 of 6" once rather than
  // reading the caption and the segments as two things.
  const caption = statusText ?? title ?? "Getting started";
  const label = title
    ? `${title}, step ${step} of ${steps}`
    : `Step ${step} of ${steps}`;
  return (
    <div
      role="img"
      aria-label={label}
      className="flex flex-1 flex-col gap-1.5"
    >
      <div className="flex items-baseline justify-between gap-2 text-xs text-muted-foreground">
        <span aria-hidden className="min-w-0 truncate font-medium">
          {caption}
        </span>
        <span aria-hidden className="shrink-0 font-mono">
          {step}/{steps}
        </span>
      </div>
      <div className="flex items-center gap-1">
        {Array.from({ length: steps }, (_, i) => (
          <div
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-[2px] transition-colors duration-300",
              i < step ? "bg-accent" : "bg-border",
            )}
          />
        ))}
      </div>
    </div>
  );
}

// A section heading is a landmark, so it is drawn as one. It used to be the smallest, faintest
// text in the pane — `text-xs` in muted grey — which put the three names that give the document
// its structure *below* the content they contain in the visual order. Sections read as unclear
// for exactly that reason: the hierarchy was inverted. The heading now carries foreground weight
// at a size above the body, a count of what it holds, and a rule closing it off.
//
// It also sticks. Scrolling through a long Behaviours run, the heading stays until the next
// section pushes it out, so the answer to "what am I looking at" is never off-screen. The
// negative inline margin lets it span the sheet's padding and cover the content passing beneath,
// which is what a sticky heading over an opaque page has to do.
function Section({
  title,
  count,
  writing = false,
  children,
}: {
  title: string;
  count?: number;
  writing?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("flex flex-col gap-3", writing && "is-writing")}>
      <div className="sticky top-0 z-10 -mx-5 flex items-baseline justify-between gap-3 border-b border-border bg-card px-5 pb-2 pt-4">
        <h2 className="min-w-0 text-base font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <div className="flex shrink-0 items-center gap-2">
          {writing && (
            <span
              aria-hidden
              className="section-writing-marker h-1.5 w-1.5 rounded-full bg-accent"
            />
          )}
          {count != null && count > 0 && <Mono className="tabular-nums">{count}</Mono>}
        </div>
      </div>
      {children}
    </section>
  );
}

function ProductField({
  label,
  value,
  preserveLines = false,
}: {
  label: string;
  value: string;
  preserveLines?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-medium text-muted-foreground">{label}</h3>
      {/* RevealText stays mounted under the placeholder. On the first response it therefore sees
          empty → written; on a resumed session its initial value is already the completed text. */}
      <p
        className={cn(
          "text-muted-foreground",
          preserveLines && "whitespace-pre-line",
          !value && "hidden",
        )}
      >
        <RevealText value={value} />
      </p>
      {!value && <Placeholder />}
    </div>
  );
}

// One of a scenario's three columns: a label, then whatever the column holds, wrapping within its
// own width. The label sits above rather than beside its contents — beside, it would consume a
// fixed slice of an already narrow column and leave the chips almost no room to sit side by side.
// One labelled line of a scenario's metadata. It draws two cells straight into the parent grid — a
// label in the fixed left column and its values in the flexible right one — so that every row's
// label shares one edge and every row's values share another, no matter which row is longest. The
// label sits at the top of a wrapping value cell (`items-start`) rather than centred, so a row that
// wraps to two lines keeps its label pinned to the first.
function ScenarioRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <span className="pt-0.5 font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap items-start gap-1.5">{children}</div>
    </>
  );
}

// Each task is a disclosure: the header toggles its behaviours open and closed, so a long
// document collapses to a scannable list of task names. Note this toggle is *view* state
// only: it opens and closes a section, it never edits the profile, so the document view stays
// read-only in the sense that matters — nothing here changes what the package built.
function TaskView({
  task,
  selecting,
  showMetrics,
  metricByFqn,
}: {
  task: Task;
  selecting?: boolean;
  showMetrics: boolean;
  metricByFqn: ReadonlyMap<string, MetricSpec>;
}) {
  const [open, setOpen] = useState(true);
  // How much of this task is actually being measured. A bare total said the task holds two
  // behaviours; it did not say that only one of them was ticked, which was left to the dormant
  // rows' opacity alone — easy to miss, and the fraction is the number that decides whether the
  // profile is thorough enough. New Behaviour rows start selected, and the fraction changes as
  // the user clears or restores them.
  const measured = task.behaviours.filter((b) => b.measured).length;
  return (
    <div className="animate-arrive flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        aria-label={`${task.name}, ${measured} of ${task.behaviours.length} measured`}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded py-1 text-left transition-colors hover:text-accent"
      >
        <Chevron dir={open ? "down" : "right"} className="text-muted-foreground transition-transform" />
        <span className="min-w-0 flex-1 font-medium text-foreground">{task.name}</span>
        {/* The fraction goes teal the moment anything in this task is actually being measured,
            and stays grey while none of it is. That makes "this task contributes nothing to the
            run" a thing you see rather than a thing you compute, and it scans down the list: the
            grey chips are the gaps. Teal is the right colour for it because this is a live state
            and not a label — the same reason the open session in the rail carries it. */}
        <span aria-hidden className="shrink-0">
          <Chip tone={measured > 0 ? "accent" : "neutral"}>
            {measured}/{task.behaviours.length}
          </Chip>
        </span>
      </button>
      {open && (
        // Behaviours within a group are spaced apart too — a behaviour with a Given/When/Then
        // block below it must read as one unit set off from the next behaviour, not run flush
        // into it. The gap is smaller than the between-group gap so the hierarchy still reads:
        // groups first, behaviours within them second.
        <div className="ml-1.5 mt-1 border-l border-border pb-1 pl-3">
          <p className="mb-3 whitespace-pre-wrap text-sm text-muted-foreground">
            {task.description}
          </p>
          <ul className="flex flex-col gap-4">
            {task.behaviours.map((b) => (
              <BehaviourView
                key={b.id}
                behaviour={b}
                selecting={selecting}
                showMetrics={showMetrics}
                metricByFqn={metricByFqn}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BehaviourView({
  behaviour,
  selecting,
  showMetrics,
  metricByFqn,
}: {
  behaviour: Behaviour;
  selecting?: boolean;
  showMetrics: boolean;
  metricByFqn: ReadonlyMap<string, MetricSpec>;
}) {
  // A behaviour the user hasn't ticked is dormant: its criteria are kept but won't be
  // measured, so it reads de-emphasised.
  const dormant = !behaviour.measured;
  // Criteria are the one part of the document that lands *inside* another section rather than as a
  // section of its own, so the scaffold reaches one level deeper here: a behaviour chosen to be
  // measured but not yet written up shows the blank where its criteria will go.
  //
  // The tick is what makes the blank honest, but only once the tick is committed. A tick flips
  // `measured` live — and is a server round-trip that recomposes the prioritise screen — so while
  // the session is on prioritise the user is still choosing and any box can still be un-ticked.
  // Drawing the blank there promises content for a selection that has not been made. `selecting` is
  // true for the whole prioritise step (keyed on the step, not on `busy`, so a tick's brief in-
  // flight window does not flicker the blank on and off), and holds it back until Continue advances
  // the session off prioritise. From then on "ticked, not yet written up" is a settled promise. A
  // dormant behaviour still shows no blank because no criteria are coming for it.
  const awaitingCriteria =
    behaviour.measured && behaviour.criteria.length === 0 && !selecting;
  return (
    // The id sits in a gutter at the left rather than trailing the description. Trailing, it landed
    // wherever the prose happened to stop wrapping, so a run of behaviours ended in a ragged
    // column of ids that competed with the text without ever lining up. In a fixed gutter the ids
    // form one straight edge to read down, which is what makes a scenario's `Behaviours EB-1 EB-3`
    // resolvable by eye — the only job the id has in this pane.
    <li
      className={cn(
        "animate-arrive grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-2 gap-y-0.5",
        dormant && "opacity-45",
      )}
    >
      {/* The id goes teal on a behaviour that is actually being measured, and stays grey
          otherwise. This is the positive half of the "which of these count" signal: dimming the
          dormant rows says which ones are *out*, but nothing said which are *in*, so the teal
          `2/5` on the group named a count with no way to see which two it was. Teal is right here
          for the same reason the fraction carries it — being measured is a live selected state,
          not a label — and the ids already form a straight column to read down, so the counted
          ones light up as a scannable set. */}
      <Mono
        tone={behaviour.measured ? "accent" : "muted"}
        className={cn("pt-px tabular-nums", behaviour.measured && "font-semibold")}
      >
        {behaviour.id}
      </Mono>
      <span className="min-w-0 text-foreground">
        <span className="font-medium">{behaviour.name}</span> — {behaviour.description}
      </span>
      {behaviour.criteria.length > 0 && (
        // The criteria are set apart from the description above them with a top gap, so a
        // behaviour and its Given/When/Then read as a labelled unit rather than five stacked
        // rows. Each criterion is spaced from the next for the same reason.
        <ul className="col-start-2 mt-1.5 flex flex-col gap-3 text-xs">
          {behaviour.criteria.map((c) => {
            const metric = c.metric_fqn ? metricByFqn.get(c.metric_fqn) : undefined;
            return (
              <li
                key={c.id}
                // A hairline sits between criteria when a behaviour has more than one, so two
                // Given/When/Then blocks read as two units rather than one six-row stack. The rule
                // is gated on `:not(:first-child)`, which is what makes it appear only from the
                // second criterion on: a behaviour with a single AC draws no divider at all, and
                // none is ever drawn above the first. The padding lifts the rule into the gap
                // above rather than crowding the label row beneath it.
                className="animate-arrive flex flex-col gap-1 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-border [&:not(:first-child)]:pt-3"
              >
                {/* Given/when/then, three labelled rows rather than one run-on sentence. The
                    prose form put the whole criterion in a single wrapped paragraph whose three
                    clauses were separated by nothing but two commas and a colour change, so the
                    longest content in the document was also the least scannable. Aligned in a
                    column, the keywords become a fixed edge to read down, and the clause is
                    findable without reading the sentence that precedes it.

                    The label is the quiet part and the clause is the loud part — the inverse of
                    a first pass that set the keywords in foreground weight and let the clauses
                    recede into muted grey. That put the three repeated words "Given/When/Then" in
                    the strongest ink on the page and the actual content behind them, so the eye
                    read the scaffolding before the substance on every criterion. Muted,
                    letter-spaced keywords become a fixed edge to scan down; the foreground clause
                    is what reads. (Sentence case, not caps: all-caps labels are the house style's
                    named AI tell, and the letter-spacing gives the label its quiet-marker look
                    without them.) */}
                <p className="font-medium text-foreground">{c.name}</p>
                <div className="grid grid-cols-[2.75rem_minmax(0,1fr)] gap-x-2 gap-y-0.5">
                  <span className="tracking-wide text-muted-foreground">Given</span>
                  <span className="text-foreground">{c.description.given}</span>
                  <span className="tracking-wide text-muted-foreground">When</span>
                  <span className="text-foreground">{c.description.when}</span>
                  <span className="tracking-wide text-muted-foreground">Then</span>
                  <span className="text-foreground">{c.description.then}</span>
                </div>
                {showMetrics && metric && (
                  <Mono className="block break-words rounded border border-border bg-muted px-2 py-1 leading-relaxed">
                    <span className="block text-foreground">{metric.name}</span>
                    <span className="block text-muted-foreground">{metric.description}</span>
                  </Mono>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {awaitingCriteria && (
        // One short rule per behaviour still to be written up. Not boxed and not the full
        // three-line placeholder: this repeats once per selected behaviour, so anything larger
        // would put the grey back on the page that the sections were kept spare to avoid. It never
        // shimmers: the criteria are drafted during the Continue that leaves prioritise, before
        // this blank is allowed to appear, so there is no in-flight window to mark here.
        <div className="col-start-2 pt-0.5">
          <Placeholder widths={["w-28"]} />
        </div>
      )}
    </li>
  );
}
