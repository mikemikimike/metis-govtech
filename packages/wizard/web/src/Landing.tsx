// The opening screen, shown in the middle region whenever no session is open — on first run
// and every time "New evaluation" is pressed. It leads with the chat input rather than a
// button: the way in is to start describing the product, exactly as a chat app opens. Two
// alternatives sit below it, each opening its own screen in place of the conversation.
//
// The composer itself is rendered by the shell beneath this, so this component owns only the
// heading and the two alternatives — the input is one consistent control across every screen.

import type { ComponentType, ReactNode } from "react";
import { FilePen, FolderGit2 } from "lucide-react";
import { Chevron, Panel } from "./ui";

export function Intro({
  composer,
  onAuthor,
  onConnectRepo,
}: {
  composer: ReactNode;
  // The way into the hand-authoring door.
  onAuthor: () => void;
  // The way into the repository facade — a real screen with a gated submission (add-locked-repo-entry).
  onConnectRepo: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="flex w-full max-w-3xl flex-col gap-8">
          <header className="flex flex-col gap-2 text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              What are we evaluating?
            </h1>
          </header>

          {/* Composer and the two entries read as one group: same width, stacked close, so the
              cards sit just beneath the input rather than floating off on their own. */}
          <div className="flex flex-col gap-3">
            {composer}

            <div className="grid grid-cols-2 gap-2">
              <LiveEntry
                icon={FolderGit2}
                title="Connect a repo"
                detail="Point the wizard at your codebase and let it read the product for you."
                onClick={onConnectRepo}
              />
              <LiveEntry
                icon={FilePen}
                title="Write the experiment yourself"
                detail="Skip the interview and fill in the tasks, personas and metrics directly."
                onClick={onAuthor}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function LiveEntry({
  icon: Icon,
  title,
  detail,
  onClick,
}: {
  icon: ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="text-left">
      <Panel className="flex items-center gap-3 p-4 transition-colors hover:bg-muted">
        {/* A leading icon in a fixed-width gutter, so the two cards' titles line up down a
            common left edge however wide each icon draws. Neutral, in currentColor — no accent,
            since these are entries, not state. */}
        <span className="flex w-6 shrink-0 justify-center text-muted-foreground">
          <Icon size={18} strokeWidth={1.75} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-sm font-medium text-foreground">{title}</span>
          <span className="text-xs text-muted-foreground">{detail}</span>
        </div>
        <Chevron dir="right" className="text-muted-foreground" />
      </Panel>
    </button>
  );
}
