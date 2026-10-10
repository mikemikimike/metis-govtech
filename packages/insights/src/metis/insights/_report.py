"""Join scores to the frozen specification by Task, Trial, and Criterion ID.

Feature and Behaviour scores keep the existing worst-Criterion rules.
Persona and Scenario scores keep the existing pass-rate rules.
"""

from __future__ import annotations

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
) -> tuple[dict, dict[str, str], list[dict]] | None:
    """Read specification.yaml, the persona map, and recorded Trial outcomes."""
    specification_path = run_dir / "inputs" / "specification.yaml"
    if not specification_path.is_file():
        return None
    try:
        import yaml

        specification = yaml.safe_load(specification_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "specification_unreadable", path=str(specification_path), error=str(exc)
        )
        return None

    persona_of, trial_outcomes = _load_trial_records(run_dir)
    return specification, persona_of, trial_outcomes


def _load_trial_records(run_dir: Path) -> tuple[dict[str, str], list[dict]]:
    """Read persona attribution and the exact recorded outcome of each trial.

    The persona lives on the simulation record, not on the trace, so it must come from
    `trials/<name>/record.json`.
    """
    persona_of: dict[str, str] = {}
    trials: list[dict] = []
    for record_path in sorted(run_dir.glob("trials/*/record.json")):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
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
                "task_id": config.get("task_id", ""),
                "trial_index": config.get("trial_index", 1),
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
        log_text = log_path.read_text(encoding="utf-8")
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


def _grader_refs(scenario: Mapping[str, Any]) -> list[str]:
    """The grader FQNs one scenario asks for. A ref is a string or a single key mapping."""
    return [
        next(iter(ref)) if isinstance(ref, dict) else ref
        for ref in scenario.get("grader_refs") or []
    ]


# ---------------------------------------------------------------------------
# One row per grader result
# ---------------------------------------------------------------------------


def flatten_results(
    test_results: Sequence[Row],
    session_graders: Sequence[Row] | None,
    persona_of: Mapping[str, str],
) -> list[dict]:
    """One row per grader result, tagged with its scenario and its persona."""
    scenario_of = {
        t.get("session_id", ""): t.get("scenario_id", "") for t in test_results
    }
    rows: list[dict] = []

    for case in test_results:
        for grader in case.get("graders", []):
            rows.append(
                {
                    "grader": grader["name"],
                    "criterion_id": grader.get("criterion_id", ""),
                    "grader_fqn": grader.get("grader_fqn", ""),
                    "grader_args": grader.get("grader_args", {}),
                    "task_id": grader.get("task_id", ""),
                    "trial_index": grader.get("trial_index", 1),
                    "scenario": case.get("scenario_id", ""),
                    "persona": persona_of.get(case.get("session_id", "")),
                    "skipped": bool(grader.get("skipped")),
                    "success": bool(grader.get("success")),
                    "reason": grader.get("reason", ""),
                    "trace": case.get("trace_id", ""),
                    "session": case.get("session_id", ""),
                    "turn": f"{case.get('turn_index', 0) + 1}/{case.get('total_turns', 1)}",
                }
            )

    for session in session_graders or []:
        sid = session.get("session_id", "")
        for grader in session.get("graders", []):
            rows.append(
                {
                    "grader": grader["name"],
                    "criterion_id": grader.get("criterion_id", ""),
                    "grader_fqn": grader.get("grader_fqn", ""),
                    "grader_args": grader.get("grader_args", {}),
                    "task_id": grader.get("task_id", ""),
                    "trial_index": grader.get("trial_index", 1),
                    "scenario": scenario_of.get(sid, ""),
                    "persona": persona_of.get(sid),
                    "skipped": bool(grader.get("skipped")),
                    "success": bool(grader.get("success")),
                    "reason": grader.get("reason", ""),
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
    """Compare planned Tasks and Trials with the recorded scores."""
    plan_personas = [p["id"] for p in experiment.get("personas", [])]
    tasks = []
    for task in experiment.get("tasks", []):
        results = [r for r in rows if r.get("task_id") == task["id"]]
        asked = set(task["criterion_refs"])
        tasks.append(
            {
                "id": task["id"],
                "scenario": task["scenario_ref"],
                "personas": [task["persona_ref"]],
                "trials": task["num_trials"],
                "trialsPlanned": task["num_trials"],
                "trialsRun": len({(r["task_id"], r["trial_index"]) for r in results}),
                "personasRun": sorted({r["persona"] for r in results if r["persona"]}),
                "gradersAsked": len(asked),
                "gradersScored": len(
                    {r["criterion_id"] for r in results if not r["skipped"]} & asked
                ),
            }
        )
    return {"personas": plan_personas, "tasks": tasks}


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def build_report(
    specification: Mapping[str, Any],
    test_results: Sequence[Row],
    *,
    persona_of: Mapping[str, str] | None = None,
    session_graders: Sequence[Row] | None = None,
    run_id: str = "report",
    timestamp: str = "",
    latency_seconds: float | None = None,
    timings: Mapping[str, Any] | None = None,
    routing: Mapping[str, Any] | None = None,
    trial_outcomes: Sequence[Row] | None = None,
) -> dict:
    """Build the report the page renders.

    :param specification: The parsed specification.yaml frozen for this run.
    :param test_results: Per turn results, in the shape the JSON report writes.
    :param persona_of: Session id to persona id, from the simulation records.
    :param session_graders: Session level results, same shape as `test_results`.
    :param trial_outcomes: Exact outcomes read from the simulation records.
    :returns: A plain dict, ready to serialise into the page.
    """
    rows = flatten_results(test_results, session_graders, persona_of or {})

    criteria: dict[str, dict] = {}
    behaviour_of: dict[str, str] = {}
    for feature in specification.get("features") or []:
        for behaviour in feature.get("behaviours") or []:
            for criterion in behaviour.get("criteria") or []:
                criteria[criterion["id"]] = criterion
                behaviour_of[criterion["id"]] = behaviour["id"]

    tasks = {t["id"]: t for t in specification.get("tasks", [])}
    covers = {
        scenario["id"]: list(
            {
                behaviour_of[cid]
                for t in tasks.values()
                if t["scenario_ref"] == scenario["id"]
                for cid in t["criterion_refs"]
                if cid in behaviour_of
            }
        )
        for scenario in specification.get("scenarios", [])
    }
    # Labels are presentation only; importing and constructing Graders is unnecessary here.
    name_of = {
        c["grader_fqn"]: c["grader_fqn"].rsplit(".", 1)[-1]
        for c in criteria.values()
        if c.get("grader_fqn")
    }
    unresolved: list[str] = []

    per_criterion: dict[str, dict] = {
        cid: {
            "all": _new_bucket(),
            "persona": defaultdict(_new_bucket),
            "scenario": defaultdict(_new_bucket),
            "session": defaultdict(_new_bucket),
            "evidence": [],
            "skips": Counter(),
            "graderName": None,
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
            "graders": set(),
            "partners": set(),
        }

    axis_stats: dict[str, dict[str, dict]] = {
        "P": defaultdict(new_axis),
        "S": defaultdict(new_axis),
    }

    for row in rows:
        cid = row["criterion_id"]
        task = tasks.get(row["task_id"])
        matched = (
            [cid] if cid in criteria and task and cid in task["criterion_refs"] else []
        )
        if not matched:
            _add(unmapped[row["grader"]], row)
            unmapped_reason[row["grader"]] = (
                "Result has no matching Task and Criterion."
            )
            continue
        row["scenario"] = task["scenario_ref"]
        row["persona"] = task["persona_ref"]
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
            slot["graders"].add(cid)
            if partner:
                slot["partners"].add(partner)

        for cid in matched:
            slot = per_criterion[cid]
            if slot["graderName"] is None:
                slot["graderName"] = row["grader"]
            _add(slot["all"], row)
            if row["persona"]:
                _add(slot["persona"][row["persona"]], row)
            if row["scenario"]:
                _add(slot["scenario"][row["scenario"]], row)
            if row["session"]:
                _add(slot["session"][(row["task_id"], row["trial_index"])], row)
            slot["evidence"].append(
                {
                    "task_id": row["task_id"],
                    "trial_index": row["trial_index"],
                    "criterion_id": cid,
                    "grader_fqn": row["grader_fqn"],
                    "grader_args": row["grader_args"],
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

    personas = [p["id"] for p in specification.get("personas") or []]
    scenarios = [s["id"] for s in specification.get("scenarios") or []]

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

    asked_criteria = {cid for task in tasks.values() for cid in task["criterion_refs"]}
    appeared = {row["criterion_id"] for row in rows}

    def blank_cause(criterion: Mapping[str, Any], slot: dict) -> dict:
        """Why a criterion has no pass rate. One cause each, checked in chain order.

        The chain can break in five places, and the reader needs to know which one,
        because each asks for a different fix: write a grader, add the class to the
        library, put the grader in the experiment, or make the run reach the behaviour.
        """
        fqn = criterion.get("grader_fqn")
        name = name_of.get(fqn or "", "")
        if not fqn:
            return {
                "cause": "no grader",
                "note": "the spec names no grader for this criterion",
            }
        if criterion["id"] not in asked_criteria:
            return {
                "cause": "not asked",
                "note": f"no scenario in the experiment asks for {name}",
            }
        if criterion["id"] not in appeared:
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
            "note": "the grader produced no result for this criterion",
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
            "grader": slot["graderName"]
            or name_of.get(criterion.get("grader_fqn") or "", ""),
            "fqn": criterion.get("grader_fqn"),
            "grader_args": criterion.get("grader_args", {}),
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
    for feature in specification.get("features") or []:
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
    for feature in specification.get("features") or []:
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
                        "graders": 0,
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
                    "graders": len(slot["graders"]),
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
        for feature in specification.get("features") or []
        for behaviour in feature.get("behaviours") or []
    }
    features_of_scenario = {
        scenario["id"]: list(
            dict.fromkeys(
                feature_of_behaviour[behaviour_id]
                for behaviour_id in covers.get(scenario["id"], [])
                if behaviour_id in feature_of_behaviour
            )
        )
        for scenario in specification.get("scenarios") or []
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
    trial_rate_fraction = trial_successes / len(trials) if trials else None

    # The scenario axis, once, shared by `axes.S` and the headline grader
    # pass rate below — the same total the page's JS used to recompute from
    # `axes.S` on every load.
    scenario_axis_rows = axis_rows("S", scenarios, len(personas))
    grader_pass_total = sum(row["pass"] for row in scenario_axis_rows)
    grader_ran_total = sum(row["ran"] for row in scenario_axis_rows)
    grader_rate = (
        round(100 * grader_pass_total / grader_ran_total) if grader_ran_total else None
    )
    grader_rate_fraction = (
        grader_pass_total / grader_ran_total if grader_ran_total else None
    )

    table_features = [
        {
            "id": feature["id"],
            "name": feature.get("name", feature["id"]),
            "columns": [
                {
                    "criterion": criterion["id"],
                    "grader": out_criteria[criterion["id"]]["grader"],
                }
                for behaviour in feature.get("behaviours") or []
                for criterion in behaviour.get("criteria") or []
                if per_criterion[criterion["id"]]["session"]
            ],
        }
        for feature in specification.get("features") or []
    ]
    table_features = [feature for feature in table_features if feature["columns"]]

    table_rows = []
    for trial in trials:
        results = {}
        for cid, slot in per_criterion.items():
            bucket = slot["session"].get(
                (trial.get("task_id", ""), trial.get("trial_index", 1))
            )
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
        "product": (specification.get("product") or {}).get("name", "the product"),
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
        "scores": {
            "graderPassRate": {
                "rate": grader_rate,
                "pass": grader_pass_total,
                "ran": grader_ran_total,
                "status": status(grader_rate_fraction),
            },
            "trialSuccess": {
                "rate": trial_rate,
                "successful": trial_successes,
                "attempted": len(trials),
                "status": status(trial_rate_fraction),
            },
        },
        "plan": build_plan(specification, rows, name_of),
        "personas": personas,
        "scenarios": scenarios,
        "describe": {
            "P": described(specification.get("personas") or []),
            "S": described(specification.get("scenarios") or []),
        },
        "axes": {
            "P": axis_rows("P", personas, len(scenarios)),
            "S": scenario_axis_rows,
        },
        "behaviourTotal": len(out_behaviours),
        "personasRun": sorted({r["persona"] for r in rows if r["persona"]}),
        "scenariosRun": sorted({r["scenario"] for r in rows if r["scenario"]}),
        "features": out_features,
        "behaviours": out_behaviours,
        "criteria": out_criteria,
        "resultTable": {"features": table_features, "rows": table_rows},
        "unmapped": [
            {"grader": name, **bucket, "why": unmapped_reason.get(name, "")}
            for name, bucket in sorted(unmapped.items())
        ],
        "unresolved": unresolved,
    }
