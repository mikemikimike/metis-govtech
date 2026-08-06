// The house style, in as few primitives as the three panes need. Every rule the style
// checklist enforces lives here once — near-black primary (never teal), borders not shadows,
// the two radius tiers from the token file — `rounded-md` for small controls, `rounded-lg` for
// surfaces — sentence case left to the package's own strings.

import { ChevronRight } from "lucide-react";
import { useId, useRef, useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function formatRuns(count: number): string {
  return `${count} ${count === 1 ? "run" : "runs"}`;
}

export function countRuns(personaCount: number, trials: number): number {
  return personaCount * trials;
}

type Variant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  active?: boolean; // a toggled chip — the one place the accent fills anything
}

// The accent earns its scarcity here: it is a 1px ring and a tint on a *selected* chip, and
// it is nowhere else. A primary button is near-black.
//
// Every variant answers a press as well as a hover. Without the pressed state a click produced no
// acknowledgement at all — the button looked identical the whole way down, and whatever the click
// started took long enough that the only feedback was the result arriving. Hover and press are two
// steps of the same neutral ramp: the fill goes to `muted` under the pointer and on to `border`,
// one step darker again, while held. The solid variant shifts opacity instead, having no fill to
// deepen.
//
// It is a colour shift and nothing else. No scale, no spring: a button that shrinks under the
// cursor is the decorative kind of motion this product does without, and the press only has to
// report that the click landed.
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground border border-primary hover:opacity-90 active:opacity-80",
  secondary:
    "bg-secondary text-secondary-foreground border border-border hover:bg-muted active:bg-border",
  ghost:
    "bg-transparent text-foreground border border-border hover:bg-muted active:bg-border",
};

export function Button({
  variant = "secondary",
  active = false,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5",
        "text-sm font-medium transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-45",
        active
          ? "border border-accent bg-accent/12 text-foreground"
          : VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// A small tooltip that works for both ordinary controls and disabled controls. Native disabled
// elements cannot receive focus, so callers can make this wrapper focusable and still expose the
// reason for the disabled state to keyboard users. Tooltips sit below their trigger so they do not
// cover the control being inspected.
export function Tooltip({
  label,
  children,
  className,
  focusable = false,
  ariaLabel,
  hoverOnly = false,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  focusable?: boolean;
  ariaLabel?: string;
  hoverOnly?: boolean;
}) {
  const id = useId();
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });

  const showBelowTrigger = () => {
    const bounds = triggerRef.current?.getBoundingClientRect();
    if (!bounds) return;
    setPosition({ left: bounds.left + bounds.width / 2, top: bounds.bottom + 14 });
    setVisible(true);
  };

  return (
    <div
      ref={triggerRef}
      className={cn("group relative", className)}
      tabIndex={focusable ? 0 : undefined}
      aria-label={focusable ? ariaLabel : undefined}
      aria-describedby={focusable ? id : undefined}
      onPointerEnter={showBelowTrigger}
      onPointerLeave={() => setVisible(false)}
      onFocusCapture={hoverOnly ? undefined : showBelowTrigger}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setVisible(false);
        }
      }}
    >
      {children}
      {visible &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            id={id}
            role="tooltip"
            style={{ left: position.left, top: position.top }}
            className={cn(
              "pointer-events-none fixed z-[100] w-max max-w-72 -translate-x-1/2",
              "rounded-[8px] border border-border bg-foreground px-3 py-2",
              "text-sm leading-5 text-background shadow-lg",
            )}
          >
            <span
              aria-hidden
              className="absolute left-1/2 -top-1.5 h-3 w-3 -translate-x-1/2 rotate-45 border-l border-t border-border bg-foreground"
            />
            <span className="relative">{label}</span>
          </div>,
          document.body,
        )}
    </div>
  );
}

// A bordered surface. Static cards get no shadow, ever — depth is a 1px line.
export function Panel({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-card text-card-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

// A chevron that points in one of the four directions. Used by the document pane's disclosures
// (the collapse affordances use lucide's panel icons instead). A thin wrapper over lucide's
// `ChevronRight`, rotated to face the asked-for direction, so every caller keeps the same `dir`
// API. Drawn in `currentColor` (lucide's default `stroke`), so it inherits its host text colour
// and never introduces the accent on its own.
export function Chevron({
  dir = "right",
  className,
}: {
  dir?: "up" | "down" | "left" | "right";
  className?: string;
}) {
  const rotation = { right: "", down: "rotate-90", left: "rotate-180", up: "-rotate-90" }[dir];
  return (
    <ChevronRight
      size={14}
      strokeWidth={1.75}
      aria-hidden
      className={cn("shrink-0", rotation, className)}
    />
  );
}

// A bordered monospace token: an id being referenced, a filename, a count.
//
// Neutral is the default and covers almost every chip, because most of them mark *what a thing
// refers to* — a behaviour, a persona, a file — and a reference is not a state. The accent tone is
// for the few that report one: a count that has become non-zero, something live. It is drawn as
// teal text and a teal edge rather than a teal fill, so a row of chips still reads as one family
// and the coloured one stands out by tone instead of by mass.
//
// This does not wrap `Mono`. Both would set a text colour, and two competing `text-*` utilities
// resolve by stylesheet order rather than by which was passed last, so the tone could silently
// lose. Setting the type here keeps the outcome deterministic.
export function Chip({
  tone = "neutral",
  className,
  children,
}: {
  tone?: "neutral" | "accent";
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-block rounded-md border px-1.5 py-0.5",
        "font-mono text-xs tracking-tight tabular-nums",
        tone === "accent"
          ? "border-accent/40 text-accent"
          : "border-border text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}

// A small monospace token — an id, metric metadata, or a filename. JetBrains Mono is reserved for
// machine-facing data, so it reads as implementation detail rather than ordinary prose.
// `tone` picks the ink, because `cn` is a plain join rather than tailwind-merge: a `text-*` passed
// through `className` does not override the base colour, it just sits beside it and loses on source
// order. So the one colour a caller legitimately varies — muted by default, accent when the id
// marks a live/selected state — is a prop the component resolves itself, leaving `className` for
// everything that does not conflict.
export function Mono({
  className,
  children,
  tone = "muted",
}: {
  className?: string;
  children: ReactNode;
  tone?: "muted" | "accent";
}) {
  return (
    <span
      className={cn(
        "font-mono text-xs tracking-tight",
        tone === "accent" ? "text-accent" : "text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}
