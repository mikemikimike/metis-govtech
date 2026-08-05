// The conversation. Every block here is drawn from request `type` and `CardComponentType`
// alone — there is not one domain word in this file, and there must never be. A behaviour, a
// persona and a task all arrive as `Card`; the door draws a card. What each card *means* is
// in its `title`, `section` and `label`s, which the package composed.
//
// One rule governs the text box, and it is the whole of the "greyed on strict screens"
// behaviour: the box is live only when the screen actually offers a way to talk to it — a
// chat request, or a choice screen carrying a `chat` action. Prioritise and criteria carry
// no such action, so the box greys itself with no step name written down anywhere here.

import { ArrowUp, PencilSparkles } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type {
  AnyCard,
  CardComponent,
  ChoiceRequest,
  FormRequest,
  Option,
  UserResponse,
  Warning,
  WizardRequest,
} from "./api";
import { optionKey } from "./api";
import { FileReferenceListInput, NumberInput } from "./inputs";
import { Button, cn, formatRuns, Mono, Panel } from "./ui";

// What a block can send up. `null` from a resolved or read-only block.
type Emit = (response: UserResponse) => void;
type CardFieldValue = number | string[];

// A section heading the package composes as "Epic 1 · Finding sources". The user wants only the
// descriptive name shown, not the "Epic N ·" prefix. Properly this belongs in the application
// layer (`screens.py` `_section`), so both doors agree — but that file is shared with the CLI and
// off-limits while it is being changed in parallel. Until then the door drops the prefix here by
// splitting on the "·" separator. This is the one place the door reads structure inside a
// package-composed string; if there is no separator it shows the string whole, so it degrades to a
// no-op rather than mangling anything. Delete this and strip the prefix in `_section` once the
// package is safe to touch.
function sectionLabel(section: string | null | undefined): string {
  if (!section) return "";
  const parts = section.split("·");
  return (parts.length > 1 ? parts.slice(1).join("·") : section).trim();
}

// ── whole transcript ─────────────────────────────────────────────────────────

export function Transcript({
  requests,
  busy,
  onRespond,
}: {
  requests: WizardRequest[];
  busy: boolean;
  onRespond: Emit;
}) {
  return (
    <div className="flex flex-col gap-8">
      {requests.map((request, i) => {
        // A light rule ahead of the first block of each new step, so consecutive steps do not
        // read as one unbroken scroll. The boundary is the per-request `step` changing between
        // adjacent blocks — the package stamps it; the door only notices when it moves. Not the
        // session's current step, which cannot mark the joins between already-resolved blocks in
        // the scrollback. The first block starts no divider (nothing precedes it), and a request
        // with no `step` never introduces one, so the rule degrades to nothing on older sessions.
        const prevStep = requests[i - 1]?.step ?? null;
        const startsStep =
          request.step != null && i > 0 && request.step !== prevStep;
        return (
          <div
            key={i}
            // The shell scrolls to the newest step's first block by finding the last one of
            // these markers; the divider and the marker are the same element.
            data-step-start={startsStep ? "" : undefined}
            className={cn(startsStep && "border-t border-border pt-8")}
          >
            <RequestBlock request={request} busy={busy} onRespond={onRespond} />
          </div>
        );
      })}
    </div>
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
  const send = (keys: string[]) => onRespond({ type: "choice", selected: keys });
  const sendField = (key: string, value: CardFieldValue) =>
    onRespond({ type: "choice", values: { [key]: value } });
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
        <div className="flex flex-col gap-3 rounded-md bg-muted p-3">
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
                    {sectionLabel(card.section)}
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
// list at prioritise sends its own action per row and Continue commits.
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
  onFieldChange: (key: string, value: CardFieldValue) => void;
}) {
  // Three cases, decided by the package, not the door:
  //   • `selected == null` — no box at all. The behaviours review sends this: it lists the drafted
  //     behaviours and only asks for a nod to continue, so a checkbox would imply a decision the
  //     user has not been asked to make yet. The ask comes one screen later, on prioritise.
  //   • `selected` set AND a real `tick` option present — an interactive checkbox. Only prioritise
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
                runCount={"runs" in card ? card.runs : undefined}
                disabled={disabled}
                onPick={onPick}
                onFieldChange={onFieldChange}
              />
            ))}

            {card.note && (
              <p className="text-sm text-muted-foreground">{card.note}</p>
            )}

            {/* Actions scoped to this card — "chat", "add a task", "remove". The tick, if any, is
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
  runCount,
  disabled,
  onPick,
  onFieldChange,
}: {
  component: CardComponent;
  runCount?: number;
  disabled: boolean;
  onPick: (key: string) => void;
  onFieldChange: (key: string, value: CardFieldValue) => void;
}) {
  // The value alone, unlabelled. `FormRow` decides where the label goes: a labelled component
  // reads as a form field (label in a left column, value at the right), an unlabelled one runs
  // full-width. This is a *shape* choice — "does this component carry a label" — not a domain
  // one; only the task card composes labelled components, so this is what gives it its form look
  // without the door ever learning it is a task.
  const value = (() => {
    switch (component.type) {
      case "text":
        return (
          <div className="flex flex-col">
            <p className="whitespace-pre-wrap text-sm text-foreground">
              {component.text}
            </p>
            {component.note && <Mono>{component.note}</Mono>}
          </div>
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
        return runCount === undefined ? (
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
              onCommit={(value) => onFieldChange(optionKey(component.id), value)}
            />
            <span className="shrink-0 border-l border-border pl-3 text-xs text-muted-foreground">
              {formatRuns(runCount)}
            </span>
          </div>
        );

      case "upload":
        return (
          <FileReferenceListInput
            value={component.value}
            disabled={disabled}
            onChange={(value) => onFieldChange(optionKey(component.id), value)}
          />
        );
    }
  })();

  return <FormRow label={component.label}>{value}</FormRow>;
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
// the value aligned to the right of the row — which is what turns the task card's stack of
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

// Rendered by source. A document gate ("your document needs a task here") is the user's to
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
        "rounded-md border p-2.5 text-sm",
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
  const [values, setValues] = useState<Record<string, string>>({});
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
              className="min-h-20 rounded-md border border-input bg-background p-2 text-sm"
              placeholder={field.placeholder}
              value={values[field.id] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setValues((v) => ({ ...v, [field.id]: e.target.value }))
              }
            />
          ) : (
            <input
              className="rounded-md border border-input bg-background p-2 text-sm"
              placeholder={field.placeholder}
              value={values[field.id] ?? ""}
              disabled={busy}
              onChange={(e) =>
                setValues((v) => ({ ...v, [field.id]: e.target.value }))
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
  leadingIcon = false,
  bare = false,
}: {
  request: WizardRequest | undefined;
  busy: boolean;
  onSend: (text: string) => void;
  // The opening screen has no session yet, so there is no request to derive from — it is a
  // way in, always open. Everywhere else the greying rule stands.
  alwaysEnabled?: boolean;
  placeholder?: string;
  // A pencil-sparkles mark inside the input, left of the text. Only the opening screen's hero
  // composer asks for it; the in-conversation composer leaves it off, so the mark reads as "this
  // is where you begin" rather than decoration on every turn.
  leadingIcon?: boolean;
  // Drop the bottom-dock chrome — the outer padding and the composer's own max-width. The
  // opening screen already lays the composer inside a sized column alongside the entry cards, so
  // it should fill that column and match their width rather than re-centre itself narrower.
  bare?: boolean;
}) {
  const [text, setText] = useState("");
  const enabled = (alwaysEnabled || acceptsChat(request)) && !busy;
  const hint = placeholder ?? (enabled ? "Type a reply" : composerHint(request));

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || !enabled) return;
    onSend(trimmed);
    setText("");
  };

  const canSend = enabled && text.trim().length > 0;

  const pill = (
    <div
      className={cn(
        "flex items-end gap-2 rounded-2xl border border-input bg-card p-2 pl-4",
        "transition-colors focus-within:border-accent",
        !enabled && "opacity-70",
      )}
    >
          {leadingIcon && (
            <PencilSparkles
              size={18}
              strokeWidth={1.75}
              aria-hidden
              // Top-left, centred on the first line of text. That line sits in a 1.6 line-height
              // box beginning after the textarea's py-2.5, so its optical centre is a little below
              // the box top — the icon takes a slightly larger top offset to land level with it
              // rather than riding above the caps.
              className="mt-[0.9rem] shrink-0 self-start text-muted-foreground"
            />
          )}
          <textarea
            className={cn(
              // Taller by default and a higher cap: the box showed barely a line, so a
              // paragraph scrolled out of sight while being written. Three lines to start,
              // grows to a comfortable draft before it scrolls.
              "max-h-64 min-h-[4.5rem] flex-1 resize-none bg-transparent py-2.5",
              "placeholder:text-muted-foreground focus:outline-none",
              "disabled:cursor-not-allowed",
            )}
            placeholder={hint}
            value={text}
            disabled={!enabled}
            rows={3}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {/* A round send affordance inside the pill, the shape people expect. */}
          <button
            type="button"
            aria-label="Send"
            disabled={!canSend}
            onClick={submit}
            className={cn(
              "mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
              "transition-colors",
              canSend
                ? "bg-primary text-primary-foreground hover:opacity-90"
                : "bg-muted text-muted-foreground",
            )}
          >
            <ArrowUp size={16} strokeWidth={1.75} aria-hidden />
          </button>
    </div>
  );

  // Bare: the caller owns width and spacing. Docked: float clear of the bottom edge with room
  // on every side, centred in its own max-width the way a modern chat input sits.
  if (bare) return pill;
  return (
    <div className="px-6 pb-6 pt-2">
      <div className="mx-auto w-full max-w-3xl">{pill}</div>
    </div>
  );
}
