from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepeval.models import GPTModel


def _get_judge_model() -> GPTModel:
    """Build the LLM-judge model shared by all GEval-based metrics.

    Configurable via environment so the judge can point at any
    OpenAI-wire-compatible provider (e.g. Platform AI) without code changes:

    - ``JUDGE_MODEL``     — model name (default ``gpt-5.6-luna``)
    - ``OPENAI_API_KEY``  — API key, shared by every component
    - ``OPENAI_BASE_URL`` — endpoint override (unset -> default OpenAI)
    """
    from deepeval.models import GPTModel

    return GPTModel(
        model=os.environ.get("JUDGE_MODEL", "gpt-5.6-luna"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
