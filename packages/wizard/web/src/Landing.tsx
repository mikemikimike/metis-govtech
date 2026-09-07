// The opening screen, shown in the middle region whenever no interview is open — on first run
// and every time "New evaluation" is pressed. It leads with the chat input rather than a
// button: the way in is to start describing the product, exactly as a chat app opens.
//
// Reference material belongs inside the composer. This module owns the source menu and passes it
// into the composer's opening-only foot row; the in-conversation composer never receives it.

import type { ComponentType, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { FilePen, Plus } from "lucide-react";
import { SourceTray, type SourceTrayKind } from "./SourceTray";
import { Chevron, Tooltip } from "./ui";

export function Intro({
  openingQuestion,
  composer,
  selectedSource,
  onAuthor,
  onSource,
  onCloseSource,
}: {
  openingQuestion: string;
  // Landing owns the menu, so the shell supplies a composer factory rather than an opaque node.
  composer: (sourceControl: ReactNode) => ReactNode;
  // One source depiction can peek beneath the composer without leaving the opening chat screen.
  selectedSource: SourceTrayKind | null;
  // The way into the hand-authoring door.
  onAuthor: () => void;
  onSource: (source: SourceTrayKind) => void;
  onCloseSource: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col">
      <div className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="flex w-full max-w-3xl flex-col gap-8">
          <header className="flex flex-col gap-2 text-center">
            <h1 className="text-2xl font-semibold text-foreground">
              {openingQuestion}
            </h1>
          </header>

          <div className="flex flex-col gap-3">
            <div className="flex flex-col">
              <div className="relative z-10">
                {composer(<SourceMenu onSource={onSource} />)}
              </div>
              {selectedSource && (
                <SourceTray
                  key={selectedSource}
                  kind={selectedSource}
                  onClose={onCloseSource}
                />
              )}
            </div>

            <LiveEntry
              icon={FilePen}
              title="Write the experiment yourself"
              detail="Skip the interview and fill in the scenarios, personas and metrics directly."
              onClick={onAuthor}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function SourceMenu({
  onSource,
}: {
  onSource: (source: SourceTrayKind) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const addRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    itemRefs.current[0]?.focus();

    const closeOnOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      addRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const focusItem = (index: number) => {
    const count = itemRefs.current.length;
    if (count === 0) return;
    itemRefs.current[(index + count) % count]?.focus();
  };

  const handleItemKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(index + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusItem(itemRefs.current.length - 1);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <Tooltip label="Add source" className="w-fit">
        <button
          ref={addRef}
          type="button"
          aria-label="Add source"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Plus size={16} strokeWidth={1.75} aria-hidden />
        </button>
      </Tooltip>

      {open && (
        <div
          role="menu"
          aria-label="Sources"
          className="absolute bottom-full left-0 z-20 mb-2 flex w-48 flex-col overflow-hidden rounded-2xl border border-border bg-card p-1 text-card-foreground"
        >
          <SourceRow
            index={0}
            label="Documents"
            onSelect={() => {
              setOpen(false);
              onSource("documents");
            }}
            onKeyDown={handleItemKeyDown}
            itemRef={(element) => {
              itemRefs.current[0] = element;
            }}
          />
          <SourceRow
            index={1}
            label="Source Code"
            onSelect={() => {
              setOpen(false);
              onSource("codebase");
            }}
            onKeyDown={handleItemKeyDown}
            itemRef={(element) => {
              itemRefs.current[1] = element;
            }}
          />
          <SourceRow
            index={2}
            label="Traces"
            onSelect={() => {
              setOpen(false);
              onSource("traces");
            }}
            onKeyDown={handleItemKeyDown}
            itemRef={(element) => {
              itemRefs.current[2] = element;
            }}
          />
        </div>
      )}
    </div>
  );
}

function SourceRow({
  index: _index,
  label,
  onSelect,
  onKeyDown,
  itemRef,
}: {
  index: number;
  label: string;
  onSelect: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => void;
  itemRef: (element: HTMLButtonElement | null) => void;
}) {
  return (
    <button
      ref={itemRef}
      type="button"
      role="menuitem"
      onClick={onSelect}
      onKeyDown={(event) => onKeyDown(event, _index)}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-muted"
    >
      <span>{label}</span>
    </button>
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
    <button type="button" onClick={onClick} className="w-full text-left">
      {/* This is the lone working alternative to the prose composer. It fills the same width so
          its singular position reads as deliberate after source paths move into the menu. */}
      <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-muted">
        <span className="flex w-6 shrink-0 justify-center text-muted-foreground">
          <Icon size={18} strokeWidth={1.75} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-sm font-medium text-foreground">{title}</span>
          <span className="text-xs text-muted-foreground">{detail}</span>
        </div>
        <Chevron dir="right" className="text-muted-foreground" />
      </div>
    </button>
  );
}
