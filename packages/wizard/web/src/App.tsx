// The shell. The interview rail is always on the left. The middle is either the opening screen
// (when no interview is open) or the conversation (when one is). The document pane sits on the
// right for the whole of an open interview.
//
//   no interview open    → the intro: a chat input and the ways in
//   interview open       → the conversation, and the document pane alongside it
//
// The document appears from the first turn, as scaffold: every section it will hold, drawn as an
// outline, filling in as the interview produces content. It used to wait until the interview was
// past clarify, on the grounds that an empty pane asserts something the wizard has not decided —
// but an outline asserts nothing, and holding it back left the user with no sight of what the
// interview would produce during the one step where they are being asked the most.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type {
  FixtureMetadata,
  MetricSpec,
  InterviewSummary,
  InterviewView,
  UserResponse,
} from "./api";
import { api, TransportError } from "./api";
import { Composer, Transcript } from "./Conversation";
import type { FixtureActions } from "./Conversation";
import { Done } from "./Done";
import { Intro } from "./Landing";
import { ManualForm } from "./ManualForm";
import { Profile, stepPosition } from "./Profile";
import { InterviewRail } from "./InterviewRail";
import type { SourceTrayKind } from "./SourceTray";
import { PanelLeft, PanelRight } from "lucide-react";
import { cn } from "./ui";

// The document pane's share of the window. It reads as the interview's other half rather than a
// margin note: the user is meant to review it as the conversation fills it in, deciding whether
// what is there is enough, and that is reading work that a narrow column makes harder — prose in a
// 30% pane wrapped every few words and turned every description into a paragraph.
const DOCUMENT_WIDTH_DEFAULT = 42;
const DOCUMENT_WIDTH_MIN = 24;
const DOCUMENT_WIDTH_MAX = 60;

function sourcePlaceholder(
  source: SourceTrayKind | null,
  openingQuestion: string,
): string {
  if (source === "codebase") return "Analyse my source code…";
  if (source === "traces") return "Analyse my traces…";
  return openingQuestion;
}

export function App() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [view, setView] = useState<InterviewView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [openingQuestion, setOpeningQuestion] = useState("");
  // Package-owned status copy, keyed by interview step. The progress caption in the document pane
  // reads the line for the interview's current step from here, so the wording lives in config.yaml
  // rather than in the frontend.
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  // Whether each side pane is open. A reading preference for the moment, not a fact about the
  // interview, so it lives here in the shell — not persisted, not on the wire. A reload returns to
  // both-open, which is the right default rather than a lost setting.
  const [railOpen, setRailOpen] = useState(true);
  const [profileOpen, setProfileOpen] = useState(true);
  // How wide the document pane is, as a percentage of the window. Dragging it is the same kind of
  // reading preference as collapsing it, so it is held the same way: in the shell, unpersisted,
  // back to the default on reload.
  const [documentWidth, setDocumentWidth] = useState(DOCUMENT_WIDTH_DEFAULT);
  // Metric details are presentation metadata, not part of the interview payload. Fetch them once
  // after the first interview opens and keep the lookup for this page lifetime; the catalogue is
  // shared by every interview and changes only when the page is reloaded.
  const [metricCatalogue, setMetricCatalogue] = useState<MetricSpec[] | null>(null);
  const [metricCatalogueState, setMetricCatalogueState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const metricCatalogueRequest = useRef<Promise<MetricSpec[]> | null>(null);
  const [showMetrics, setShowMetrics] = useState(false);
  // The hand-authoring door: a form that writes an experiment file directly, with no interview.
  // It is a second front door alongside the interview, not a step within one — so it is view
  // state on the shell, and leaving it discards any unsaved form work, by design.
  const [authoring, setAuthoring] = useState(false);
  // Source depictions peek beneath the opening composer. They hold presentation state only;
  // closing or changing the tray retains no source data.
  const [sourceTray, setSourceTray] = useState<SourceTrayKind | null>(null);

  const activeInterviewId = view?.id ?? null;

  // This is deliberately keyed by the interview id, not by pane mount state: collapsing the profile
  // unmounts it, while moving to another interview should restore the quiet default.
  useEffect(() => {
    setShowMetrics(false);
  }, [activeInterviewId]);

  const hasInterview = view !== null;
  useEffect(() => {
    if (!hasInterview || metricCatalogueRequest.current) return;

    setMetricCatalogueState("loading");
    const request = api.metrics();
    metricCatalogueRequest.current = request;
    void request.then(
      (rows) => {
        setMetricCatalogue(rows);
        setMetricCatalogueState("ready");
      },
      () => {
        setMetricCatalogueState("error");
      },
    );
  }, [hasInterview]);

  const metricByFqn = useMemo(
    () => new Map((metricCatalogue ?? []).map((metric) => [metric.fqn, metric])),
    [metricCatalogue],
  );

  // Capture the reader's intent before an action changes the transcript. The browser can reset the
  // scroll position while the API response replaces the view, so the decision must not depend on a
  // later scroll event or on the temporary thinking line.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pendingScroll = useRef<{
    sourceView: InterviewView;
    top: number;
    followBottom: boolean;
  } | null>(null);

  // A pending action belongs to one interview only. Do not let it affect a interview opened while the
  // previous request is still settling.
  useEffect(() => {
    if (pendingScroll.current && pendingScroll.current.sourceView.id !== activeInterviewId) {
      pendingScroll.current = null;
    }
  }, [activeInterviewId]);

  // Apply the intent after the API has supplied a new view. Waiting for that identity change is
  // important: applying it when busy starts would be too early, before the response recomposes the
  // transcript, and the browser could reset the position again afterwards.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const intent = pendingScroll.current;
    if (!el || !intent) return;
    if (view?.id !== intent.sourceView.id) {
      pendingScroll.current = null;
      return;
    }
    if (view === intent.sourceView) return;

    if (intent.followBottom) {
      el.scrollTop = el.scrollHeight;
    } else {
      el.scrollTop = intent.top;
    }
    pendingScroll.current = null;
  }, [view]);

  const refreshList = useCallback(async () => {
    try {
      setInterviews(await api.listInterviews());
    } catch (e) {
      report(e, setError);
    }
  }, []);

  // First paint: learn the interviews and the package-owned opening copy, which the landing door
  // needs before a interview exists.
  useEffect(() => {
    const load = async () => {
      try {
        const [existing, configuration] = await Promise.all([
          api.listInterviews(),
          api.interview(),
        ]);
        setInterviews(existing);
        setOpeningQuestion(configuration.opening_question);
        setStatuses(configuration.statuses);
      } catch (e) {
        report(e, setError);
      } finally {
        setLoaded(true);
      }
    };
    void load();
  }, []);

  const open = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    setAuthoring(false);
    setSourceTray(null);
    try {
      setView(await api.readInterview(id));
    } catch (e) {
      report(e, setError);
    } finally {
      setBusy(false);
    }
  }, []);

  // "New evaluation" just clears the open interview, which reveals the intro. Nothing is
  // created until the user actually types their first message — an empty interview on disk for
  // every stray click is litter the list would have to carry.
  const startNew = useCallback(() => {
    setError(null);
    setView(null);
    setAuthoring(false);
    setSourceTray(null);
  }, []);

  // Typing the first message from the intro: create the interview, then send that text as the
  // opening answer. A fresh interview arrives on the clarify step with a pending chat question,
  // so the user's first line answers it — the interview is under way in one move.
  const beginWithMessage = useCallback(
    async (text: string) => {
      setBusy(true);
      setError(null);
      try {
        const created = await api.createInterview();
        // The source tray is a depiction only. Starting chat discards it before the live interview
        // appears; no source selection or value enters the request.
        setSourceTray(null);
        // Draw the new interview before its first answer returns so its package-authored
        // activity message is visible during that initial model call too.
        setView(created);
        setView(await api.respond(created.id, { type: "chat", text }));
        await refreshList();
      } catch (e) {
        report(e, setError);
      } finally {
        setBusy(false);
      }
    },
    [refreshList],
  );

  // Every turn is the same shape: send one response, receive the whole state back, redraw.
  // The list is refreshed alongside because a reply can change a interview's title or step.
  const send = useCallback(
    async (response: UserResponse) => {
      if (!view) return;
      const el = scrollRef.current;
      if (el) {
        const distanceFromBottom =
          el.scrollHeight - el.scrollTop - el.clientHeight;
        pendingScroll.current = {
          sourceView: view,
          top: el.scrollTop,
          followBottom: distanceFromBottom < 80,
        };
      }
      setBusy(true);
      setError(null);
      try {
        setView(await api.respond(view.id, response));
        await refreshList();
      } catch (e) {
        pendingScroll.current = null;
        report(e, setError);
      } finally {
        setBusy(false);
      }
    },
    [view, refreshList],
  );

  // Typing into the composer. The composer is only ever live on a chat request — a choice
  // screen disables it and carries "Chat about it" as a button instead — so a submission here
  // is always a chat response, sent straight. Reaching the text box is a click on that button,
  // which swaps the screen to a chat request; by the time the box is typable, this is all it
  // needs to do. That sequencing is the "one editor at a time" rule: the buttons and the box
  // are never both live.
  const sendChat = useCallback(
    async (text: string) => {
      await send({ type: "chat", text });
    },
    [send],
  );

  const uploadFixtures = useCallback(
    async (files: File[]): Promise<FixtureMetadata[]> => {
      if (!view) return [];
      setBusy(true);
      try {
        const result = await api.uploadFixtures(view.id, files);
        return result.added;
      } finally {
        setBusy(false);
      }
    },
    [view],
  );

  const fixtureActions: FixtureActions = {
    onUpload: uploadFixtures,
  };

  if (!loaded) return null; // one frame, avoids flashing the intro before the list lands

  // The document belongs to a interview, so it shows whenever one is open — and only then. The two
  // other front doors write no profile at all, and the opening screen has no interview behind it.
  const showDocument = !authoring && view !== null;
  const pending = view?.requests.find((r) => r.state === "pending");

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* The three regions read 15 · 55 · 30 when both side panes are open: the rail is 15%, the
          document pane 30%, and the conversation (flex-1) takes the rest. Either side pane can be
          folded to a slim strip; the conversation reclaims the freed width by construction, since
          it is the only pane that grows. Collapse is view state only — it never edits the profile
          and is not persisted, so a reload returns to both-open. */}
      {railOpen ? (
        <InterviewRail
          interviews={interviews}
          currentId={view?.id ?? null}
          busy={busy}
          onOpen={open}
          onNew={startNew}
          onCollapse={() => setRailOpen(false)}
        />
      ) : (
        <EdgeStrip side="left" label="Show interviews" onClick={() => setRailOpen(true)} />
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {error && <Banner message={error} onDismiss={() => setError(null)} />}

        {authoring ? (
          // The hand-authoring door, occupying the middle region alone — no document pane, no
          // composer. Leaving it returns to the intro and drops the form's contents.
          <ManualForm onBack={() => setAuthoring(false)} />
        ) : view === null ? (
          // No interview open: the intro, with a type-first composer that begins the interview.
          <Intro
            openingQuestion={openingQuestion}
            composer={(sourceControl) => (
              <Composer
                request={undefined}
                busy={busy}
                alwaysEnabled
                leadingIcon
                bare
                placeholder={sourcePlaceholder(sourceTray, openingQuestion)}
                onSend={beginWithMessage}
                sourceControl={sourceControl}
              />
            )}
            selectedSource={sourceTray}
            onAuthor={() => {
              setSourceTray(null);
              setAuthoring(true);
            }}
            onSource={(source) => {
              setError(null);
              setSourceTray(source);
            }}
            onCloseSource={() => setSourceTray(null)}
          />
        ) : (
          <>
            {/* Keyed on the interview id so the entrance animation re-fires each time a
                different conversation is opened, not only on first mount. */}
            <div
              key={view.id}
              ref={scrollRef}
              className="quiet-scrollbar animate-enter-conversation flex-1 overflow-y-auto py-10"
            >
              {/* The chat column is 80% of the panel, centred — the 10% gutters on each side are
                  the pane's column padding, wider than a fixed inset and proportional to the panel
                  as it resizes. The docked composer uses the same 80% column so the two align. */}
              <div className="mx-auto flex w-4/5 flex-col gap-8">
                <Transcript
                  requests={view.requests}
                  busy={busy}
                  onRespond={send}
                  fixtureActions={fixtureActions}
                />
                {busy && <ThinkingLine message={view.busy_message} />}
                {view.done && <Done />}
              </div>
            </div>
            <Composer request={pending} busy={busy} onSend={sendChat} />
          </>
        )}
      </main>

      {showDocument &&
        view &&
        (profileOpen ? (
          <>
          <ResizeHandle
            width={documentWidth}
            onWidth={setDocumentWidth}
          />
          <aside
            style={{ width: `${documentWidth}%` }}
            className="min-w-[20rem] shrink-0 border-l border-border bg-muted"
          >
            <Profile
              key={view.id}
              profile={view.profile}
              // Where the interview has got to, and what it is doing right now. Both are read
              // straight off the payload: the position from the step metadata the package stamps
              // on requests, the step name as the package's own string. The shell carries them
              // across; `Profile` is the one component that maps them onto sections.
              position={stepPosition(view.requests)}
              interviewStep={view.step}
              statusText={statuses[view.step]}
              busy={busy}
              showMetrics={showMetrics}
              onShowMetricsChange={setShowMetrics}
              metricByFqn={metricByFqn}
              metricsLoading={
                metricCatalogueState === "idle" || metricCatalogueState === "loading"
              }
              metricsError={metricCatalogueState === "error"}
              onCollapse={() => setProfileOpen(false)}
              interviewId={view.id}
              done={view.done}
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

// The divider between the conversation and the document, and the grip that moves it. It is a
// hairline at rest — the panes are separated by a border like every other pane boundary — and it
// takes the accent only while it is being pointed at or driven, which is the accent doing its one
// job of marking state. Keyboard users get the same control through the arrow keys, since a pane
// width that only a pointer can reach is a pane width some users cannot set at all.
function ResizeHandle({
  width,
  onWidth,
}: {
  width: number;
  onWidth: (width: number) => void;
}) {
  const clamp = (value: number) =>
    Math.min(DOCUMENT_WIDTH_MAX, Math.max(DOCUMENT_WIDTH_MIN, value));

  // Width is tracked from the right edge, because that is the edge the document is anchored to:
  // dragging left widens it. Listeners live on the window for the duration of the drag so the
  // pointer can leave the 4px handle without dropping it.
  const startDrag = (event: React.PointerEvent) => {
    event.preventDefault();
    const move = (moved: PointerEvent) => {
      onWidth(
        clamp(((window.innerWidth - moved.clientX) / window.innerWidth) * 100),
      );
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      document.body.style.userSelect = "";
    };
    // Without this a drag across the conversation selects the transcript as it goes.
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize document"
      aria-valuenow={Math.round(width)}
      aria-valuemin={DOCUMENT_WIDTH_MIN}
      aria-valuemax={DOCUMENT_WIDTH_MAX}
      tabIndex={0}
      onPointerDown={startDrag}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") onWidth(clamp(width + 2));
        else if (event.key === "ArrowRight") onWidth(clamp(width - 2));
        else return;
        event.preventDefault();
      }}
      className={cn(
        "w-1 shrink-0 cursor-col-resize bg-transparent transition-colors duration-150",
        "hover:bg-accent/40 focus-visible:bg-accent/40",
      )}
    />
  );
}

// The sliver a collapsed side pane leaves behind: a full-height strip at the window edge with a
// chevron pointing inward, so a folded pane is always one click from coming back. It carries no
// pane content — just the way in. Drawn in `currentColor`, no accent fill, so it stays chrome.
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
        "flex h-full w-8 shrink-0 items-start justify-center bg-muted/30 pt-4 text-muted-foreground",
        "transition-colors hover:bg-muted hover:text-foreground",
        side === "left" ? "border-r border-border" : "border-l border-border",
      )}
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}

// A single status line while work is in flight. Its sentence arrives finished from the package;
// this component owns only the browser presentation.
function ThinkingLine({ message }: { message: string }) {
  return (
    <div
      aria-live="polite"
      // The whole line takes the accent, not just the dot: the wizard working is a live state,
      // and teal is what the palette reserves for live state. It is the strongest single "the
      // model is doing something" signal in the conversation, so it earns the colour.
      className="flex items-center gap-2 text-sm font-medium text-accent"
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      {message}
    </div>
  );
}

// For errors the package never composed — an outage, a dropped connection. Kept visually
// distinct from a RUNTIME warning, which the package chose to attach and phrased itself.
function Banner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 border-b border-destructive/50 bg-destructive/10 px-6 py-2 text-sm"
    >
      <span>{message}</span>
      <button
        className="text-xs text-muted-foreground hover:text-foreground"
        onClick={onDismiss}
      >
        Dismiss
      </button>
    </div>
  );
}

function report(error: unknown, set: (message: string) => void) {
  if (error instanceof TransportError) set(error.message);
  else set("Something went wrong.");
}
