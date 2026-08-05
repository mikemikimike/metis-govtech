// The hand-authoring door: a form that writes an experiment document directly, with no
// interview and no session.
//
// ── A DELIBERATE EXCEPTION TO THE WEB DOOR'S DISCIPLINE ───────────────────────────────────────
// Everywhere else in this browser, not one domain word appears: the conversation renderer draws
// a `Card` without ever knowing whether it is a persona or a task, because the package composes
// every string and the browser only branches on shape. This module is the one place that names
// the domain — "personas", "tasks", "trials", "fixtures", "metrics" — in the browser.
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
import type { MetricSpec } from "./api";
import { api, TransportError } from "./api";
import { FileReferenceListInput, NumberInput } from "./inputs";
import { Button, Chevron, cn, countRuns, formatRuns, Mono, Panel } from "./ui";

interface PersonaDraft {
  id: string;
  description: string;
}

interface TaskDraft {
  id: string;
  description: string;
  num_trials: number;
  persona_refs: string[];
  metric_refs: string[]; // metric FQNs
  fixtures: string[];
}

function newPersona(): PersonaDraft {
  return { id: "", description: "" };
}

function newTask(): TaskDraft {
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
  const [tasks, setTasks] = useState<TaskDraft[]>([]);

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
    // A task can no longer reference a persona that no longer exists — drop the reference so the
    // document never carries a dangling id.
    if (removed) {
      setTasks((ts) =>
        ts.map((t) => ({
          ...t,
          persona_refs: t.persona_refs.filter((ref) => ref !== removed),
        })),
      );
    }
  };

  // ── task editing ──────────────────────────────────────────────────────────────

  const addTask = () => setTasks((ts) => [...ts, newTask()]);
  const updateTask = (i: number, patch: Partial<TaskDraft>) =>
    setTasks((ts) => ts.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const removeTask = (i: number) =>
    setTasks((ts) => ts.filter((_, j) => j !== i));

  // The personas a task may reference: exactly those currently defined and named. A blank-id
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
    if (!id.trim()) problems.push("an experiment id");
    if (!description.trim()) problems.push("a description");
    if (personas.length === 0) problems.push("at least one persona");
    else if (personas.some((p) => !p.id.trim() || !p.description.trim()))
      problems.push("an id and a description for every persona");
    if (tasks.length === 0) problems.push("at least one task");
    else {
      if (tasks.some((t) => !t.id.trim()))
        problems.push("an id for every task");
      if (tasks.some((t) => !t.description.trim()))
        problems.push("a description for every task");
      if (tasks.some((t) => t.persona_refs.length === 0))
        problems.push("a persona for every task");
    }
    return problems;
  }, [id, description, personas, tasks]);

  const ready = missing.length === 0;

  // ── download ────────────────────────────────────────────────────────────────

  const download = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    // Built to match the compiler's task shape: num_trials, persona_refs and metric_refs always
    // present; fixtures only when the task names some. Metric references are plain FQN strings,
    // which the schema accepts directly.
    const payload = {
      id: id.trim(),
      description: description.trim(),
      personas: personas.map((p) => ({
        id: p.id.trim(),
        description: p.description.trim(),
      })),
      tasks: tasks.map((t) => ({
        id: t.id.trim(),
        description: t.description.trim(),
        num_trials: t.num_trials,
        persona_refs: t.persona_refs,
        metric_refs: t.metric_refs,
        ...(t.fixtures.length ? { fixtures: t.fixtures } : {}),
      })),
    };
    try {
      const yaml = await api.compileExperiment(payload);
      const url = URL.createObjectURL(
        new Blob([yaml], { type: "application/x-yaml" }),
      );
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = "experiment.yaml";
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
              Fill in the tasks, personas and metrics, and download the
              experiment file.
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
                      placeholder="Hands the agent a task and trusts it to finish."
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

        {/* ── tasks ─────────────────────────────────────────────────────── */}
        <section className="flex flex-col gap-3">
          <SectionHeading
            title="Tasks"
            hint="What the agent is asked to do, and how it is measured."
          />
          {tasks.map((task, i) => (
            <Panel key={i} className="flex flex-col gap-3 p-3">
              <div className="flex items-start gap-3">
                <div className="flex flex-1 flex-col gap-3">
                  <div className="flex gap-3">
                    <Field label="Id" className="flex-1">
                      <TextInput
                        value={task.id}
                        placeholder="T-1"
                        onChange={(v) => updateTask(i, { id: v })}
                      />
                    </Field>
                    <Field label="Trials" className="w-48">
                      <NumberInput
                        value={task.num_trials}
                        min={1}
                        onChange={(v) => updateTask(i, { num_trials: v })}
                      />
                    </Field>
                  </div>
                  <Field label="Description">
                    <TextArea
                      value={task.description}
                      placeholder="Ask the agent to summarise a long report and keep its citations."
                      onChange={(v) => updateTask(i, { description: v })}
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
                          const on = task.persona_refs.includes(pid);
                          return (
                            <Button
                              key={pid}
                              variant="ghost"
                              active={on}
                              className="px-2 py-0.5 text-xs"
                              onClick={() =>
                                updateTask(i, {
                                  persona_refs: on
                                    ? task.persona_refs.filter((r) => r !== pid)
                                    : [...task.persona_refs, pid],
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
                      selected={task.metric_refs}
                      onToggle={(fqn) =>
                        updateTask(i, {
                          metric_refs: task.metric_refs.includes(fqn)
                            ? task.metric_refs.filter((r) => r !== fqn)
                            : [...task.metric_refs, fqn],
                        })
                      }
                    />
                  </Field>

                  <Field label="Fixtures">
                    <FileReferenceListInput
                      value={task.fixtures}
                      onChange={(fixtures) => updateTask(i, { fixtures })}
                    />
                  </Field>
                  <div className="flex justify-end pt-1 text-xs text-muted-foreground">
                    {formatRuns(
                      countRuns(task.persona_refs.length, task.num_trials),
                    )}
                  </div>
                </div>
                <RemoveButton label="Remove task" onClick={() => removeTask(i)} />
              </div>
            </Panel>
          ))}
          <AddButton label="Add a task" onClick={addTask} />
          {tasks.length > 0 && (
            <div className="flex justify-end border-t border-border pt-4 text-sm text-muted-foreground">
              Total: {formatRuns(
                tasks.reduce(
                  (total, task) =>
                    total + countRuns(task.persona_refs.length, task.num_trials),
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
// Collapsible groups by module with a search across all groups. Selection is by ticking an
// entry; there is no way to type an identifier and no control over a metric's arguments — the
// only metrics offerable are the ones the library actually carries.

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
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (error)
    return <p className="text-sm text-destructive">{error}</p>;
  if (metrics === null)
    return <p className="text-xs text-muted-foreground">Loading metrics…</p>;

  const q = query.trim().toLowerCase();
  const shown = q
    ? metrics.filter(
        (m) =>
          m.name.toLowerCase().includes(q) || m.fqn.toLowerCase().includes(q),
      )
    : metrics;

  // Preserve the catalogue's sorted order within each group.
  const groups = new Map<string, MetricSpec[]>();
  for (const m of shown) {
    const list = groups.get(m.group) ?? [];
    list.push(m);
    groups.set(m.group, list);
  }

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
      <div className="flex flex-col gap-1.5">
        {[...groups.entries()].map(([group, rows]) => {
          // A search opens every group with a match; otherwise groups start collapsed.
          const expanded = q ? true : (open[group] ?? false);
          const chosen = rows.filter((m) => selected.includes(m.fqn)).length;
          return (
            <Panel key={group} className="overflow-hidden">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-muted"
                onClick={() =>
                  setOpen((o) => ({ ...o, [group]: !expanded }))
                }
              >
                <span className="flex items-center gap-2">
                  <Chevron dir={expanded ? "down" : "right"} />
                  <span className="text-sm font-medium text-foreground">
                    {group}
                  </span>
                </span>
                <Mono>
                  {chosen ? `${chosen}/${rows.length}` : rows.length}
                </Mono>
              </button>
              {expanded && (
                <div className="flex flex-col border-t border-border">
                  {rows.map((m) => {
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
                          <span className="text-sm text-foreground">
                            {m.name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {m.description}
                          </span>
                          <Mono>{m.fqn}</Mono>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </Panel>
          );
        })}
        {groups.size === 0 && (
          <p className="text-xs text-muted-foreground">
            No metrics match “{query}”.
          </p>
        )}
      </div>
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
