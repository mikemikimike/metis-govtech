import { Plus, X } from "lucide-react";
import type { ReactNode } from "react";

export function DocumentTray({
  onClose,
  children,
}: {
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <section
      aria-label="Documents"
      className="relative z-0 mx-auto -mt-4 flex min-h-16 w-[95%] flex-wrap items-start gap-3 rounded-2xl border border-border bg-card px-4 pb-3 pt-7 text-muted-foreground"
    >
      <h2 className="shrink-0 text-sm font-medium text-foreground">
        Documents
      </h2>
      <span aria-hidden className="h-5 w-px shrink-0 bg-border" />
      <div className="flex min-w-0 flex-1 flex-col items-stretch">
        {children}
      </div>
      <button
        type="button"
        aria-label="Close documents"
        onClick={onClose}
        className="ml-auto shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
      >
        <X size={16} strokeWidth={1.75} aria-hidden />
      </button>
    </section>
  );
}

export function AddDocuments({
  onOpen,
  disabled,
  expanded,
}: {
  onOpen: () => void;
  disabled: boolean;
  expanded: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={disabled}
      aria-label="Add documents"
      aria-expanded={expanded}
      title="Add documents"
      className="inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-45"
    >
      <Plus size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}
