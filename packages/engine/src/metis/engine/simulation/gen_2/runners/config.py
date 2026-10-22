"""LLM settings for gen_2's runner agent.

``RUNNER_AGENT_MODEL`` names its model. Unset or empty, it is ``USER_AGENT_MODEL``. It
uses the same ``OPENAI_API_KEY`` / ``OPENAI_BASE_URL`` provider as the user agent.
"""

import os

from ..user_agent.config import USER_AGENT_MODEL

RUNNER_AGENT_MODEL = os.environ.get("RUNNER_AGENT_MODEL") or USER_AGENT_MODEL
