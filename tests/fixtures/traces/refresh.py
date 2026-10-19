"""Refetch the Orca case-study session and write it, scrubbed, to ``orca_session.json``.

Run once, by hand, with Langfuse credentials in the environment::

    uv run python -m tests.fixtures.traces.refresh

Tests never run this: they read the committed JSON. It stores the raw Observations API v2 rows,
so the fixture is exactly what Langfuse returns, minus what must not be committed:

- deployment metadata (every ``resourceAttributes.*`` key), the Langfuse public key and the
  Langfuse project id;
- user ids and every e-mail address, replaced with ``user@example.invalid``;
- string values longer than ``_MAX_CHARS``, shortened from the middle so both ends survive
  (system prompts and skill instructions dominate the file's size, and Orca puts the user's
  actual message at the end of a long root input).

- each LLM call's tool definitions (``tools``) keep only their names: every call repeats the
  same full schemas, which would make up most of the file.

``input`` and ``output`` arrive as JSON strings. Each is parsed first, trimmed leaf by leaf,
and written back as JSON, so trimming never breaks a payload that METIS would parse.

Every observation is kept, so the counts ``test_trace_fixture.py`` pins still hold.
"""

from __future__ import annotations

import json
import re
from typing import Any

from metis.engine.extractor.langfuse import (
    _FIELDS,
    _session_trace_ids,
    get_langfuse_client,
)
from tests.fixtures.traces import FIXTURE, SESSION_ID

_MAX_CHARS = 2_000
_KEEP = _MAX_CHARS // 2
_IO_KEYS = {"input", "output"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PLACEHOLDER = "user@example.invalid"
_DROPPED_KEY_PREFIXES = ("resourceAttributes.",)
_DROPPED_KEYS = {"scope.attributes.public_key", "public_key", "projectId"}
_USER_KEYS = {"userId", "attributes.user.id", "user_id"}


def _parsed(value: str) -> Any:
    """``value`` parsed as JSON when it is a JSON object or array, the way METIS parses I/O."""
    if value.lstrip()[:1] not in ("{", "["):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _tool_name(tool: Any) -> Any:
    """A tool definition reduced to its name, in the OpenAI shape it arrived in."""
    function = tool.get("function") if isinstance(tool, dict) else None
    if isinstance(function, dict) and "name" in function:
        return {
            "type": tool.get("type", "function"),
            "function": {"name": function["name"]},
        }
    return tool


def _scrub(value: Any, key: str | None = None) -> Any:
    if key in _USER_KEYS and value:
        return _PLACEHOLDER
    if key == "tools" and isinstance(value, list):
        return [_tool_name(tool) for tool in value]
    if key in _IO_KEYS and isinstance(value, str):
        parsed = _parsed(value)
        if parsed is not None:
            return json.dumps(_scrub(parsed), ensure_ascii=False)
    if isinstance(value, dict):
        return {
            k: _scrub(v, k)
            for k, v in value.items()
            if k not in _DROPPED_KEYS and not k.startswith(_DROPPED_KEY_PREFIXES)
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        value = _EMAIL.sub(_PLACEHOLDER, value)
        if len(value) > _MAX_CHARS:
            value = value[:_KEEP] + " …[trimmed]… " + value[-_KEEP:]
    return value


def main() -> None:
    langfuse = get_langfuse_client()
    # Paged here, not with the engine's pager, because that one parses rows into Observations
    # and the fixture keeps them raw.
    rows: list[dict[str, Any]] = []
    for trace_id in _session_trace_ids(langfuse, SESSION_ID):
        flt = json.dumps(
            [
                {
                    "type": "string",
                    "column": "traceId",
                    "operator": "=",
                    "value": trace_id,
                }
            ]
        )
        cursor = None
        while True:
            response = langfuse.api.observations_v_2.get_many(
                fields=_FIELDS, filter=flt, limit=1000, cursor=cursor
            )
            rows.extend(_scrub(row) for row in response.data)
            cursor = response.meta.cursor
            if not cursor:
                break
    FIXTURE.write_text(
        json.dumps(
            {"session_id": SESSION_ID, "rows": rows}, indent=1, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} observations -> {FIXTURE}")


if __name__ == "__main__":
    main()
