import {
  ArrowLeft,
  ChevronRight,
  FilePen,
  Plus,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downloadArchive } from "./download";
import {
  ACCEPTED_FIXTURE_EXTENSIONS,
  validateFixtureSelection,
} from "./fixture-policy";
import { NumberInput } from "./inputs";
import {
  emptyManualExperiment,
  emptyManualPersona,
  emptyManualScenario,
  emptyManualTestCase,
  keepReferencedFixtures,
  manualFieldErrors,
  replaceTaskReference,
  synthesizeManualSpecification,
  type ManualExperiment,
  type ManualFixture,
  type ManualPersona,
  type ManualScenario,
  type ManualTestCase,
} from "./manual";
import { api, TransportError, type GraderSpec } from "./transport/api";
import { Button, cn, formatTrials, Mono } from "./ui";

export function ManualAuthoringEntry({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      aria-label="Prefer to skip the interview? Write it yourself"
      onClick={onOpen}
      className="group flex w-full items-center gap-3 rounded-lg border border-border bg-card p-4 text-left text-card-foreground transition-colors hover:bg-muted active:bg-border"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors group-hover:text-foreground">
        <FilePen size={17} strokeWidth={1.75} aria-hidden />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium text-foreground">
          Prefer to skip the interview? Write it yourself
        </span>
        <span className="text-xs text-muted-foreground">
          Define Personas and Scenarios, then select them in test cases.
        </span>
      </span>
      <ChevronRight
        size={16}
        strokeWidth={1.75}
        aria-hidden
        className="text-muted-foreground transition-transform group-hover:translate-x-0.5"
      />
    </button>
  );
}

type CollectionKind = "Persona" | "Scenario" | "Test case";
type FocusTarget = {
  kind: "persona" | "scenario" | "task";
  index: number;
} | null;
export type ManualFocusTarget = Exclude<FocusTarget, null>;

export function itemHeading(kind: CollectionKind, id: string): string {
  return id.trim() || `New ${kind}`;
}

function itemContext(kind: CollectionKind, index: number, id: string): string {
  return `${kind} ${id.trim() || index + 1}`;
}

function openItem(indexes: readonly number[], index: number): number[] {
  return indexes.includes(index) ? [...indexes] : [...indexes, index];
}

function closeItem(indexes: readonly number[], index: number): number[] {
  return indexes.filter((value) => value !== index);
}

function removeItemIndex(
  indexes: readonly number[],
  removedIndex: number,
): number[] {
  return indexes.flatMap((index) => {
    if (index === removedIndex) return [];
    return [index > removedIndex ? index - 1 : index];
  });
}

export function focusManualInput(
  target: ManualFocusTarget | null,
  personaRefs: ReadonlyArray<Pick<HTMLInputElement, "focus"> | null>,
  scenarioRefs: ReadonlyArray<Pick<HTMLInputElement, "focus"> | null>,
  taskRefs: ReadonlyArray<Pick<HTMLInputElement, "focus"> | null> = [],
): boolean {
  if (!target) return false;
  const refs =
    target.kind === "persona"
      ? personaRefs
      : target.kind === "scenario"
        ? scenarioRefs
        : taskRefs;
  const element = refs[target.index];
  if (!element) return false;
  element.focus();
  return true;
}

export function ManualForm({ onBack }: { onBack: () => void }) {
  const [experiment, setExperiment] = useState<ManualExperiment>(
    emptyManualExperiment,
  );
  const [library, setLibrary] = useState<ManualFixture[]>([]);
  const [graders, setGraders] = useState<GraderSpec[] | null>(null);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [editingPersonas, setEditingPersonas] = useState<number[]>([]);
  // Field errors stay hidden until the first download attempt, then update as the user types.
  const [showErrors, setShowErrors] = useState(false);
  const [submitAttempt, setSubmitAttempt] = useState(0);
  const formRef = useRef<HTMLDivElement | null>(null);

  const personaIdRefs = useRef<Array<HTMLInputElement | null>>([]);
  const scenarioIdRefs = useRef<Array<HTMLInputElement | null>>([]);
  const taskPersonaRefs = useRef<Array<HTMLSelectElement | null>>([]);

  const loadGraders = useCallback(() => {
    let live = true;
    setCatalogueError(null);
    void api.graders().then(
      (rows) => {
        if (live) setGraders(rows);
      },
      (cause) => {
        if (!live) return;
        setCatalogueError(
          cause instanceof TransportError
            ? cause.message
            : "Could not load the scorer library. Try again.",
        );
      },
    );
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => loadGraders(), [loadGraders]);

  useEffect(() => {
    if (
      focusManualInput(
        focusTarget,
        personaIdRefs.current,
        scenarioIdRefs.current,
        taskPersonaRefs.current,
      )
    ) {
      setFocusTarget(null);
    }
  }, [
    experiment.personas.length,
    experiment.scenarios.length,
    experiment.tasks.length,
    focusTarget,
  ]);

  const fieldErrors = useMemo(
    () => manualFieldErrors(experiment, library),
    [experiment, library],
  );
  const ready = fieldErrors.length === 0;
  const errorFor = (field: string): string | undefined =>
    showErrors
      ? fieldErrors.find((value) => value.field === field)?.message
      : undefined;

  useEffect(() => {
    if (!submitAttempt) return;
    formRef.current
      ?.querySelector<HTMLElement>('[aria-invalid="true"]')
      ?.focus();
  }, [submitAttempt]);
  const personaIds = useMemo(
    () =>
      experiment.personas.map((persona) => persona.id.trim()).filter(Boolean),
    [experiment.personas],
  );

  const updatePersona = (index: number, patch: Partial<ManualPersona>) => {
    setExperiment((current) => {
      const previousId = current.personas[index]?.id ?? "";
      const personas = current.personas.map((persona, position) =>
        position === index ? { ...persona, ...patch } : persona,
      );
      const nextId = personas[index]?.id ?? "";
      return {
        ...current,
        personas,
        tasks:
          patch.id === undefined
            ? current.tasks
            : replaceTaskReference(
                current.tasks,
                "persona_ref",
                previousId,
                nextId,
              ),
      };
    });
  };

  const removePersona = (index: number) => {
    setEditingPersonas((current) => removeItemIndex(current, index));
    setExperiment((current) => {
      const removedId = current.personas[index]?.id ?? "";
      return {
        ...current,
        personas: current.personas.filter((_, position) => position !== index),
        tasks: replaceTaskReference(
          current.tasks,
          "persona_ref",
          removedId,
          "",
        ),
      };
    });
  };

  const updateScenario = (index: number, patch: Partial<ManualScenario>) => {
    setExperiment((current) => ({
      ...current,
      scenarios: current.scenarios.map((scenario, position) =>
        position === index ? { ...scenario, ...patch } : scenario,
      ),
      tasks:
        patch.id === undefined
          ? current.tasks
          : replaceTaskReference(
              current.tasks,
              "scenario_ref",
              current.scenarios[index].id,
              patch.id,
            ),
    }));
  };
  const removeScenario = (index: number) => {
    setExperiment((current) => ({
      ...current,
      scenarios: current.scenarios.filter((_, position) => position !== index),
      tasks: replaceTaskReference(
        current.tasks,
        "scenario_ref",
        current.scenarios[index].id,
        "",
      ),
    }));
  };
  const updateTask = (index: number, patch: Partial<ManualTestCase>) => {
    const tasks = experiment.tasks.map((task, position) =>
      position === index ? { ...task, ...patch } : task,
    );
    setExperiment((current) => ({ ...current, tasks }));
    setLibrary((current) => keepReferencedFixtures(tasks, current));
  };
  const removeTask = (index: number) => {
    const tasks = experiment.tasks.filter((_, position) => position !== index);
    setExperiment((current) => ({ ...current, tasks }));
    setLibrary((current) => keepReferencedFixtures(tasks, current));
  };

  const uploadFiles = (index: number, files: File[]) => {
    const names = validateFixtureSelection(files, library);
    const added = files.map((file, position) => ({
      name: names[position] ?? file.name,
      size: file.size,
      blob: file,
    }));
    const tasks = experiment.tasks.map((task, position) =>
      position === index
        ? {
            ...task,
            fixtures: [
              ...task.fixtures,
              ...names.filter((name) => !task.fixtures.includes(name)),
            ],
          }
        : task,
    );
    setExperiment((current) => ({ ...current, tasks }));
    setLibrary((current) => [...current, ...added]);
  };

  const download = async () => {
    if (busy) return;
    if (!ready) {
      setShowErrors(true);
      // A closed Persona editor cannot show its field errors, so open it.
      const invalidPersonas = fieldErrors.flatMap((value) => {
        const match = /^persona\.(\d+)\./.exec(value.field);
        return match ? [Number(match[1])] : [];
      });
      setEditingPersonas((current) => [
        ...new Set([...current, ...invalidPersonas]),
      ]);
      setSubmitAttempt((value) => value + 1);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const usedFiles = keepReferencedFixtures(experiment.tasks, library);
      const submitted = synthesizeManualSpecification(experiment);
      const compiled = await api.compile(submitted);
      const assigned = compiled.specification.tasks ?? [];
      setExperiment((current) =>
        current === experiment
          ? {
              ...current,
              tasks: current.tasks.map((task, index) => ({
                ...task,
                id: assigned[index]?.id ?? task.id,
              })),
            }
          : current,
      );
      const archive = await api.package(
        {
          specification: {
            ...submitted,
            tasks: assigned.map((task) => ({
              ...task,
              fixtures: task.fixtures ?? [],
              behaviour_refs: task.behaviour_refs ?? [],
              num_trials: task.num_trials ?? 3,
            })),
          },
        },
        usedFiles,
      );
      downloadArchive(archive);
    } catch (cause) {
      setError(
        cause instanceof TransportError
          ? cause.message
          : "Could not build the specification. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="quiet-scrollbar flex-1 overflow-y-auto px-5 py-7 sm:px-10 sm:py-9">
      <div
        ref={formRef}
        className="mx-auto flex w-full max-w-4xl flex-col gap-10 pb-10"
      >
        <header className="flex flex-col gap-5">
          <button
            type="button"
            onClick={onBack}
            className="flex w-fit items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={15} strokeWidth={1.75} aria-hidden />
            Return to the opening screen
          </button>
          <div className="max-w-2xl">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Write the experiment yourself
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Define what to run and how to score it. METIS will build a
              ready-to-use experiment package.
            </p>
          </div>
        </header>

        <section
          aria-labelledby="manual-experiment"
          className="overflow-hidden rounded-lg border border-border bg-card text-card-foreground"
        >
          <div className="border-b border-border bg-muted/35 px-5 py-5 sm:px-7 sm:py-6">
            <SectionHeading
              id="manual-experiment"
              title="Experiment"
              hint="Define the inputs for the Test Cases in this Experiment."
            />
          </div>

          <section
            aria-labelledby="manual-experiment-details"
            className="flex flex-col gap-5 px-5 py-6 sm:px-7 sm:py-7"
          >
            <SectionHeading
              id="manual-experiment-details"
              title="Experiment details"
              hint="Set an ID and a short description."
              level={3}
            />
            <div className="flex flex-col gap-5">
              <Field label="ID" error={errorFor("experiment.id")}>
                <TextInput
                  id="manual-experiment-id"
                  invalid={Boolean(errorFor("experiment.id"))}
                  ariaLabel="Experiment ID"
                  value={experiment.id}
                  placeholder="research-assistant"
                  spellCheck={false}
                  onChange={(id) =>
                    setExperiment((value) => ({ ...value, id }))
                  }
                />
              </Field>
              <Field
                label="Description"
                error={errorFor("experiment.description")}
              >
                <TextArea
                  id="manual-experiment-description"
                  invalid={Boolean(errorFor("experiment.description"))}
                  ariaLabel="Experiment description"
                  value={experiment.description}
                  placeholder="What this Experiment evaluates."
                  onChange={(description) =>
                    setExperiment((value) => ({ ...value, description }))
                  }
                />
              </Field>
            </div>
          </section>

          <section
            aria-labelledby="manual-personas"
            className="flex flex-col gap-5 border-t border-border px-5 py-6 sm:px-7 sm:py-7"
          >
            <SectionHeading
              id="manual-personas"
              title="Personas"
              hint="Describe the people who will interact with the agent."
              level={3}
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    const index = experiment.personas.length;
                    setFocusTarget({ kind: "persona", index });
                    setEditingPersonas((current) => openItem(current, index));
                    setExperiment((value) => ({
                      ...value,
                      personas: [...value.personas, emptyManualPersona()],
                    }));
                  }}
                >
                  <Plus size={14} strokeWidth={1.75} aria-hidden />
                  Add Persona
                </Button>
              }
            />
            {experiment.personas.length === 0 && (
              <EmptyRow error={errorFor("personas")}>
                No Personas yet. Add a Persona to make it available to test
                cases.
              </EmptyRow>
            )}
            {experiment.personas.length > 0 && (
              <div className="flex flex-col gap-4">
                {experiment.personas.map((persona, index) => {
                  const itemLabel = itemContext("Persona", index, persona.id);
                  const isEditing = editingPersonas.includes(index);
                  const canFinish = Boolean(
                    persona.id.trim() && persona.description.trim(),
                  );
                  return (
                    <article
                      key={index}
                      aria-labelledby={`manual-persona-${index}-heading`}
                      className="rounded-lg border border-border bg-muted/50 p-5 sm:p-6"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <h4
                          id={`manual-persona-${index}-heading`}
                          className="min-w-0 pt-1 text-sm font-semibold text-foreground"
                        >
                          {itemHeading("Persona", persona.id)}
                        </h4>
                        <div className="flex shrink-0 items-center gap-2">
                          <Button
                            variant={isEditing ? "secondary" : "ghost"}
                            className="px-2.5 py-1 text-xs"
                            disabled={isEditing && !canFinish}
                            title={
                              isEditing && !canFinish
                                ? "Enter an ID and description first."
                                : undefined
                            }
                            aria-label={
                              isEditing
                                ? `Finish editing ${itemLabel}`
                                : `Edit ${itemLabel}`
                            }
                            onClick={() => {
                              if (isEditing) {
                                setEditingPersonas((current) =>
                                  closeItem(current, index),
                                );
                                return;
                              }
                              setFocusTarget({ kind: "persona", index });
                              setEditingPersonas((current) =>
                                openItem(current, index),
                              );
                            }}
                          >
                            {isEditing ? "Done" : "Edit"}
                          </Button>
                          <RemoveButton
                            label={`Remove ${itemLabel}`}
                            onClick={() => removePersona(index)}
                          />
                        </div>
                      </div>
                      {isEditing ? (
                        <div className="mt-5 flex flex-col gap-5">
                          <Field
                            label="ID"
                            error={errorFor(`persona.${index}.id`)}
                          >
                            <TextInput
                              id={`manual-persona-${index}-id`}
                              invalid={Boolean(errorFor(`persona.${index}.id`))}
                              inputRef={(element) => {
                                personaIdRefs.current[index] = element;
                              }}
                              ariaLabel={`${itemLabel}, ID`}
                              value={persona.id}
                              placeholder="policy-analyst"
                              spellCheck={false}
                              onChange={(id) => updatePersona(index, { id })}
                            />
                          </Field>
                          <Field
                            label="Description"
                            error={errorFor(`persona.${index}.description`)}
                          >
                            <TextArea
                              id={`manual-persona-${index}-description`}
                              invalid={Boolean(
                                errorFor(`persona.${index}.description`),
                              )}
                              ariaLabel={`${itemLabel}, Description`}
                              value={persona.description}
                              placeholder="How this person acts during the evaluation."
                              onChange={(description) =>
                                updatePersona(index, { description })
                              }
                            />
                          </Field>
                        </div>
                      ) : (
                        <p className="mt-2 text-sm text-muted-foreground">
                          {persona.description.trim()}
                        </p>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <section
            aria-labelledby="manual-scenarios"
            className="flex flex-col gap-5 border-t border-border px-5 py-6 sm:px-7 sm:py-7"
          >
            <SectionHeading
              id="manual-scenarios"
              title="Scenarios"
              hint="Define the situations that your test cases will use."
              level={3}
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setFocusTarget({
                      kind: "scenario",
                      index: experiment.scenarios.length,
                    });
                    setExperiment((current) => ({
                      ...current,
                      scenarios: [...current.scenarios, emptyManualScenario()],
                    }));
                  }}
                >
                  <Plus size={14} aria-hidden />
                  Add Scenario
                </Button>
              }
            />
            {!experiment.scenarios.length && (
              <EmptyRow error={errorFor("scenarios")}>
                No Scenarios yet. Add a Scenario to make it available to test
                cases.
              </EmptyRow>
            )}
            {experiment.scenarios.map((scenario, index) => (
              <article
                key={index}
                className="flex flex-col gap-5 rounded-lg border border-border bg-muted/50 p-5 sm:p-6"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold">
                    {itemHeading("Scenario", scenario.id)}
                  </h4>
                  <RemoveButton
                    label={`Remove Scenario ${scenario.id || index + 1}`}
                    onClick={() => removeScenario(index)}
                  />
                </div>
                <Field label="ID" error={errorFor(`scenario.${index}.id`)}>
                  <TextInput
                    ariaLabel={`Scenario ${index + 1}, ID`}
                    invalid={Boolean(errorFor(`scenario.${index}.id`))}
                    value={scenario.id}
                    placeholder="supported-answer"
                    inputRef={(element) => {
                      scenarioIdRefs.current[index] = element;
                    }}
                    onChange={(id) => updateScenario(index, { id })}
                  />
                </Field>
                <Field
                  label="Description"
                  error={errorFor(`scenario.${index}.description`)}
                >
                  <TextArea
                    ariaLabel={`Scenario ${index + 1}, Description`}
                    invalid={Boolean(errorFor(`scenario.${index}.description`))}
                    value={scenario.description}
                    placeholder="Describe the situation and expected work."
                    onChange={(description) =>
                      updateScenario(index, { description })
                    }
                  />
                </Field>
                {scenario.id.trim() &&
                  !experiment.tasks.some(
                    (task) => task.scenario_ref === scenario.id.trim(),
                  ) && (
                    <p
                      className={
                        errorFor(`scenario.${index}.tasks`)
                          ? "text-xs text-destructive"
                          : "text-xs text-muted-foreground"
                      }
                    >
                      Select this Scenario in at least one test case.
                    </p>
                  )}
              </article>
            ))}
          </section>
          <section
            aria-labelledby="manual-tasks"
            className="flex flex-col gap-5 border-t border-border px-5 py-6 sm:px-7 sm:py-7"
          >
            <SectionHeading
              id="manual-tasks"
              title="Test cases"
              hint="Select one Persona and one Scenario for each test case. Set its Trials, scorers, and files."
              level={3}
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setFocusTarget({
                      kind: "task",
                      index: experiment.tasks.length,
                    });
                    setExperiment((current) => ({
                      ...current,
                      tasks: [...current.tasks, emptyManualTestCase()],
                    }));
                  }}
                >
                  <Plus size={14} aria-hidden />
                  Add test case
                </Button>
              }
            />
            {!experiment.tasks.length && (
              <EmptyRow error={errorFor("tasks")}>
                No test cases yet. Define Personas and Scenarios above, then add
                a test case.
              </EmptyRow>
            )}
            {experiment.tasks.map((task, index) => {
              const itemLabel = itemContext("Test case", index, task.id);
              return (
                <article
                  key={index}
                  className="flex flex-col gap-5 rounded-lg border border-border bg-muted/50 p-5 sm:p-6"
                >
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold">{itemLabel}</h4>
                    <RemoveButton
                      label={`Remove ${itemLabel}`}
                      onClick={() => removeTask(index)}
                    />
                  </div>
                  <Field
                    label="Persona"
                    error={errorFor(`task.${index}.persona`)}
                  >
                    <select
                      aria-invalid={Boolean(errorFor(`task.${index}.persona`))}
                      ref={(element) => {
                        taskPersonaRefs.current[index] = element;
                      }}
                      aria-label={`${itemLabel}, Persona`}
                      value={task.persona_ref}
                      onChange={(event) =>
                        updateTask(index, { persona_ref: event.target.value })
                      }
                      className={selectClass}
                    >
                      <option value="">Select a Persona</option>
                      {personaIds.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Scenario"
                    error={errorFor(`task.${index}.scenario`)}
                  >
                    <select
                      aria-invalid={Boolean(errorFor(`task.${index}.scenario`))}
                      aria-label={`${itemLabel}, Scenario`}
                      value={task.scenario_ref}
                      onChange={(event) =>
                        updateTask(index, { scenario_ref: event.target.value })
                      }
                      className={selectClass}
                    >
                      <option value="">Select a Scenario</option>
                      {experiment.scenarios
                        .filter((s) => s.id.trim())
                        .map((s) => (
                          <option key={s.id} value={s.id.trim()}>
                            {s.id.trim()}
                          </option>
                        ))}
                    </select>
                  </Field>
                  <Field
                    label="Trials"
                    error={errorFor(`task.${index}.trials`)}
                  >
                    <NumberInput
                      value={task.num_trials}
                      min={1}
                      max={20}
                      ariaLabel={`${itemLabel}, Trials`}
                      onChange={(num_trials) =>
                        updateTask(index, { num_trials })
                      }
                    />
                  </Field>
                  <ScorerPicker
                    itemLabel={itemLabel}
                    searchId={`manual-task-${index}-scorer-search`}
                    graders={graders}
                    error={catalogueError}
                    invalid={errorFor(`task.${index}.scorers`)}
                    selected={task.scorers}
                    onRetry={() => loadGraders()}
                    onToggle={(scorer) => {
                      const selected = task.scorers.some(
                        (value) => value.fqn === scorer.fqn,
                      );
                      updateTask(index, {
                        scorers: selected
                          ? task.scorers.filter(
                              (value) => value.fqn !== scorer.fqn,
                            )
                          : [...task.scorers, scorer],
                      });
                    }}
                  />
                  {task.scorers.map((scorer) => (
                    <Field
                      key={scorer.fqn}
                      label={`${scorer.name} settings`}
                      error={errorFor(`task.${index}.settings.${scorer.fqn}`)}
                    >
                      <TextArea
                        ariaLabel={`${itemLabel}, ${scorer.name} settings`}
                        invalid={Boolean(
                          errorFor(`task.${index}.settings.${scorer.fqn}`),
                        )}
                        value={
                          task.grader_args_text?.[scorer.fqn] ??
                          JSON.stringify(
                            task.grader_args?.[scorer.fqn] ?? {},
                            null,
                            2,
                          )
                        }
                        placeholder="{}"
                        onChange={(value) =>
                          updateTask(index, {
                            grader_args_text: {
                              ...task.grader_args_text,
                              [scorer.fqn]: value,
                            },
                          })
                        }
                      />
                    </Field>
                  ))}
                  <FixturePicker
                    itemLabel={itemLabel}
                    inputId={`manual-task-${index}-files`}
                    names={task.fixtures}
                    invalid={errorFor(`task.${index}.files`)}
                    onAdd={(files) => uploadFiles(index, files)}
                    onRemove={(name) =>
                      updateTask(index, {
                        fixtures: task.fixtures.filter(
                          (value) => value !== name,
                        ),
                      })
                    }
                  />
                </article>
              );
            })}
            <p className="text-sm text-muted-foreground">
              Total:{" "}
              {formatTrials(
                experiment.tasks.reduce(
                  (total, task) => total + task.num_trials,
                  0,
                ),
              )}
            </p>
          </section>
        </section>

        <section className="flex flex-col gap-3 border-t border-border pt-6">
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex items-center justify-end gap-3">
            {showErrors && !ready && (
              <p role="alert" className="text-sm text-destructive">
                Some fields are not complete.
              </p>
            )}
            <Button
              variant="primary"
              disabled={busy}
              title={ready ? undefined : "Some fields are not complete."}
              onClick={() => void download()}
            >
              {busy ? "Building specification…" : "Download specification"}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}

function SectionHeading({
  id,
  title,
  hint,
  level = 2,
  action,
}: {
  id: string;
  title: string;
  hint: string;
  level?: 2 | 3;
  action?: React.ReactNode;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <Heading id={id} className="text-base font-semibold text-foreground">
          {title}
        </Heading>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </div>
      {action}
    </div>
  );
}

const selectClass =
  "rounded-lg border border-input bg-background px-3 py-2 text-sm aria-[invalid=true]:border-destructive";

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {error && <span className="text-xs text-destructive">{error}</span>}
    </label>
  );
}

function TextInput({
  id,
  inputRef,
  ariaLabel,
  value,
  placeholder,
  spellCheck,
  invalid = false,
  onChange,
}: {
  id?: string;
  inputRef?: (element: HTMLInputElement | null) => void;
  ariaLabel?: string;
  value: string;
  placeholder: string;
  spellCheck?: boolean;
  invalid?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <input
      id={id}
      ref={inputRef}
      aria-label={ariaLabel}
      aria-invalid={invalid}
      value={value}
      placeholder={placeholder}
      spellCheck={spellCheck}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground aria-[invalid=true]:border-destructive"
    />
  );
}

function TextArea({
  id,
  ariaLabel,
  value,
  placeholder,
  invalid = false,
  onChange,
}: {
  id?: string;
  ariaLabel?: string;
  value: string;
  placeholder: string;
  invalid?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <textarea
      id={id}
      aria-label={ariaLabel}
      aria-invalid={invalid}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className="min-h-24 resize-y rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground aria-[invalid=true]:border-destructive"
    />
  );
}

function ScorerPicker({
  itemLabel,
  searchId,
  graders,
  error,
  selected,
  invalid,
  onRetry,
  onToggle,
}: {
  itemLabel: string;
  searchId: string;
  graders: GraderSpec[] | null;
  error: string | null;
  selected: GraderSpec[];
  invalid?: string;
  onRetry: () => void;
  onToggle: (grader: GraderSpec) => void;
}) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!graders || !value) return graders ?? [];
    return graders.filter(
      (grader) =>
        grader.name.toLowerCase().includes(value) ||
        grader.description.toLowerCase().includes(value),
    );
  }, [graders, query]);

  return (
    <fieldset
      aria-label={`${itemLabel}, Scorers`}
      className="flex flex-col gap-2"
    >
      <legend className="text-xs font-medium text-muted-foreground">
        Scorers
      </legend>
      {error ? (
        <div
          className="flex items-center gap-3 text-sm text-destructive"
          role="alert"
        >
          <span>{error}</span>
          <Button variant="ghost" className="text-xs" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : graders === null ? (
        <p className="text-sm text-muted-foreground">Loading scorers…</p>
      ) : (
        <>
          <label className="sr-only" htmlFor={searchId}>
            Search scorers
          </label>
          <input
            id={searchId}
            type="search"
            aria-label={`${itemLabel}, Search scorers`}
            aria-invalid={Boolean(invalid)}
            value={query}
            placeholder="Search scorers"
            onChange={(event) => setQuery(event.target.value)}
            className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground"
          />
          <div
            className={cn(
              "max-h-64 overflow-y-auto rounded-lg border",
              invalid ? "border-destructive" : "border-border",
            )}
          >
            {shown.map((grader) => {
              const checked = selected.some(
                (value) => value.fqn === grader.fqn,
              );
              return (
                <label
                  key={grader.fqn}
                  className="flex cursor-pointer items-start gap-3 border-b border-border px-3 py-3 last:border-b-0 hover:bg-muted"
                >
                  <input
                    type="checkbox"
                    aria-label={`${itemLabel}, ${grader.name}`}
                    checked={checked}
                    onChange={() => onToggle(grader)}
                    className="mt-1 h-4 w-4 accent-[hsl(var(--accent))]"
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="text-sm font-medium text-foreground">
                      {grader.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {grader.description}
                    </span>
                  </span>
                </label>
              );
            })}
            {shown.length === 0 && (
              <p className="px-3 py-3 text-sm text-muted-foreground">
                No scorers match this search.
              </p>
            )}
          </div>
          {invalid && <p className="text-xs text-destructive">{invalid}</p>}
          {selected.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {selected.length} {selected.length === 1 ? "scorer" : "scorers"}{" "}
              selected
            </p>
          )}
        </>
      )}
    </fieldset>
  );
}

function FixturePicker({
  itemLabel,
  inputId,
  names,
  invalid,
  onAdd,
  onRemove,
}: {
  itemLabel: string;
  inputId: string;
  names: string[];
  invalid?: string;
  onAdd: (files: File[]) => void;
  onRemove: (name: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <fieldset
      aria-label={`${itemLabel}, Files`}
      className="flex flex-col gap-2"
    >
      <legend className="text-xs font-medium text-muted-foreground">
        Files
      </legend>
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border border-input bg-background px-3 text-sm text-foreground transition-colors hover:bg-muted">
          <Upload size={14} strokeWidth={1.75} aria-hidden />
          Choose files
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            multiple
            accept={ACCEPTED_FIXTURE_EXTENSIONS.map(
              (value) => `.${value}`,
            ).join(",")}
            aria-label={`${itemLabel}, Choose files`}
            className="sr-only"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              setError(null);
              try {
                onAdd(files);
              } catch (cause) {
                setError(
                  cause instanceof Error
                    ? cause.message
                    : "Could not add the files.",
                );
              } finally {
                if (inputRef.current) inputRef.current.value = "";
              }
            }}
          />
        </label>
        {names.length === 0 && (
          <span className="text-sm text-muted-foreground">
            No files selected
          </span>
        )}
      </div>
      {names.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {names.map((name) => (
            <span
              key={name}
              className="inline-flex min-w-0 items-center gap-2 rounded-md border border-border px-2 py-1"
            >
              <Mono className="max-w-56 truncate">{name}</Mono>
              <button
                type="button"
                aria-label={`Remove ${name}`}
                onClick={() => onRemove(name)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X size={13} strokeWidth={2} aria-hidden />
              </button>
            </span>
          ))}
        </div>
      )}
      {(error ?? invalid) && (
        <p role="alert" className="text-xs text-destructive">
          {error ?? invalid}
        </p>
      )}
    </fieldset>
  );
}

function EmptyRow({
  error,
  children,
}: {
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-dashed px-4 py-5 text-sm text-muted-foreground",
        error ? "border-destructive" : "border-border",
      )}
    >
      {children}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
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
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
    >
      <X size={16} strokeWidth={1.75} aria-hidden />
    </button>
  );
}
