import { Minus, Plus, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import type { FixtureMetadata } from "./api";
import {
  ACCEPTED_FIXTURE_EXTENSIONS,
  FIXTURE_MAX_FILES,
  validateFixtureSelection,
} from "./fixture-policy";
import { cn, Mono } from "./ui";

export {
  ACCEPTED_FIXTURE_EXTENSIONS,
  FIXTURE_MAX_BYTES,
  FIXTURE_MAX_FILES,
  fixtureNames,
} from "./fixture-policy";

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

export function FixtureInput({
  value,
  onChange,
  onUpload,
  disabled = false,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  onUpload: (files: File[]) => Promise<FixtureMetadata[]>;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addFiles = async (files: File[]) => {
    if (disabled || uploading || files.length === 0) return;
    setError(null);
    try {
      if (files.length > FIXTURE_MAX_FILES) {
        setError(`You can upload up to ${FIXTURE_MAX_FILES} files at a time.`);
        return;
      }
      const names = validateFixtureSelection(files, []);
      setUploading(true);
      const added = await onUpload(files);
      const approved = added.map((item) => item.name);
      onChange([...value, ...approved.filter((name) => !value.includes(name))]);
      // `names` is evaluated before the request so browser-only tests and old servers still get
      // a useful local validation path if a response carries no added rows.
      if (approved.length === 0 && names.length > 0) onChange([...value, ...names]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't upload the files.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const toggle = (name: string) => {
    if (disabled || uploading) return;
    onChange(
      value.includes(name)
        ? value.filter((item) => item !== name)
        : [...value, name],
    );
  };

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <label
          className={cn(
            "inline-flex h-8 w-fit shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-md border border-input bg-background px-2.5 text-sm",
            "transition-colors hover:border-accent hover:bg-accent/5 focus-within:border-accent",
            (disabled || uploading) && "pointer-events-none opacity-45",
          )}
        >
          <Upload size={14} strokeWidth={1.75} aria-hidden />
          Choose file
          <input
            ref={inputRef}
            type="file"
            multiple
            disabled={disabled || uploading}
            accept={ACCEPTED_FIXTURE_EXTENSIONS.map((item) => `.${item}`).join(",")}
            className="sr-only"
            aria-label="Choose fixture files"
            onChange={(event) => void addFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          {uploading && (
            <span className="truncate text-sm text-muted-foreground">Uploading…</span>
          )}
          {!uploading && value.length === 0 && (
            <span className="truncate text-sm text-muted-foreground">No file chosen</span>
          )}
          {!uploading &&
            value.length > 0 &&
            value.map((name) => (
              <span
                key={name}
                className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-border px-2 py-0.5"
              >
                <Mono className="truncate">{name}</Mono>
                <button
                  type="button"
                  aria-label={`Remove ${name}`}
                  disabled={disabled || uploading}
                  className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-40"
                  onClick={() => toggle(name)}
                >
                  <X size={12} strokeWidth={2} aria-hidden />
                </button>
              </span>
            ))}
        </div>
      </div>
      {error && (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      )}
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
