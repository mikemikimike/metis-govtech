"""CLI input for the target connection: the mode, the transport, and the binding values.

Each secret field takes the name of an environment variable, never its value. The CLI runs the
live check on the user's computer, so it reads the user's own environment.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

import yaml

from metis.wizard.application.connection import check_connection
from metis.wizard.contracts.connection import (
    ConnectionCheckResult,
    ConnectionStatus,
    TargetConnection,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import httpx

Printer = Callable[[str], None]
Reader = Callable[[str], str]
Mode = Literal["spec", "run"]

_SECRET_NOTE = "Secret fields take a variable name. Set its value in .env."


def panel(title: str, body: str = "") -> str:
    """A titled panel as text, in the same style as the Interview step headers."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    with console.capture() as capture:
        console.print(Panel(body, title=title, title_align="left"))
    return capture.get().rstrip("\n")


def rule() -> str:
    """A rule that separates a screen's content from its choices."""
    from rich.console import Console
    from rich.rule import Rule

    console = Console()
    with console.capture() as capture:
        console.print(Rule())
    return capture.get().rstrip("\n")


def read_mode(*, out: Printer, read: Reader = input) -> Mode:
    """Ask whether to make a Specification only, or also connect a target to run it."""
    out(panel("Mode", "What do you want to do?"))
    out("  1. Build Spec only")
    out("  2. Build Spec and Run Evals (connect the target)")
    while True:
        raw = read("Mode (1 or 2, blank for 1): ").strip().casefold()
        if raw in ("", "1", "spec"):
            return "spec"
        if raw in ("2", "run"):
            return "run"
        out("  Enter 1 or 2.")


def read_binding_source(*, out: Printer, read: Reader = input) -> Path | None:
    """Ask how to give the binding: in the CLI, or as a file path. Returns the path, if any."""
    from pathlib import Path

    out("\nHow do you want to give the target binding?")
    out("  1. Fill in the fields here")
    out("  2. Give the path to a binding YAML file")
    while True:
        raw = read("Binding (1 or 2, blank for 1): ").strip().casefold()
        if raw in ("", "1"):
            return None
        if raw == "2":
            break
        out("  Enter 1 or 2.")
    while True:
        raw = read("Binding file path: ").strip()
        path = Path(raw).expanduser()
        if raw and path.is_file():
            return path
        out("  No file at that path. Enter the path to a binding YAML file.")


def load_binding_file(path: Path) -> dict[str, Any]:
    """Read binding values from a YAML file. The values are checked later."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a target binding mapping")
    return data


def read_target_connection(
    *,
    out: Printer,
    read: Reader = input,
    values: Mapping[str, Any] | None = None,
    interactive: bool = True,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[[bool], httpx.Client] | None = None,
) -> TargetConnection | None:
    """Read and test binding values until the binding is valid and the user continues.

    Run mode needs a valid binding, so there is no skip. A failed live test (for example the
    server is down) is a warning only, because the engine runs later, maybe somewhere else.

    :param values: Binding values to test first, for example from `--binding`.
    :param interactive: When false, test `values` once and ask nothing.
    :returns: The connection, or `None` when `values` is not valid and nothing can be asked.
    """
    out(panel("Target connection", _SECRET_NOTE))
    data = dict(values) if values is not None else _read_values(out=out, read=read)
    while True:
        result = check_connection(
            data, live=True, environ=environ, client_factory=client_factory
        )
        out(rule())
        _show(result, out)
        if not interactive:
            return result.connection()
        if result.binding is None:
            out("Fix the values. To continue without a binding, run with --mode spec.")
            data = _read_values(out=out, read=read, current=data)
            continue
        choice = _choose(
            out=out,
            read=read,
            prompt="[t]est again, [f]ix the values, or [c]ontinue",
            choices={"t": "test", "f": "fix", "c": "continue"},
        )
        if choice == "continue":
            if result.status is not ConnectionStatus.CHECKED:
                out(
                    "The export keeps this binding. review.md says that it was not tested."
                )
            return result.connection()
        if choice == "fix":
            data = _read_values(out=out, read=read, current=data)


def _choose(*, out: Printer, read: Reader, prompt: str, choices: dict[str, str]) -> str:
    while True:
        raw = read(f"{prompt}: ").strip().casefold()[:1]
        if raw in choices:
            return choices[raw]
        out(f"  Enter one of: {', '.join(choices)}.")


def _show(result: ConnectionCheckResult, out: Printer) -> None:
    """Show field errors and live checks. Each message names a field or a variable only."""
    if result.errors:
        out("\nThe binding is not valid:")
        for error in result.errors:
            where = ".".join(str(part) for part in error.loc) or "binding"
            out(f"  - {where}: {error.msg}")
        return
    out("\nThe binding is valid.")
    for probe in result.probes:
        mark = "✓" if probe.ok else "✗"
        out(f"  {mark} {probe.name}: {probe.message}")


# ── binding values ────────────────────────────────────────────────────────


def _read_values(
    *, out: Printer, read: Reader, current: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Ask for the values that the target cannot supply. Enter keeps the current value."""
    current = current or {}
    out("\nHow does METIS reach the target?")
    out("  1. HTTP API (the target has an OpenAPI document)")
    out("  2. Browser (the target has only a web page)")
    default = "2" if current.get("transport") == "browser" else "1"
    while True:
        raw = read(f"Transport (1 or 2, blank for {default}): ").strip().casefold()
        raw = raw or default
        if raw in ("1", "http"):
            transport = "http"
            break
        if raw in ("2", "browser"):
            transport = "browser"
            break
        out("  Enter 1 or 2.")
    identity = current.get("identity") or {}
    advice = current.get("advice") or {}
    name = _ask(read, "Target name", identity.get("name"))
    data: dict[str, Any] = {
        "schema_version": 1,
        "identity": {"name": name},
        "transport": transport,
    }
    if transport == "http":
        data["spec_url"] = _ask(
            read,
            "OpenAPI document URL (${NAME} reads a variable)",
            current.get("spec_url"),
        )
        auth = current.get("auth") or {}
        secret_env = _ask(
            read,
            "Environment variable that holds the API credential (blank for none)",
            auth.get("secret_env"),
        )
        if secret_env:
            data["auth"] = {"secret_env": secret_env}
        headers = _read_secret_headers(out, read, current.get("secret_headers") or [])
        if headers:
            data["secret_headers"] = headers
        forbidden = _ask_list(
            read,
            "Calls the engine must refuse, as METHOD /path (comma-separated)",
            current.get("forbidden_calls"),
        )
        if forbidden:
            data["forbidden_calls"] = forbidden
        submissions = _ask_list(
            read,
            "Calls that send the user's message (comma-separated; blank for any POST, PUT, or PATCH)",
            current.get("submissions"),
        )
        if submissions:
            data["submissions"] = submissions
        tls = _ask(
            read,
            "Verify the TLS certificate? (y/n)",
            "n" if current.get("tls_verify") is False else "y",
        )
        if tls.casefold().startswith("n"):
            data["tls_verify"] = False
    else:
        data["start_url"] = _ask(
            read, "Start page URL (${NAME} reads a variable)", current.get("start_url")
        )
        login = current.get("login") or {}
        note = _ask(
            read,
            "Sign-in steps, with {{secret:NAME}} where a secret is typed (blank for none)",
            login.get("note"),
        )
        if note:
            data["login"] = {
                "note": note,
                "secrets": _ask_list(
                    read,
                    "Environment variables that the sign-in types (comma-separated)",
                    login.get("secrets"),
                ),
            }
    notes = _ask(
        read, "Notes for the runner agent (blank for none)", advice.get("notes")
    )
    if notes:
        data["advice"] = {"notes": notes}
    return data


def _ask(read: Reader, label: str, current: object = None) -> str:
    shown = f" [{current}]" if current else ""
    raw = read(f"{label}{shown}: ").strip()
    return raw or (str(current) if current else "")


def _ask_list(read: Reader, label: str, current: object = None) -> list[str]:
    joined = ", ".join(current) if isinstance(current, list) else ""
    raw = _ask(read, label, joined or None)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _read_secret_headers(
    out: Printer, read: Reader, current: list[dict[str, Any]]
) -> list[dict[str, str]]:
    if current:
        out(f"  {len(current)} secret header(s) are set.")
        keep = read("Keep them? (y/n, blank for y): ").strip().casefold()
        if not keep.startswith("n"):
            return current
    headers: list[dict[str, str]] = []
    out(
        "Secret headers: one per line as METHOD /path HEADER ENV_NAME, "
        "for example `POST /chat X-Api-Key APP_KEY`. Blank to finish."
    )
    while True:
        raw = read("Secret header: ").strip()
        if not raw:
            return headers
        parts = raw.split()
        if len(parts) != 4:
            out("  Enter four parts: METHOD /path HEADER ENV_NAME.")
            continue
        method, path, header, env = parts
        headers.append({"match": f"{method} {path}", "header": header, "env": env})


__all__ = [
    "load_binding_file",
    "read_mode",
    "read_target_connection",
]
