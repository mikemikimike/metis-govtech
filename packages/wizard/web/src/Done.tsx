// The end of the interview. Two actions, and the asymmetry between them is the point: the
// document is built, so downloading it is a real link; running the evaluation belongs to the
// engine, which this door is forbidden to import, so that button is present but disabled and
// labelled as such. Nothing here reaches across the dependency boundary.

import { api } from "./api";
import { Button, cn, Panel } from "./ui";

export function Done({ sessionId }: { sessionId: string }) {
  return (
    <Panel className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-foreground">
          Your evaluation is ready
        </h2>
        <p className="text-sm text-muted-foreground">
          The document on the right compiles to an experiment definition. Download it to run
          later, or hand it to the engine once that's wired up.
        </p>
      </div>

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
