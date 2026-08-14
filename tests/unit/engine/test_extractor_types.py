"""Unit tests for extractor TypedDicts."""

from metis.engine.extractor.types import ChatMessage, Delegation


def test_delegation_structural_compatibility() -> None:
    """A plain dict with the right keys satisfies Delegation."""
    d: Delegation = {"target": "data-analyst", "task": "summarize"}
    assert d["target"] == "data-analyst"
    assert d["task"] == "summarize"


def test_assistant_message_structural_compatibility() -> None:
    """A plain dict with the right keys satisfies ChatMessage."""
    m: ChatMessage = {"role": "assistant", "content": "hello"}
    assert m["role"] == "assistant"
    assert m["content"] == "hello"
