"""Library artifact extraction reads the unified core.Artifact shape (#307, #328)."""

from __future__ import annotations

from pathlib import Path

from deepeval.test_case import LLMTestCase

from metis.core import Artifact
from metis.library.graders._extraction import (
    _artifact_paths,
    _latest_target_pdf_path,
    get_artifacts,
    get_deck_slide_images,
    render_pdf_slides,
)


def _case(
    artifacts: list[dict[str, object]], turn_index: int | None = None
) -> LLMTestCase:
    metadata: dict[str, object] = {"artifacts": artifacts}
    if turn_index is not None:
        metadata["turn_index"] = turn_index
    return LLMTestCase(input="i", actual_output="o", metadata=metadata)


def test_get_artifacts_validates_to_core_artifact() -> None:
    tc = _case([{"name": "out.csv", "path": "/tmp/out.csv", "state": "received"}])
    arts = get_artifacts(tc)
    assert len(arts) == 1
    assert isinstance(arts[0], Artifact)
    assert arts[0].name == "out.csv"
    assert arts[0].path == "/tmp/out.csv"


def test_get_artifacts_skips_malformed_dicts() -> None:
    # missing required 'name' -> skipped, not raised
    tc = _case(
        [
            {"path": "/tmp/x", "state": "unavailable"},
            {"name": "ok.csv", "path": "/tmp/ok.csv", "state": "received"},
        ]
    )
    arts = get_artifacts(tc)
    assert [a.name for a in arts] == ["ok.csv"]


def test_get_artifacts_empty_when_absent() -> None:
    assert get_artifacts(LLMTestCase(input="i", actual_output="o")) == []


def test_get_artifacts_silently_drops_a_dict_missing_state() -> None:
    """Review Focus: a real, otherwise-valid dict missing the new required
    `state` key is swallowed by get_artifacts' except ValidationError:
    continue, not surfaced as an error."""
    tc = _case([{"name": "report.csv", "path": "report.csv"}])
    assert get_artifacts(tc) == []


def test_artifact_paths_resolve_from_path(tmp_path: Path) -> None:
    deck = tmp_path / "slides.pptx"
    deck.write_bytes(b"PK\x03\x04")
    tc = _case([{"name": "slides.pptx", "path": str(deck), "state": "received"}])
    assert _artifact_paths(tc, ".pptx") == [str(deck)]
    assert _artifact_paths(tc, ".csv") == []


def test_artifact_paths_skips_when_path_absent() -> None:
    tc = _case([{"name": "remote.csv", "path": None, "state": "unavailable"}])
    assert _artifact_paths(tc, ".csv") == []


def test_artifact_paths_skips_a_path_bearing_record_not_yet_received(
    tmp_path: Path,
) -> None:
    """A record can carry a path while state != "received" (e.g. a runner
    holding a path mid-capture before state is decided — see Artifact's own
    docstring). This is the one shape that discriminates the old
    `if not art.path` gate from the new `if art.state != "received"` gate:
    a path-bearing artifact must still be excluded when its state isn't
    "received"."""
    deck = tmp_path / "slides.pptx"
    deck.write_bytes(b"PK\x03\x04")
    tc = _case([{"name": "slides.pptx", "path": str(deck), "state": "unfetched"}])
    assert _artifact_paths(tc, ".pptx") == []


# ---------------------------------------------------------------------------
# PDF deck rendering (#381, rescoped): render only an already-PDF target
# artifact via pymupdf; a .pptx-only deck has no local conversion path.
# ---------------------------------------------------------------------------


def test_get_deck_slide_images_empty_without_artifacts() -> None:
    assert get_deck_slide_images(_case([])) == []


def test_get_deck_slide_images_skips_pptx_only_deck(tmp_path: Path) -> None:
    deck = tmp_path / "slides.pptx"
    deck.write_bytes(b"PK\x03\x04")
    tc = _case([{"name": "slides.pptx", "path": str(deck), "state": "received"}])
    assert get_deck_slide_images(tc) == []


def test_get_deck_slide_images_renders_target_pdf(pdf_factory) -> None:
    pdf_path = str(pdf_factory("deck.pdf", pages=3))
    tc = _case(
        [{"name": "deck.pdf", "path": pdf_path, "state": "received", "at_turn": 0}]
    )
    images = get_deck_slide_images(tc)
    assert len(images) == 3
    assert all(Path(p).is_file() for p in images)


def test_latest_target_pdf_path_excludes_fixture_source(pdf_factory) -> None:
    pdf_path = str(pdf_factory("reference.pdf"))
    tc = _case(
        [
            {
                "name": "reference.pdf",
                "path": pdf_path,
                "state": "received",
                "source": "fixture",
            }
        ]
    )
    assert _latest_target_pdf_path(tc) is None
    assert get_deck_slide_images(tc) == []


def test_latest_target_pdf_path_excludes_artifact_after_current_turn(
    pdf_factory,
) -> None:
    pdf_path = str(pdf_factory("deck.pdf"))
    tc = _case(
        [{"name": "deck.pdf", "path": pdf_path, "state": "received", "at_turn": 5}],
        turn_index=2,
    )
    assert _latest_target_pdf_path(tc) is None


def test_latest_target_pdf_path_picks_most_recent_at_turn(pdf_factory) -> None:
    older = str(pdf_factory("older.pdf"))
    newer = str(pdf_factory("newer.pdf"))
    tc = _case(
        [
            {"name": "older.pdf", "path": older, "state": "received", "at_turn": 0},
            {"name": "newer.pdf", "path": newer, "state": "received", "at_turn": 1},
        ],
        turn_index=1,
    )
    assert _latest_target_pdf_path(tc) == newer


def test_render_pdf_slides_missing_path_is_empty() -> None:
    assert render_pdf_slides("/no/such/deck.pdf") == []


def test_render_pdf_slides_corrupt_file_is_empty(tmp_path: Path) -> None:
    bad = tmp_path / "garbage.pdf"
    bad.write_bytes(b"not a real pdf")
    assert render_pdf_slides(bad) == []


def test_render_pdf_slides_renders_ordered_pages(pdf_factory) -> None:
    pdf_path = pdf_factory("deck.pdf", pages=4)
    images = render_pdf_slides(pdf_path)
    assert len(images) == 4
    assert images == sorted(images)
    assert all(Path(p).is_file() for p in images)
