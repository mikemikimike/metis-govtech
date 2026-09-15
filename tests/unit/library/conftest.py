"""Shared fixtures and builders for metis-library metric tests.

These helpers construct the exact ``LLMTestCase`` / ``ConversationalTestCase``
shapes that the CSV-aligned metrics read, plus a portable in-memory PPTX so
deck extraction can be exercised without a presentation library or network.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from deepeval.test_case import LLMTestCase, ToolCall, Turn
from deepeval.test_case.conversational_test_case import ConversationalTestCase


def make_case(
    *,
    input: str = "Do the analysis.",
    actual_output: str = "Here is the analysis.",
    metadata: dict | None = None,
    context: list[str] | None = None,
) -> LLMTestCase:
    """A per-turn LLMTestCase with the given TraceMetadata dict."""
    return LLMTestCase(
        input=input,
        actual_output=actual_output,
        context=context,
        metadata=metadata or {},
    )


def tool_call(name: str, tool_input: dict | str | None = None, output=None) -> dict:
    """A ToolCallSummary dict as stored in TraceMetadata['tool_calls']."""
    return {"name": name, "type": "TOOL", "input": tool_input, "output": output}


def artifact(filename: str, path: str, collected_at_turn: int = 0) -> dict:
    """A serialized metis.core.Artifact dict as stored in metadata['artifacts']."""
    from pathlib import Path

    uri = Path(path).resolve().as_uri() if path else None
    return {
        "name": filename,
        "type": "download",
        "uri": uri,
        "collected_at_turn": collected_at_turn,
    }


def make_session(
    turns: list[Turn], metadata: dict | None = None
) -> ConversationalTestCase:
    """A ConversationalTestCase from ready-made Turn objects."""
    return ConversationalTestCase(turns=turns, metadata=metadata or {})


def turn(
    role: str,
    content: str = "",
    *,
    tools: list[str] | None = None,
    routed_to: str = "",
) -> Turn:
    """One session Turn with optional tool calls and routing metadata."""
    return Turn(
        role=role,
        content=content,
        tools_called=[ToolCall(name=n) for n in (tools or [])] or None,
        metadata={"routed_to": routed_to} if routed_to else None,
    )


_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _slide_xml(paragraphs: list[str]) -> bytes:
    body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sld xmlns:p="{_P_NS}" xmlns:a="{_A_NS}">'
        f"<p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>"
    )
    return xml.encode("utf-8")


def write_pptx(path: Path, slides: list[list[str]]) -> Path:
    """Write a minimal but valid-enough PPTX zip for read_pptx_slides.

    Each element of ``slides`` is a list of paragraph strings; the first is the
    slide title and the rest are body lines.
    """
    with zipfile.ZipFile(path, "w") as zf:
        for i, paragraphs in enumerate(slides, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", _slide_xml(paragraphs))
    return path


@pytest.fixture(autouse=True)
def _dummy_openai_key(monkeypatch):
    """Let the judge model construct offline.

    ``_get_judge_model`` builds a ``GPTModel`` whose constructor requires a key
    to be present (it is never called in these tests — the judge is either
    skipped or replaced with a fake). A placeholder key satisfies construction
    without enabling any network call.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")


@pytest.fixture
def pptx_factory(tmp_path: Path):
    """Factory that writes a PPTX under tmp_path and returns its path."""

    def _make(slides: list[list[str]], name: str = "deck.pptx") -> Path:
        return write_pptx(tmp_path / name, slides)

    return _make


@pytest.fixture
def image_factory(tmp_path: Path):
    """Factory that writes a tiny placeholder PNG and returns its path."""

    def _make(name: str) -> Path:
        p = tmp_path / name
        # A 1x1 transparent PNG — enough for MLLMImage base64 loading.
        p.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
            b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return p

    return _make
