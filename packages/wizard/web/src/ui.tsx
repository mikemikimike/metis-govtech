// The house style, in as few primitives as the three panes need. Every rule the style
// checklist enforces lives here once — near-black primary (never teal), borders not shadows,
// the single 3px radius from the token file, sentence case left to the package's own strings.

import { ChevronRight } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

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
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground border border-primary hover:opacity-90",
  secondary:
    "bg-secondary text-secondary-foreground border border-border hover:bg-muted",
  ghost: "bg-transparent text-foreground border border-border hover:bg-muted",
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
        "rounded-md border border-border bg-card text-card-foreground",
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

// A small monospace token — an id, a metric FQN, a filename. JetBrains Mono is reserved for
// the machine-named things, so they read as machine-named.
export function Mono({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "font-mono text-xs text-muted-foreground tracking-tight",
        className,
      )}
    >
      {children}
    </span>
  );
}
