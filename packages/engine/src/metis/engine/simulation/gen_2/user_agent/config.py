"""LLM settings for gen_2's user agent: the same environment variables as gen_1's.

``USER_AGENT_MODEL`` (default ``gpt-5.6-luna``), ``USER_AGENT_MAX_TOKENS`` and
``USER_AGENT_TEMPERATURE`` (both omitted from the request when unset or empty), and the
shared ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL``.
"""

import os

USER_AGENT_MODEL = os.environ.get("USER_AGENT_MODEL", "gpt-5.6-luna")
USER_AGENT_API_KEY = os.environ.get("OPENAI_API_KEY")
USER_AGENT_BASE_URL = os.environ.get("OPENAI_BASE_URL")
_max_tokens = os.environ.get("USER_AGENT_MAX_TOKENS")
USER_AGENT_MAX_TOKENS: int | None = int(_max_tokens) if _max_tokens else None
_temperature = os.environ.get("USER_AGENT_TEMPERATURE")
USER_AGENT_TEMPERATURE: float | None = float(_temperature) if _temperature else None
