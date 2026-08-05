// The document view. This is the component in the door that reads `ProductProfile` and knows
// its shape — epics hold behaviours hold criteria; personas and tasks are flat lists. The
// conversation stays shape-only so this can hold all of the interview's domain knowledge in one
// place. There is one other domain-aware component, deliberately: the hand-authoring form
// (`ManualForm.tsx`), which names the experiment schema's own fields; its header comment
// explains why that exception is allowed. Neither of those names leaks into the shape-only
// conversation renderer, which remains the rule.
//
// It is read-only where it counts: no control here changes the profile — every edit still
// originates in the conversation. The only controls are presentation: disclosures that fold an
// epic open or closed, and a control to collapse the whole pane — both view state, not document
// state.
//
// The pane is scaffold first and document second. Every section it will ever hold is drawn from
// the first turn, blank ones as ruled placeholders, so the shape of what the interview produces is
// visible before any of it exists and the boundary between written and unwritten reads as the
// interview's frontier. This is also where the interview's progress is expressed — the ring in the
// header, and the rules of the section being written — because the document and the interview are
// the same six things in the same order, and a second stepper in the conversation would be a
// second drawing of what is already on screen.
//
// It is a live mirror of the profile the package built, drawn fresh each time the payload arrives.
// It holds no change history and no diff: content that has just landed animates in as it mounts,
// and once that has finished it is drawn exactly like content that arrived ten turns ago. The
// arrival is marked; the change is not remembered.

import { useState } from "react";
import type { Behaviour, Epic, ProductProfile, WizardRequest } from "./api";
import { PanelRight } from "lucide-react";
import { Chevron, cn, countRuns, formatRuns, Mono } from "./ui";

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
// Clarify is absent for a different reason. A clarify turn writes nothing to the profile: the
// driver files the answer in history and asks the next question, and only the final turn falls
// through to drafting — a choice made inside the model call, which neither the door nor the package
// can see coming. Marking a section there would promise content that is four turns away, and would
// put motion on screen through the interview's longest conversational phase, competing with the
// chat exactly when the document has nothing to say. The cost is that the one turn which writes the
// most is the one turn nothing is marked; the arrival animation still fires when the draft lands.
//
// This exclusion is provisional. It follows from clarify writing nothing until its last turn, not
// from any rule that the document must be still while the user is being asked questions — a later
// change makes clarify populate the document as it goes, and should loosen this then.
type WritingTarget = "behaviours" | "personas" | "tasks";

const WRITING_TARGET: Record<string, WritingTarget> = {
  behaviours: "behaviours",
  criteria: "personas",
  personas: "tasks",
};

export function Profile({
  profile,
  position,
  sessionStep,
  busy,
  onCollapse,
}: {
  profile: ProductProfile;
  position?: StepPosition | null;
  sessionStep?: string;
  busy?: boolean;
  onCollapse?: () => void;
}) {
  const { product } = profile;
  const named = product.name.trim() || "Untitled product";

  const { epics } = profile;
  const writing = busy && sessionStep ? WRITING_TARGET[sessionStep] : undefined;

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

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* The collapse control sits in the pane, above the sheet, rather than pinned inside the
          sheet's corner. It folds the pane away — it is chrome belonging to the pane, not part of
          the document — and moving it out leaves the sheet's corner free for the ring, which is
          about the document's own state. */}
      {onCollapse && (
        <div className="mb-2 flex justify-end">
          <button
            type="button"
            aria-label="Hide document"
            title="Hide document"
            onClick={onCollapse}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelRight size={16} strokeWidth={1.75} aria-hidden />
          </button>
        </div>
      )}

      {/* The document is a produced artifact, not an editable field, and it reads that way: a white
          sheet floating on the grey pane, carrying a single soft shadow. That shadow is the one
          exception the house style grants — depth is a border everywhere else — because "this is a
          finished page" is exactly what a sheet-with-shadow says and a border cannot. Nothing here
          is an input; the shadow's job is to say so. */}
      <div className="flex flex-col gap-6 rounded-[12px] bg-card p-5 text-sm text-card-foreground shadow-sm">
        <header className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <h2 className="text-base font-semibold text-foreground">{named}</h2>
            {product.summary ? (
              <p className="animate-arrive text-muted-foreground">
                {product.summary}
              </p>
            ) : (
              // The header holds one piece of prose — the product summary — not a list, so it gets
              // the ruled lines without the frame. The frame says "a region reserved for a growing
              // list of items"; the sections below fill with lists, the summary does not.
              <Placeholder />
            )}
          </div>
          {/* The ring alone — the step's name is not repeated here. The conversation's activity
              line already names what the wizard is doing, and a two-line title under the ring
              crowded the corner and competed with the product's own name for the eye. The name
              still reaches assistive technology through the ring's label. */}
          {position && (
            <ProgressRing
              step={position.step}
              steps={position.steps}
              title={position.title}
            />
          )}
        </header>

        {/* Sections run in the order the interview fills them, and every one of them is drawn
            whether or not it holds anything yet.

            Each heading is the package's own name for the step that fills it — "Behaviours",
            "Personas", "Tasks" — so the document and the conversation use one vocabulary and the
            sheet reads as the interview's output section by section. They are entity names, all
            three of the same kind; "What should be true" was a sentence sitting between two nouns,
            which is what made it read as the odd one out. */}
        <Section title="Behaviours">
          {epics.length > 0 ? (
            <div className="flex flex-col gap-2">
              {epics.map((epic) => (
                <EpicView key={epic.id} epic={epic} selecting={selecting} />
              ))}
            </div>
          ) : (
            <Placeholder boxed writing={writing === "behaviours"} />
          )}
        </Section>

        <Section title="Personas">
          {profile.personas.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {profile.personas.map((p) => (
                <li key={p.id} className="animate-arrive flex flex-col">
                  <Mono>{p.id}</Mono>
                  <span className="text-foreground">{p.description}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Placeholder boxed writing={writing === "personas"} />
          )}
        </Section>

        <Section title="Tasks">
          {profile.tasks.length > 0 ? (
            <div className="flex flex-col gap-3">
              <ul className="flex flex-col gap-4">
                {profile.tasks.map((t) => (
                  <li key={t.id} className="animate-arrive flex flex-col gap-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 flex-1 text-foreground">{t.description}</span>
                      <Mono className="shrink-0 whitespace-nowrap">{t.id}</Mono>
                    </div>
                    <TaskField label="Covers">
                      {t.behaviour_refs.length > 0 ? (
                        t.behaviour_refs.map((ref) => <Mono key={ref}>{ref}</Mono>)
                      ) : (
                        <span className="text-xs text-muted-foreground">none</span>
                      )}
                    </TaskField>
                    <TaskField label="Run as">
                      {t.persona_refs.length > 0 ? (
                        t.persona_refs.map((ref) => <Mono key={ref}>{ref}</Mono>)
                      ) : (
                        <span className="text-xs text-muted-foreground">none</span>
                      )}
                    </TaskField>
                    <TaskField label="Trials">
                      <Mono>{t.num_trials}</Mono>
                    </TaskField>
                    <TaskField label="Files">
                      {t.fixtures.length > 0 ? (
                        t.fixtures.map((file) => <Mono key={file}>{file}</Mono>)
                      ) : (
                        <span className="text-xs text-muted-foreground">none</span>
                      )}
                    </TaskField>
                    <div className="flex items-baseline gap-3">
                      <span className="w-16 shrink-0" aria-hidden />
                      <span className="ml-auto text-xs text-muted-foreground">
                        {formatRuns(countRuns(t.persona_refs.length, t.num_trials))}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="flex justify-end border-t border-border pt-2 text-sm text-muted-foreground">
                Total: {formatRuns(
                  profile.tasks.reduce(
                    (total, task) =>
                      total + countRuns(task.persona_refs.length, task.num_trials),
                    0,
                  ),
                )}
              </div>
            </div>
          ) : (
            <Placeholder boxed writing={writing === "tasks"} />
          )}
        </Section>
      </div>
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
// The frame specifically means "a list will grow here": Behaviours, Personas and Tasks all fill
// with lists of items, so all three get the identical framed placeholder. The header summary is one
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
      className="rounded-md border border-dotted border-border px-3 py-3"
    >
      {rules}
    </div>
  );
}

// The interview's position, as an arc. It draws the package's own numbers and computes neither:
// six steps is what the package says six steps is. The arc animates between positions rather than
// jumping, which marks the step advancing — the only reason it moves at all.
function ProgressRing({
  step,
  steps,
  title,
}: {
  step: number;
  steps: number;
  title?: string | null;
}) {
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  const fraction = Math.max(0, Math.min(1, step / steps));
  // The step's name is not drawn, so it is carried here instead — a screen reader hears
  // "Behaviours, step 2 of 6" rather than a bare fraction.
  const label = title
    ? `${title}, step ${step} of ${steps}`
    : `Step ${step} of ${steps}`;
  return (
    <svg
      className="shrink-0"
      width="38"
      height="38"
      viewBox="0 0 38 38"
      role="img"
      aria-label={label}
    >
      <circle
        cx="19"
        cy="19"
        r={radius}
        fill="none"
        stroke="hsl(var(--border))"
        strokeWidth="2"
      />
      <circle
        cx="19"
        cy="19"
        r={radius}
        fill="none"
        stroke="hsl(var(--accent))"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - fraction)}
        transform="rotate(-90 19 19)"
        style={{ transition: "stroke-dashoffset 0.3s ease-out" }}
      />
      <text
        x="19"
        y="19"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="9"
        fill="hsl(var(--muted-foreground))"
        fontFamily="var(--font-mono)"
      >
        {step}/{steps}
      </text>
    </svg>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

function TaskField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-16 shrink-0 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      <div className="flex min-w-0 flex-1 flex-wrap gap-x-3 gap-y-0.5">
        {children}
      </div>
    </div>
  );
}

// Each epic is a disclosure: the header toggles its behaviours open and closed, so a long
// document collapses to a scannable list of epic names. Note this toggle is *view* state
// only: it opens and closes a section, it never edits the profile, so the document view stays
// read-only in the sense that matters — nothing here changes what the package built.
function EpicView({
  epic,
  selecting,
}: {
  epic: Epic;
  selecting?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="animate-arrive flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded py-1 text-left transition-colors hover:text-accent"
      >
        <Chevron dir={open ? "down" : "right"} className="text-muted-foreground transition-transform" />
        <span className="font-medium text-foreground">{epic.name}</span>
        <span className="text-xs text-muted-foreground">
          {epic.behaviours.length}
        </span>
      </button>
      {open && (
        <ul className="flex flex-col gap-1.5 border-l border-border pb-1 pl-3 ml-1.5">
          {epic.behaviours.map((b) => (
            <BehaviourView key={b.id} behaviour={b} selecting={selecting} />
          ))}
        </ul>
      )}
    </div>
  );
}

function BehaviourView({
  behaviour,
  selecting,
}: {
  behaviour: Behaviour;
  selecting?: boolean;
}) {
  // A behaviour the user hasn't ticked is dormant: its criteria are kept but won't be
  // measured, so it reads de-emphasised.
  const dormant = !behaviour.priority;
  // Criteria are the one part of the document that lands *inside* another section rather than as a
  // section of its own, so the scaffold reaches one level deeper here: a behaviour chosen to be
  // measured but not yet written up shows the blank where its criteria will go.
  //
  // The tick is what makes the blank honest, but only once the tick is committed. A tick flips
  // `priority` live — and is a server round-trip that recomposes the prioritise screen — so while
  // the session is on prioritise the user is still choosing and any box can still be un-ticked.
  // Drawing the blank there promises content for a selection that has not been made. `selecting` is
  // true for the whole prioritise step (keyed on the step, not on `busy`, so a tick's brief in-
  // flight window does not flicker the blank on and off), and holds it back until Continue advances
  // the session off prioritise. From then on "ticked, not yet written up" is a settled promise. A
  // dormant behaviour still shows no blank — none are coming for it — and before prioritise nothing
  // is ticked at all.
  const awaitingCriteria =
    behaviour.priority && behaviour.criteria.length === 0 && !selecting;
  return (
    <li className={cn("animate-arrive flex flex-col gap-0.5", dormant && "opacity-45")}>
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 text-foreground">{behaviour.statement}</span>
        <Mono className="shrink-0 whitespace-nowrap">{behaviour.id}</Mono>
      </div>
      {behaviour.criteria.length > 0 && (
        <ul className="flex flex-col gap-0.5 pl-3">
          {behaviour.criteria.map((c) => (
            <li key={c.id} className="animate-arrive flex flex-col gap-1 text-xs text-muted-foreground">
              <span>
                <span className="text-foreground">Given</span> {c.given},{" "}
                <span className="text-foreground">when</span> {c.when},{" "}
                <span className="text-foreground">then</span> {c.then}
              </span>
              {c.metric_fqn && (
                // The metric is machine-named, so it reads as a line of code: mono on a light
                // editor backing, set apart from the plain-language criterion above it.
                <Mono className="block break-all rounded border border-border bg-muted px-2 py-1 leading-relaxed">
                  {c.metric_fqn}
                </Mono>
              )}
            </li>
          ))}
        </ul>
      )}
      {awaitingCriteria && (
        // One short rule per behaviour still to be written up. Not boxed and not the full
        // three-line placeholder: this repeats once per selected behaviour, so anything larger
        // would put the grey back on the page that the sections were kept spare to avoid. It never
        // shimmers: the criteria are drafted during the Continue that leaves prioritise, before
        // this blank is allowed to appear, so there is no in-flight window to mark here.
        <div className="pl-3 pt-0.5">
          <Placeholder widths={["w-28"]} />
        </div>
      )}
    </li>
  );
}
