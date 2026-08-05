import { Minus, Plus, X } from "lucide-react";
import { useState } from "react";
import { Button, cn, Mono } from "./ui";

export function NumberInput({
  value,
  min = 1,
  max,
  disabled = false,
  onChange,
  onCommit,
}: {
  value: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  onChange: (value: number) => void;
  onCommit?: (value: number) => void;
}) {
  const clamp = (value: number) =>
    Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min, value));

  return (
    <div
      className={cn(
        "flex w-full max-w-48 items-stretch overflow-hidden rounded-md border border-input bg-background",
        "transition-colors focus-within:border-accent",
        disabled && "opacity-45",
      )}
    >
      <Stepper
        label="Decrease"
        disabled={disabled || value <= min}
        onClick={() => {
          const next = clamp(value - 1);
          onChange(next);
          onCommit?.(next);
        }}
      >
        <Minus size={14} strokeWidth={1.75} aria-hidden />
      </Stepper>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(event) =>
          onChange(clamp(Math.round(Number(event.target.value) || min)))
        }
        onBlur={() => onCommit?.(clamp(value))}
        onKeyDown={(event) => {
          if (event.key === "Enter") onCommit?.(clamp(value));
        }}
        className={cn(
          "min-w-0 flex-1 bg-transparent p-2 text-center text-sm focus:outline-none",
          "[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
        )}
      />
      <Stepper
        label="Increase"
        disabled={disabled || (max != null && value >= max)}
        onClick={() => {
          const next = clamp(value + 1);
          onChange(next);
          onCommit?.(next);
        }}
      >
        <Plus size={14} strokeWidth={1.75} aria-hidden />
      </Stepper>
    </div>
  );
}

export function FileReferenceListInput({
  value,
  onChange,
  disabled = false,
  placeholder = "report.pdf",
}: {
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const name = draft.trim();
    if (disabled || !name || value.includes(name)) return;
    onChange([...value, name]);
    setDraft("");
  };

  return (
    <div className="flex w-full flex-col gap-2">
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((name) => (
            <span
              key={name}
              className="flex items-center gap-1.5 rounded-md border border-border px-2 py-0.5"
            >
              <Mono>{name}</Mono>
              <button
                type="button"
                aria-label={`Remove ${name}`}
                disabled={disabled}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
                onClick={() => onChange(value.filter((item) => item !== name))}
              >
                <X size={12} strokeWidth={2} aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex w-full gap-2">
        <input
          className="flex-1 rounded-md border border-input bg-background p-2 text-sm"
          placeholder={placeholder}
          value={draft}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={add}
          disabled={disabled || !draft.trim()}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

function Stepper({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      className={cn(
        "flex h-8 w-10 shrink-0 items-center justify-center px-2 text-lg leading-none text-muted-foreground transition-colors",
        "hover:bg-muted hover:text-foreground",
        "disabled:pointer-events-none disabled:opacity-40",
      )}
    >
      {children}
    </button>
  );
}
