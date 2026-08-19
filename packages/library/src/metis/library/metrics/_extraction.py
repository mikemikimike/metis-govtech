"""Shared evidence extraction for the Orca metric suite.

Reusable, tolerant helpers that derive observable evidence from a metric's
test case: conversation chronology, tool calls, routing events, completion
claims, the slide brief, source content, the generated deck (via portable
stdlib ZIP/XML parsing of a PPTX artifact), and output artifacts.

Design rules (see the change proposal):

- Read only observable data — messages, tool calls, routing events, files,
  timestamps, cancellation state, and stop reasons. Never require hidden
  chain-of-thought.
- Be tolerant: return empty/None when a signal is absent so the calling
  metric can return an explicit skipped result instead of fabricating one.
- No new third-party dependency: PPTX text/structure is read through the
  standard-library ZIP/XML representation, not a presentation parser.

Both per-turn metrics (``LLMTestCase`` + ``TraceMetadata``) and session
metrics (``ConversationalTestCase`` + ``Turn`` list) are supported; each
helper documents which shape it accepts.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from deepeval.test_case import LLMTestCase
from deepeval.test_case.conversational_test_case import ConversationalTestCase

from ._types import (
    ArtifactSummary,
    ObservationSummary,
    OrcaChatMetadata,
    ToolCallSummary,
    TraceMetadata,
)

# ---------------------------------------------------------------------------
# Metadata access (per-turn)
# ---------------------------------------------------------------------------


def get_metadata(test_case: LLMTestCase) -> TraceMetadata:
    """Return the TraceMetadata dict for a per-turn test case (never None)."""
    return cast(TraceMetadata, test_case.metadata or {})


def get_observations(test_case: LLMTestCase) -> list[ObservationSummary]:
    """All Langfuse observation dicts for a per-turn test case."""
    return list(get_metadata(test_case).get("observations") or [])


def get_tool_calls(test_case: LLMTestCase) -> list[ToolCallSummary]:
    """TOOL-type observations (name/type/input/output) for a per-turn case."""
    return list(get_metadata(test_case).get("tool_calls") or [])


def tool_calls_named(test_case: LLMTestCase, *names: str) -> list[ToolCallSummary]:
    """Tool calls whose name matches any of ``names`` (case-insensitive)."""
    wanted = {n.lower() for n in names}
    return [
        tc
        for tc in get_tool_calls(test_case)
        if (tc.get("name") or "").lower() in wanted
    ]


def has_tool_call(test_case: LLMTestCase, *names: str) -> bool:
    """True if the per-turn trace called any of the named tools."""
    return bool(tool_calls_named(test_case, *names))


# Code-interpreter tool names used across agent adapters.
CODE_TOOLS = ("execute_python", "run_python", "python", "code_interpreter")


def get_executed_code(test_case: LLMTestCase) -> list[str]:
    """Executed Python source from code-interpreter tool calls, in order."""
    snippets: list[str] = []
    for tc in tool_calls_named(test_case, *CODE_TOOLS):
        inp = tc.get("input")
        code = ""
        if isinstance(inp, dict):
            code = inp.get("code") or inp.get("script") or inp.get("source") or ""
        elif isinstance(inp, str):
            code = inp
        if code:
            snippets.append(str(code))
    return snippets


def get_chat_metadata(test_case: LLMTestCase) -> OrcaChatMetadata:
    """OrcaChatMetadata for a per-turn case (default-valued when absent)."""
    return get_metadata(test_case).get("chat_metadata") or OrcaChatMetadata()


# ---------------------------------------------------------------------------
# Routing events and completion claims
# ---------------------------------------------------------------------------


def get_routing_targets(test_case: LLMTestCase) -> list[str]:
    """Agent targets this turn routed to (delegation + orca-chat fallback)."""
    metadata = get_metadata(test_case)
    targets: list[str] = []
    delegation = metadata.get("delegation")
    if delegation and delegation.get("target"):
        targets.append(delegation["target"])
    routed = get_chat_metadata(test_case).routed_to_agents or []
    for agent in routed:
        if agent and agent not in targets:
            targets.append(agent)
    return targets


def get_completion_claims(test_case: LLMTestCase) -> list[str]:
    """Assistant messages that assert a deliverable is ready/done/saved.

    Observable surface only: matches common completion phrasing in the
    assistant's own messages. Used by verification-style metrics to locate
    the claim whose supporting evidence must exist.
    """
    phrases = (
        "done",
        "completed",
        "finished",
        "ready",
        "saved",
        "created",
        "generated",
        "here is",
        "here's",
        "i have",
        "i've",
        "attached",
    )
    claims: list[str] = []
    for msg in get_metadata(test_case).get("assistant_messages", []) or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str) and any(p in content.lower() for p in phrases):
            claims.append(content)
    return claims


# ---------------------------------------------------------------------------
# Source content and slide brief
# ---------------------------------------------------------------------------


def extract_source_texts(test_case: LLMTestCase) -> list[str]:
    """Source-document contents read via read_source_file tool calls.

    Falls back to ``test_case.context`` (subagent output / retrieval context)
    when no explicit source-read observations are present.
    """
    texts: list[str] = []
    for obs in get_observations(test_case):
        name = (obs.get("name") or "").lower()
        if "read_source" in name or "source_file" in name:
            output = obs.get("output")
            if isinstance(output, str) and output:
                texts.append(output)
            elif isinstance(output, dict):
                content = output.get("content") or output.get("text") or ""
                if content:
                    texts.append(str(content))
    if not texts and test_case.context:
        texts = [c for c in test_case.context if isinstance(c, str) and c]
    return texts


def extract_brief(test_case: LLMTestCase) -> str | None:
    """The slide brief produced before deck generation, if observable.

    Looks for an explicit brief-producing tool call, then for a brief passed
    as the ``make_ppt`` input, then for an assistant message that presents a
    brief. Returns None when no brief evidence exists (caller should skip).
    """
    # 1. An explicit brief tool call.
    for tc in get_tool_calls(test_case):
        name = (tc.get("name") or "").lower()
        if "brief" in name:
            out = tc.get("output") or tc.get("input")
            if out:
                return out if isinstance(out, str) else str(out)
    # 2. A brief supplied as make_ppt input.
    for tc in tool_calls_named(test_case, "make_ppt"):
        inp = tc.get("input")
        if isinstance(inp, dict):
            for key in ("brief", "outline", "content", "spec"):
                if inp.get(key):
                    val = inp[key]
                    return val if isinstance(val, str) else str(val)
    # 3. An assistant message that presents a brief.
    for msg in get_metadata(test_case).get("assistant_messages", []) or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str) and "brief" in content.lower():
            return content
    return None


# ---------------------------------------------------------------------------
# Output artifacts and portable PPTX/deck extraction
# ---------------------------------------------------------------------------


def get_artifacts(test_case: LLMTestCase) -> list[ArtifactSummary]:
    """Collected output artifacts recorded in metadata (may be empty)."""
    return list(get_metadata(test_case).get("artifacts", []) or [])


def get_slide_image_refs(test_case: LLMTestCase) -> list[str] | None:
    """Ordered pre-rendered slide-image paths (engine-supplied), or None."""
    return get_metadata(test_case).get("slide_image_refs")


def _artifact_paths(test_case: LLMTestCase, *suffixes: str) -> list[str]:
    out: list[str] = []
    for art in get_artifacts(test_case):
        path = art.get("path")
        filename = (art.get("filename") or "").lower()
        if path and (not suffixes or any(filename.endswith(s) for s in suffixes)):
            out.append(path)
    return out


@dataclass
class DeckSlide:
    """One slide's extracted text: its title line and remaining body lines."""

    index: int
    title: str
    body: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join([self.title, *self.body]).strip()


# PresentationML text runs live in the DrawingML ``a`` namespace.
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_T_TAG = f"{{{_A_NS}}}t"
_P_TAG = f"{{{_A_NS}}}p"


def read_pptx_slides(pptx_path: str | Path) -> list[DeckSlide]:
    """Read per-slide text from a .pptx via stdlib ZIP/XML (no dependency).

    Each ``ppt/slides/slideN.xml`` part is parsed; the first non-empty
    paragraph becomes the slide title and the rest becomes the body. Returns
    an empty list when the path is missing or unreadable — callers skip.
    """
    path = Path(pptx_path)
    if not path.is_file():
        return []
    try:
        with zipfile.ZipFile(path) as zf:
            slide_names = sorted(
                (
                    n
                    for n in zf.namelist()
                    if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                ),
                key=_slide_sort_key,
            )
            slides: list[DeckSlide] = []
            for idx, name in enumerate(slide_names):
                paragraphs = _paragraph_texts(zf.read(name))
                if not paragraphs:
                    slides.append(DeckSlide(index=idx, title="", body=[]))
                    continue
                slides.append(
                    DeckSlide(index=idx, title=paragraphs[0], body=paragraphs[1:])
                )
            return slides
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError):
        return []


def _slide_sort_key(name: str) -> int:
    digits = "".join(c for c in name.rsplit("/", 1)[-1] if c.isdigit())
    return int(digits) if digits else 0


def _paragraph_texts(xml_bytes: bytes) -> list[str]:
    """Return non-empty paragraph strings from a slide XML part, in order."""
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for para in root.iter(_P_TAG):
        runs = [node.text or "" for node in para.iter(_T_TAG)]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def extract_deck_slides(test_case: LLMTestCase) -> list[DeckSlide]:
    """Slide title/body text for the generated deck, or empty if unavailable.

    Reads the first ``.pptx`` artifact path present in metadata. Returns an
    empty list when no readable deck artifact exists (caller should skip).
    """
    for path in _artifact_paths(test_case, ".pptx"):
        slides = read_pptx_slides(path)
        if slides:
            return slides
    return []


# ---------------------------------------------------------------------------
# Session-level chronology (ConversationalTestCase)
# ---------------------------------------------------------------------------


@dataclass
class SessionTurn:
    """A normalized user or assistant turn from a session test case."""

    index: int
    role: str
    content: str
    routed_to: str = ""
    tool_names: list[str] = field(default_factory=list)


def get_session_turns(test_case: ConversationalTestCase) -> list[SessionTurn]:
    """Normalize a ConversationalTestCase into ordered SessionTurn records."""
    turns: list[SessionTurn] = []
    for idx, turn in enumerate(test_case.turns or []):
        # deepeval's Turn normalizes the additionalMetadata/additional_metadata
        # aliases into .metadata, so read the canonical field only (the
        # deprecated alias would emit a warning on every access).
        meta = getattr(turn, "metadata", None) or {}
        tool_names = [
            (tc.name or "") for tc in (getattr(turn, "tools_called", None) or [])
        ]
        turns.append(
            SessionTurn(
                index=idx,
                role=getattr(turn, "role", "") or "",
                content=getattr(turn, "content", "") or "",
                routed_to=meta.get("routed_to", "") if isinstance(meta, dict) else "",
                tool_names=tool_names,
            )
        )
    return turns


def get_session_metadata(test_case: ConversationalTestCase) -> dict[str, Any]:
    """Session-level metadata dict for a ConversationalTestCase (never None)."""
    return cast("dict[str, Any]", test_case.metadata or {})


def first_tool_turn(turns: list[SessionTurn], *names: str) -> int | None:
    """Index of the first turn that called any of the named tools, else None."""
    wanted = {n.lower() for n in names}
    for turn in turns:
        if any(name.lower() in wanted for name in turn.tool_names):
            return turn.index
    return None
