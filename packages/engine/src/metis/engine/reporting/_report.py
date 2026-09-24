"""Join a run's metric results onto the product profile that asked for them.

The metric table tells you which metric failed. It does not tell you which product
behaviour is weak, because a metric name is not a behaviour. This module builds that
answer, and it builds it mechanically: every number comes from a file the run already
wrote. No model writes any text.

The chain, from the spec to a score::

    profile.yaml  criterion.metric_fqn
       -> library class .__name__          the metric display name
       -> metric result name               pass / fail / skip per turn or per session
       -> record.json config.persona       the persona axis

Two roll-ups answer two questions, so both are kept:

* The spec tree is **worst of**. A behaviour is only as strong as its weakest criterion,
  and a feature is only as strong as its weakest behaviour. That is a compliance question.
* The persona axis and the scenario axis are a **plain pass rate**, counted once per
  metric result. That is a difficulty question. One result can attribute to several
  criteria, so a count of attributions would make a busy persona look busier than it is.
"""

from __future__ import annotations

import importlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from metis.core.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

logger = get_logger(__name__)

#: A result entry as the JSON report writes it. Read only, so the caller's own entry type
#: (a `TypedDict`, for one) is accepted as is.
Row = Mapping[str, Any]

# This is a report fallback. The aggregator will supply the threshold in a later change.
PASS_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def load_report_sources(
    run_dir: Path,
) -> tuple[dict, dict, dict[str, str], list[dict]] | None:
    """Read the profile, experiment, persona map, and trial outcomes.

    `simulate` freezes its input directory into the run, so the profile and the
    experiment beside the results are the ones this run actually used.

    :param run_dir: The experiment directory that holds `inputs/` and `runs/`.
    :returns: profile, experiment, and session id to persona id. `None` if the run has
        no profile, which is the case for every run made before the wizard wrote one.
    """
    profile_path = run_dir / "inputs" / "profile.yaml"
    if not profile_path.is_file():
        logger.debug("report_skipped", reason="no profile.yaml", path=str(profile_path))
        return None

    try:
        import yaml

        profile = yaml.safe_load(profile_path.read_text())
    except (OSError, ValueError) as exc:
        logger.warning("profile_unreadable", path=str(profile_path), error=str(exc))
        return None

    experiment: dict = {}
    experiment_path = run_dir / "inputs" / "experiment.yaml"
    if experiment_path.is_file():
        try:
            import yaml

            experiment = yaml.safe_load(experiment_path.read_text()) or {}
        except (OSError, ValueError) as exc:
            logger.warning(
                "experiment_unreadable",
                path=str(experiment_path),
                error=str(exc),
            )

    persona_of, trial_outcomes = _load_run_records(run_dir)
    return profile, experiment, persona_of, trial_outcomes


def _load_run_records(run_dir: Path) -> tuple[dict[str, str], list[dict]]:
    """Read persona attribution and the exact recorded outcome of each trial.

    The persona lives on the simulation record, not on the trace, so it must come from
    `runs/<name>/record.json`.
    """
    persona_of: dict[str, str] = {}
    trials: list[dict] = []
    for record_path in sorted(run_dir.glob("runs/*/record.json")):
        try:
            record = json.loads(record_path.read_text())
        except (OSError, ValueError) as exc:
            logger.debug("record_unreadable", path=str(record_path), error=str(exc))
            continue
        config = record.get("config") or {}
        outcome = record.get("outcome") or {}
        session = record.get("target_session_id")
        persona = config.get("persona")
        if session and persona:
            persona_of[session] = persona

        stop_reason = str(outcome.get("stop_reason") or "unknown")
        conversation = record.get("conversation") or []
        product_errors = [
            problem for turn in conversation for problem in _turn_problems(turn)
        ]
        failure_source = _failure_source(
            outcome.get("failure_source") or record.get("failure_source")
        )
        message = stop_reason if stop_reason == "goal_achieved" else None
        message = outcome.get("failure_message") or message
        message = message or outcome.get("message") or outcome.get("error")
        message = message or record.get("error")
        if not message and product_errors:
            message = product_errors[-1]
        if stop_reason == "goal_achieved":
            failure_source = "outcome"
        elif not failure_source and product_errors:
            failure_source = "product"

        if stop_reason == "system_error" and (not failure_source or not message):
            legacy_source, legacy_message = _legacy_failure_details(
                run_dir, record_path, config
            )
            failure_source = failure_source or legacy_source
            message = message or legacy_message

        if not failure_source:
            if stop_reason == "goal_achieved":
                failure_source = "outcome"
            elif stop_reason == "user_abandoned":
                failure_source = "userAgent"
            else:
                failure_source = "evaluationRunner"
        trials.append(
            {
                "id": record_path.parent.name,
                "session": session or "",
                "persona": persona or "",
                "scenario": config.get("scenario") or "",
                "stopReason": stop_reason,
                "message": str(message or stop_reason),
                "failureSource": failure_source,
                "turns": int(outcome.get("total_turns") or 0),
                "duration": outcome.get("duration_seconds"),
                # A retried run is a run whose comparability is worth a second
                # look: a retry is a free do-over only if the failure was
                # independent of what the run was doing, which is not obvious
                # for ConsecutiveFailureEscalation. Issue #346.
                #
                # The flag only, deliberately. `attempt` already says how many
                # attempts were spent, and the per-attempt detail (failure type,
                # turn reached, message) stays in the run's `record.json`, which
                # is not a published schema. report.schema.json is audited by
                # downstream consumers, so every field in it is a contract to
                # keep — not somewhere to mirror data nothing renders.
                "attempt": int(record.get("attempt_number") or 1),
                "conversation": [
                    {
                        "turn": int(turn.get("turn_number") or index + 1),
                        "user": str(turn.get("user_message") or ""),
                        "product": str(
                            (turn.get("target_response") or {}).get("text") or ""
                        ),
                        "errors": _turn_problems(turn),
                    }
                    for index, turn in enumerate(conversation)
                ],
            }
        )
    return persona_of, trials


def _row_index(row: dict) -> int:
    """``action_index`` if it survived the round trip as an int, else ``0``.

    Coerced rather than trusted for the same reason :func:`_turn_problems`
    sorts at all: no validator ran on this record, so a missing key or a string
    must order somewhere rather than raise mid-report.
    """
    value = row.get("action_index")
    return value if isinstance(value, int) else 0


def _turn_problems(turn: dict) -> list[str]:
    """Problem strings from one recorded turn that count against the product.

    Notices first, then the ``detail`` of each failed action row in
    ``action_index`` order. Three things here look like defensive noise and
    are not, because this read path never rebuilds the Pydantic model — a
    record from an older engine, a hand-built fixture or a third-party runner
    arrives with no validator having run on it:

    - the **sort**, because ``product_errors[-1]`` becomes the report's
      headline message and I1's ordering guarantee binds only the write path;
    - the **detail fallback**, because I2's non-empty-detail rule binds only
      the write path too, and dropping a row with an empty detail would empty
      ``product_errors`` and flip ``failureSource`` to ``evaluationRunner`` —
      blaming METIS for the target's own failure;
    - the **withheld exclusion**, which keeps the opposite misattribution out:
      an action METIS itself rejected before dispatch never reached the
      target, so the target cannot be blamed for it.
    """
    response = turn.get("target_response") or {}
    results = sorted(response.get("action_results") or [], key=_row_index)
    return [
        *(str(notice) for notice in response.get("response_notices") or []),
        *(
            str(
                row.get("detail")
                or f"action {row.get('action_index')} failed with no detail recorded"
            )
            for row in results
            if not row.get("succeeded") and not row.get("withheld")
        ),
    ]


def _failure_source(value: object) -> str | None:
    """Map recorded failure-source names to the report vocabulary."""
    if value is None:
        return None
    normalised = str(value).strip().lower().replace("-", "_")
    return {
        "product": "product",
        "target": "product",
        "orca": "product",
        "user_agent": "userAgent",
        "useragent": "userAgent",
        "evaluation_runner": "evaluationRunner",
        "eval_runner": "evaluationRunner",
        "runner": "evaluationRunner",
        "system": "evaluationRunner",
    }.get(normalised)


def _legacy_failure_details(
    run_dir: Path, record_path: Path, config: Mapping[str, Any]
) -> tuple[str | None, str | None]:
    """Read an explicit error source from old simulation logs when available.

    Older records stored only ``system_error``. Their matching run log still states
    whether the user-agent LLM failed or the evaluation runner crashed. This fallback
    lets old reports use that fact without guessing from the error text.
    """
    _, separator, trial_text = record_path.parent.name.rpartition("-")
    scenario = str(config.get("scenario") or "")
    persona = str(config.get("persona") or "")
    if not separator or not trial_text.isdigit() or not scenario or not persona:
        return None, None
    log_path = (
        run_dir / "logs" / f"simulate-{scenario}_{persona}-{int(trial_text):02d}.log"
    )
    try:
        log_text = log_path.read_text()
    except OSError:
        return None, None

    user_agent_marker = "STOP: system_error (user agent LLM failed: "
    marker_at = log_text.rfind(user_agent_marker)
    if marker_at >= 0:
        message = log_text[marker_at + len(user_agent_marker) :]
        message = message.split("\n[", 1)[0].strip()
        if message.endswith(")"):
            message = message[:-1].rstrip()
        return "userAgent", message or None

    runner_marker = f"unexpected crash for {scenario} × {persona}: "
    marker_at = log_text.rfind(runner_marker)
    if marker_at >= 0:
        message = log_text[marker_at + len(runner_marker) :]
        message = message.split("\n[", 1)[0].strip()
        return "evaluationRunner", message or None
    return None, None


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def status(rate: float | None, threshold: float = PASS_THRESHOLD) -> str | None:
    """Return pass or fail for a 0 to 1 rate. Keep no-data separate."""
    if rate is None:
        return None
    return "pass" if rate >= threshold else "fail"


def display_names(fqns: set[str]) -> tuple[dict[str, str], list[str]]:
    """Map each metric FQN to the display name its results carry.

    The display name lives on a `__name__` property, so the class must be built. Default
    arguments are enough for every metric in the library today. A bad reference is
    reported, not raised, because one broken criterion must not lose the whole report.
    """
    resolved: dict[str, str] = {}
    failed: list[str] = []
    modules: dict[str, Any] = {}
    for fqn in sorted(fqns):
        module_path, _, class_name = fqn.rpartition(".")
        try:
            module = modules.setdefault(
                module_path, importlib.import_module(module_path)
            )
            resolved[fqn] = getattr(module, class_name)().__name__
        except Exception as exc:  # noqa: BLE001 - a bad reference must not stop the report
            failed.append(f"{fqn}: {type(exc).__name__}")
    return resolved, failed


def clean_reason(text: str) -> str:
    """A skip reason without its marker and without its dashes."""
    out = (text or "").strip()
    for marker in (" - SKIPPED", " — SKIPPED", " SKIPPED"):
        if out.endswith(marker):
            out = out[: -len(marker)].rstrip()
    return out.replace("—", ",").replace("  ", " ")


def _clean_prose(text: str | None) -> str:
    """Spec prose as the page shows it. The page keeps one punctuation style."""
    return (text or "").replace("—", ",").strip()


def _new_bucket() -> dict:
    return {"pass": 0, "fail": 0, "skip": 0}


def _rate_of(bucket: dict) -> float | None:
    ran = bucket["pass"] + bucket["fail"]
    return bucket["pass"] / ran if ran else None


def _add(bucket: dict, row: dict) -> None:
    if row["skipped"]:
        bucket["skip"] += 1
    elif row["success"]:
        bucket["pass"] += 1
    else:
        bucket["fail"] += 1


def _metric_refs(scenario: Mapping[str, Any]) -> list[str]:
    """The metric FQNs one scenario asks for. A ref is a string or a single key mapping."""
    return [
        next(iter(ref)) if isinstance(ref, dict) else ref
        for ref in scenario.get("metric_refs") or []
    ]


# ---------------------------------------------------------------------------
# One row per metric result
# ---------------------------------------------------------------------------


def flatten_results(
    test_results: Sequence[Row],
    session_metrics: Sequence[Row] | None,
    persona_of: Mapping[str, str],
) -> list[dict]:
    """One row per metric result, tagged with its scenario and its persona."""
    scenario_of = {
        t.get("session_id", ""): t.get("scenario_id", "") for t in test_results
    }
    rows: list[dict] = []

    for case in test_results:
        for metric in case.get("metrics", []):
            rows.append(
                {
                    "metric": metric["name"],
                    "scenario": case.get("scenario_id", ""),
                    "persona": persona_of.get(case.get("session_id", "")),
                    "skipped": bool(metric.get("skipped")),
                    "success": bool(metric.get("success")),
                    "reason": metric.get("reason", ""),
                    "trace": case.get("trace_id", ""),
                    "session": case.get("session_id", ""),
                    "turn": f"{case.get('turn_index', 0) + 1}/{case.get('total_turns', 1)}",
                }
            )

    for session in session_metrics or []:
        sid = session.get("session_id", "")
        for metric in session.get("metrics", []):
            rows.append(
                {
                    "metric": metric["name"],
                    "scenario": scenario_of.get(sid, ""),
                    "persona": persona_of.get(sid),
                    "skipped": bool(metric.get("skipped")),
                    "success": bool(metric.get("success")),
                    "reason": metric.get("reason", ""),
                    "trace": sid,
                    "session": sid,
                    "turn": f"session, {session.get('num_turns', 0)} turns",
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Plan against actual
# ---------------------------------------------------------------------------


def build_plan(
    experiment: Mapping[str, Any], rows: list[dict], name_of: dict[str, str]
) -> dict:
    """What `experiment.yaml` asked for, beside what the run produced.

    Three levels matter to a reader, and each one can lose things::

        spec    profile.yaml      every persona and scenario the product owner declared
        plan    experiment.yaml   the subset this experiment asked to run
        actual  the results       what came back
    """
    plan_personas = [p["id"] for p in experiment.get("personas") or [] if p.get("id")]

    seen_sessions: dict[str, set[str]] = defaultdict(set)
    seen_personas: dict[str, set[str]] = defaultdict(set)
    ran_metrics: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        sid = row["scenario"] or ""
        seen_sessions[sid].add(row["session"])
        if row["persona"]:
            seen_personas[sid].add(row["persona"])
        if not row["skipped"]:
            ran_metrics[sid].add(row["metric"])

    scenarios = []
    for scenario in experiment.get("scenarios") or []:
        sid = scenario.get("id")
        if not sid:
            continue
        personas = list(scenario.get("persona_refs") or plan_personas)
        # Mirror metis-engine's Scenario schema default of 1, not the wizard's
        # domain default of 3: the plan describes what the engine would run,
        # and a hand-written config that omits the field runs once. Unreachable
        # for a wizard-generated config, which always writes it explicitly.
        trials = int(scenario.get("num_trials", 1))
        refs = _metric_refs(scenario)
        # A scenario can ask for a metric no criterion names, so resolve the strays too.
        strays = {fqn for fqn in refs if fqn not in name_of}
        if strays:
            name_of.update(display_names(strays)[0])
        asked = {name_of.get(fqn, fqn.rpartition(".")[2]) for fqn in refs}
        scenarios.append(
            {
                "id": sid,
                "personas": personas,
                "trials": trials,
                "sessionsPlanned": len(personas) * trials,
                "sessionsRun": len(seen_sessions.get(sid, ())),
                "personasRun": sorted(seen_personas.get(sid, ())),
                "metricsAsked": len(asked),
                "metricsScored": len(asked & ran_metrics.get(sid, set())),
            }
        )

    return {"personas": plan_personas, "scenarios": scenarios}


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def build_report(
    profile: Mapping[str, Any],
    experiment: Mapping[str, Any],
    test_results: Sequence[Row],
    *,
    persona_of: Mapping[str, str] | None = None,
    session_metrics: Sequence[Row] | None = None,
    run_id: str = "report",
    timestamp: str = "",
    latency_seconds: float | None = None,
    timings: Mapping[str, Any] | None = None,
    routing: Mapping[str, Any] | None = None,
    trial_outcomes: Sequence[Row] | None = None,
) -> dict:
    """Build the report the page renders.

    :param profile: The parsed `profile.yaml` for the product under test.
    :param experiment: The parsed `experiment.yaml` that planned this run.
    :param test_results: Per turn results, in the shape the JSON report writes.
    :param persona_of: Session id to persona id, from the simulation records.
    :param session_metrics: Session level results, same shape as `test_results`.
    :param trial_outcomes: Exact outcomes read from the simulation records.
    :returns: A plain dict, ready to serialise into the page.
    """
    rows = flatten_results(test_results, session_metrics, persona_of or {})

    criteria: dict[str, dict] = {}
    behaviour_of: dict[str, str] = {}
    for feature in profile.get("features") or []:
        for behaviour in feature.get("behaviours") or []:
            for criterion in behaviour.get("criteria") or []:
                criteria[criterion["id"]] = criterion
                behaviour_of[criterion["id"]] = behaviour["id"]

    # Which behaviours each scenario is meant to exercise. A metric result is attributed
    # only to criteria on a behaviour its own scenario covers, so a shared metric does
    # not spill its score across unrelated behaviours.
    covers: dict[str, list[str]] = {
        s["id"]: s.get("behaviour_refs") or [] for s in profile.get("scenarios") or []
    }

    fqns = {c["metric_fqn"] for c in criteria.values() if c.get("metric_fqn")}
    name_of, unresolved = display_names(fqns)

    by_name: dict[str, list[str]] = defaultdict(list)
    for cid, criterion in criteria.items():
        fqn = criterion.get("metric_fqn")
        if fqn and fqn in name_of:
            by_name[name_of[fqn]].append(cid)

    per_criterion: dict[str, dict] = {
        cid: {
            "all": _new_bucket(),
            "persona": defaultdict(_new_bucket),
            "scenario": defaultdict(_new_bucket),
            "session": defaultdict(_new_bucket),
            "evidence": [],
            "skips": Counter(),
            "metricName": None,
        }
        for cid in criteria
    }
    unmapped: dict[str, dict] = defaultdict(_new_bucket)
    unmapped_reason: dict[str, str] = {}

    def new_axis() -> dict:
        return {
            "pass": 0,
            "fail": 0,
            "skip": 0,
            "sessions": set(),
            "behaviours": set(),
            "metrics": set(),
            "partners": set(),
        }

    axis_stats: dict[str, dict[str, dict]] = {
        "P": defaultdict(new_axis),
        "S": defaultdict(new_axis),
    }

    for row in rows:
        candidates = by_name.get(row["metric"], [])
        allowed = set(covers.get(row["scenario"] or "", []))
        matched = [
            cid for cid in candidates if behaviour_of[cid] in allowed
        ] or candidates
        if not matched:
            _add(unmapped[row["metric"]], row)
            if row["metric"] not in unmapped_reason:
                unmapped_reason[row["metric"]] = (
                    "not named by any criterion"
                    if row["metric"] not in by_name
                    else "no covering scenario"
                )
            continue

        touched = {behaviour_of[cid] for cid in matched}
        for key, name, partner in (
            ("P", row["persona"], row["scenario"]),
            ("S", row["scenario"], row["persona"]),
        ):
            if not name:
                continue
            slot = axis_stats[key][name]
            _add(slot, row)
            slot["sessions"].add(row["session"])
            slot["behaviours"] |= touched
            slot["metrics"].add(row["metric"])
            if partner:
                slot["partners"].add(partner)

        for cid in matched:
            slot = per_criterion[cid]
            if slot["metricName"] is None:
                slot["metricName"] = row["metric"]
            _add(slot["all"], row)
            if row["persona"]:
                _add(slot["persona"][row["persona"]], row)
            if row["scenario"]:
                _add(slot["scenario"][row["scenario"]], row)
            if row["session"]:
                _add(slot["session"][row["session"]], row)
            slot["evidence"].append(
                {
                    "status": (
                        "skip"
                        if row["skipped"]
                        else "pass"
                        if row["success"]
                        else "fail"
                    ),
                    "message": row["reason"],
                    "trace": row["trace"],
                    "session": row["session"],
                    "turn": row["turn"],
                    "persona": row["persona"],
                    "scenario": row["scenario"],
                }
            )
            if row["skipped"]:
                slot["skips"][clean_reason(row["reason"])] += 1

    personas = [p["id"] for p in profile.get("personas") or []]
    scenarios = [s["id"] for s in profile.get("scenarios") or []]

    def split(slot: dict, key: str, order: list[str]) -> list[dict | None]:
        """One cell per column of the tree strip. `None` means never exercised."""
        out: list[dict | None] = []
        for name in order:
            bucket = slot[key].get(name)
            if not bucket or bucket["pass"] + bucket["fail"] == 0:
                out.append(None)
            else:
                out.append(
                    {
                        "rate": round(100 * (_rate_of(bucket) or 0)),
                        "n": bucket["pass"] + bucket["fail"],
                        "pass": bucket["pass"],
                        "fail": bucket["fail"],
                        "skip": bucket["skip"],
                    }
                )
        return out

    asked_fqns = {
        fqn
        for scenario in experiment.get("scenarios") or []
        for fqn in _metric_refs(scenario)
    }
    unresolved_fqns = {item.split(":")[0] for item in unresolved}
    appeared = {row["metric"] for row in rows}

    def blank_cause(criterion: Mapping[str, Any], slot: dict) -> dict:
        """Why a criterion has no pass rate. One cause each, checked in chain order.

        The chain can break in five places, and the reader needs to know which one,
        because each asks for a different fix: write a metric, add the class to the
        library, put the metric in the experiment, or make the run reach the behaviour.
        """
        fqn = criterion.get("metric_fqn")
        name = name_of.get(fqn or "", "")
        if not fqn:
            return {
                "cause": "no metric",
                "note": "the spec names no metric for this criterion",
            }
        if fqn in unresolved_fqns:
            short = fqn.rpartition(".")[2]
            return {"cause": "no class", "note": f"{short} is not in the library"}
        if fqn not in asked_fqns:
            return {
                "cause": "not asked",
                "note": f"no scenario in the experiment asks for {name}",
            }
        if name not in appeared:
            return {
                "cause": "no result",
                "note": f"{name} produced no result in this run",
            }
        if slot["skips"]:
            reason, count = slot["skips"].most_common(1)[0]
            return {
                "cause": "all skipped",
                "note": f"{count} skipped, {reason.lower()}",
            }
        return {
            "cause": "no result",
            "note": "the metric produced no result for this criterion",
        }

    out_criteria: dict[str, dict] = {}
    for cid, criterion in criteria.items():
        slot = per_criterion[cid]
        rate = _rate_of(slot["all"])
        description = criterion["description"]
        out_criteria[cid] = {
            "given": description["given"],
            "when": description["when"],
            "then": description["then"],
            "metric": slot["metricName"]
            or name_of.get(criterion.get("metric_fqn") or "", ""),
            "fqn": criterion.get("metric_fqn"),
            "pass": slot["all"]["pass"],
            "fail": slot["all"]["fail"],
            "skip": slot["all"]["skip"],
            "rate": None if rate is None else round(100 * rate),
            "status": status(rate),
            "blank": None if rate is not None else blank_cause(criterion, slot),
            "P": split(slot, "persona", personas),
            "S": split(slot, "scenario", scenarios),
            "evidence": slot["evidence"],
        }

    out_behaviours: dict[str, dict] = {}
    for feature in profile.get("features") or []:
        for behaviour in feature.get("behaviours") or []:
            live = [
                out_criteria[c["id"]]["rate"]
                for c in behaviour.get("criteria") or []
                if out_criteria[c["id"]]["rate"] is not None
            ]
            statement = _clean_prose(behaviour["description"])
            _, _, rest = statement.partition(". ")
            out_behaviours[behaviour["id"]] = {
                "label": behaviour["name"],
                "statement": statement,
                "detail": rest,
                "priority": behaviour["measured"],
                "criteria": [c["id"] for c in behaviour.get("criteria") or []],
                "rate": min(live) if live else None,
                "status": status(min(live) / 100 if live else None),
            }

    out_features = []
    for feature in profile.get("features") or []:
        live = [
            out_behaviours[b["id"]]["rate"]
            for b in feature.get("behaviours") or []
            if out_behaviours[b["id"]]["rate"] is not None
        ]
        out_features.append(
            {
                "id": feature["id"],
                "name": feature.get("name", feature["id"]),
                "behaviours": [b["id"] for b in feature.get("behaviours") or []],
                "rate": min(live) if live else None,
                "status": status(min(live) / 100 if live else None),
            }
        )

    def axis_rows(key: str, order: list[str], partner_total: int) -> list[dict]:
        out = []
        for name in order:
            slot = axis_stats[key].get(name)
            if slot is None:
                out.append(
                    {
                        "id": name,
                        "rate": None,
                        "pass": 0,
                        "fail": 0,
                        "ran": 0,
                        "skip": 0,
                        "sessions": 0,
                        "behaviours": 0,
                        "metrics": 0,
                        "partners": 0,
                        "partnerTotal": partner_total,
                    }
                )
                continue
            rate = _rate_of(slot)
            out.append(
                {
                    "id": name,
                    "rate": None if rate is None else round(100 * rate),
                    "pass": slot["pass"],
                    "fail": slot["fail"],
                    "ran": slot["pass"] + slot["fail"],
                    "skip": slot["skip"],
                    "sessions": len(slot["sessions"]),
                    "behaviours": len(slot["behaviours"]),
                    "metrics": len(slot["metrics"]),
                    "partners": len(slot["partners"]),
                    "partnerTotal": partner_total,
                }
            )
        return out

    def described(items: Sequence[Row]) -> dict[str, str]:
        return {
            i["id"]: _clean_prose(i.get("description")) for i in items if i.get("id")
        }

    feature_of_behaviour = {
        behaviour["id"]: feature.get("name", feature["id"])
        for feature in profile.get("features") or []
        for behaviour in feature.get("behaviours") or []
    }
    features_of_scenario = {
        scenario["id"]: list(
            dict.fromkeys(
                feature_of_behaviour[behaviour_id]
                for behaviour_id in scenario.get("behaviour_refs") or []
                if behaviour_id in feature_of_behaviour
            )
        )
        for scenario in profile.get("scenarios") or []
    }

    trials = []
    for item in trial_outcomes or []:
        stop_reason = str(item.get("stopReason") or "unknown")
        if stop_reason == "goal_achieved":
            category = "succeeded"
        elif "timeout" in stop_reason:
            category = "timedOut"
        elif "error" in stop_reason:
            category = "error"
        else:
            category = "abandoned"
        scenario_id = str(item.get("scenario") or "")
        trials.append(
            {
                **item,
                "category": category,
                "features": features_of_scenario.get(scenario_id, []),
            }
        )
    trial_successes = sum(t["category"] == "succeeded" for t in trials)
    trial_rate = round(100 * trial_successes / len(trials)) if trials else None

    table_features = [
        {
            "id": feature["id"],
            "name": feature.get("name", feature["id"]),
            "columns": [
                {
                    "criterion": criterion["id"],
                    "metric": out_criteria[criterion["id"]]["metric"],
                }
                for behaviour in feature.get("behaviours") or []
                for criterion in behaviour.get("criteria") or []
                if per_criterion[criterion["id"]]["session"]
            ],
        }
        for feature in profile.get("features") or []
    ]
    table_features = [feature for feature in table_features if feature["columns"]]

    table_rows = []
    for trial in trials:
        session = str(trial.get("session") or "")
        results = {}
        for cid, slot in per_criterion.items():
            bucket = slot["session"].get(session)
            if not bucket:
                continue
            evaluated = bucket["pass"] + bucket["fail"]
            rate = _rate_of(bucket)
            results[cid] = {
                "pass": bucket["pass"],
                "fail": bucket["fail"],
                "skip": bucket["skip"],
                "evaluated": evaluated,
                "rate": None if rate is None else round(100 * rate),
                "status": status(rate),
            }
        table_rows.append({**trial, "results": results})

    return {
        "product": (profile.get("product") or {}).get("name", "the product"),
        "run": run_id,
        "date": (timestamp or "")[:10],
        "sessions": len({t.get("session_id", "") for t in test_results}),
        "turns": len(test_results),
        "results": len(rows),
        "latency": latency_seconds,
        "timings": timings or {},
        "routing": routing or {},
        "threshold": round(100 * PASS_THRESHOLD),
        "trials": {
            "attempted": len(trials),
            "successful": trial_successes,
            "rate": trial_rate,
            "items": trials,
        },
        "plan": build_plan(experiment, rows, name_of),
        "personas": personas,
        "scenarios": scenarios,
        "describe": {
            "P": described(profile.get("personas") or []),
            "S": described(profile.get("scenarios") or []),
        },
        "axes": {
            "P": axis_rows("P", personas, len(scenarios)),
            "S": axis_rows("S", scenarios, len(personas)),
        },
        "behaviourTotal": len(out_behaviours),
        "personasRun": sorted({r["persona"] for r in rows if r["persona"]}),
        "scenariosRun": sorted({r["scenario"] for r in rows if r["scenario"]}),
        "features": out_features,
        "behaviours": out_behaviours,
        "criteria": out_criteria,
        "resultTable": {"features": table_features, "rows": table_rows},
        "unmapped": [
            {"metric": name, **bucket, "why": unmapped_reason.get(name, "")}
            for name, bucket in sorted(unmapped.items())
        ],
        "unresolved": unresolved,
    }
