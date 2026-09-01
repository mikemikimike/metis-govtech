"""Configuration for the user agent LLM calls.

The user agent talks to any OpenAI-wire-compatible provider (for example
Platform AI) through the shared credentials:

- ``USER_AGENT_MODEL``       — model name (default ``gpt-5.6-luna``)
- ``USER_AGENT_MAX_TOKENS``  — max output tokens per turn (unset/empty ->
  parameter omitted, provider default applies)
- ``USER_AGENT_TEMPERATURE`` — sampling temperature (unset/empty -> parameter
  omitted, provider default applies; required for models that reject a
  non-default temperature)
- ``OPENAI_API_KEY``         — API key, shared by every component
- ``OPENAI_BASE_URL``        — endpoint override (unset -> default OpenAI)
"""

import os

# LLM configuration for the user agent. Credentials are shared across every
# component through OPENAI_API_KEY / OPENAI_BASE_URL; only the model is per-use-case.
USER_AGENT_MODEL = os.environ.get("USER_AGENT_MODEL", "gpt-5.6-luna")
_raw_max_tokens = os.environ.get("USER_AGENT_MAX_TOKENS")
USER_AGENT_MAX_TOKENS: int | None = int(_raw_max_tokens) if _raw_max_tokens else None
_raw_temp = os.environ.get("USER_AGENT_TEMPERATURE")
USER_AGENT_TEMPERATURE: float | None = float(_raw_temp) if _raw_temp else None
USER_AGENT_API_KEY = os.environ.get("OPENAI_API_KEY")
USER_AGENT_BASE_URL = os.environ.get("OPENAI_BASE_URL")
