// The opening screen, shown in the middle region whenever no session is open — on first run
// and every time "New evaluation" is pressed. It leads with the chat input rather than a
// button: the way in is to start describing the product, exactly as a chat app opens. The two
// alternatives below are present but disabled, so the shape of what's coming is visible
// without pretending it works yet.
//
// The composer itself is rendered by the shell beneath this, so this component owns only the
// heading and the two alternatives — the input is one consistent control across every screen.

import type { ReactNode } from "react";
import { cn, Panel } from "./ui";

export function Intro({ composer }: { composer: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="flex w-full max-w-3xl flex-col gap-8">
          <header className="flex flex-col gap-2 text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              What are we evaluating?
            </h1>
            <p className="text-sm text-muted-foreground">
              Describe your agent and the wizard turns it into behaviours, criteria and tasks
              you can run.
            </p>
          </header>

          {composer}

          <div className="flex flex-col gap-2">
            <SoonEntry
              title="Connect a repo"
              detail="Point the wizard at your codebase and let it read the product for you."
            />
            <SoonEntry
              title="I know what to evaluate"
              detail="Skip the interview and write the behaviours yourself."
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function SoonEntry({ title, detail }: { title: string; detail: string }) {
  return (
    <Panel
      className={cn(
        "flex items-center justify-between gap-3 p-4 opacity-55",
        "cursor-not-allowed",
      )}
      aria-disabled
    >
      <div className="flex flex-col">
        <span className="text-sm font-medium text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">{detail}</span>
      </div>
      <span className="rounded border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        soon
      </span>
    </Panel>
  );
}
