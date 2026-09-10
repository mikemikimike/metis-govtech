import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Code2,
  ClipboardCheck,
  PanelLeft,
  PanelRight,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type {
  InterviewSummary,
  LocalInterviewRecord,
  Perspective,
  PerspectiveDefinition,
  UserResponse,
} from "./transport/api";
import { api, TransportError, toSummary } from "./transport/api";
import { Composer, Transcript } from "./Conversation";
import { Done } from "./Done";
import { Profile, stepPosition } from "./Profile";
import { InterviewRail } from "./InterviewRail";
import { cn } from "./ui";
import {
  InterviewRepository,
  emptyRecord,
  removeUnreferencedFixtures,
  type LocalStorageProblem,
  withProvisionalFixtures,
} from "./storage/repository";
import { profileHasCriteria } from "./metrics";
import { downloadArchive } from "./download";
import {
  applyEnd,
  applyTurn,
  startTranscript,
  toPresentation,
} from "./wizard/transcript";

const DOCUMENT_WIDTH_DEFAULT = 42;
const DOCUMENT_WIDTH_MIN = 24;
const DOCUMENT_WIDTH_MAX = 60;
const SELECTED_INTERVIEW_KEY = "metis-web-selected-interview";
const repository = new InterviewRepository();
type WizardConfig = Awaited<ReturnType<typeof api.config>>;

const PERSPECTIVE_ICONS: Record<Perspective, LucideIcon> = {
  end_user: UserRound,
  engineer: Code2,
  compliance: ClipboardCheck,
  security: ShieldCheck,
};

type RetryIntent =
  | {
      kind: "turn";
      response: UserResponse;
      files?: File[];
      removedFixtures?: string[];
    }
  | { kind: "end" }
  | { kind: "package"; record: LocalInterviewRecord };

export function App() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [storageProblems, setStorageProblems] = useState<
    readonly LocalStorageProblem[]
  >([]);
  const [record, setRecord] = useState<LocalInterviewRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [workingStatus, setWorkingStatus] = useState("Working…");
  const [wizardConfig, setWizardConfig] = useState<WizardConfig | null>(null);
  const [selectedPerspective, setSelectedPerspective] =
    useState<Perspective>("end_user");
  const [error, setError] = useState<string | null>(null);
  const [retryIntent, setRetryIntent] = useState<RetryIntent | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [railOpen, setRailOpen] = useState(true);
  const [profileOpen, setProfileOpen] = useState(true);
  const [documentWidth, setDocumentWidth] = useState(DOCUMENT_WIDTH_DEFAULT);
  const [showMetrics, setShowMetrics] = useState(false);
  const [metricCatalogue, setMetricCatalogue] = useState<Awaited<
    ReturnType<typeof api.metrics>
  > | null>(null);
  const [metricState, setMetricState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const metricRequest = useRef<Promise<
    Awaited<ReturnType<typeof api.metrics>>
  > | null>(null);
  const restored = useRef(false);

  const view = useMemo(() => record && toPresentation(record), [record]);
  const pending = record?.state.pending ?? undefined;
  const metricByFqn = useMemo(
    () =>
      new Map((metricCatalogue ?? []).map((metric) => [metric.fqn, metric])),
    [metricCatalogue],
  );
  const hasCriteria = view ? profileHasCriteria(view.profile) : false;
  const showError = useCallback((cause: unknown, intent?: RetryIntent) => {
    setError(errorMessage(cause));
    setRetryIntent(isRetryable(cause) ? (intent ?? null) : null);
  }, []);

  useEffect(() => {
    setShowMetrics(false);
  }, [record?.id]);

  useEffect(() => {
    void api.config().then(
      (config) => {
        setWizardConfig(config);
        setWorkingStatus(config.working_status);
      },
      () => undefined,
    );
  }, []);

  const refreshList = useCallback(async () => {
    const rows = await repository.list();
    setInterviews(rows.map(toSummary));
    setStorageProblems([...repository.problems]);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const rows = await repository.list();
        setInterviews(rows.map(toSummary));
        setStorageProblems([...repository.problems]);
        if (!restored.current) {
          const selectedId = readSelectedInterview();
          setRecord(
            rows.find((row) => row.id === selectedId) ?? rows[0] ?? null,
          );
        }
      } catch (cause) {
        showError(cause);
      } finally {
        restored.current = true;
        setLoaded(true);
      }
    })();
  }, [showError]);
  useEffect(() => {
    if (!hasCriteria || metricRequest.current) return;
    setMetricState("loading");
    const request = api.metrics();
    metricRequest.current = request;
    void request.then(
      (rows) => {
        setMetricCatalogue(rows);
        setMetricState("ready");
      },
      () => setMetricState("error"),
    );
  }, [hasCriteria]);

  const open = useCallback(
    async (id: string) => {
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        const next = await repository.read(id);
        if (!next) throw new Error("This local Interview is not available.");
        setRecord(next);
        rememberSelectedInterview(id);
      } catch (cause) {
        showError(cause);
      } finally {
        setBusy(false);
      }
    },
    [showError],
  );
  const startNew = useCallback(() => {
    setRecord(null);
    setError(null);
    setRetryIntent(null);
    forgetSelectedInterview();
  }, []);

  const beginWithMessage = useCallback(
    async (
      description: string,
      perspective: Perspective = selectedPerspective,
    ) => {
      if (busy) return;
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        const result = await api.start(description, perspective);
        const next = emptyRecord(
          crypto.randomUUID(),
          result.state,
          result.stage,
          startTranscript(description, result.state),
        );
        await repository.put(next);
        setRecord(next);
        rememberSelectedInterview(next.id);
        await refreshList();
      } catch (cause) {
        showError(cause);
      } finally {
        setBusy(false);
      }
    },
    [busy, refreshList, selectedPerspective, showError],
  );

  const saveResult = useCallback(
    async (next: LocalInterviewRecord) => {
      const previous = record;
      try {
        await repository.put(next);
        setRecord(next);
        await refreshList();
      } catch (cause) {
        if (previous) setRecord(previous);
        throw cause;
      }
    },
    [record, refreshList],
  );

  const packageAndDownload = useCallback(
    async (localRecord: LocalInterviewRecord) => {
      const archive = await api.package(
        localRecord.state.profile,
        localRecord.fixtures,
      );
      downloadArchive(archive);
    },
    [],
  );

  const showPackageError = useCallback(
    (cause: unknown, localRecord: LocalInterviewRecord) => {
      setError(errorMessage(cause));
      // Packaging is request-scoped and idempotent. A retry never invokes another model turn,
      // including when the API returned a correctable validation error.
      setRetryIntent({ kind: "package", record: localRecord });
    },
    [],
  );

  const downloadCurrent = useCallback(
    async (localRecord: LocalInterviewRecord) => {
      if (busy) return;
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        await packageAndDownload(localRecord);
      } catch (cause) {
        showPackageError(cause, localRecord);
      } finally {
        setBusy(false);
      }
    },
    [busy, packageAndDownload, showPackageError],
  );

  const send = useCallback(
    async (
      response: UserResponse,
      files: readonly File[] = [],
      removedFixtures: readonly string[] = [],
    ) => {
      if (!record?.state.pending || busy) return;
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        await withProvisionalFixtures(
          repository,
          record,
          files,
          async (base) => {
            if (files.length > 0) setRecord(base);
            const result = await api.respond(
              base.state,
              base.state.pending?.request_id ?? "",
              response,
            );
            const next = removeUnreferencedFixtures(
              applyTurn(base, result, response),
              removedFixtures,
            );
            await saveResult(next);
          },
        );
      } catch (cause) {
        if (files.length > 0) {
          // A successful rollback is already durable. Read it back so the rendered record also
          // reflects the exact state that will survive a reload. If rollback failed, this read
          // gives the user the durable record without claiming that it was restored.
          try {
            const restored = await repository.read(record.id);
            if (restored) setRecord(restored);
          } catch {
            // Keep the operation error visible; the durable record may be inspected on reload.
          }
        }
        showError(cause, {
          kind: "turn",
          response,
          files: [...files],
          removedFixtures: [...removedFixtures],
        });
      } finally {
        setBusy(false);
      }
    },
    [busy, record, saveResult, showError],
  );

  const finish = useCallback(async () => {
    if (!record || busy) return;
    setBusy(true);
    setError(null);
    setRetryIntent(null);
    try {
      const result = await api.end(record.state);
      const next = applyEnd(record, result);
      await saveResult(next);
      if (result.outcome === "done") {
        try {
          await packageAndDownload(next);
        } catch (cause) {
          showPackageError(cause, next);
        }
      }
    } catch (cause) {
      showError(cause, { kind: "end" });
    } finally {
      setBusy(false);
    }
  }, [
    busy,
    packageAndDownload,
    record,
    saveResult,
    showError,
    showPackageError,
  ]);

  const retry = useCallback(() => {
    const intent = retryIntent;
    if (!intent) return;
    setRetryIntent(null);
    setError(null);
    if (intent.kind === "turn")
      void send(intent.response, intent.files, intent.removedFixtures);
    else if (intent.kind === "end") void finish();
    else void downloadCurrent(intent.record);
  }, [downloadCurrent, finish, retryIntent, send]);

  const remove = useCallback(
    async (id: string) => {
      try {
        await repository.delete(id);
        if (record?.id === id) {
          setRecord(null);
          forgetSelectedInterview();
        }
        await refreshList();
      } catch (cause) {
        showError(cause);
      }
    },
    [record?.id, refreshList, showError],
  );

  if (!loaded) return null;
  const showDocument = view !== null;

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {railOpen ? (
        <InterviewRail
          interviews={interviews}
          problems={storageProblems}
          currentId={record?.id ?? null}
          busy={busy}
          onOpen={open}
          onNew={startNew}
          onDelete={remove}
          onCollapse={() => setRailOpen(false)}
        />
      ) : (
        <EdgeStrip
          side="left"
          label="Show interviews"
          onClick={() => setRailOpen(true)}
        />
      )}
      <main className="flex min-w-0 flex-1 flex-col">
        {error && (
          <Banner
            message={error}
            onDismiss={() => {
              setError(null);
              setRetryIntent(null);
            }}
            onRetry={retryIntent ? retry : undefined}
          />
        )}
        {view === null ? (
          <OpeningScreen
            config={wizardConfig}
            busy={busy}
            perspective={selectedPerspective}
            onPerspective={setSelectedPerspective}
            onBegin={(description, perspective) =>
              void beginWithMessage(description, perspective)
            }
          />
        ) : (
          <>
            <div
              key={view.id}
              className="quiet-scrollbar animate-enter-conversation flex-1 overflow-y-auto py-10"
            >
              <div className="mx-auto flex w-4/5 flex-col gap-8">
                <Transcript
                  requests={view.requests}
                  busy={busy}
                  onRespond={send}
                />
                {busy && <ThinkingLine message={workingStatus} />}
                {view.done && <Done />}
              </div>
            </div>
            <div className="w-full">
              <Composer
                request={pending}
                busy={busy}
                onSend={(text) => void send({ type: "chat", text })}
              />
            </div>
          </>
        )}
      </main>
      {showDocument &&
        view &&
        (profileOpen ? (
          <>
            <ResizeHandle width={documentWidth} onWidth={setDocumentWidth} />
            <aside
              style={{ width: `${documentWidth}%` }}
              className="min-w-[20rem] shrink-0 border-l border-border bg-muted"
            >
              <Profile
                key={view.id}
                profile={view.profile}
                position={stepPosition(view.requests)}
                interviewStep={view.stage}
                busy={busy}
                showMetrics={showMetrics}
                onShowMetricsChange={setShowMetrics}
                metricByFqn={metricByFqn}
                metricsLoading={
                  metricState === "idle" || metricState === "loading"
                }
                metricsError={metricState === "error"}
                onCollapse={() => setProfileOpen(false)}
                done={view.done}
                onFinish={() => void finish()}
                onDownload={() => {
                  if (record) void downloadCurrent(record);
                }}
              />
            </aside>
          </>
        ) : (
          <EdgeStrip
            side="right"
            label="Show document"
            onClick={() => setProfileOpen(true)}
          />
        ))}
    </div>
  );
}

export function OpeningScreen({
  config,
  busy,
  perspective,
  onPerspective,
  onBegin,
}: {
  config: WizardConfig | null;
  busy: boolean;
  perspective: Perspective;
  onPerspective: (perspective: Perspective) => void;
  onBegin: (description: string, perspective: Perspective) => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6">
      <div className="flex w-full max-w-2xl flex-col gap-6">
        <h1 className="text-center text-2xl font-semibold text-foreground">
          {config?.opening_question}
        </h1>
        <div className="flex flex-col gap-3">
          <Composer
            request={undefined}
            busy={busy}
            alwaysEnabled
            leadingIcon
            bare
            placeholder={config?.opening_question}
            onSend={(description) => onBegin(description, perspective)}
          />
          <PerspectivePicker
            perspectives={config?.perspectives ?? []}
            selected={perspective}
            onSelect={onPerspective}
          />
        </div>
      </div>
    </div>
  );
}

export function PerspectivePicker({
  perspectives,
  selected,
  onSelect,
}: {
  perspectives: PerspectiveDefinition[];
  selected: Perspective;
  onSelect: (perspective: Perspective) => void;
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="text-sm text-muted-foreground">
        Who is this evaluation for?
      </legend>
      <div
        role="radiogroup"
        aria-label="Who is this evaluation for?"
        className="flex flex-col gap-2"
      >
        {perspectives.map((perspective) => {
          const Icon = PERSPECTIVE_ICONS[perspective.id];
          const active = perspective.id === selected;
          return (
            <button
              key={perspective.id}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={`${perspective.label}: ${perspective.question}`}
              onClick={() => onSelect(perspective.id)}
              className={cn(
                "group relative flex w-full items-center gap-3 overflow-hidden rounded-xl border px-4 py-3 text-left",
                "transition-colors duration-200",
                active
                  ? "border-accent bg-accent/10 text-foreground"
                  : "border-border bg-card text-card-foreground hover:border-accent/40 hover:bg-accent/10",
              )}
            >
              <Icon
                size={18}
                strokeWidth={1.75}
                aria-hidden
                className={cn(
                  "shrink-0 transition-colors duration-200",
                  active
                    ? "text-accent"
                    : "text-muted-foreground group-hover:text-accent group-focus-visible:text-accent",
                )}
              />
              <span className="relative block h-5 min-w-0 flex-1">
                <span className="absolute inset-0 flex items-center truncate text-sm font-medium leading-5 transition-all duration-200 group-hover:-translate-y-full group-hover:opacity-0 group-focus-visible:-translate-y-full group-focus-visible:opacity-0">
                  {perspective.label}
                </span>
                <span className="absolute inset-0 flex translate-y-full items-center truncate text-xs leading-5 text-muted-foreground opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
                  {perspective.question}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function ResizeHandle({
  width,
  onWidth,
}: {
  width: number;
  onWidth: (width: number) => void;
}) {
  const clamp = (value: number) =>
    Math.min(DOCUMENT_WIDTH_MAX, Math.max(DOCUMENT_WIDTH_MIN, value));
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize document"
      aria-valuenow={Math.round(width)}
      aria-valuemin={DOCUMENT_WIDTH_MIN}
      aria-valuemax={DOCUMENT_WIDTH_MAX}
      tabIndex={0}
      onPointerDown={(event) => {
        event.preventDefault();
        const move = (next: PointerEvent) =>
          onWidth(
            clamp(
              ((window.innerWidth - next.clientX) / window.innerWidth) * 100,
            ),
          );
        const stop = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", stop);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop);
      }}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") onWidth(clamp(width + 2));
        else if (event.key === "ArrowRight") onWidth(clamp(width - 2));
        else return;
        event.preventDefault();
      }}
      className="w-1 shrink-0 cursor-col-resize bg-transparent hover:bg-accent/40"
    />
  );
}
function EdgeStrip({
  side,
  label,
  onClick,
}: {
  side: "left" | "right";
  label: string;
  onClick: () => void;
}) {
  const Icon = side === "left" ? PanelLeft : PanelRight;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "flex h-full w-8 shrink-0 items-start justify-center bg-muted/30 pt-4 text-muted-foreground hover:bg-muted hover:text-foreground",
        side === "left" ? "border-r border-border" : "border-l border-border",
      )}
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}
function ThinkingLine({ message }: { message: string }) {
  return (
    <div
      aria-live="polite"
      className="flex items-center gap-2 text-sm font-medium text-accent"
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      {message}
    </div>
  );
}
function Banner({
  message,
  onDismiss,
  onRetry,
}: {
  message: string;
  onDismiss: () => void;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b border-destructive/50 bg-destructive/10 px-6 py-2 text-sm"
    >
      <span>{message}</span>
      <div className="flex shrink-0 items-center gap-3">
        {onRetry && (
          <button
            className="text-xs font-medium text-foreground hover:text-accent"
            onClick={onRetry}
          >
            Retry
          </button>
        )}
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={onDismiss}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
function isRetryable(error: unknown): error is TransportError {
  return error instanceof TransportError && error.retryable;
}
function errorMessage(error: unknown): string {
  return error instanceof TransportError || error instanceof Error
    ? error.message
    : "Something went wrong.";
}

function readSelectedInterview(): string | null {
  try {
    return globalThis.localStorage?.getItem(SELECTED_INTERVIEW_KEY) ?? null;
  } catch {
    return null;
  }
}

function rememberSelectedInterview(id: string): void {
  try {
    globalThis.localStorage?.setItem(SELECTED_INTERVIEW_KEY, id);
  } catch {
    // IndexedDB still restores the records when localStorage is unavailable.
  }
}

function forgetSelectedInterview(): void {
  try {
    globalThis.localStorage?.removeItem(SELECTED_INTERVIEW_KEY);
  } catch {
    // The local record remains removable when localStorage is unavailable.
  }
}
