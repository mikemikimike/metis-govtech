// The hand-authoring door: a form that writes an experiment document directly, with no
// interview and no session.
//
// ── A DELIBERATE EXCEPTION TO THE WEB DOOR'S DISCIPLINE ───────────────────────────────────────
// Everywhere else in this browser, not one domain word appears: the conversation renderer draws
// a `Card` without ever knowing whether it is a persona or a scenario, because the package composes
// every string and the browser only branches on shape. This module is the one place that names
// the domain — "personas", "scenarios", "trials", "fixtures", "metrics" — in the browser.
//
// That is allowed here, and only here, for the same reason the catalogue reader is allowed its
// one import of the engine: the names are not the package's to choose. They are the field names
// of the engine's experiment schema, fixed by that schema, not composed by METIS. There is no
// authoring decision to relocate into Python — moving these strings there would not make them
// any more authoritative, only harder to see beside the inputs they label. The exception is
// confined to this file; no shared component gains a domain word. This makes the form the
// *second* domain-aware frontend component, after the read-only document view.
//
// It builds the same document shape the server's compiler emits, posts it to the stateless
// compile route, and streams the returned file to a download. It stores nothing and creates no
// session — leaving the screen discards the work, by design.

import { ArrowLeft, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { FixtureMetadata, MetricSpec } from "./api";
import { api, TransportError } from "./api";
import { FixtureInput, NumberInput } from "./inputs";
import { validateFixtureSelection } from "./fixture-policy";
import { Button, cn, countRuns, formatRuns, Mono, Panel } from "./ui";

interface PersonaDraft {
  id: string;
  description: string;
}

interface ScenarioDraft {
  id: string;
  description: string;
  num_trials: number;
  persona_refs: string[];
  metric_refs: string[]; // metric FQNs
  fixtures: string[];
}

interface BrowserFixture extends FixtureMetadata {
  file: File;
}

function newPersona(): PersonaDraft {
  return { id: "", description: "" };
}

function newScenario(): ScenarioDraft {
  return {
    id: "",
    description: "",
    num_trials: 1,
    persona_refs: [],
    metric_refs: [],
    fixtures: [],
  };
}

export function ManualForm({ onBack }: { onBack: () => void }) {
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const [personas, setPersonas] = useState<PersonaDraft[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioDraft[]>([]);
  const [library, setLibrary] = useState<BrowserFixture[]>([]);

  // The catalogue the metric picker offers. `null` while it is still loading; a fetch failure is
  // reported in the door's own error style rather than leaving an empty picker that looks like a
  // library with no metrics.
  const [metrics, setMetrics] = useState<MetricSpec[] | null>(null);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  // The server's rejection — which the download gate should make unreachable, but which is kept
  // as a safety net and surfaced here if it ever fires.
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .metrics()
      .then((rows) => live && setMetrics(rows))
      .catch((e) => {
        if (!live) return;
        setCatalogueError(
          e instanceof TransportError
            ? e.message
            : "Couldn't load the metric library.",
        );
      });
    return () => {
      live = false;
    };
  }, []);

  // ── persona editing ─────────────────────────────────────────────────────────

  const addPersona = () => setPersonas((ps) => [...ps, newPersona()]);
  const updatePersona = (i: number, patch: Partial<PersonaDraft>) =>
    setPersonas((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const removePersona = (i: number) => {
    const removed = personas[i]?.id.trim();
    setPersonas((ps) => ps.filter((_, j) => j !== i));
    // A scenario can no longer reference a persona that no longer exists — drop the reference so
    // the document never carries a dangling id.
    if (removed) {
      setScenarios((ss) =>
        ss.map((s) => ({
          ...s,
          persona_refs: s.persona_refs.filter((ref) => ref !== removed),
        })),
      );
    }
  };

  // ── scenario editing ────────────────────────────────────────────────────────────

  const addScenario = () => setScenarios((ss) => [...ss, newScenario()]);
  const updateScenario = (i: number, patch: Partial<ScenarioDraft>) =>
    setScenarios((ss) => ss.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const removeScenario = (i: number) =>
    setScenarios((ss) => ss.filter((_, j) => j !== i));

  const uploadFiles = async (files: File[]): Promise<FixtureMetadata[]> => {
    const names = validateFixtureSelection(files, library);
    const added = files.map((file, i) => ({
      name: names[i],
      size: file.size,
      file,
    }));
    setLibrary((current) => [...current, ...added]);
    return added.map(({ file: _file, ...metadata }) => metadata);
  };

  // The personas a scenario may reference: exactly those currently defined and named. A blank-id
  // persona offers nothing to reference, so it is not listed.
  const definedPersonaIds = useMemo(
    () => personas.map((p) => p.id.trim()).filter(Boolean),
    [personas],
  );

  // ── the mandatory rules, gated in the browser ─────────────────────────────────
  // The same presence checks the schema enforces, stated as what is still missing. The server
  // validates against the schema itself and stays the authority; this only decides when the
  // download becomes available.

  const missing = useMemo(() => {
    const problems: string[] = [];
    const uploaded = new Set(library.map((item) => item.name));
    const missingFiles = [
      ...new Set(
        scenarios.flatMap((scenario) =>
          scenario.fixtures.filter((name) => !uploaded.has(name)),
        ),
      ),
    ];
    if (!id.trim()) problems.push("an experiment id");
    if (!description.trim()) problems.push("a description");
    if (personas.length === 0) problems.push("at least one persona");
    else if (personas.some((p) => !p.id.trim() || !p.description.trim()))
      problems.push("an id and a description for every persona");
    if (scenarios.length === 0) problems.push("at least one scenario");
    else {
      if (scenarios.some((s) => !s.id.trim()))
        problems.push("an id for every scenario");
      if (scenarios.some((s) => !s.description.trim()))
        problems.push("a description for every scenario");
      if (scenarios.some((s) => s.persona_refs.length === 0))
        problems.push("a persona for every scenario");
    }
    if (missingFiles.length > 0)
      problems.push(`files: ${missingFiles.join(", ")}`);
    return problems;
  }, [id, description, personas, scenarios, library]);

  const ready = missing.length === 0;

  // ── download ────────────────────────────────────────────────────────────────

  const download = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    // Built to match the compiler's scenario shape: num_trials, persona_refs and metric_refs
    // always present; fixtures only when the scenario names some. Metric references are plain FQN
    // strings, which the schema accepts directly.
    const payload = {
      id: id.trim(),
      description: description.trim(),
      personas: personas.map((p) => ({
        id: p.id.trim(),
        description: p.description.trim(),
      })),
      scenarios: scenarios.map((s) => ({
        id: s.id.trim(),
        description: s.description.trim(),
        num_trials: s.num_trials,
        persona_refs: s.persona_refs,
        metric_refs: s.metric_refs,
        ...(s.fixtures.length ? { fixtures: s.fixtures } : {}),
      })),
    };
    try {
      const bundle = await api.compileBundle(
        payload,
        library.map(({ name, file }) => ({ name, file })),
      );
      const url = URL.createObjectURL(bundle);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = "experiment.zip";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(
        e instanceof TransportError ? e.message : "Couldn't build the file.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-10 py-8">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <div className="flex flex-col gap-4">
          <button
            type="button"
            onClick={onBack}
            className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={14} strokeWidth={1.75} aria-hidden />
            Back
          </button>
          <header className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold text-foreground">
              Write the experiment yourself
            </h1>
            <p className="text-sm text-muted-foreground">
              Fill in the scenarios, personas, metrics and fixture files, and
              download the experiment bundle.
            </p>
          </header>
        </div>

        {/* ── experiment ────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-3">
          <Field label="Experiment id">
            <TextInput
              value={id}
              placeholder="research-assistant"
              onChange={setId}
            />
          </Field>
          <Field label="Description">
            <TextArea
              value={description}
              placeholder="What this experiment evaluates, in a sentence or two."
              onChange={setDescription}
            />
          </Field>
        </section>

        {/* ── personas ──────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-3">
          <SectionHeading
            title="Personas"
            hint="The people the agent is tested against."
          />
          {personas.map((persona, i) => (
            <Panel key={i} className="flex flex-col gap-3 p-3">
              <div className="flex items-start gap-3">
                <div className="flex flex-1 flex-col gap-3">
                  <Field label="Id">
                    <TextInput
                      value={persona.id}
                      placeholder="cooperative-delegator"
                      onChange={(v) => updatePersona(i, { id: v })}
                    />
                  </Field>
                  <Field label="Description">
                    <TextArea
                      value={persona.description}
                      placeholder="Hands the agent a job and trusts it to finish."
                      onChange={(v) => updatePersona(i, { description: v })}
                    />
                  </Field>
                </div>
                <RemoveButton label="Remove persona" onClick={() => removePersona(i)} />
              </div>
            </Panel>
          ))}
          <AddButton label="Add a persona" onClick={addPersona} />
        </section>

        {/* ── scenarios ─────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-3">
          <SectionHeading
            title="Scenarios"
            hint="What the agent is asked to do, and how it is measured."
          />
          {scenarios.map((scenario, i) => (
            <Panel key={i} className="flex flex-col gap-3 p-3">
              <div className="flex items-start gap-3">
                <div className="flex flex-1 flex-col gap-3">
                  <div className="flex gap-3">
                    <Field label="Id" className="flex-1">
                      <TextInput
                        value={scenario.id}
                        placeholder="S-1"
                        onChange={(v) => updateScenario(i, { id: v })}
                      />
                    </Field>
                    <Field label="Trials" className="w-48">
                      <NumberInput
                        value={scenario.num_trials}
                        min={1}
                        onChange={(v) => updateScenario(i, { num_trials: v })}
                      />
                    </Field>
                  </div>
                  <Field label="Description">
                    <TextArea
                      value={scenario.description}
                      placeholder="Ask the agent to summarise a long report and keep its citations."
                      onChange={(v) => updateScenario(i, { description: v })}
                    />
                  </Field>

                  <Field label="Personas">
                    {definedPersonaIds.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        Add a persona above, then choose it here.
                      </p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {definedPersonaIds.map((pid) => {
                          const on = scenario.persona_refs.includes(pid);
                          return (
                            <Button
                              key={pid}
                              variant="ghost"
                              active={on}
                              className="px-2 py-0.5 text-xs"
                              onClick={() =>
                                updateScenario(i, {
                                  persona_refs: on
                                    ? scenario.persona_refs.filter((r) => r !== pid)
                                    : [...scenario.persona_refs, pid],
                                })
                              }
                            >
                              {pid}
                            </Button>
                          );
                        })}
                      </div>
                    )}
                  </Field>

                  <Field label="Metrics">
                    <MetricPicker
                      metrics={metrics}
                      error={catalogueError}
                      selected={scenario.metric_refs}
                      onToggle={(fqn) =>
                        updateScenario(i, {
                          metric_refs: scenario.metric_refs.includes(fqn)
                            ? scenario.metric_refs.filter((r) => r !== fqn)
                            : [...scenario.metric_refs, fqn],
                        })
                      }
                    />
                  </Field>

                  <Field label="Fixtures">
                    <FixtureInput
                      value={scenario.fixtures}
                      onChange={(fixtures) => updateScenario(i, { fixtures })}
                      onUpload={uploadFiles}
                    />
                  </Field>
                  <div className="flex justify-end pt-1 text-xs text-muted-foreground">
                    {formatRuns(
                      countRuns(scenario.persona_refs.length, scenario.num_trials),
                    )}
                  </div>
                </div>
                <RemoveButton label="Remove scenario" onClick={() => removeScenario(i)} />
              </div>
            </Panel>
          ))}
          <AddButton label="Add a scenario" onClick={addScenario} />
          {scenarios.length > 0 && (
            <div className="flex justify-end border-t border-border pt-4 text-sm text-muted-foreground">
              Total: {formatRuns(
                scenarios.reduce(
                  (total, scenario) =>
                    total + countRuns(scenario.persona_refs.length, scenario.num_trials),
                  0,
                ),
              )}
            </div>
          )}
        </section>

        {/* ── download ──────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-2 border-t border-border pt-6">
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              disabled={!ready || busy}
              onClick={download}
            >
              Download experiment.yaml
            </Button>
            {!ready && (
              <p className="text-sm text-muted-foreground">
                Still needs {missing.join(", ")}.
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// ── the metric picker ───────────────────────────────────────────────────────
//
// One flat alphabetical list with a search. The library re-exports every metric from one flat
// namespace, so there is no module segment to group on. Selection is by ticking an entry; there
// is no way to type an identifier and no control over a metric's arguments — the only metrics
// offerable are the ones the library actually carries.

function MetricPicker({
  metrics,
  error,
  selected,
  onToggle,
}: {
  metrics: MetricSpec[] | null;
  error: string | null;
  selected: string[];
  onToggle: (fqn: string) => void;
}) {
  const [query, setQuery] = useState("");

  if (error)
    return <p className="text-sm text-destructive">{error}</p>;
  if (metrics === null)
    return <p className="text-xs text-muted-foreground">Loading metrics…</p>;

  const q = query.trim().toLowerCase();
  // Preserve the catalogue's sorted order.
  const shown = q
    ? metrics.filter(
        (m) =>
          m.name.toLowerCase().includes(q) || m.fqn.toLowerCase().includes(q),
      )
    : metrics;

  return (
    <div className="flex flex-col gap-2">
      <input
        className="rounded-md border border-input bg-background p-2 text-sm"
        placeholder="Search metrics"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {selected.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {selected.length} selected
        </p>
      )}
      <Panel className="flex flex-col overflow-hidden">
        {shown.map((m) => {
          const on = selected.includes(m.fqn);
          return (
            <label
              key={m.fqn}
              className="flex items-start gap-2.5 border-b border-border px-3 py-2 last:border-b-0 hover:bg-muted"
            >
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-[hsl(var(--accent))]"
                checked={on}
                onChange={() => onToggle(m.fqn)}
              />
              <span className="flex flex-1 flex-col gap-0.5">
                <span className="text-sm text-foreground">{m.name}</span>
                <span className="text-xs text-muted-foreground">
                  {m.description}
                </span>
                <Mono>{m.fqn}</Mono>
              </span>
            </label>
          );
        })}
        {shown.length === 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            No metrics match “{query}”.
          </p>
        )}
      </Panel>
    </div>
  );
}

// ── small building blocks ─────────────────────────────────────────────────────

function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={cn("flex flex-col gap-1", className)}>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      className="rounded-md border border-input bg-background p-2 text-sm"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function TextArea({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
}) {
  return (
    <textarea
      className="min-h-16 rounded-md border border-input bg-background p-2 text-sm"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="ghost" className="w-fit" onClick={onClick}>
      <Plus size={14} strokeWidth={1.75} aria-hidden />
      {label}
    </Button>
  );
}

function RemoveButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="mt-1 shrink-0 text-muted-foreground transition-colors hover:text-foreground"
    >
      <X size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}
