"""The rules code enforces on the runner agent's HTTP calls, whatever the target.

Each is a case where an LLM did something plausible but wrong: a path that escapes the
API, a header that carries a credential, a call the binding forbids.
"""

from __future__ import annotations

import re

SUBMIT_METHODS = frozenset({"POST", "PUT", "PATCH"})
"""With a JSON body, the default meaning of a submission."""

_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "host"})


class ToolRefused(ValueError):
    """A tool call that code refuses, worded for the agent that made it."""


def check_path(path: str) -> None:
    """Refuse a path that is not absolute, plain and as the specification writes it."""
    if (
        not path.startswith("/")
        or "//" in path
        or ".." in path.split("/")
        or "?" in path
        or "#" in path
    ):
        raise ToolRefused(
            f"path must be an absolute path on the target as the specification "
            f"writes it, without // or .. or a query: {path!r}"
        )


def check_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """The agent's extra headers; it can never set a credential."""
    for name in headers or {}:
        if name.lower() in _CREDENTIAL_HEADERS:
            raise ToolRefused(
                f"you cannot set the {name} header; code adds credentials"
            )
    return dict(headers or {})


def matches(pattern: str, method: str, path: str) -> bool:
    """Whether ``METHOD /glob`` covers a call: ``*`` within a segment, ``**`` across."""
    verb, _, glob = pattern.partition(" ")
    regex = "".join(
        ".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part)
        for part in re.split(r"(\*\*|\*)", glob)
    )
    return verb in ("*", method) and re.fullmatch(regex, path) is not None
