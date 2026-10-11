from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepeval.models import GPTModel


def _get_judge_model() -> GPTModel:
    """Build the LLM-judge model shared by all GEval-based graders.

    Configurable via environment so the judge can point at any
    OpenAI-wire-compatible provider (e.g. Platform AI) without code changes:

    - ``JUDGE_MODEL``     — model name (default ``gemini-3.5-flash-lite``)
    - ``OPENAI_API_KEY``  — API key, shared by every component
    - ``OPENAI_BASE_URL`` — endpoint override (unset -> default OpenAI)
    """
    from deepeval.models import GPTModel

    # Default to a temperature-tolerant model: DeepEval's ``GPTModel``
    # always sends a ``temperature`` field, which some models (e.g.
    # ``gpt-5.6-luna`` on Bedrock) reject with a 400. ``gemini-3.5-flash-lite``
    # accepts it and is a fast/cheap fit for a judge.
    return GPTModel(
        model=os.environ.get("JUDGE_MODEL", "gemini-3.5-flash-lite"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
