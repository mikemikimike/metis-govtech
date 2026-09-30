"""save_report() writes UTF-8 regardless of host locale (issue #385).

The report page hardcodes a literal → in its own template text
(_report_page.py's "Swipe to metric →"), so any write that falls back to
the platform's locale encoding crashes on a cp1252 machine — U+2192 isn't
representable there — and leaves a 0-byte file on disk behind a swallowed
UnicodeEncodeError. Writing must always pass encoding="utf-8" explicitly,
never rely on the platform default.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

from metis.engine.reporting.generator import save_report


def test_save_report_writes_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "profile.yaml").write_text(
        "product:\n  name: Test Product\n", encoding="utf-8"
    )

    encodings_used: list[str | None] = []
    original_write_text = pathlib.Path.write_text

    def spy_write_text(self: pathlib.Path, data: str, *args: object, **kwargs: object):
        encodings_used.append(kwargs.get("encoding"))  # type: ignore[arg-type]
        return original_write_text(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pathlib.Path, "write_text", spy_write_text)

    paths = save_report([], "run-1", output_dir=tmp_path / "results")

    assert paths is not None
    html_path, json_path = paths
    assert encodings_used == ["utf-8", "utf-8"]

    html_text = html_path.read_text(encoding="utf-8")
    assert "→" in html_text
    assert json_path.read_text(encoding="utf-8")
