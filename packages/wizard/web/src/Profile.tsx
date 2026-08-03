// The document view. This is the *one* component in the door that reads `ProductProfile` and
// knows its shape — epics hold behaviours hold criteria; personas and tasks are flat lists.
// Everything domain-aware in the UI is quarantined here, on purpose, so the conversation can
// stay shape-only. It is read-only where it counts: no control here changes the profile — every
// edit still originates in the conversation. The only controls are presentation: disclosures that
// fold an epic open or closed, and a control to collapse the whole pane — both view state, not
// document state.
//
// It is a live mirror of the profile the package built, drawn fresh each time the payload
// arrives — no change-highlighting, no diffing. The pane simply reflects the current state.

import { useState } from "react";
import type { Behaviour, Epic, ProductProfile } from "./api";
import { PanelRight } from "lucide-react";
import { Chevron, cn, Mono } from "./ui";

export function Profile({
  profile,
  onCollapse,
}: {
  profile: ProductProfile;
  onCollapse?: () => void;
}) {
  const { product } = profile;
  const named = product.name.trim() || "Untitled product";

  const { epics } = profile;

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-5 text-sm">
      <header className="flex items-start gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-base font-semibold text-foreground">{named}</h2>
          {product.summary && (
            <p className="text-muted-foreground">{product.summary}</p>
          )}
        </div>
        {onCollapse && (
          <button
            type="button"
            aria-label="Hide document"
            title="Hide document"
            onClick={onCollapse}
            className="-mr-1 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelRight size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
      </header>

      {epics.length > 0 && (
        <Section title="What should be true">
          <div className="flex flex-col gap-2">
            {epics.map((epic) => (
              <EpicView key={epic.id} epic={epic} />
            ))}
          </div>
        </Section>
      )}

      {profile.personas.length > 0 && (
        <Section title="Who runs it">
          <ul className="flex flex-col gap-2">
            {profile.personas.map((p) => (
              <li key={p.id} className="flex flex-col">
                <Mono>{p.id}</Mono>
                <span className="text-foreground">{p.description}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {profile.tasks.length > 0 && (
        <Section title="How we'll check it">
          <ul className="flex flex-col gap-3">
            {profile.tasks.map((t) => (
              <li key={t.id} className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-foreground">{t.description}</span>
                  <Mono>{t.id}</Mono>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                  {t.behaviour_refs.map((ref) => (
                    <Mono key={ref}>{ref}</Mono>
                  ))}
                  {t.persona_refs.map((ref) => (
                    <Mono key={ref}>{ref}</Mono>
                  ))}
                  <Mono>{t.num_trials}×</Mono>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

// Each epic is a disclosure: the header toggles its behaviours open and closed, so a long
// document collapses to a scannable list of epic names. Note this toggle is *view* state
// only: it opens and closes a section, it never edits the profile, so the document view stays
// read-only in the sense that matters — nothing here changes what the package built.
function EpicView({ epic }: { epic: Epic }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded py-1 text-left transition-colors hover:text-accent"
      >
        <Chevron dir={open ? "down" : "right"} className="text-muted-foreground transition-transform" />
        <span className="font-medium text-foreground">{epic.name}</span>
        <span className="text-xs text-muted-foreground">
          {epic.behaviours.length}
        </span>
      </button>
      {open && (
        <ul className="flex flex-col gap-1.5 border-l border-border pb-1 pl-3 ml-1.5">
          {epic.behaviours.map((b) => (
            <BehaviourView key={b.id} behaviour={b} />
          ))}
        </ul>
      )}
    </div>
  );
}

function BehaviourView({ behaviour }: { behaviour: Behaviour }) {
  // A behaviour the user hasn't ticked is dormant: its criteria are kept but won't be
  // measured, so it reads de-emphasised.
  const dormant = !behaviour.priority;
  return (
    <li className={cn("flex flex-col gap-0.5", dormant && "opacity-45")}>
      <div className="flex items-center gap-2">
        <span className="text-foreground">{behaviour.statement}</span>
        <Mono>{behaviour.id}</Mono>
      </div>
      {behaviour.criteria.length > 0 && (
        <ul className="flex flex-col gap-0.5 pl-3">
          {behaviour.criteria.map((c) => (
            <li key={c.id} className="text-xs text-muted-foreground">
              <span className="text-foreground">Given</span> {c.given},{" "}
              <span className="text-foreground">when</span> {c.when},{" "}
              <span className="text-foreground">then</span> {c.then}
              {c.metric_fqn && (
                <>
                  {" "}
                  <Mono>{c.metric_fqn}</Mono>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
