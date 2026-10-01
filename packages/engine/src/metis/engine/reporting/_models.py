"""Pydantic models for the product evaluation report (report.json).

These models define the contract for the JSON report that downstream
consumers (web frontend, insights, external integrations) depend on.
They are the source of truth for schemas/report.schema.json.

After any change here, run `make generate-schema` and commit the
updated schema files.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

_REPORT_VERSION = 2


class Timings(BaseModel, extra="allow"):
    turn_metrics_seconds: float = 0.0
    session_metrics_seconds: float = 0.0


class Routing(BaseModel, extra="allow"):
    total_traces: int = 0
    total_sessions: int = 0
    direct_handle: int = 0
    routing_failed: int = 0
    subagent_counts: dict[str, int] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    turn: int
    user: str
    product: str
    errors: list[str] = Field(default_factory=list)


class Trial(BaseModel):
    id: str
    session: str
    persona: str
    scenario: str
    stopReason: str
    message: str
    failureSource: str
    turns: int
    duration: float | None = None
    conversation: list[ConversationTurn] = Field(default_factory=list)
    category: str
    features: list[str] = Field(default_factory=list)
    results: dict[str, object] = Field(default_factory=dict)


class TrialsSummary(BaseModel):
    attempted: int
    successful: int
    rate: int | None = None
    items: list[Trial] = Field(default_factory=list)


class PlanScenario(BaseModel):
    id: str
    personas: list[str]
    trials: int
    sessionsPlanned: int
    sessionsRun: int
    personasRun: list[str]
    metricsAsked: int
    metricsScored: int


class Plan(BaseModel):
    personas: list[str]
    scenarios: list[PlanScenario]


class AxisRow(BaseModel):
    id: str
    rate: int | None = None
    pass_: int = Field(0, alias="pass")
    fail: int = 0
    ran: int = 0
    skip: int = 0
    sessions: int = 0
    behaviours: int = 0
    metrics: int = 0
    partners: int = 0
    partnerTotal: int = 0

    model_config = {"populate_by_name": True}


class CriterionBreakdownCell(BaseModel):
    rate: int
    n: int
    pass_: int = Field(alias="pass")
    fail: int
    skip: int

    model_config = {"populate_by_name": True}


class BlankCause(BaseModel):
    cause: str
    note: str


class EvidenceItem(BaseModel):
    status: str
    message: str
    trace: str
    session: str
    turn: str
    persona: str | None = None
    scenario: str | None = None


class Criterion(BaseModel):
    given: str
    when: str
    then: str
    metric: str
    fqn: str | None = None
    pass_: int = Field(0, alias="pass")
    fail: int = 0
    skip: int = 0
    rate: int | None = None
    status: str | None = None
    blank: BlankCause | None = None
    P: list[CriterionBreakdownCell | None] = Field(default_factory=list)
    S: list[CriterionBreakdownCell | None] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class Behaviour(BaseModel):
    label: str
    statement: str
    detail: str
    priority: bool
    criteria: list[str]
    rate: int | None = None
    status: str | None = None


class Feature(BaseModel):
    id: str
    name: str
    behaviours: list[str]
    rate: int | None = None
    status: str | None = None


class ResultTableColumn(BaseModel):
    criterion: str
    metric: str


class ResultTableFeature(BaseModel):
    id: str
    name: str
    columns: list[ResultTableColumn]


class TrialResult(BaseModel):
    pass_: int = Field(0, alias="pass")
    fail: int = 0
    skip: int = 0
    evaluated: int = 0
    rate: int | None = None
    status: str | None = None

    model_config = {"populate_by_name": True}


class ResultTableRow(Trial):
    results: dict[str, TrialResult] = Field(default_factory=dict)


class ResultTable(BaseModel):
    features: list[ResultTableFeature]
    rows: list[ResultTableRow]


class UnmappedMetric(BaseModel):
    metric: str
    pass_: int = Field(0, alias="pass")
    fail: int = 0
    skip: int = 0
    why: str = ""

    model_config = {"populate_by_name": True}


class Report(BaseModel):
    """Top-level model for report.json.

    This is the contract downstream consumers depend on.
    """

    product: str
    run: str
    date: str
    sessions: int
    turns: int
    results: int
    latency: float | None = None
    timings: Timings = Field(default_factory=Timings)
    routing: Routing = Field(default_factory=Routing)
    threshold: int
    trials: TrialsSummary
    plan: Plan
    personas: list[str]
    scenarios: list[str]
    describe: dict[str, dict[str, str]]
    axes: dict[str, list[AxisRow]]
    behaviourTotal: int
    personasRun: list[str]
    scenariosRun: list[str]
    features: list[Feature]
    behaviours: dict[str, Behaviour]
    criteria: dict[str, Criterion]
    resultTable: ResultTable
    unmapped: list[UnmappedMetric]
    unresolved: list[str]

    model_config = {"populate_by_name": True}
