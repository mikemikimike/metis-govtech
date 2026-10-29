"""Tests for the typed user-agent action union (issue #311)."""

from __future__ import annotations

import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from metis.engine.simulation.gen_1.types import (
    ButtonClickAction,
    FormFillAction,
    UploadFileAction,
    UserAgentOutput,
)


def test_output_parses_each_action_variant_by_type_literal() -> None:
    out = UserAgentOutput.model_validate(
        {
            "message": "hi",
            "actions": [
                {
                    "type": "upload_file",
                    "slot_id": "sales.csv",
                    "filename": "sales.csv",
                },
                {"type": "button_click", "slot_id": "run"},
                {"type": "form_fill", "slot_id": "q1", "value": ["a", "b"]},
            ],
        }
    )
    assert [type(a).__name__ for a in out.actions] == [
        "UploadFileAction",
        "ButtonClickAction",
        "FormFillAction",
    ]
    assert isinstance(out.actions[0], UploadFileAction)
    assert out.actions[0].filename == "sales.csv"
    assert isinstance(out.actions[2], FormFillAction)
    assert out.actions[2].value == ["a", "b"]


def test_output_schema_is_openai_strict_compatible() -> None:
    # Regression guard: reintroducing Field(discriminator=...) emits
    # oneOf+discriminator and breaks client.beta.chat.completions.parse.
    to_strict_json_schema(UserAgentOutput)  # must not raise


def test_variants_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ButtonClickAction.model_validate(
            {"type": "button_click", "slot_id": "x", "junk": 1}
        )
