"""Configuration for the user agent LLM calls.

The user agent talks to any OpenAI-wire-compatible provider (for example
Platform AI) through the shared credentials:

- ``USER_AGENT_MODEL``       — model name (default ``gpt-5.6-luna``)
- ``USER_AGENT_MAX_TOKENS``  — max output tokens per turn (default ``1024``)
- ``USER_AGENT_TEMPERATURE`` — sampling temperature (default ``0.7``)
- ``OPENAI_API_KEY``         — API key, shared by every component
- ``OPENAI_BASE_URL``        — endpoint override (unset -> default OpenAI)
"""

import os

# LLM configuration for the user agent. Credentials are shared across every
# component through OPENAI_API_KEY / OPENAI_BASE_URL; only the model is per-use-case.
USER_AGENT_MODEL = os.environ.get("USER_AGENT_MODEL", "gpt-5.6-luna")
USER_AGENT_MAX_TOKENS = int(os.environ.get("USER_AGENT_MAX_TOKENS", "1024"))
USER_AGENT_TEMPERATURE = float(os.environ.get("USER_AGENT_TEMPERATURE", "0.7"))
USER_AGENT_API_KEY = os.environ.get("OPENAI_API_KEY")
USER_AGENT_BASE_URL = os.environ.get("OPENAI_BASE_URL")
