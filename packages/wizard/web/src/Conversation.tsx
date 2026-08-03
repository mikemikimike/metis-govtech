// The conversation. Every block here is drawn from request `type` and `CardComponentType`
// alone — there is not one domain word in this file, and there must never be. A behaviour, a
// persona and a task all arrive as `Card`; the door draws a card. What each card *means* is
// in its `title`, `section` and `label`s, which the package composed.
//
// One rule governs the text box, and it is the whole of the "greyed on strict screens"
// behaviour: the box is live only when the screen actually offers a way to talk to it — a
// chat request, or a choice screen carrying a `chat` action. Prioritise and criteria carry
// no such action, so the box greys itself with no step name written down anywhere here.

import { ArrowUp } from "lucide-react";
import { useState } from "react";
import type {
  Card,
  CardComponent,
  ChoiceRequest,
  FormRequest,
  Option,
  UserResponse,
  Warning,
  WizardRequest,
} from "./api";
import { optionKey } from "./api";
import { Button, cn, Mono, Panel } from "./ui";

// What a block can send up. `null` from a resolved or read-only block.
type Emit = (response: UserResponse) => void;

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
      {requests.map((request, i) => (
        <RequestBlock
          key={i}
          request={request}
          busy={busy}
          onRespond={onRespond}
        />
      ))}
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
        <div className="flex flex-col gap-3">
          {request.cards.map((card, i) => {
            // The heading is emitted once per group, ahead of that group's cards — a header
            // is drawn only when this card's section differs from the one before it. The door
            // never learns what a section is; it only notices when the string changes.
            const prev = request.cards[i - 1]?.section;
            const startsGroup = card.section && card.section !== prev;
            return (
              <div key={card.id} className="flex flex-col gap-1.5">
                {startsGroup && (
                  <p className="pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {sectionLabel(card.section)}
                  </p>
                )}
                <CardBlock
                  card={card}
                  disabled={disabled}
                  onPick={(k) => send([k])}
                />
              </div>
            );
          })}
        </div>
      )}

      {request.footer && (
        <p className="text-muted-foreground">{request.footer}</p>
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
}: {
  card: Card;
  disabled: boolean;
  onPick: (key: string) => void;
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
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-foreground">{card.title}</span>
              <Mono>{card.id}</Mono>
            </div>

            {card.components.map((component, i) => (
              <ComponentBlock
                key={i}
                component={component}
                disabled={disabled}
                onPick={onPick}
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
  disabled,
  onPick,
}: {
  component: CardComponent;
  disabled: boolean;
  onPick: (key: string) => void;
}) {
  switch (component.type) {
    case "text":
      return (
        <div className="flex flex-col">
          {component.label && (
            <span className="text-xs font-medium text-muted-foreground">
              {component.label}
            </span>
          )}
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
        <div className="flex flex-col gap-1">
          {component.label && (
            <span className="text-xs font-medium text-muted-foreground">
              {component.label}
            </span>
          )}
          <div className="flex flex-wrap gap-1.5">
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
        </div>
      );

    case "number":
      // Display-only in the MVP. The package composes the field but registers no action for
      // it — the CLI draws the same value as static text, and a door that grew its own
      // stepper would be inventing a response the package does not read. Its bounds ride
      // along so a later change can make it operable without a wire change.
      return (
        <div className="flex items-center gap-2">
          {component.label && (
            <span className="text-xs font-medium text-muted-foreground">
              {component.label}
            </span>
          )}
          <span className="font-mono text-sm text-foreground">
            {component.value}
          </span>
          <Mono>
            [{component.min}–{component.max}]
          </Mono>
        </div>
      );

    case "upload":
      // Filenames only in the MVP — no upload, and no action registered for it either. A
      // labelled read-back of the finished text the package built, nothing operable.
      return (
        <div className="flex flex-col gap-1">
          {component.label && (
            <span className="text-xs font-medium text-muted-foreground">
              {component.label}
            </span>
          )}
          <Mono>{component.value || "—"}</Mono>
        </div>
      );
  }
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
}: {
  request: WizardRequest | undefined;
  busy: boolean;
  onSend: (text: string) => void;
  // The opening screen has no session yet, so there is no request to derive from — it is a
  // way in, always open. Everywhere else the greying rule stands.
  alwaysEnabled?: boolean;
  placeholder?: string;
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

  return (
    // Not glued to the bottom edge: the composer floats clear of it, with room on every side,
    // so it is comfortable to reach and click the way a modern chat input is.
    <div className="px-6 pb-6 pt-2">
      <div className="mx-auto w-full max-w-3xl">
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border border-input bg-card p-2 pl-4",
            "transition-colors focus-within:border-accent",
            !enabled && "opacity-70",
          )}
        >
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
      </div>
    </div>
  );
}
