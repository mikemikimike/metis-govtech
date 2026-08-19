import os


def _get_judge_model():
    """Build the LLM-judge model shared by all GEval-based metrics.

    Configurable via environment so the judge can point at any
    OpenAI-wire-compatible provider (e.g. Platform AI) without code changes:

    - ``JUDGE_MODEL``    — model name (default ``gpt-4.1-mini``)
    - ``JUDGE_API_KEY``  — API key (falls back to ``OPENAI_API_KEY``)
    - ``JUDGE_BASE_URL`` — endpoint override (unset -> default OpenAI)
    """
    from deepeval.models import GPTModel

    return GPTModel(
        model=os.environ.get("JUDGE_MODEL", "gpt-4.1-mini"),
        api_key=os.environ.get("JUDGE_API_KEY", os.environ.get("OPENAI_API_KEY")),
        base_url=os.environ.get("JUDGE_BASE_URL"),
    )
