// The wire contract, mirrored from the package's Pydantic models. These types describe
// *shape* only — a behaviour and a persona are the same `Card` here, exactly as the package
// intends. The door branches on `type` and `CardComponentType`, never on domain words.
//
// Every string the user reads is composed by the package and arrives finished. This file
// invents no sentences.

// ── option identity ─────────────────────────────────────────────────────────

export interface OptionId {
  action: string; // "chat" · "tick" · "cover" · "continue"
  target?: string | null; // "EB-1" · "T-1"
  via?: string | null; // "EB-4" · "P-2"
}

// The key a door sends back — must match the package's `str(OptionId)` exactly.
export function optionKey(id: OptionId): string {
  return [id.action, id.target, id.via].filter(Boolean).join(":");
}

export interface Option {
  id: OptionId;
  label: string;
  selected?: boolean | null; // a toggleable chip when set, a plain button when null
  primary: boolean;
  enabled: boolean;
}

// ── card components (discriminated by shape) ─────────────────────────────────

export type CardComponentType = "text" | "options" | "number" | "upload";

export interface CardText {
  type: "text";
  label?: string | null;
  text: string;
}

export interface CardOptionGroup {
  type: "options";
  label?: string | null;
  options: Option[];
}

export interface CardNumberField {
  type: "number";
  label?: string | null;
  id: OptionId;
  value: number;
  min: number;
  max: number;
}

export interface CardUploadField {
  type: "upload";
  label?: string | null;
  id: OptionId;
  value: string[];
}

export type CardComponent =
  | CardText
  | CardOptionGroup
  | CardNumberField
  | CardUploadField;

interface CardBase {
  kind: "standard" | "scenario";
  id: string;
  title: string;
  section?: string | null;
  selected?: boolean | null; // a checkbox when set; none when null
  components: CardComponent[];
  options: Option[];
  note?: string | null;
  blocking: boolean;
}

export interface Card extends CardBase {
  kind: "standard";
}

export interface ScenarioCard extends CardBase {
  kind: "scenario";
  runs: number;
}

export type AnyCard = Card | ScenarioCard;

// ── warnings ─────────────────────────────────────────────────────────────────

export type WarningSource = "document" | "runtime";

export interface Warning {
  text: string;
  source: WarningSource;
  blocking: boolean;
  options: Option[];
}

// ── requests (discriminated by type) ─────────────────────────────────────────

export type RequestState = "pending" | "resolved";

// Fields every request shares, a one-directional projection of the interview's position that
// the package stamps on so a door can show a header and mark step boundaries. They never come
// back in a response. `step` here is the per-request 1-based step position — distinct from the
// `step` on `SessionView`/`SessionSummary`, which is the session's *current* step as a string.
// Optional because they are additive: an older persisted request omits them and renders as
// before.
interface RequestHeader {
  title?: string | null;
  step?: number | null;
  steps?: number | null;
}

export interface ChatRequest extends RequestHeader {
  type: "chat";
  prompt: string;
  state: RequestState;
  multiline: boolean;
  // Which node this exchange is scoped to when a per-card action raised it (a behaviour id).
  // Application context the door carries opaquely — it never branches on it. Null for a
  // screen-level chat.
  target?: string | null;
  // What the user typed, stamped on when the request resolves. Empty while pending — the
  // package records it here so a resolved block can show the reply beneath the question.
  answer: string;
}

export interface ChoiceRequest extends RequestHeader {
  type: "choice";
  prompt: string;
  state: RequestState;
  options: Option[];
  multi: boolean;
  cards: AnyCard[];
  warnings: Warning[];
  footer?: string | null;
  instruction?: string | null;
}

export interface FormField {
  id: string;
  label: string;
  placeholder: string;
  multiline: boolean;
}

export interface FormRequest extends RequestHeader {
  type: "form";
  prompt: string;
  state: RequestState;
  fields: FormField[];
  // Which behaviour a "Write one myself" criterion belongs to, carried opaquely so the scope
  // survives the round trip; the package reads it back on submit. Absent for the screen-level
  // add forms. Same field as a chat's `target`, same reason.
  target?: string | null;
  // The values the user submitted, stamped on at resolve — the form's analogue of a chat's
  // `answer`, keyed by field id. Empty while pending.
  answer: Record<string, string>;
}

export type WizardRequest = ChatRequest | ChoiceRequest | FormRequest;

// ── responses ─────────────────────────────────────────────────────────────────

export type UserResponse =
  | { type: "chat"; text: string }
  | {
      type: "choice";
      selected?: string[];
      values?: Record<string, number | string[]>;
    }
  | { type: "form"; values: Record<string, string> };

// ── profile (read-only document view) ────────────────────────────────────────

export interface Criterion {
  id: string;
  given: string;
  when: string;
  then: string;
  metric_fqn?: string | null;
}

export interface Behaviour {
  id: string;
  statement: string;
  priority: boolean;
  criteria: Criterion[];
}

export interface Epic {
  id: string;
  name: string;
  behaviours: Behaviour[];
}

export interface Persona {
  id: string;
  description: string;
}

export interface Scenario {
  id: string;
  description: string;
  behaviour_refs: string[];
  persona_refs: string[];
  fixtures: string[];
  num_trials: number;
}

export interface Product {
  name: string;
  summary: string;
  users: string;
  architecture: string;
}

export interface ProductProfile {
  product: Product;
  epics: Epic[];
  personas: Persona[];
  scenarios: Scenario[];
}

// ── the one payload that serves all three panes ──────────────────────────────

export interface SessionView {
  id: string;
  step: string;
  busy_message: string;
  done: boolean;
  requests: WizardRequest[];
  profile: ProductProfile;
}

export interface SessionSummary {
  id: string;
  title: string;
  step: string;
  updated: number;
}

// ── the metric catalogue (the hand-authoring door's picker) ───────────────────

// One row of the catalogue the manual form's metric picker offers. The library re-exports every
// metric from one flat namespace, so there is no module segment to group on; the picker shows one
// alphabetical list.
export interface MetricSpec {
  fqn: string;
  name: string;
  description: string;
}

// ── transport ─────────────────────────────────────────────────────────────────

// Errors the package never composed — an outage, a dropped connection, a 5xx. The banner
// that shows these is the door's own, kept visually distinct from a RUNTIME warning the
// package chose to attach.
export class TransportError extends Error {}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // a non-JSON error body is not worth surfacing over the status text
    }
    throw new TransportError(detail);
  }
  return res.json() as Promise<T>;
}

async function call<T>(input: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(input, init);
  } catch (cause) {
    throw new TransportError("Couldn't reach the wizard.", { cause });
  }
  return json<T>(res);
}

const POST = {
  method: "POST",
  headers: { "content-type": "application/json" },
};

export const api = {
  listSessions: () => call<SessionSummary[]>("/api/sessions"),

  createSession: () => call<SessionView>("/api/sessions", { ...POST }),

  readSession: (id: string) =>
    call<SessionView>(`/api/sessions/${encodeURIComponent(id)}`),

  respond: (id: string, response: UserResponse) =>
    call<SessionView>(`/api/sessions/${encodeURIComponent(id)}/respond`, {
      ...POST,
      body: JSON.stringify(response),
    }),

  experimentUrl: (id: string) =>
    `/api/sessions/${encodeURIComponent(id)}/experiment.yaml`,

  // ── the hand-authoring door ────────────────────────────────────────────────

  metrics: () => call<MetricSpec[]>("/api/metrics"),

  // Compile a hand-authored document and return the serialised file text. The browser gates
  // on the same rules the server enforces, so a rejection here is a safety net; when it does
  // fire, the server's message is surfaced through the same TransportError path as any 4xx.
  compileExperiment: async (document: unknown): Promise<string> => {
    let res: Response;
    try {
      res = await fetch("/api/experiment.yaml", {
        ...POST,
        body: JSON.stringify(document),
      });
    } catch (cause) {
      throw new TransportError("Couldn't reach the wizard.", { cause });
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // a non-JSON error body is not worth surfacing over the status text
      }
      throw new TransportError(detail);
    }
    return res.text();
  },
};
