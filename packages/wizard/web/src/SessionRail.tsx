// The list of sessions, shown once at least one exists. A session is a title, when it was
// last touched, and where in the interview it got to. The current one is marked; a control
// at the top starts a new one.

import { CirclePlus, FolderClosed, PanelLeft } from "lucide-react";
import type { SessionSummary } from "./api";
import { Button, cn } from "./ui";

export function SessionRail({
  sessions,
  currentId,
  busy,
  onOpen,
  onNew,
  onCollapse,
}: {
  sessions: SessionSummary[];
  currentId: string | null;
  busy: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onCollapse?: () => void;
}) {
  return (
    <nav className="flex h-full w-[15%] min-w-[13rem] flex-col border-r border-border bg-muted/30">
      {/* The wordmark sits at the top-left, then a margin, then the new-evaluation control below
          it — the shape a chat app's rail takes, so the product name anchors the shell and the
          action reads as the first row of the list beneath it rather than a toolbar button. */}
      <div className="flex items-center justify-between gap-2 px-3 pt-3">
        <span className="text-sm font-semibold text-foreground">METIS-Wizard</span>
        {onCollapse && (
          <button
            type="button"
            aria-label="Hide sessions"
            title="Hide sessions"
            onClick={onCollapse}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelLeft size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
      </div>
      <div className="border-b border-border p-3">
        <Button
          variant="primary"
          // Left-aligned rather than centred: the rail is a list of conversations, and its lead
          // control should read as the first row of that list, not as a centred toolbar button.
          className="w-full justify-start"
          disabled={busy}
          onClick={onNew}
        >
          <CirclePlus size={15} strokeWidth={1.75} aria-hidden />
          New evaluation
        </Button>
      </div>
      <ul className="flex-1 overflow-y-auto p-3">
        {sessions.map((s) => (
          <li key={s.id}>
            <button
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left transition-colors",
                s.id === currentId
                  ? "border border-accent bg-accent/10"
                  : "border border-transparent hover:bg-muted",
              )}
              onClick={() => onOpen(s.id)}
            >
              <FolderClosed
                size={15}
                strokeWidth={1.3}
                aria-hidden
                className="shrink-0 text-muted-foreground"
              />
              {/* One line per session: the title runs at the start and truncates, the timestamp
                  sits at the end and never shrinks. The step is shown in the conversation header,
                  not repeated here, so the rail stays scannable as a plain list. */}
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                {s.title}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {relativeTime(s.updated)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// The one bit of phrasing the door owns rather than the package: a timestamp is data, not
// finished text, so turning epoch seconds into "3 minutes ago" is a rendering decision.
function relativeTime(epochSeconds: number): string {
  const seconds = Math.max(0, Date.now() / 1000 - epochSeconds);
  const minutes = seconds / 60;
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}
