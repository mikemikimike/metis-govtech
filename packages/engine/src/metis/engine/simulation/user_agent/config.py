"""Configuration for the user agent LLM calls.

The user agent can point at any OpenAI-wire-compatible provider (for example
Platform AI) without code changes:

- ``USER_AGENT_MODEL``    — model name (default ``gpt-4o-mini``)
- ``USER_AGENT_API_KEY``  — API key (falls back to ``OPENAI_API_KEY``)
- ``USER_AGENT_BASE_URL`` — endpoint override (unset -> default OpenAI)
"""

import os

# LLM configuration for the user agent
USER_AGENT_MODEL = os.environ.get("USER_AGENT_MODEL", "gpt-4o-mini")
USER_AGENT_MAX_TOKENS = int(os.environ.get("USER_AGENT_MAX_TOKENS", "1024"))
USER_AGENT_TEMPERATURE = float(os.environ.get("USER_AGENT_TEMPERATURE", "0.7"))
USER_AGENT_API_KEY = os.environ.get(
    "USER_AGENT_API_KEY", os.environ.get("OPENAI_API_KEY")
)
USER_AGENT_BASE_URL = os.environ.get("USER_AGENT_BASE_URL")
