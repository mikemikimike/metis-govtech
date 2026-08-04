// The end of the interview. Two actions, and the asymmetry between them is the point: the
// document is built, so downloading it is a real link; running the evaluation belongs to the
// engine, which this door is forbidden to import, so that button is present but disabled and
// labelled as such. Nothing here reaches across the dependency boundary.

import { api } from "./api";
import { Button, cn, Panel } from "./ui";

export function Done({ sessionId }: { sessionId: string }) {
  return (
    // Reaching the end is a state worth marking, but not with a coloured left-rule — that reads
    // as generated chrome and breaks the borders-not-accents rule. The panel stays a plain
    // bordered card; the accent lands only on the heading, where "ready" is the state being
    // signalled. The download stays a near-black primary — the accent marks the state, it does
    // not fill the action.
    <Panel className="flex flex-col gap-4 p-5">
      <h2 className="text-base font-semibold text-accent">
        Your evaluation is ready
      </h2>

      <div className="flex flex-wrap items-center gap-2">
        <a
          href={api.experimentUrl(sessionId)}
          download
          className={cn(
            "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5",
            "border border-primary bg-primary text-sm font-medium text-primary-foreground",
            "transition-colors duration-150 hover:opacity-90",
          )}
        >
          Download experiment.yaml
        </a>

        {/* Wired to the engine later — the wizard package must not depend on it, so the
            control ships disabled rather than absent. */}
        <Button variant="secondary" disabled title="Coming soon">
          Run evaluation
        </Button>
      </div>
    </Panel>
  );
}
