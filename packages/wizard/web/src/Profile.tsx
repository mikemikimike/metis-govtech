// The document view. This is the component in the door that reads `ProductProfile` and knows
// its shape — epics hold behaviours hold criteria; personas and tasks are flat lists. The
// conversation stays shape-only so this can hold all of the interview's domain knowledge in one
// place. There is one other domain-aware component, deliberately: the hand-authoring form
// (`ManualForm.tsx`), which names the experiment schema's own fields; its header comment
// explains why that exception is allowed. Neither of those names leaks into the shape-only
// conversation renderer, which remains the rule.
//
// It is read-only where it counts: no control here changes the profile — every edit still
// originates in the conversation. The only controls are presentation: disclosures that fold an
// epic open or closed, and a control to collapse the whole pane — both view state, not document
// state.
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
    // The document is a produced artifact, not an editable field, and it reads that way: a white
    // sheet floating on the grey pane, carrying a single soft shadow. That shadow is the one
    // exception the house style grants — depth is a border everywhere else — because "this is a
    // finished page" is exactly what a sheet-with-shadow says and a border cannot. Nothing here
    // is an input; the shadow's job is to say so.
    <div className="h-full overflow-y-auto p-4">
      <div className="relative flex flex-col gap-6 rounded-[12px] bg-card p-5 text-sm text-card-foreground shadow-sm">
        {/* Pinned to the sheet's top-right corner rather than laid out beside the header, so its
            position stays put when the summary reflows to fewer lines at a wider pane. */}
        {onCollapse && (
          <button
            type="button"
            aria-label="Hide document"
            title="Hide document"
            onClick={onCollapse}
            className="absolute right-3 top-3 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelRight size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
        <header className="flex min-w-0 flex-col gap-1 pr-8">
          <h2 className="text-base font-semibold text-foreground">{named}</h2>
          {product.summary && (
            <p className="text-muted-foreground">{product.summary}</p>
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
        <Section title="Personas">
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
        <Section title="Task descriptions">
          <ul className="flex flex-col gap-3">
            {profile.tasks.map((t) => (
              <li key={t.id} className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 flex-1 text-foreground">{t.description}</span>
                  <Mono className="shrink-0 whitespace-nowrap">{t.id}</Mono>
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
      <h3 className="text-xs font-semibold text-muted-foreground">
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
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 text-foreground">{behaviour.statement}</span>
        <Mono className="shrink-0 whitespace-nowrap">{behaviour.id}</Mono>
      </div>
      {behaviour.criteria.length > 0 && (
        <ul className="flex flex-col gap-0.5 pl-3">
          {behaviour.criteria.map((c) => (
            <li key={c.id} className="flex flex-col gap-1 text-xs text-muted-foreground">
              <span>
                <span className="text-foreground">Given</span> {c.given},{" "}
                <span className="text-foreground">when</span> {c.when},{" "}
                <span className="text-foreground">then</span> {c.then}
              </span>
              {c.metric_fqn && (
                // The metric is machine-named, so it reads as a line of code: mono on a light
                // editor backing, set apart from the plain-language criterion above it.
                <Mono className="block break-all rounded border border-border bg-muted px-2 py-1 leading-relaxed">
                  {c.metric_fqn}
                </Mono>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
