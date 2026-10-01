// The conversation. Every block here is drawn from request `type` and `CardComponentType`
// alone — there is not one domain word in this file, and there must never be. A behaviour, a
// persona and a scenario all arrive as `Card`; the door draws a card. What each card *means* is
// in its `title`, `section` and `label`s, which the package composed.
//
// One rule governs the text box, and it is the whole of the "greyed on strict screens"
// behaviour: the box is live only when the screen actually offers a way to talk to it — a
// chat request, or a choice screen carrying a `chat` action. Prioritise and criteria carry
// no such action, so the box greys itself with no step name written down anywhere here.

import { ArrowUp, PencilSparkles } from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import type {
  TranscriptEntry,
  AnyCard,
  CardComponent,
  ChoiceRequest,
  FormRequest,
  Option,
  UserResponse,
  Warning,
  WizardRequest,
} from "./transport/api";
import { optionKey } from "./transport/api";
import { NumberInput } from "./inputs";
import { Button, cn, formatTrials, Mono, Panel } from "./ui";

// What a block can send up. `null` from a resolved or read-only block.
type Emit = (
  response: UserResponse,
  files?: readonly File[],
  removedFixtures?: readonly string[],
) => void;
type CardFieldValue = number | string[];

const FormDraftContext = createContext<{
  values: Map<string, Record<string, string>>;
  prefix: string;
} | null>(null);

// ── whole transcript ─────────────────────────────────────────────────────────

export function Transcript({
  requests,
  entries,
  formDrafts,
  draftPrefix = "",
  onRetry,
  onEdit,
  busy,
  onRespond,
}: {
  requests: WizardRequest[];
  entries?: TranscriptEntry[];
  formDrafts?: Map<string, Record<string, string>>;
  draftPrefix?: string;
  onRetry?: () => void;
  onEdit?: () => void;
  busy: boolean;
  onRespond: Emit;
}) {
  return (
    <FormDraftContext.Provider
      value={formDrafts ? { values: formDrafts, prefix: draftPrefix } : null}
    >
      <div className="flex flex-col gap-8">
        {requests.map((request, i) => {
          // A light rule ahead of the first block of each new step, so consecutive steps do not
          // read as one unbroken scroll. The boundary is the per-request `step` changing between
          // adjacent blocks — the package stamps it; the door only notices when it moves. Not the
          // interview's current step, which cannot mark the joins between already-resolved blocks in
          // the scrollback. The first block starts no divider (nothing precedes it), and a request
          // with no `step` never introduces one, so the rule degrades to nothing on older interviews.
          const prevStep = requests[i - 1]?.step ?? null;
          const startsStep =
            request.step != null && i > 0 && request.step !== prevStep;
          const entry = entries?.[i];
          const failed =
            entry?.kind === "interaction" && entry.status === "failed";
          return (
            <div
              key={request.request_id ?? i}
              className={cn(startsStep && "border-t border-border pt-8")}
            >
              <RequestBlock
                request={request}
                busy={busy}
                onRespond={onRespond}
              />
              {entry?.kind === "interaction" && entry.status === "sending" && (
                <p role="status" className="mt-2 text-sm text-muted-foreground">
                  Sending…
                </p>
              )}
              {failed && (
                <div role="alert" className="mt-2 flex items-center gap-3">
                  <p>{entry.failure?.message}</p>
                  {entry.failure?.retryable && (
                    <Button disabled={busy} onClick={onRetry}>
                      Retry
                    </Button>
                  )}
                  {entry.failure?.kind !== "storage" && (
                    <Button disabled={busy} onClick={onEdit}>
                      Edit reply
                    </Button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </FormDraftContext.Provider>
  );
}

function RequestBlock({
  request,
  busy,
  onRespond,
}: {
  request: WizardRequest;
  busy: boolean;
  onRespond: Emit;
}) {
  const resolved = request.state === "resolved";
  return (
    <section
      className={cn(
        "flex flex-col gap-3",
        // A resolved block is a receipt: dimmed, and its controls are gone, not merely
        // disabled. The distinction is what stops a screen being answered twice.
        resolved && "opacity-55",
      )}
      aria-live={resolved ? undefined : "polite"}
    >
      {request.prompt && (
        <p className="whitespace-pre-wrap text-foreground">{request.prompt}</p>
      )}
      <RequestBody
        request={request}
        resolved={resolved}
        busy={busy}
        onRespond={onRespond}
      />
    </section>
  );
}

function RequestBody({
  request,
  resolved,
  busy,
  onRespond,
}: {
  request: WizardRequest;
  resolved: boolean;
  busy: boolean;
  onRespond: Emit;
}) {
  switch (request.type) {
    case "chat":
      // The prompt is the wizard's question; the live reply is typed in the composer at the
      // foot of the pane, so a live chat block draws nothing further. Once resolved, the reply
      // the package stamped onto the request is shown beneath the question, so the exchange
      // reads as a conversation rather than a one-sided list of prompts.
      return request.answer ? <UserSaid text={request.answer} /> : null;
    case "form":
      return (
        <FormBlock
          request={request}
          resolved={resolved}
          busy={busy}
          onRespond={onRespond}
        />
      );
    case "choice":
      return (
        <ChoiceBlock
          request={request}
          resolved={resolved}
          busy={busy}
          onRespond={onRespond}
        />
      );
  }
}

// ── choice ─────────────────────────────────────────────────────────────────────

function ChoiceBlock({
  request,
  resolved,
  busy,
  onRespond,
}: {
  request: ChoiceRequest;
  resolved: boolean;
  busy: boolean;
  onRespond: Emit;
}) {
  const send = (keys: string[]) =>
    onRespond({ type: "choice", selected: keys });
  const sendField = (
    key: string,
    value: CardFieldValue,
    files?: readonly File[],
    removedFixtures?: readonly string[],
  ) =>
    onRespond(
      { type: "choice", values: { [key]: value } },
      files,
      removedFixtures,
    );
  const disabled = resolved || busy;

  return (
    <div className="flex flex-col gap-3">
      {request.warnings.map((warning, i) => (
        <WarningBlock
          key={i}
          warning={warning}
          disabled={disabled}
          onPick={(k) => send([k])}
        />
      ))}

      {request.cards.length > 0 && (
        // A muted backing sits behind the whole run of cards — the grey the Jira columns and
        // the document sheet share — so a card-bearing screen reads as its own grouped surface,
        // set apart from the plain chat turns above and below it. It is drawn from the cards
        // alone, not the resolved flag, so it persists once the block becomes a receipt; the
        // receipt's dimming rides on top from the enclosing section.
        <div className="flex flex-col gap-3 rounded-lg bg-muted p-3">
          {request.cards.map((card, i) => {
            // The heading is emitted once per group, ahead of that group's cards — a header
            // is drawn only when this card's section differs from the one before it. The door
            // never learns what a section is; it only notices when the string changes.
            const prev = request.cards[i - 1]?.section;
            const startsGroup = card.section && card.section !== prev;
            return (
              <div key={card.id} className="flex flex-col gap-1.5">
                {startsGroup && (
                  <p className="pt-1 text-xs font-semibold text-muted-foreground">
                    {card.section}
                  </p>
                )}
                <CardBlock
                  card={card}
                  disabled={disabled}
                  onPick={(k) => send([k])}
                  onFieldChange={sendField}
                />
              </div>
            );
          })}
        </div>
      )}

      {request.footer && (
        <p className="text-right text-muted-foreground">{request.footer}</p>
      )}

      {/* Screen-level actions — every one the screen offers, including "Chat about it". A
          choice screen edits the profile, so it owns the only live controls: the composer is
          disabled while it is up (see `acceptsChat`). Choosing "Chat about it" makes the driver
          swap this screen for a chat request, and that is what hands editing to the text box —
          one editor at a time, never the buttons and the box together. */}
      {!resolved && (
        <div className="flex flex-wrap gap-2">
          {request.options.map((o) => (
            <ActionButton
              key={optionKey(o.id)}
              option={o}
              disabled={busy}
              onPick={(k) => send([k])}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// A screen-level button. `selected` on a screen option is rare, but honoured: a checkbox
// list on the measurement review screen sends its own action per row and Continue commits.
function ActionButton({
  option,
  disabled,
  onPick,
}: {
  option: Option;
  disabled: boolean;
  onPick: (key: string) => void;
}) {
  return (
    <Button
      variant={option.primary ? "primary" : "secondary"}
      active={option.selected === true}
      disabled={disabled || !option.enabled}
      onClick={() => onPick(optionKey(option.id))}
    >
      {option.label}
    </Button>
  );
}

// ── cards ─────────────────────────────────────────────────────────────────────

function CardBlock({
  card,
  disabled,
  onPick,
  onFieldChange,
}: {
  card: AnyCard;
  disabled: boolean;
  onPick: (key: string) => void;
  onFieldChange: (
    key: string,
    value: CardFieldValue,
    files?: readonly File[],
    removedFixtures?: readonly string[],
  ) => void;
}) {
  // Three cases, decided by the package, not the door:
  //   • `selected == null` — no box at all. The behaviours review sends this: it lists the drafted
  //     behaviours and only asks for a nod to continue, so a checkbox would imply a decision the
  //     user has not been asked to make yet. The measurement choice is part of this screen.
  //   • `selected` set AND a real `tick` option present — an interactive checkbox. Only the
  //     composes that option (with a patch). We drive the box from the option and send *its* key,
  //     so the tick matches an option server-side and the recomposed screen reflects the flip.
  //   • `selected` set but no `tick` option — a read-only marker. Criteria sends this to show which
  //     behaviours are covered; it is display-only, exactly as the CLI draws `[x]`/`[ ]`.
  // (Inventing a `tick:<id>` key from `selected` alone used to match nothing on the read-only
  // screens, which is the flicker-and-revert bug this replaced.)
  const tick = card.options.find((o) => o.id.action === "tick");
  const showBox = card.selected !== null && card.selected !== undefined;
  const checked = tick?.selected ?? card.selected ?? false;
  // The tick lives in the checkbox now; keep it out of the action-button row below so it is not
  // drawn twice.
  const actions = card.options.filter((o) => o.id.action !== "tick");
  // The section heading is drawn by the caller, once per group; a card renders only its panel.
  return (
    <Panel className={cn("p-3", card.blocking && "border-destructive/60")}>
      <div className="flex items-start gap-3">
        {showBox && (
          <input
            type="checkbox"
            className="mt-1 h-4 w-4 accent-[hsl(var(--accent))]"
            checked={checked}
            // Read-only when the screen offers no toggle for this card: the box then reports
            // state rather than accepting a click that would post a key matching no option.
            disabled={disabled || !tick}
            onChange={tick ? () => onPick(optionKey(tick.id)) : undefined}
            aria-label={card.title}
          />
        )}
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-foreground">{card.title}</span>
            {/* The id keeps its own gutter: it never shrinks and never wraps, so a short
                  identifier like EB-1 or T-1 reads on one line however long the title runs. */}
            <Mono className="shrink-0 whitespace-nowrap">{card.id}</Mono>
          </div>

          {card.components.map((component, i) => (
            <ComponentBlock
              key={i}
              component={component}
              trialCount={"trials" in card ? card.trials : undefined}
              disabled={disabled}
              onPick={onPick}
              onFieldChange={onFieldChange}
            />
          ))}

          {card.note && (
            <p className="text-sm text-muted-foreground">{card.note}</p>
          )}

          {/* Actions scoped to this card — "chat", "add a scenario", "remove". The tick, if any, is
                the checkbox above, so it is filtered out here. */}
          {actions.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {actions.map((o) => (
                <ActionButton
                  key={optionKey(o.id)}
                  option={o}
                  disabled={disabled}
                  onPick={onPick}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

function ComponentBlock({
  component,
  trialCount,
  disabled,
  onPick,
  onFieldChange,
}: {
  component: CardComponent;
  trialCount?: number;
  disabled: boolean;
  onPick: (key: string) => void;
  onFieldChange: (
    key: string,
    value: CardFieldValue,
    files?: readonly File[],
    removedFixtures?: readonly string[],
  ) => void;
}) {
  // The value alone, unlabelled. `FormRow` decides where the label goes: a labelled component
  // reads as a form field (label in a left column, value at the right), an unlabelled one runs
  // full-width. This is a *shape* choice — "does this component carry a label" — not a domain
  // one; only the scenario card composes labelled components, so this is what gives it its form look
  // without the door ever learning it is a scenario.
  const value = (() => {
    switch (component.type) {
      case "text":
        return (
          <p className="whitespace-pre-wrap text-sm text-foreground">
            {component.text}
          </p>
        );

      case "options":
        // A chip row. Each chip carries its own `selected`, so it toggles in place and posts
        // its action on click — a "T-1 covers EB-4" reference is one such chip.
        return (
          <div className="flex w-full flex-wrap gap-1.5">
            {component.options.map((o) => (
              <Button
                key={optionKey(o.id)}
                variant="ghost"
                active={o.selected === true}
                disabled={disabled || !o.enabled}
                className="px-2 py-0.5 text-xs"
                onClick={() => onPick(optionKey(o.id))}
              >
                {o.label}
              </Button>
            ))}
          </div>
        );

      case "number":
        return trialCount === undefined ? (
          <NumberCardField
            component={component}
            disabled={disabled}
            onCommit={(value) => onFieldChange(optionKey(component.id), value)}
          />
        ) : (
          <div className="flex min-w-0 items-center gap-3">
            <NumberCardField
              component={component}
              disabled={disabled}
              onCommit={(value) =>
                onFieldChange(optionKey(component.id), value)
              }
            />
            <span className="shrink-0 border-l border-border pl-3 text-xs text-muted-foreground">
              {formatTrials(trialCount)}
            </span>
          </div>
        );

      case "upload":
        return (
          <FixtureField
            component={component}
            disabled={disabled}
            onChange={(names, files, removedFixtures) =>
              onFieldChange(
                optionKey(component.id),
                names,
                files,
                removedFixtures,
              )
            }
          />
        );

      case "divider":
        // A hairline between two component groups. The package drops it between a behaviour's
        // acceptance criteria; the door draws the rule and never learns what it separates. It
        // spans the full card width, so it returns before FormRow's label column below.
        return <div className="border-t border-border" />;
    }
  })();

  // A divider owns the whole row — it carries no label, so it skips FormRow's label/value split
  // and rules straight across.
  if (component.type === "divider") return value;

  return <FormRow label={component.label}>{value}</FormRow>;
}

export function FixtureField({
  component,
  disabled,
  onChange,
}: {
  component: Extract<CardComponent, { type: "upload" }>;
  disabled: boolean;
  onChange: (
    names: string[],
    files: readonly File[],
    removedFixtures: readonly string[],
  ) => void;
}) {
  const remove = (name: string) => {
    const next = component.value.filter((item) => item !== name);
    onChange(next, [], [name]);
  };

  const names = component.value;
  const available = component.available ?? [];
  const toggle = (name: string, checked: boolean) => {
    const next = checked
      ? [...names, name]
      : names.filter((item) => item !== name);
    const removed = names.filter((item) => !next.includes(item));
    onChange(next, [], removed);
  };

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {names.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {names.map((name) => (
            <li
              key={name}
              className="flex items-center gap-1 rounded-md border border-border bg-muted px-2 py-1 text-xs"
            >
              <span className="max-w-48 truncate">{name}</span>
              <button
                type="button"
                aria-label={`Remove ${name}`}
                disabled={disabled}
                onClick={() => remove(name)}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {available.length > 0 && (
        <fieldset className="flex flex-col gap-1.5 rounded-md border border-border p-2">
          <legend className="px-1 text-xs font-medium text-muted-foreground">
            Available early files
          </legend>
          {available.map((name) => (
            <label key={name} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={names.includes(name)}
                disabled={disabled}
                onChange={(event) => toggle(name, event.currentTarget.checked)}
                className="h-4 w-4 accent-[hsl(var(--accent))]"
              />
              <span>{name}</span>
            </label>
          ))}
        </fieldset>
      )}
      <input
        type="file"
        multiple
        disabled={disabled}
        onChange={(event) => {
          const files = [...(event.currentTarget.files ?? [])];
          if (files.length === 0) return;
          const next = [...component.value];
          for (const file of files) {
            if (!next.includes(file.name)) next.push(file.name);
          }
          onChange(next, files, []);
          event.currentTarget.value = "";
        }}
        className="block w-full min-w-0 text-xs text-muted-foreground file:mr-2 file:rounded-md file:border-0 file:bg-background file:px-2 file:py-1 file:text-xs file:font-medium file:text-foreground hover:file:bg-muted"
      />
    </div>
  );
}

function NumberCardField({
  component,
  disabled,
  onCommit,
}: {
  component: Extract<CardComponent, { type: "number" }>;
  disabled: boolean;
  onCommit: (value: number) => void;
}) {
  const [draft, setDraft] = useState(component.value);

  useEffect(() => setDraft(component.value), [component.value]);

  const commit = (value: number) => {
    const bounded = Math.min(component.max, Math.max(component.min, value));
    setDraft(bounded);
    if (bounded === component.value) return;
    onCommit(bounded);
  };

  return (
    <NumberInput
      value={draft}
      min={component.min}
      max={component.max}
      disabled={disabled}
      onChange={setDraft}
      onCommit={commit}
    />
  );
}

// One component's row. With a label it reads as a form field — the label in a fixed left column,
// the value aligned to the right of the row — which is what turns the scenario card's stack of
// labelled components into a two-column form. Without a label it runs full-width, so the
// behaviours', criteria' and personas' unlabelled text is untouched.
function FormRow({
  label,
  children,
}: {
  label?: string | null;
  children: ReactNode;
}) {
  if (!label) return <>{children}</>;
  return (
    <div className="flex items-baseline gap-4">
      <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground">
        {label}
      </span>
      {/* The value column: content left-aligned to a common edge just right of the label, so a
          list of chips forms a clean left rule and a scalar sits at the same start. "Fields on
          the right side" means this column, not text pushed to the far margin. */}
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
        {children}
      </div>
    </div>
  );
}

// ── warnings ─────────────────────────────────────────────────────────────────

// Rendered by source. A document gate ("your document needs a scenario here") is the user's to
// clear and reads calm; a runtime event ("we couldn't reach the model") is not their fault
// and reads as ours. Same component, different skin — never the same skin.
function WarningBlock({
  warning,
  disabled,
  onPick,
}: {
  warning: Warning;
  disabled: boolean;
  onPick: (key: string) => void;
}) {
  const runtime = warning.source === "runtime";
  return (
    <div
      role="status"
      className={cn(
        "rounded-lg border p-2.5 text-sm",
        runtime
          ? "border-destructive/50 bg-destructive/8 text-foreground"
          : "border-gold/50 bg-gold/10 text-foreground",
      )}
    >
      <p>{warning.text}</p>
      {warning.options.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {warning.options.map((o) => (
            <ActionButton
              key={optionKey(o.id)}
              option={o}
              disabled={disabled}
              onPick={onPick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── form ─────────────────────────────────────────────────────────────────────

function FormBlock({
  request,
  resolved,
  busy,
  onRespond,
}: {
  request: FormRequest;
  resolved: boolean;
  busy: boolean;
  onRespond: Emit;
}) {
  const drafts = useContext(FormDraftContext);
  const key = `${drafts?.prefix}:${request.request_id}`;
  const [values, updateValues] = useState<Record<string, string>>(
    drafts?.values.get(key) ?? {},
  );
  const setValues = (value: Record<string, string>) => {
    drafts?.values.set(key, value);
    updateValues(value);
  };
  // A resolved form is a receipt: show what was submitted, labelled by field, the same way a
  // resolved chat shows its answer. The package stamped the values onto the request.
  if (resolved) {
    const submitted = request.fields
      .map((field) => ({ field, value: request.answer[field.id] }))
      .filter((row) => row.value);
    if (submitted.length === 0) return null;
    return (
      <div className="flex flex-col gap-2">
        {submitted.map(({ field, value }) => (
          <div key={field.id} className="flex flex-col gap-0.5">
            <span className="text-xs font-medium text-muted-foreground">
              {field.label}
            </span>
            <UserSaid text={value} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (busy) return;
        onRespond({ type: "form", values });
      }}
    >
      {request.fields.map((field) => (
        <label key={field.id} className="flex flex-col gap-1">
          <span className="text-sm font-medium">{field.label}</span>
          {field.multiline ? (
            <textarea
              className="min-h-20 rounded-lg border border-input bg-background p-2 text-sm"
              placeholder={field.placeholder}
              value={values[field.id] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setValues({ ...values, [field.id]: e.target.value })
              }
            />
          ) : (
            <input
              className="rounded-md border border-input bg-background p-2 text-sm"
              placeholder={field.placeholder}
              value={values[field.id] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setValues({ ...values, [field.id]: e.target.value })
              }
            />
          )}
        </label>
      ))}
      <div>
        <Button type="submit" variant="primary" disabled={busy}>
          Save
        </Button>
      </div>
    </form>
  );
}

// ── the user's own voice ───────────────────────────────────────────────────

// What the user typed, shown back in a resolved block. Set apart from the package's prompt —
// which is plain foreground text flush to the left — by a tint, a left rule and an indent, so
// the two sides of the exchange read as two sides without either being domain-aware. The
// package composed the question; this is the only text in the transcript the user wrote.
function UserSaid({ text }: { text: string }) {
  return (
    <div className="border-l-2 border-accent/40 bg-muted/40 pl-3 pr-2 py-1.5">
      <p className="whitespace-pre-wrap text-foreground">{text}</p>
    </div>
  );
}

// ── the composer ─────────────────────────────────────────────────────────────

// Whether the live screen can be talked to, and the single source of the greying rule: only a
// chat request. A choice screen edits the profile through its own controls — "Chat about it"
// among them — so the composer stays disabled there, and one component edits at a time. Choosing
// "Chat about it" makes the next request a chat request, which is what turns this true. No step
// names, no domain checks.
export function acceptsChat(request: WizardRequest | undefined): boolean {
  if (!request || request.state !== "pending") return false;
  return request.type === "chat";
}

// The instruction to show as placeholder when the box is greyed — the package's own words
// for how this particular screen wants to be answered.
export function composerHint(request: WizardRequest | undefined): string {
  if (request && request.type === "choice" && request.instruction)
    return request.instruction;
  return "";
}

export function Composer({
  request,
  busy,
  onSend,
  alwaysEnabled = false,
  placeholder,
  initialText = "",
  value,
  onValueChange,
  roomy = false,
  leadingIcon = false,
  bare = false,
  sourceControl,
}: {
  request: WizardRequest | undefined;
  busy: boolean;
  onSend: (text: string) => void;
  // The opening screen has no interview yet, so there is no request to derive from — it is a
  // way in, always open. Everywhere else the greying rule stands.
  alwaysEnabled?: boolean;
  placeholder?: string;
  // The opening flow can return from capability selection to the description without losing the
  // user's draft. Interview replies remain empty on mount.
  initialText?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  // Give the opening product prompt enough room for a useful first description. Conversation
  // replies keep the smaller composer.
  roomy?: boolean;
  // A pencil-sparkles mark inside the input, left of the text. Only the opening screen's hero
  // composer asks for it; the in-conversation composer leaves it off, so the mark reads as "this
  // is where you begin" rather than decoration on every turn.
  leadingIcon?: boolean;
  // Drop the bottom-dock chrome — the outer padding and the composer's own max-width. The
  // opening screen already lays the composer inside a sized column alongside the entry cards, so
  // it should fill that column and match their width rather than re-centre itself narrower.
  bare?: boolean;
  sourceControl?: ReactNode;
}) {
  const [localText, setLocalText] = useState(initialText);
  const text = value ?? localText;
  const setText = (next: string) => {
    setLocalText(next);
    onValueChange?.(next);
  };
  const enabled = (alwaysEnabled || acceptsChat(request)) && !busy;
  const hint =
    placeholder ?? (enabled ? "Type a reply" : composerHint(request));

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || !enabled) return;
    onSend(trimmed);
    if (value === undefined) setText("");
  };

  const canSend = enabled && text.trim().length > 0;

  // The box grows with what is being typed and only scrolls once it has run out of room. The
  // comment below the textarea has always claimed this; nothing implemented it, so `rows={3}` was
  // the whole story and a paragraph was written through a three-line slot that scrolled from the
  // second sentence onward. Measuring is the only way to do it: reset to `auto` first, or
  // `scrollHeight` reports the height already set rather than the height wanted.
  const field = useRef<HTMLTextAreaElement | null>(null);
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [text]);

  // Whether the field has been scrolled away from its first line. Once it has, the top edge takes
  // a short fade so the partial line at the cut reads as text continuing above rather than as text
  // sliced through — the hard clip a few pixels under a rounded border looked like a rendering
  // fault. At rest there is nothing to fade, and applying it then would wash out the first line.
  const [scrolled, setScrolled] = useState(false);

  const sendButton = (
    <button
      type="button"
      aria-label="Send"
      disabled={!canSend}
      onClick={submit}
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
        "mb-0.5",
        "transition-colors",
        canSend
          ? "bg-primary text-primary-foreground hover:opacity-90"
          : "bg-muted text-muted-foreground",
      )}
    >
      <ArrowUp size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );

  const textarea = (
    <textarea
      ref={field}
      className={cn(
        // Taller by default and a higher cap: the box showed barely a line, so a
        // paragraph scrolled out of sight while being written. Three lines to start,
        // grows to a comfortable draft before it scrolls.
        "max-h-64 flex-1 resize-none bg-transparent py-2.5",
        roomy ? "min-h-32" : "min-h-[4.5rem]",
        "placeholder:text-muted-foreground focus:outline-none",
        "disabled:cursor-not-allowed",
        // A hairline thumb instead of the platform's default bar, which sat wide and opaque
        // against the rounded edge of the composer and read as a piece of another interface.
        "quiet-scrollbar",
        scrolled && "faded-top",
      )}
      placeholder={hint}
      value={text}
      disabled={!enabled}
      rows={roomy ? 5 : 3}
      onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 0)}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          submit();
        }
      }}
    />
  );

  const leading = leadingIcon && (
    <PencilSparkles
      size={18}
      strokeWidth={1.75}
      aria-hidden
      // Top-left, centred on the first line of text. That line sits in a 1.6 line-height
      // box beginning after the textarea's py-2.5, so the icon takes a slightly larger top
      // offset to land level with it rather than riding above the caps.
      className="mt-[0.9rem] shrink-0 self-start text-muted-foreground"
    />
  );

  const pill = (
    <div
      className={cn(
        "flex rounded-2xl border border-input bg-card p-2 pl-4",
        sourceControl ? "flex-col gap-1" : "items-end gap-2",
        "transition-colors focus-within:border-accent",
        !enabled && "opacity-70",
      )}
    >
      {sourceControl ? (
        <>
          <div className="flex w-full items-start gap-2">
            {leading}
            {textarea}
          </div>
          <div className="flex w-full items-center justify-between gap-2">
            {sourceControl}
            {sendButton}
          </div>
        </>
      ) : (
        <>
          {leading}
          {textarea}
          {sendButton}
        </>
      )}
    </div>
  );

  // Bare: the caller owns width and spacing. Docked: float clear of the bottom edge, centred in an
  // 80%-wide column so the 10% gutters on each side match the transcript's and the input sits over
  // the same width as the conversation above it.
  if (bare) return pill;
  return (
    <div className="w-full pb-6 pt-2">
      <div className="mx-auto w-4/5">{pill}</div>
    </div>
  );
}
