"""Loads a target binding from the experiment's ``inputs/`` and reads its secrets.

Core's ``TargetBinding`` checks the file's shape. This module adds what needs the
environment: ``${NAME}`` references in ``spec_url`` are expanded, a relative ``spec_url``
becomes a file beside the binding, and the credentials the binding names are read. A
value read from the environment never appears in an error, a repr or a log line; errors
name the variable instead.

The binding must sit inside the input folder, because only that folder is copied into
the experiment, and ``--resume`` reads the copy.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import yaml
from pydantic import SecretStr, ValidationError

from metis.core.logging import get_logger
from metis.core.target_binding import TargetBinding

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    _Fail = Callable[[str], "TargetBindingError"]

logger = get_logger()

_ENV = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class TargetBindingError(ValueError):
    """A target binding that cannot be used; raised before any trial runs."""


@dataclass(frozen=True)
class LoadedBinding:
    """A binding as written, with what the engine read from the environment for it."""

    path: Path
    """The binding file, resolved."""
    binding: TargetBinding
    """As written: holds ``${NAME}`` references and no environment value."""
    spec_url: str = field(repr=False)
    """``spec_url`` expanded: an http(s) URL, or a ``file:`` URI inside the input folder."""
    secrets: Mapping[str, SecretStr]
    """Environment variable name to value, for the variables that are set."""

    def secret(self, env: str) -> SecretStr | None:
        """The value of ``env``, or ``None`` when it was not set."""
        return self.secrets.get(env)


def _env(name: str) -> str | None:
    """The variable's value; empty counts as unset."""
    return os.environ.get(name) or None


def load_target_binding(inputs_dir: Path, relative: str) -> LoadedBinding:
    """Load the binding at ``relative`` (relative to ``specification.yaml``).

    :param inputs_dir: The experiment's ``inputs/`` folder.
    :raises TargetBindingError: Whatever makes the binding unusable. The message
        starts with ``relative`` as written.
    """

    def fail(message: str) -> TargetBindingError:
        return TargetBindingError(f"{relative}: {message}")

    root = inputs_dir.resolve()
    path = (inputs_dir / relative).resolve()
    if not path.is_relative_to(root):
        raise fail(
            "the target binding must be inside the input folder; move it there and "
            "name it relative to specification.yaml"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise fail("target binding file not found") from None
    except UnicodeDecodeError:
        raise fail("target binding file is not valid UTF-8") from None
    except OSError:
        raise fail("target binding file cannot be read") from None

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise fail(f"not valid YAML{where}") from None
    if not isinstance(data, dict):
        raise fail("a target binding must be a mapping")
    try:
        # before expansion, so an error can only hold what the user wrote
        binding = TargetBinding.model_validate(data)
    except ValidationError as exc:
        raise fail(str(exc)) from None

    spec_url = _resolve_spec_url(binding.spec_url, path.parent, root, fail)
    return LoadedBinding(
        path=path,
        binding=binding,
        spec_url=spec_url,
        secrets=_read_secrets(binding, fail),
    )


def _resolve_spec_url(written: str, folder: Path, root: Path, fail: _Fail) -> str:
    """Expand ``${NAME}`` in ``written`` and make it absolute."""
    if "${" in _ENV.sub("", written):
        raise fail('spec_url has a "${" that is not a ${NAME} reference')

    def expand(match: re.Match[str]) -> str:
        value = _env(match.group(1))
        if value is None:
            raise fail(
                f"spec_url needs the environment variable {match.group(1)}, "
                "which is not set"
            )
        return value

    expanded = _ENV.sub(expand, written)
    try:
        return _absolute(expanded, written, folder, root, fail)
    except TargetBindingError:
        raise
    except (ValueError, OSError):
        # urlsplit and the path calls quote the value they reject, which may be secret
        raise fail(
            f"spec_url {written!r}, once expanded, is not a usable URL or path"
        ) from None


def _absolute(
    expanded: str, written: str, folder: Path, root: Path, fail: _Fail
) -> str:
    """``expanded`` as an http(s) URL or a ``file:`` URI; messages quote ``written`` only."""
    scheme = urlsplit(expanded).scheme.lower()
    if scheme in ("http", "https"):
        return expanded
    if scheme:
        # name the scheme only when the user wrote it, not when a variable supplied it
        shown = urlsplit(written).scheme.lower() == scheme
        raise fail(
            "spec_url must be an http(s) URL or a file path relative to the binding, "
            + (
                f'not "{scheme}:"'
                if shown
                else "and the expanded spec_url has an unsupported scheme"
            )
        )
    local = (folder / expanded).resolve()
    if not local.is_relative_to(root):
        raise fail(f"spec_url {written!r} must name a file inside the input folder")
    if not local.is_file():
        raise fail(f"spec_url {written!r} names a file that does not exist")
    return local.as_uri()


def _read_secrets(binding: TargetBinding, fail: _Fail) -> dict[str, SecretStr]:
    """Read the credential (required) and each secret header's value (optional)."""
    secrets: dict[str, SecretStr] = {}
    if binding.auth is not None:
        value = _env(binding.auth.secret_env)
        if value is None:
            raise fail(
                f"auth.secret_env names {binding.auth.secret_env}, which is not set"
            )
        secrets[binding.auth.secret_env] = SecretStr(value)
    for header in binding.secret_headers:
        value = _env(header.env)
        if value is None:
            logger.warning(
                "[binding] secret header %s is left out: %s is not set",
                header.header,
                header.env,
            )
            continue
        secrets[header.env] = SecretStr(value)
    return secrets
