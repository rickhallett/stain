"""Input resolution — files, stdin, URLs, globs."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TextIO


class SourceType(str, Enum):
    FILE = "file"
    STDIN = "stdin"
    URL = "url"


@dataclass
class InputItem:
    text: str
    source: str
    source_type: SourceType


class InputError(Exception):
    """Bad input — maps to exit code 2."""
    pass


def resolve_inputs(
    sources: tuple[str, ...],
    stdin_stream: TextIO | None = None,
) -> list[InputItem]:
    """Resolve source arguments into InputItems.

    Sources can be file paths, glob patterns, URLs, or '-' for stdin.
    When no sources are given, reads from stdin if it's not a TTY.
    """
    if not sources:
        stream = stdin_stream or sys.stdin
        is_tty = hasattr(stream, "isatty") and stream.isatty()
        # Also treat pytest's DontReadFromInput as "no piped data"
        has_fileno = False
        try:
            stream.fileno()
            has_fileno = True
        except (AttributeError, OSError):
            pass
        if is_tty or (not has_fileno and stdin_stream is None):
            raise InputError("No input provided. Pass a file, URL, or pipe via stdin.")
        return [_read_stdin(stream)]

    items: list[InputItem] = []
    for source in sources:
        if source == "-":
            stream = stdin_stream or sys.stdin
            items.append(_read_stdin(stream))
        elif source.startswith(("http://", "https://")):
            items.append(_fetch_url(source))
        elif "*" in source or "?" in source:
            items.extend(_expand_glob(source))
        else:
            items.append(_read_file(source))

    return items


def _read_file(path_str: str) -> InputItem:
    """Read a single file and return an InputItem."""
    path = Path(path_str)
    if not path.is_file():
        raise InputError(f"File not found: {path_str}")
    text = path.read_text()
    if not text.strip():
        raise InputError(f"File is empty: {path_str}")
    return InputItem(text=text, source=str(path), source_type=SourceType.FILE)


def _expand_glob(pattern: str) -> list[InputItem]:
    """Expand a glob pattern and return InputItems for each match."""
    p = Path(pattern)
    parent = p.parent
    glob_part = p.name

    if not parent.exists():
        raise InputError(f"No files match pattern: {pattern}")

    matches = sorted(parent.glob(glob_part))
    matches = [m for m in matches if m.is_file()]

    if not matches:
        raise InputError(f"No files match pattern: {pattern}")

    return [_read_file(str(m)) for m in matches]


def _read_stdin(stream: TextIO) -> InputItem:
    """Read all of stdin and return an InputItem."""
    text = stream.read()
    if not text.strip():
        raise InputError("Stdin is empty.")
    return InputItem(text=text, source="<stdin>", source_type=SourceType.STDIN)


def _fetch_url(url: str) -> InputItem:
    """Fetch a URL and extract text content. Requires trafilatura."""
    raise NotImplementedError("URL fetching requires trafilatura (Task 3)")
