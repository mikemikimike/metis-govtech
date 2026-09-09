import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelLeft, PanelRight } from "lucide-react";
import type {
  InterviewSummary,
  LocalInterviewRecord,
  ProductProfile,
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
  type LocalStorageProblem,
} from "./storage/repository";
import { profileHasCriteria } from "./metrics";
import { downloadCompileResult } from "./download";
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

type RetryIntent =
  | { kind: "turn"; response: UserResponse }
  | { kind: "end" }
  | { kind: "compile"; profile: ProductProfile };

export function App() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [storageProblems, setStorageProblems] = useState<
    readonly LocalStorageProblem[]
  >([]);
  const [record, setRecord] = useState<LocalInterviewRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [workingStatus, setWorkingStatus] = useState("Working…");
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
      (config) => setWorkingStatus(config.working_status),
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
    async (description: string) => {
      if (busy) return;
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        const result = await api.start(description);
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
    [busy, refreshList, showError],
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

  const compileAndDownload = useCallback(
    async (profile: LocalInterviewRecord["state"]["profile"]) => {
      const result = await api.compile(profile);
      downloadCompileResult(result);
    },
    [],
  );

  const send = useCallback(
    async (response: UserResponse) => {
      if (!record?.state.pending || busy) return;
      setBusy(true);
      setError(null);
      setRetryIntent(null);
      try {
        const result = await api.respond(
          record.state,
          record.state.pending.request_id ?? "",
          response,
        );
        const next = applyTurn(record, result, response);
        await saveResult(next);
      } catch (cause) {
        showError(cause, { kind: "turn", response });
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
      await saveResult(applyEnd(record, result));
      if (result.outcome === "done") {
        try {
          await compileAndDownload(result.state.profile);
        } catch (cause) {
          showError(cause, { kind: "compile", profile: result.state.profile });
        }
      }
    } catch (cause) {
      showError(cause, { kind: "end" });
    } finally {
      setBusy(false);
    }
  }, [busy, compileAndDownload, record, saveResult, showError]);

  const retry = useCallback(() => {
    const intent = retryIntent;
    if (!intent) return;
    setRetryIntent(null);
    setError(null);
    if (intent.kind === "turn") void send(intent.response);
    else if (intent.kind === "end") void finish();
    else
      void compileAndDownload(intent.profile).catch((cause) =>
        showError(cause, intent),
      );
  }, [compileAndDownload, finish, retryIntent, send, showError]);

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
          <div className="flex flex-1 flex-col items-center justify-center px-6">
            <div className="flex w-full max-w-3xl flex-col gap-8">
              <h1 className="text-center text-2xl font-semibold text-foreground">
                Describe the product you want to evaluate
              </h1>
              <Composer
                request={undefined}
                busy={busy}
                alwaysEnabled
                leadingIcon
                bare
                placeholder="Tell METIS what this product does…"
                onSend={beginWithMessage}
              />
            </div>
          </div>
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
                onDownload={() =>
                  void compileAndDownload(view.profile).catch((cause) =>
                    showError(cause, {
                      kind: "compile",
                      profile: view.profile,
                    }),
                  )
                }
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
