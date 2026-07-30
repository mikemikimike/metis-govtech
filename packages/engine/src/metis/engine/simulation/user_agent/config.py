"""Configuration for the user agent LLM calls."""

import os

# LLM configuration for the user agent
USER_AGENT_MODEL = os.environ.get("USER_AGENT_MODEL", "gpt-4o-mini")
USER_AGENT_MAX_TOKENS = int(os.environ.get("USER_AGENT_MAX_TOKENS", "1024"))
USER_AGENT_TEMPERATURE = float(os.environ.get("USER_AGENT_TEMPERATURE", "0.7"))
