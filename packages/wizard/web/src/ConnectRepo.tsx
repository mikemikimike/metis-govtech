// The "connect a repo" door — a depiction, not a feature.
//
// ── THIS SCREEN DELIBERATELY DOES NOTHING BEHIND ITS SUBMIT ───────────────────────────────────
// Reading a repository to draft an evaluation is not built. This screen shows the *shape* of that
// feature — what we would ask for — with the submission plainly gated. The omissions below are
// specified, not oversights; a future contributor "completing" this by adding an upload would be
// changing the specification, not filling a gap:
//
//   • The chosen archive's contents NEVER leave the browser. The file control reads the chosen
//     file's *name* only, for display — it never calls `.text()`, `.arrayBuffer()`, or `.stream()`,
//     and there is no endpoint that would receive an upload.
//   • The address is NEVER validated or contacted. It is a text field that looks like one.
//   • NOTHING is retained. Neither value survives leaving the screen; no session is created; no
//     draft is offered on return.
//   • NO result is depicted. The screen shows what would be asked for, never what would come back.
//
// The lock sits on the submit control, not on the fields: the user fills the form and meets the
// lock where an expectation actually forms, and the lock is visible before activation so it does
// not read as a bait-and-switch. Its explanation names the paths that do work, so a person who
// walks in is redirected rather than stranded.

import { ArrowLeft, Lock } from "lucide-react";
import { useState } from "react";
import { Button, cn, Mono } from "./ui";

export function ConnectRepo({ onBack }: { onBack: () => void }) {
  const [address, setAddress] = useState("");
  // The chosen archive's *name* only. The File object itself is never held, read or sent — the
  // display name is all this screen ever learns about it.
  const [archiveName, setArchiveName] = useState<string | null>(null);
  // Set only when the locked submit is activated, so the explanation appears where the
  // expectation forms rather than sitting on the screen from the start.
  const [blocked, setBlocked] = useState(false);

  return (
    <div className="flex-1 overflow-y-auto px-10 py-8">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <div className="flex flex-col gap-4">
          <button
            type="button"
            onClick={onBack}
            className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={14} strokeWidth={1.75} aria-hidden />
            Back
          </button>
          <header className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold text-foreground">
              Connect a repo
            </h1>
            <p className="text-sm text-muted-foreground">
              Point the wizard at your codebase and it drafts the evaluation
              from what it reads.
            </p>
          </header>
        </div>

        <section className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">
              Repository address
            </span>
            <input
              className="rounded-md border border-input bg-background p-2 text-sm"
              placeholder="https://gitlab.com/team/product.git"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">
              Source archive
            </span>
            <div className="flex items-center gap-3">
              <label
                className={cn(
                  "cursor-pointer rounded-md border border-border bg-secondary px-3 py-1.5",
                  "text-sm font-medium text-secondary-foreground transition-colors hover:bg-muted",
                )}
              >
                Choose file
                <input
                  type="file"
                  accept=".zip"
                  className="hidden"
                  // The name is read here for display; the file is not kept, opened or read.
                  onChange={(e) =>
                    setArchiveName(e.target.files?.[0]?.name ?? null)
                  }
                />
              </label>
              {archiveName ? (
                <Mono>{archiveName}</Mono>
              ) : (
                <span className="text-xs text-muted-foreground">
                  No file chosen
                </span>
              )}
            </div>
          </label>
        </section>

        <section className="flex flex-col gap-2 border-t border-border pt-6">
          <div className="flex items-center gap-3">
            {/* Locked before activation, not after: the lock icon states the gate up front. */}
            <Button variant="primary" onClick={() => setBlocked(true)}>
              <Lock size={14} strokeWidth={1.75} aria-hidden />
              Analyse repository
            </Button>
          </div>
          {blocked && (
            <p className="text-sm text-muted-foreground" role="status">
              Repository analysis isn't available yet. To evaluate a product
              now, describe it to the wizard or write the experiment yourself
              from the opening screen.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
