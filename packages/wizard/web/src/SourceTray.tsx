// The source tray depicts future source features; it does not upload anything.
//
// This component accepts no source values and owns no file objects. Its controls show the shape
// of the planned paths, but every source input is disabled from the first render. The only live
// state is the Codebase Link/ZIP presentation switch. Nothing here contacts an address, reads a
// file, creates a interview or depicts a result.

import { X } from "lucide-react";
import { useState } from "react";
import { Button, Mono, Tooltip } from "./ui";

export type SourceTrayKind = "documents" | "codebase" | "traces";

export function SourceTray({
  kind,
  onClose,
}: {
  kind: SourceTrayKind;
  onClose: () => void;
}) {
  const [method, setMethod] = useState<"link" | "zip">("zip");
  const title = {
    documents: "Documents",
    codebase: "Source Code",
    traces: "Traces",
  }[kind];

  return (
    <section
      aria-label={`${title} source`}
      className="relative z-0 mx-auto -mt-4 flex min-h-16 w-[95%] flex-wrap items-center gap-3 rounded-2xl border border-border bg-card px-4 pb-3 pt-7 text-muted-foreground"
    >
      <h2 className="shrink-0 text-sm font-medium text-foreground">{title}</h2>
      <span aria-hidden className="h-5 w-px shrink-0 bg-border" />

      <div className="flex min-w-0 flex-1 items-center">
        {kind === "codebase" ? (
          <CodebaseFields method={method} onMethodChange={setMethod} />
        ) : (
          <FileFields kind={kind} />
        )}
      </div>

      <button
        type="button"
        aria-label={`Close ${title.toLowerCase()} source`}
        title="Close source"
        onClick={onClose}
        className="ml-auto shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
      >
        <X size={16} strokeWidth={1.75} aria-hidden />
      </button>
    </section>
  );
}

function CodebaseFields({
  method,
  onMethodChange,
}: {
  method: "link" | "zip";
  onMethodChange: (method: "link" | "zip") => void;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
      <div className="flex shrink-0 gap-1" role="group" aria-label="Source Code source method">
        <Button
          type="button"
          variant="ghost"
          active={method === "zip"}
          aria-pressed={method === "zip"}
          className="px-2 py-1 text-xs"
          onClick={() => onMethodChange("zip")}
        >
          ZIP
        </Button>
        <Button
          type="button"
          variant="ghost"
          active={method === "link"}
          aria-pressed={method === "link"}
          className="px-2 py-1 text-xs"
          onClick={() => onMethodChange("link")}
        >
          Link
        </Button>
      </div>

      {method === "link" ? <RepositoryLinkField /> : <ArchiveField />}
    </div>
  );
}

function RepositoryLinkField() {
  return (
    <Tooltip
      label="Source code upload is not supported yet"
      focusable
      className="min-w-48 flex-1"
      ariaLabel="Repository link. Source code upload is not supported yet"
    >
      <input
        className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-45"
        placeholder="https://sgts.gitlab-dedicated.com/users/name"
        disabled
        readOnly
        aria-label="Repository link"
      />
    </Tooltip>
  );
}

function ArchiveField() {
  return (
    <Tooltip
      label="Source code upload is not supported yet"
      focusable
      className="w-fit"
      ariaLabel="ZIP archive. Source code upload is not supported yet"
    >
      <div className="flex items-center gap-2">
        <Button type="button" variant="secondary" className="py-1 text-xs" disabled>
          Choose ZIP file
        </Button>
        <Mono className="whitespace-nowrap">No file chosen</Mono>
      </div>
    </Tooltip>
  );
}

function FileFields({ kind }: { kind: "documents" | "traces" }) {
  const label = kind === "documents" ? "Choose documents" : "Choose trace file";
  const tooltip =
    kind === "documents"
      ? "Document upload is not supported yet"
      : "Trace upload is not supported yet";

  return (
    <Tooltip
      label={tooltip}
      focusable
      className="w-fit"
      ariaLabel={`${label}. ${tooltip}`}
    >
      <div className="flex items-center gap-2">
        <Button type="button" variant="secondary" className="py-1 text-xs" disabled>
          {label}
        </Button>
        <Mono className="whitespace-nowrap">No file chosen</Mono>
      </div>
    </Tooltip>
  );
}
