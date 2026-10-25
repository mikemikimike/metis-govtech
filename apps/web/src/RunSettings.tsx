// Model settings in the browser: the banner for roles that are not configured, and the run
// settings step after the last review. The browser never sees a key or a URL. `GET /models`
// returns names and status only, and the run settings step writes model names only.

import { Info } from "lucide-react";
import type {
  InterviewState,
  ModelRole,
  ModelStatus,
  Specification,
} from "./transport/api";
import { Button, Mono, Panel } from "./ui";

export const MODEL_GUIDE = "docs/guide/models.md";

// The roles whose model a Specification records. Interview and embeddings stay in the
// environment, so the run settings step does not show them.
export type RunModelRole = Extract<
  ModelRole,
  "user_agent" | "runner_agent" | "judge"
>;
export type RunModels = Partial<Record<RunModelRole, string>>;

const DEFAULT_FIELD: Record<
  RunModelRole,
  "user_agent_model" | "runner_agent_model" | "judge_model"
> = {
  user_agent: "user_agent_model",
  runner_agent: "runner_agent_model",
  judge: "judge_model",
};

const ROLE_HELP: Record<RunModelRole, string> = {
  user_agent:
    "Acts as a real user. Use a capable model that is different from your target.",
  runner_agent:
    "Works out how to act on the target for a generic runner. Empty uses the user agent model.",
  judge:
    "Scores each criterion. Use a model from a different family than your target.",
};

// The roles that a run of this Specification calls. The runner agent runs only for a generic
// runner, which a target binding selects.
export function runRoles(specification: Specification): RunModelRole[] {
  return specification.target_binding
    ? ["user_agent", "runner_agent", "judge"]
    : ["user_agent", "judge"];
}

// The model names that the Specification records now.
export function runModels(specification: Specification): RunModels {
  const defaults = specification.defaults ?? {};
  const models: RunModels = {};
  for (const role of Object.keys(DEFAULT_FIELD) as RunModelRole[]) {
    const value = defaults[DEFAULT_FIELD[role]];
    if (value) models[role] = value;
  }
  return models;
}

// Write model names into the Specification defaults. A blank name removes the default, so the
// run uses the environment. No other field changes.
export function withRunModels(
  state: InterviewState,
  models: RunModels,
): InterviewState {
  const defaults = { ...(state.specification.defaults ?? {}) };
  for (const role of Object.keys(models) as RunModelRole[]) {
    const name = models[role]?.trim();
    if (name) defaults[DEFAULT_FIELD[role]] = name;
    else delete defaults[DEFAULT_FIELD[role]];
  }
  return { ...state, specification: { ...state.specification, defaults } };
}

// The state to package when the user continues from the run settings step. With no draft, the
// user changed nothing, so the state, and so the ZIP, stays the same.
export function stateForDownload(
  state: InterviewState,
  drafts: RunModels | null,
): InterviewState {
  return drafts ? withRunModels(state, drafts) : state;
}

// Whether the Interview can start. Only the interview role is required. The run roles are needed
// only for `metis engine run`, and embeddings are optional.
export function interviewReady(statuses: readonly ModelStatus[]): boolean {
  return !statuses.some(
    (status) => status.role === "interview" && !status.configured,
  );
}

// The text on the greyed-out start control while the interview role has no key.
export const START_BLOCKED = "Configure API keys to start interview";

// A banner above the page when the embeddings role has no key. The Interview still runs, but the
// Wizard cannot match Criteria to library graders. A missing interview key is not a banner: the
// start control turns grey and says what to do.
export function ModelBanner({
  statuses,
}: {
  statuses: readonly ModelStatus[];
}) {
  const embeddings = statuses.some(
    (status) => status.role === "embeddings" && !status.configured,
  );
  if (!embeddings) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-3 border-b border-border bg-muted px-6 py-2 text-sm"
    >
      <Info
        size={16}
        strokeWidth={1.75}
        aria-hidden
        className="shrink-0 text-muted-foreground"
      />
      <p>Set up embedding models to select optimal graders.</p>
    </div>
  );
}

// The run settings step: one model name for each role that the run calls. It comes after the
// last review and before the download. It is controlled, so the caller keeps the draft, saves it
// into the client-held state, and starts the download when the user continues.
export function RunSettings({
  roles,
  statuses,
  values,
  busy,
  onChange,
  onContinue,
}: {
  roles: readonly RunModelRole[];
  statuses: readonly ModelStatus[];
  values: RunModels;
  busy: boolean;
  onChange: (role: RunModelRole, value: string) => void;
  onContinue: () => void;
}) {
  const byRole = new Map(statuses.map((status) => [status.role, status]));
  return (
    <Panel className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold">Run settings</h2>
        <p className="text-sm text-muted-foreground">
          These models affect scores, so the specification records them. The
          download starts when you continue. Keys stay in <Mono>.env</Mono>.
          Leave a field empty to use the environment. See{" "}
          <Mono>{MODEL_GUIDE}</Mono>.
        </p>
      </div>
      {roles.map((role) => {
        const status = byRole.get(role);
        const id = `run-model-${role}`;
        return (
          <div key={role} className="flex flex-col gap-1">
            <label htmlFor={id} className="text-sm font-medium">
              {status?.label ?? role}
            </label>
            <input
              id={id}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
              value={values[role] ?? ""}
              placeholder={status?.model ?? ""}
              disabled={busy}
              onChange={(event) => onChange(role, event.currentTarget.value)}
            />
            <p className="text-xs text-muted-foreground">{ROLE_HELP[role]}</p>
            {status && !status.configured && (
              <p className="text-xs text-muted-foreground">
                Not configured: set {status.missing_vars.join(" or ")} before
                the run.
              </p>
            )}
          </div>
        );
      })}
      <div className="flex items-center gap-3">
        <Button variant="primary" disabled={busy} onClick={onContinue}>
          Continue and download
        </Button>
      </div>
    </Panel>
  );
}
