// The shell. The session rail is always on the left. The middle is either the opening screen
// (when no session is open) or the conversation (when one is). The document pane appears on
// the right once the interview is past clarify.
//
//   no session open    → the intro: a chat input and the ways in
//   session open       → the conversation
//   step past clarify  → the document pane joins on the right

import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionSummary, SessionView, UserResponse } from "./api";
import { api, TransportError } from "./api";
import { Composer, Transcript } from "./Conversation";
import { ConnectRepo } from "./ConnectRepo";
import { Done } from "./Done";
import { Intro } from "./Landing";
import { ManualForm } from "./ManualForm";
import { Profile } from "./Profile";
import { SessionRail } from "./SessionRail";
import { PanelLeft, PanelRight } from "lucide-react";
import { cn } from "./ui";

export function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [view, setView] = useState<SessionView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // Whether each side pane is open. A reading preference for the moment, not a fact about the
  // interview, so it lives here in the shell — not persisted, not on the wire. A reload returns to
  // both-open, which is the right default rather than a lost setting.
  const [railOpen, setRailOpen] = useState(true);
  const [profileOpen, setProfileOpen] = useState(true);
  // The hand-authoring door: a form that writes an experiment file directly, with no session.
  // It is a second front door alongside the interview, not a step within one — so it is view
  // state on the shell, and leaving it discards any unsaved form work, by design.
  const [authoring, setAuthoring] = useState(false);
  // The repository facade: a screen depicting "connect a repo", with a gated submission. Like
  // the authoring form it is a front door held in shell view state; leaving it discards its
  // inputs and creates no session, which is the whole point of the depiction.
  const [connectingRepo, setConnectingRepo] = useState(false);

  // The conversation's scroll viewport, and a record of the last `busy` value, so the effect
  // below can act on the busy→ready edge — the moment the model finished the next screen — and
  // not on every render while it is composing.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const wasBusy = useRef(false);
  const turns = view?.requests.length ?? 0;

  // When the model finishes composing the next screen, glide the start of that new step into
  // view — but only for a user already reading near the foot, so someone who has scrolled up to
  // re-read is left where they are. The first turn is exempt: its arrival is the entrance
  // animation's job, not a scroll. Smooth here degrades to instant under `prefers-reduced-motion`
  // via the global rule in globals.css, so no extra guard is needed.
  useEffect(() => {
    const finished = wasBusy.current && !busy;
    wasBusy.current = busy;
    if (!finished) return;
    const container = scrollRef.current;
    if (!container || turns <= 1) return;

    const distanceFromFoot =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromFoot > container.clientHeight) return; // reading scrollback — leave it

    const marks = container.querySelectorAll<HTMLElement>("[data-step-start]");
    const target = marks[marks.length - 1];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }, [busy, turns]);

  const refreshList = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
    } catch (e) {
      report(e, setError);
    }
  }, []);

  // First paint: learn whether any sessions exist, which decides the whole layout.
  useEffect(() => {
    void refreshList().finally(() => setLoaded(true));
  }, [refreshList]);

  const open = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    setAuthoring(false);
    setConnectingRepo(false);
    try {
      setView(await api.readSession(id));
    } catch (e) {
      report(e, setError);
    } finally {
      setBusy(false);
    }
  }, []);

  // "New evaluation" just clears the open session, which reveals the intro. Nothing is
  // created until the user actually types their first message — an empty session on disk for
  // every stray click is litter the list would have to carry.
  const startNew = useCallback(() => {
    setError(null);
    setView(null);
    setAuthoring(false);
    setConnectingRepo(false);
  }, []);

  // Typing the first message from the intro: create the session, then send that text as the
  // opening answer. A fresh session arrives on the clarify step with a pending chat question,
  // so the user's first line answers it — the interview is under way in one move.
  const beginWithMessage = useCallback(
    async (text: string) => {
      setBusy(true);
      setError(null);
      try {
        const created = await api.createSession();
        // Draw the new session before its first answer returns so its package-authored
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
  // The list is refreshed alongside because a reply can change a session's title or step.
  const send = useCallback(
    async (response: UserResponse) => {
      if (!view) return;
      setBusy(true);
      setError(null);
      try {
        setView(await api.respond(view.id, response));
        await refreshList();
      } catch (e) {
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

  if (!loaded) return null; // one frame, avoids flashing the intro before the list lands

  const showDocument =
    !authoring &&
    !connectingRepo &&
    view !== null &&
    view.step !== "clarify";
  const pending = view?.requests.find((r) => r.state === "pending");

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* The three regions read 15 · 55 · 30 when both side panes are open: the rail is 15%, the
          document pane 30%, and the conversation (flex-1) takes the rest. Either side pane can be
          folded to a slim strip; the conversation reclaims the freed width by construction, since
          it is the only pane that grows. Collapse is view state only — it never edits the profile
          and is not persisted, so a reload returns to both-open. */}
      {railOpen ? (
        <SessionRail
          sessions={sessions}
          currentId={view?.id ?? null}
          busy={busy}
          onOpen={open}
          onNew={startNew}
          onCollapse={() => setRailOpen(false)}
        />
      ) : (
        <EdgeStrip side="left" label="Show sessions" onClick={() => setRailOpen(true)} />
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {error && <Banner message={error} onDismiss={() => setError(null)} />}

        {authoring ? (
          // The hand-authoring door, occupying the middle region alone — no document pane, no
          // composer. Leaving it returns to the intro and drops the form's contents.
          <ManualForm onBack={() => setAuthoring(false)} />
        ) : connectingRepo ? (
          // The repository facade, in the same region on the same terms — leaving it returns to
          // the intro and drops its inputs.
          <ConnectRepo onBack={() => setConnectingRepo(false)} />
        ) : view === null ? (
          // No session open: the intro, with a type-first composer that begins the interview.
          <Intro
            composer={
              <Composer
                request={undefined}
                busy={busy}
                alwaysEnabled
                leadingIcon
                bare
                placeholder="Describe your agent — what it does and for whom — and the wizard turns it into behaviours, criteria and tasks you can run."
                onSend={beginWithMessage}
              />
            }
            onAuthor={() => setAuthoring(true)}
            onConnectRepo={() => setConnectingRepo(true)}
          />
        ) : (
          <>
            {/* Keyed on the session id so the entrance animation re-fires each time a
                different conversation is opened, not only on first mount. */}
            <div
              key={view.id}
              ref={scrollRef}
              className="animate-enter-conversation flex-1 overflow-y-auto px-10 py-10"
            >
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
                <Transcript
                  requests={view.requests}
                  busy={busy}
                  onRespond={send}
                />
                {busy && <ThinkingLine message={view.busy_message} />}
                {view.done && <Done sessionId={view.id} />}
              </div>
            </div>
            <Composer request={pending} busy={busy} onSend={sendChat} />
          </>
        )}
      </main>

      {showDocument &&
        view &&
        (profileOpen ? (
          <aside className="w-[30%] min-w-[20rem] shrink-0 border-l border-border bg-muted">
            <Profile profile={view.profile} onCollapse={() => setProfileOpen(false)} />
          </aside>
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
