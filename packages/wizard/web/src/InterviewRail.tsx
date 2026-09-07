// The list of interviews, shown once at least one exists. A interview is a title, when it was
// last touched, and where in the interview it got to. The current one is marked; a control
// at the top starts a new one.

import { CirclePlus, FolderClosed, PanelLeft } from "lucide-react";
import type { InterviewSummary } from "./api";
import { Button, cn } from "./ui";

export function InterviewRail({
  interviews,
  currentId,
  busy,
  onOpen,
  onNew,
  onCollapse,
}: {
  interviews: InterviewSummary[];
  currentId: string | null;
  busy: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onCollapse?: () => void;
}) {
  return (
    <nav className="flex h-full w-[15%] min-w-[13rem] flex-col border-r border-border bg-muted">
      {/* The wordmark sits at the top-left, then a margin, then the new-evaluation control below
          it — the shape a chat app's rail takes, so the product name anchors the shell and the
          action reads as the first row of the list beneath it rather than a toolbar button. */}
      <div className="flex items-center justify-between gap-2 px-3 pt-3">
        <span className="text-sm font-semibold text-foreground">METIS-Wizard</span>
        {onCollapse && (
          <button
            type="button"
            aria-label="Hide interviews"
            title="Hide interviews"
            onClick={onCollapse}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelLeft size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
      </div>
      <div className="border-b border-border p-3">
        <Button
          // Bordered rather than solid. The rail's strongest mark belongs to the interview you are
          // in, and a near-black button above the list was competing with it for that job — two
          // emphatic things stacked, only one of which reports state. Outlined, this reads as an
          // available action and the filled row below reads as where you are.
          variant="ghost"
          // Left-aligned rather than centred: the rail is a list of conversations, and its lead
          // control should read as the first row of that list, not as a centred toolbar button.
          // `bg-background` lifts it off the rail's muted fill, which `ghost` alone leaves flat.
          className="w-full justify-start bg-background"
          disabled={busy}
          onClick={onNew}
        >
          <CirclePlus size={15} strokeWidth={1.75} aria-hidden />
          New evaluation
        </Button>
      </div>
      <ul className="quiet-scrollbar flex-1 overflow-y-auto p-3">
        {interviews.map((s) => (
          <li key={s.id}>
            {/* The open interview is filled with the accent outright, not tinted with it. A 10%
                wash was the quietest possible way to say "you are here" and it lost that argument
                against a near-black button sitting directly above it. A solid row is the one
                place in the rail worth spending the accent on, and it is at most one row at a
                time, so the colour stays as scarce as it was.

                Everything inside the row inherits the fill's foreground rather than keeping its
                own grey: muted text on a dark teal ground is unreadable, so the icon and the
                timestamp step up with it, the timestamp held back by opacity so the title still
                leads. */}
            <button
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left transition-colors duration-150",
                s.id === currentId
                  ? "bg-accent text-accent-foreground"
                  // The rail is already `bg-muted`, so a muted hover was a no-op. The lift is to
                  // the canvas colour, matching the new-evaluation control above.
                  : "hover:bg-background",
              )}
              onClick={() => onOpen(s.id)}
            >
              <FolderClosed
                size={15}
                strokeWidth={1.3}
                aria-hidden
                className={cn(
                  "shrink-0",
                  s.id === currentId ? "text-accent-foreground" : "text-muted-foreground",
                )}
              />
              {/* One line per interview: the title runs at the start and truncates, the timestamp
                  sits at the end and never shrinks. The step is shown in the conversation header,
                  not repeated here, so the rail stays scannable as a plain list. */}
              <span
                className={cn(
                  "min-w-0 flex-1 truncate text-sm",
                  s.id === currentId ? "font-semibold" : "font-medium text-foreground",
                )}
              >
                {s.title}
              </span>
              <span
                className={cn(
                  "shrink-0 text-xs",
                  s.id === currentId
                    ? "text-accent-foreground/75"
                    : "text-muted-foreground",
                )}
              >
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
