"""An offline OpenAI transport for criterion judge contract checks."""

import json
from typing import Any

import httpx
from openai import AsyncOpenAI

from metis.core.traces import GradingInput, Observation, Trace


def recorded_session() -> GradingInput:
    return GradingInput(
        traces=(
            Trace(
                id="trace-1",
                session_id="session-1",
                observations=(
                    Observation(
                        id="root",
                        trace_id="trace-1",
                        input="Find a source",
                        output="The source is example.org",
                    ),
                    Observation(
                        id="tool",
                        trace_id="trace-1",
                        parent_observation_id="root",
                        type="TOOL",
                        name="search",
                        output={"url": "example.org"},
                    ),
                ),
            ),
        )
    )


def judge_client(
    content: str,
    requests: list[dict[str, Any]],
    *,
    status_code: int = 200,
    finish_reason: str = "stop",
    refusal: str | None = None,
) -> AsyncOpenAI:
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            status_code,
            json={
                "id": "completion-1",
                "object": "chat.completion",
                "created": 1,
                "model": "test-judge",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish_reason,
                        "message": {
                            "role": "assistant",
                            "content": content,
                            "refusal": refusal,
                        },
                    }
                ],
            },
        )

    return AsyncOpenAI(
        api_key="test-only",
        base_url="https://judge.invalid/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
