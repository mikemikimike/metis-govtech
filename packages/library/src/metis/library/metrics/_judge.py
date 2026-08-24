import os


def _get_judge_model():
    """Build the LLM-judge model shared by all GEval-based metrics.

    Configurable via environment so the judge can point at any
    OpenAI-wire-compatible provider (e.g. Platform AI) without code changes:

    - ``JUDGE_MODEL``     — model name (default ``gemini-3.5-flash-lite``)
    - ``OPENAI_API_KEY``  — API key, shared by every component
    - ``OPENAI_BASE_URL`` — endpoint override (unset -> default OpenAI)
    """
    from deepeval.models import GPTModel

    return GPTModel(
        model=os.environ.get("JUDGE_MODEL", "gemini-3.5-flash-lite"),
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
