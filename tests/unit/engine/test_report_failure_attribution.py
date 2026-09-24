"""How a failed trial gets blamed — the report's failureSource rule (issue #329).

`_load_run_records` decides whether a trial's failure is attributed to the
product under test or to METIS. Nothing tested it before this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from metis.engine.reporting._report import _load_run_records, _turn_problems


def _write_record(run_dir: Path, name: str, record: dict) -> None:
    trial_dir = run_dir / "runs" / name
    trial_dir.mkdir(parents=True)
    (trial_dir / "record.json").write_text(json.dumps(record))


def _record(*target_responses: dict, stop_reason: str = "max_turns") -> dict:
    """A minimal record with one conversation turn per target_response."""
    return {
        "config": {"persona": "p", "scenario": "s"},
        "target_session_id": "sess-1",
        "outcome": {"stop_reason": stop_reason, "total_turns": len(target_responses)},
        "conversation": [
            {
                "turn_number": index + 1,
                "user_message": "hi",
                "target_response": response,
            }
            for index, response in enumerate(target_responses)
        ],
    }


def _only_trial(tmp_path: Path, record: dict) -> dict:
    _write_record(tmp_path, "trial-1", record)
    _, trials = _load_run_records(tmp_path)
    assert len(trials) == 1
    return trials[0]


class TestBlameAttribution:
    def test_an_upload_the_target_rejected_is_the_products_failure(
        self, tmp_path: Path
    ) -> None:
        """The rejection reached us from the target, so the product owns it —
        and the rejection text, not the bare stop_reason, is the headline."""
        trial = _only_trial(
            tmp_path,
            _record(
                {
                    "text": "",
                    "action_results": [
                        {
                            "action_index": 0,
                            "succeeded": False,
                            "detail": "Turn not submitted: file 'sales.csv' "
                            "rejected by Orca (413): payload too large",
                        }
                    ],
                }
            ),
        )
        assert trial["failureSource"] == "product"
        assert "413" in trial["message"]

    def test_an_action_metis_withheld_is_not_the_products_failure(
        self, tmp_path: Path
    ) -> None:
        """The persona named a fixture the scenario never staged. The target
        never saw the action, so blaming the product would be a lie."""
        trial = _only_trial(
            tmp_path,
            _record(
                {
                    "text": "",
                    "action_results": [
                        {
                            "action_index": 0,
                            "succeeded": False,
                            "detail": "Turn not submitted: file 'evil.exe' is not "
                            "a fixture for this scenario",
                            "withheld": True,
                        }
                    ],
                }
            ),
        )
        assert trial["failureSource"] != "product"
        assert trial["failureSource"] == "evaluationRunner"

    def test_a_failed_row_with_no_detail_still_blames_the_product(
        self, tmp_path: Path
    ) -> None:
        """I2 forbids this shape on the write path, but this read path never
        rebuilds the model. Filtering on `detail` truthiness would empty
        product_errors and blame METIS for the target's own failure."""
        trial = _only_trial(
            tmp_path,
            _record(
                {
                    "text": "",
                    "action_results": [{"action_index": 3, "succeeded": False}],
                }
            ),
        )
        assert trial["failureSource"] == "product"
        assert trial["message"] == "action 3 failed with no detail recorded"

    def test_a_turn_notice_alone_blames_the_product(self, tmp_path: Path) -> None:
        trial = _only_trial(
            tmp_path,
            _record({"text": "", "response_notices": ["Turn failed: guardrail"]}),
        )
        assert trial["failureSource"] == "product"
        assert trial["message"] == "Turn failed: guardrail"

    def test_a_clean_trial_is_not_blamed_on_the_product(self, tmp_path: Path) -> None:
        trial = _only_trial(
            tmp_path, _record({"text": "here you go"}, stop_reason="goal_achieved")
        )
        assert trial["failureSource"] == "outcome"


class TestTheHeadlineIsTheLastProblem:
    def test_rows_are_sorted_so_the_last_action_is_the_headline(
        self, tmp_path: Path
    ) -> None:
        """product_errors[-1] becomes the message, so order decides what the
        reader sees. I1 guarantees ascending order on the write path only."""
        trial = _only_trial(
            tmp_path,
            _record(
                {
                    "text": "",
                    "action_results": [
                        {"action_index": 1, "succeeded": False, "detail": "second"},
                        {"action_index": 0, "succeeded": False, "detail": "first"},
                    ],
                }
            ),
        )
        assert trial["message"] == "second"

    def test_notices_come_before_action_details(self) -> None:
        turn = {
            "target_response": {
                "response_notices": ["a notice"],
                "action_results": [
                    {"action_index": 0, "succeeded": False, "detail": "a detail"}
                ],
            }
        }
        assert _turn_problems(turn) == ["a notice", "a detail"]


class TestThePerTurnArray:
    def test_each_turn_carries_its_own_problems(self, tmp_path: Path) -> None:
        trial = _only_trial(
            tmp_path,
            _record(
                {"text": "ok"},
                {"text": "", "response_notices": ["Turn failed: guardrail"]},
            ),
        )
        assert [t["errors"] for t in trial["conversation"]] == [
            [],
            ["Turn failed: guardrail"],
        ]

    def test_a_withheld_row_is_absent_from_the_turn_array_too(
        self, tmp_path: Path
    ) -> None:
        trial = _only_trial(
            tmp_path,
            _record(
                {
                    "text": "",
                    "action_results": [
                        {
                            "action_index": 0,
                            "succeeded": False,
                            "detail": "not a fixture",
                            "withheld": True,
                        }
                    ],
                }
            ),
        )
        assert trial["conversation"][0]["errors"] == []


class TestPreContractRecords:
    def test_an_old_record_loses_its_attribution_and_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        """Accepted cost, named in the spec's Out of scope: a record written
        before this contract has neither new channel, so it reads as clean.
        The point of the test is that it degrades rather than raising."""
        trial = _only_trial(
            tmp_path, _record({"text": "", "errors": ["Turn failed: guardrail"]})
        )
        assert trial["failureSource"] == "evaluationRunner"
        assert trial["conversation"][0]["errors"] == []

    def test_a_turn_with_no_target_response_is_tolerated(self) -> None:
        assert _turn_problems({}) == []
        assert _turn_problems({"target_response": None}) == []
