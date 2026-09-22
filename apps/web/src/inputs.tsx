import { Minus, Plus } from "lucide-react";
import { cn } from "./ui";

export function NumberInput({
  value,
  min = 1,
  max,
  disabled = false,
  ariaLabel,
  onChange,
  onCommit,
}: {
  value: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  ariaLabel?: string;
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
        aria-label={ariaLabel}
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
