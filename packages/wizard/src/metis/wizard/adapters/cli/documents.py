"""CLI input for the opening documents of an Interview.

The CLI does the same steps as the web client when it adds opening files. It checks the names,
the count, and the total size before it reads any bytes. Then it reads the text of each file
that has a text reader, one file at a time, so that one bad file does not stop the others. A
file type with no text reader (an image, for example) goes to the Interview by name only.
"""

from __future__ import annotations

import shutil
from contextlib import ExitStack
from pathlib import PurePath
from typing import TYPE_CHECKING, NoReturn

import typer

from metis.wizard.application.compile.specification import SpecificationFixture
from metis.wizard.application.documents import (
    DocumentExtractionError,
    extract_documents,
)
from metis.wizard.application.fixtures import (
    FixtureCandidate,
    FixtureError,
    FixtureLibrary,
    normalize_upload_name,
    validate_batch,
)
from metis.wizard.contracts.documents import (
    InterviewDocument,
    validate_interview_documents,
)
from metis.wizard.domain.documents import EXTRACTION_DOCUMENT_EXTENSIONS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    Printer = Callable[[str], None]
    Confirm = Callable[[str], bool]

KEEP_UNREAD_PROMPT = "Keep unread files without text?"


def read_opening_documents(
    paths: Sequence[Path], *, out: Printer, confirm: Confirm | None
) -> list[InterviewDocument]:
    """Read the opening files into Interview documents, or stop with exit 1.

    `confirm` asks the user whether to keep the files that could not be read. Give `None` when
    no terminal can answer. Then a file that could not be read stops the command.
    """
    if not paths:
        return []
    try:
        names = [
            item.name
            for item in validate_batch(
                [
                    FixtureCandidate(name=path.name, size=path.stat().st_size)
                    for path in paths
                ]
            )
        ]
    except FixtureError as exc:
        _stop(str(exc))

    documents: list[InterviewDocument] = []
    unread: list[str] = []
    for path, name in zip(paths, names, strict=True):
        if _extension(name) not in EXTRACTION_DOCUMENT_EXTENSIONS:
            out(f"Not read: {name} (no text reader for this file type)")
            documents.append(InterviewDocument(name=name))
            continue
        try:
            with path.open("rb") as stream:
                result = extract_documents([SpecificationFixture(name, stream)])
        except DocumentExtractionError as exc:
            out(f"Could not read: {name}: {exc}")
            unread.append(name)
            documents.append(InterviewDocument(name=name))
            continue
        out(f"Read: {name}")
        documents.append(InterviewDocument(name=name, text=result.documents[0].text))

    # The web client asks the same question: keep each file that could not be read without
    # its text, or remove it. The CLI cannot remove one file from the command line, so a No
    # stops the command before any model call.
    if unread:
        if confirm is None:
            _stop(
                "Some files could not be read. Remove them from the command, "
                "or run the command in a terminal to keep them without text."
            )
        if not confirm(KEEP_UNREAD_PROMPT):
            _stop("Remove the files that could not be read, then run init again.")

    try:
        return validate_interview_documents(documents)
    except ValueError as exc:
        _stop(str(exc))


def copy_opening_documents(paths: Sequence[Path], root: Path) -> None:
    """Replace the experiment's copy of the opening files with the original bytes.

    `resume` cannot see the source paths, so `init` keeps a copy. A Task can then use an
    opening file as a fixture after the source file moves.
    """
    shutil.rmtree(root, ignore_errors=True)
    if not paths:
        return
    with ExitStack() as stack:
        FixtureLibrary(root).upload(
            [
                (normalize_upload_name(path.name), stack.enter_context(path.open("rb")))
                for path in paths
            ]
        )


def publish_task_fixtures(
    task_fixtures: Sequence[Sequence[str]], documents_root: Path, fixtures_root: Path
) -> list[str]:
    """Copy each opening file that a Task uses into the fixture folder.

    The package contains only the files that a Test Case uses. A file that the user put in the
    fixture folder stays there. The return value lists each used name that has no file, so
    that the user can add that file before a run.
    """
    fixtures_root.mkdir(parents=True, exist_ok=True)
    originals = FixtureLibrary(documents_root)
    published = FixtureLibrary(fixtures_root)
    missing: list[str] = []
    for name in dict.fromkeys(name for names in task_fixtures for name in names):
        try:
            source = originals.path_for(name)
        except FixtureError:
            try:
                published.path_for(name)
            except FixtureError:
                missing.append(name)
            continue
        shutil.copyfile(source, fixtures_root / source.name)
    return missing


def _extension(name: str) -> str:
    return PurePath(name).suffix.lower().removeprefix(".")


def _stop(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)
