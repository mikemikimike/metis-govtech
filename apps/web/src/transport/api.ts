// The API wire contract is generated from FastAPI. The small projections below only make
// server-defaulted arrays required for rendering and add browser-owned display types later in
// this module. They do not copy the Pydantic wire models.
import type { components, operations, paths } from "../generated/api.ts";

export type ApiPaths = paths;
type Schema = components["schemas"];
type RequiredFields<T, K extends keyof T> = Omit<T, K> & {
  [P in K]-?: T[P];
};
type Present<T> = Exclude<T, undefined | null>;
type JsonResponse<O, Status extends PropertyKey = 200> = O extends {
  responses: infer Responses;
}
  ? Responses extends Record<
      Status,
      { content: { "application/json": infer Body } }
    >
    ? Body
    : never
  : never;
type BinaryResponse<O, Status extends PropertyKey = 200> = O extends {
  responses: infer Responses;
}
  ? Responses extends Record<
      Status,
      { content: { "application/zip": infer Body } }
    >
    ? Body
    : never
  : never;

type StartOperation = operations["start_api_v1_wizard_interview_start_post"];
type TurnOperation = operations["turn_api_v1_wizard_interview_turn_post"];
type EndOperation = operations["end_api_v1_wizard_interview_end_post"];
type ExtractDocumentsOperation =
  operations["extract_document_text_api_v1_wizard_documents_extract_post"];
type CompileOperation = operations["compile__api_v1_wizard_compile_post"];
type MetricsOperation = operations["metrics_api_v1_metrics_get"];
type ConfigOperation = operations["config_api_v1_wizard_config_get"];
type PackageOperation = operations["package_api_v1_wizard_package_post"];
type PackageWireRequest = Schema["Body_package_api_v1_wizard_package_post"];

export type InterviewStep = Schema["InterviewStep"];
export type Perspective = Schema["Perspective"];
export type InterviewDocument = Schema["InterviewDocument"];
export type PerspectiveDefinition = Schema["PerspectiveDefinition"];
export type CapabilityCategory = Schema["CapabilityCategory"];
export type CapabilityCategoryDefinition =
  Schema["CapabilityCategoryDefinition"];
export type CapabilityConfidence = Schema["CapabilityConfidence"];
export type CapabilityDefinition = Schema["CapabilityDefinition"];
export type CapabilityEvidence = Schema["CapabilityEvidence"];
export type CapabilityId = Schema["CapabilityId"];
export type OptionId = Schema["OptionId"];
export function optionKey(id: OptionId): string {
  return [id.action, id.target, id.via].filter(Boolean).join(":");
}
export type Option = Schema["Option"];
export type CardText = Schema["CardText"];
export type CardOptionGroup = RequiredFields<
  Schema["CardOptionGroup"],
  "options"
>;
export type CardNumberField = Schema["CardNumberField"];
export type CardUploadField = RequiredFields<
  Schema["CardUploadField"],
  "value"
>;
export type CardDivider = Schema["CardDivider"];
export type CardComponent =
  CardText | CardOptionGroup | CardNumberField | CardUploadField | CardDivider;
export type Card = Omit<Schema["BehaviourCard"], "components" | "options"> & {
  components: CardComponent[];
  options: Option[];
};
export type ScenarioCard = Omit<
  Schema["ScenarioCard"],
  "components" | "options"
> & {
  components: CardComponent[];
  options: Option[];
};
export type AnyCard = Card | ScenarioCard;
export type WarningSource = Schema["WarningSource"];
export type Warning = RequiredFields<Schema["Warning"], "options">;

export type ChatRequest = Schema["ChatRequest"];
export type ChoiceRequest = Omit<
  Schema["ChoiceRequest"],
  "options" | "cards" | "warnings"
> & {
  options: Option[];
  cards: AnyCard[];
  warnings: Warning[];
};
export type FormField = Schema["FormField"];
export type FormRequest = RequiredFields<Schema["FormRequest"], "answer">;
export type WizardRequest = ChatRequest | ChoiceRequest | FormRequest;
export type AnyRequest = WizardRequest;
export type UserResponse =
  Schema["ChatResponse"] | Schema["ChoiceResponse"] | Schema["FormResponse"];
export type AnyResponse = UserResponse;

export type Criterion = Schema["Criterion"];
export type Behaviour = Omit<Schema["Behaviour"], "criteria"> & {
  criteria: Criterion[];
};
export type Feature = Omit<Schema["Feature"], "behaviours"> & {
  behaviours: Behaviour[];
};
export type Persona = Schema["Persona"];
export type Scenario = Schema["Scenario"];
export type Task = Omit<
  Schema["Task"],
  "fixtures" | "criterion_refs" | "num_trials"
> & { fixtures: string[]; criterion_refs: string[]; num_trials: number };
export type Product = Schema["Product"];
export type Specification = Omit<
  Schema["Specification"],
  "features" | "personas" | "scenarios" | "tasks"
> & {
  features: Feature[];
  personas: Persona[];
  scenarios: Scenario[];
  tasks: Task[];
};
export type Turn = Schema["Turn"];
export type InterviewState = RequiredFields<
  Omit<Schema["InterviewState"], "specification" | "pending">,
  "history" | "user_typed" | "issued_ids"
> & { specification: Specification; pending: WizardRequest | null };
export type MissingData = Schema["MissingData"];
export type InterviewSuccess = Omit<
  Schema["InterviewSuccess"],
  "state" | "missing"
> & {
  state: InterviewState;
  missing: MissingData[];
};
export type InterviewFailure = Omit<
  Schema["InterviewFailure"],
  "state" | "missing"
> & {
  state?: InterviewState | null;
  missing: MissingData[];
};
export type InterviewResult = InterviewSuccess | InterviewFailure;
export type CompileResult = Schema["CompileResult"];
export type MetricSpec = Schema["MetricSummary"];
export type StartRequest = Schema["InterviewStartRequest"];
export type StartResponse = JsonResponse<StartOperation>;
export type TurnRequest = Schema["InterviewTurnRequest"];
export type TurnResponse = JsonResponse<TurnOperation>;
export type EndRequest = Schema["InterviewEndRequest"];
export type EndResponse = JsonResponse<EndOperation>;
export type ExtractDocumentsResponse = JsonResponse<ExtractDocumentsOperation>;
export type CompileResponse = JsonResponse<CompileOperation>;
export type MetricsResponse = JsonResponse<MetricsOperation>;
export type ConfigResponse = JsonResponse<ConfigOperation>;
export type PackageRequest = Omit<PackageWireRequest, "files"> & {
  files?: PackageFile[] | null;
};
export type PackageResponse =
  BinaryResponse<PackageOperation> extends string
    ? Blob
    : BinaryResponse<PackageOperation>;

export interface PackageFile {
  name: string;
  blob: Blob;
}

type GeneratedCardComponent = Present<
  Schema["BehaviourCard"]["components"]
>[number];
function normalizeComponent(component: GeneratedCardComponent): CardComponent {
  if (component.type === "options")
    return { ...component, options: component.options ?? [] };
  if (component.type === "upload")
    return {
      ...component,
      value: component.value ?? [],
      available: component.available ?? [],
    };
  return component;
}

function normalizeCard(
  card: Schema["BehaviourCard"] | Schema["ScenarioCard"],
): AnyCard {
  return {
    ...card,
    components: (card.components ?? []).map(normalizeComponent),
    options: card.options ?? [],
  } as AnyCard;
}

function normalizeRequest(
  request: NonNullable<Schema["InterviewState"]["pending"]>,
): WizardRequest {
  if (request.type === "choice")
    return {
      ...request,
      options: request.options ?? [],
      cards: (request.cards ?? []).map(normalizeCard),
      warnings: (request.warnings ?? []).map((warning) => ({
        ...warning,
        options: warning.options ?? [],
      })),
    } as ChoiceRequest;
  if (request.type === "form")
    return { ...request, answer: request.answer ?? {} } as FormRequest;
  return request;
}

function normalizeSpecification(
  specification: Schema["Specification"],
): Specification {
  return {
    ...specification,
    features: (specification.features ?? []).map((feature) => ({
      ...feature,
      behaviours: (feature.behaviours ?? []).map((behaviour) => ({
        ...behaviour,
        criteria: behaviour.criteria ?? [],
      })),
    })),
    personas: specification.personas ?? [],
    scenarios: specification.scenarios ?? [],
    tasks: (specification.tasks ?? []).map((task) => ({
      ...task,
      fixtures: task.fixtures ?? [],
      criterion_refs: task.criterion_refs ?? [],
      num_trials: task.num_trials ?? 3,
    })),
  };
}

function normalizeState(state: Schema["InterviewState"]): InterviewState {
  return {
    ...state,
    specification: normalizeSpecification(state.specification),
    context: state.context,
    history: state.history ?? [],
    user_typed: state.user_typed ?? [],
    issued_ids: state.issued_ids ?? [],
    pending: state.pending ? normalizeRequest(state.pending) : null,
  };
}

type WireInterviewResult = StartResponse | TurnResponse | EndResponse;
function normalizeResult(resultValue: WireInterviewResult): InterviewResult {
  if (resultValue.type === "failure")
    return {
      ...resultValue,
      state: resultValue.state
        ? normalizeState(resultValue.state)
        : resultValue.state,
      missing: resultValue.missing ?? [],
    } as InterviewFailure;
  return {
    ...resultValue,
    state: normalizeState(resultValue.state),
    missing: resultValue.missing ?? [],
  } as InterviewSuccess;
}

// Browser-only display state. These fields never enter InterviewState or an API request.
export interface InitialDescriptionEntry {
  kind: "initial_description";
  id: string;
  description: string;
}
export interface InteractionEntry {
  kind: "interaction";
  request_id: string;
  request: WizardRequest;
  response?: UserResponse;
  status: "pending" | "sending" | "failed" | "answered" | "ended_unanswered";
  outbound?: {
    files: LocalFixture[];
    removedFixtures: string[];
    attempt: number;
  };
  failure?: {
    message: string;
    retryable: boolean;
    kind: "request" | "interrupted" | "storage";
  };
}
export type TranscriptEntry = InitialDescriptionEntry | InteractionEntry;
export interface LocalInterviewRecord {
  storage_version: 5;
  submission_revision?: number;
  id: string;
  created_at: number;
  updated_at: number;
  title: string;
  stage: InterviewStep;
  state: InterviewState;
  transcript: TranscriptEntry[];
  fixtures: LocalFixture[];
}
export interface LocalFixture {
  name: string;
  type: string;
  size: number;
  blob: Blob;
}
export interface InterviewSummary {
  id: string;
  title: string;
  updated: number;
}
export interface PresentationView {
  id: string;
  stage: InterviewStep;
  done: boolean;
  requests: WizardRequest[];
  specification: Specification;
}

export class TransportError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly retryable: boolean;
  constructor(
    message: string,
    options: {
      status?: number;
      code?: string;
      retryable?: boolean;
      cause?: unknown;
    } = {},
  ) {
    super(
      message,
      options.cause === undefined ? undefined : { cause: options.cause },
    );
    this.name = "TransportError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable ?? false;
  }
}

async function responseFor(
  path: keyof ApiPaths,
  init?: RequestInit,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    throw new TransportError("Couldn't reach the METIS API.", {
      retryable: true,
      cause,
    });
  }
  if (!response.ok) {
    let detail: Partial<InterviewFailure> = {};
    try {
      detail = (await response.json()) as Partial<InterviewFailure>;
    } catch {
      /* status is enough */
    }
    throw new TransportError(
      detail.message ?? `The METIS API returned HTTP ${response.status}.`,
      {
        status: response.status,
        code: detail.code,
        retryable: detail.retryable ?? response.status >= 500,
      },
    );
  }
  return response;
}

async function call<T>(path: keyof ApiPaths, init?: RequestInit): Promise<T> {
  return (await responseFor(path, init).then((response) =>
    response.json(),
  )) as T;
}

async function callBlob(
  path: keyof ApiPaths,
  init?: RequestInit,
): Promise<Blob> {
  return responseFor(path, init).then((response) => response.blob());
}

const JSON_POST: RequestInit = {
  method: "POST",
  headers: { "content-type": "application/json" },
};
function result(resultValue: WireInterviewResult): InterviewSuccess {
  const normalized = normalizeResult(resultValue);
  if (normalized.type === "failure")
    throw new TransportError(normalized.message, {
      code: normalized.code,
      retryable: normalized.retryable,
    });
  return normalized;
}

export const api = {
  start: async (
    description: string,
    capabilityEvidence: CapabilityEvidence,
    perspective: Perspective = "end_user",
    documents: InterviewDocument[] = [],
  ) => {
    const body: StartRequest = {
      description,
      perspective,
      known_capability_ids: capabilityEvidence.known_capability_ids,
      capability_confidence: capabilityEvidence.confidence,
      documents,
    };
    return result(
      await call<StartResponse>("/api/v1/wizard/interview/start", {
        ...JSON_POST,
        body: JSON.stringify(body),
      }),
    );
  },
  respond: async (
    state: InterviewState,
    request_id: string,
    response: UserResponse,
  ) => {
    const body: TurnRequest = { state, request_id, response };
    return result(
      await call<TurnResponse>("/api/v1/wizard/interview/turn", {
        ...JSON_POST,
        body: JSON.stringify(body),
      }),
    );
  },
  end: async (state: InterviewState) => {
    const body: EndRequest = { state };
    return result(
      await call<EndResponse>("/api/v1/wizard/interview/end", {
        ...JSON_POST,
        body: JSON.stringify(body),
      }),
    );
  },
  compile: (specification: Specification) =>
    call<CompileResponse>("/api/v1/wizard/compile", {
      ...JSON_POST,
      body: JSON.stringify(specification),
    }),
  metrics: () => call<MetricsResponse>("/api/v1/metrics"),
  config: () => call<ConfigResponse>("/api/v1/wizard/config"),
  extractDocuments: (files: readonly File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return call<ExtractDocumentsResponse>("/api/v1/wizard/documents/extract", {
      method: "POST",
      body: form,
    });
  },
  package: (specification: Specification, files: readonly PackageFile[]) => {
    const form = new FormData();
    form.append("specification", JSON.stringify(specification));
    for (const file of files) form.append("files", file.blob, file.name);
    return callBlob("/api/v1/wizard/package", {
      method: "POST",
      body: form,
    });
  },
};

export function toSummary(record: LocalInterviewRecord): InterviewSummary {
  return { id: record.id, title: record.title, updated: record.updated_at };
}
export function titleFor(specification: Specification): string {
  return specification.product.name.trim() || "Untitled Interview";
}
