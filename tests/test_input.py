"""Tests for input resolution — files, stdin, URLs, globs."""

import io

import pytest
from pathlib import Path

from stain.input import InputError, InputItem, SourceType, resolve_inputs


class TestReadFile:
    def test_read_single_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        items = resolve_inputs((str(f),))
        assert len(items) == 1
        assert items[0].text == "hello world"
        assert items[0].source == str(f)
        assert items[0].source_type == SourceType.FILE

    def test_missing_file_raises(self):
        with pytest.raises(InputError, match="not found"):
            resolve_inputs(("/nonexistent/file.txt",))

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        with pytest.raises(InputError, match="empty"):
            resolve_inputs((str(f),))


class TestGlobExpansion:
    def test_glob_matches(self, tmp_path):
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "b.txt").write_text("bravo")
        (tmp_path / "c.md").write_text("charlie")
        items = resolve_inputs((str(tmp_path / "*.txt"),))
        assert len(items) == 2
        texts = {item.text for item in items}
        assert texts == {"alpha", "bravo"}

    def test_glob_no_matches_raises(self):
        with pytest.raises(InputError, match="No files match"):
            resolve_inputs(("/tmp/nonexistent_dir_12345/*.xyz",))

    def test_multiple_sources(self, tmp_path):
        f1 = tmp_path / "one.txt"
        f2 = tmp_path / "two.txt"
        f1.write_text("first")
        f2.write_text("second")
        items = resolve_inputs((str(f1), str(f2)))
        assert len(items) == 2


class TestNoInput:
    def test_no_sources_no_stdin_raises(self):
        with pytest.raises(InputError, match="No input"):
            resolve_inputs(())


class TestStdin:
    def test_read_stdin_dash(self):
        stream = io.StringIO("piped content")
        items = resolve_inputs(("-",), stdin_stream=stream)
        assert len(items) == 1
        assert items[0].text == "piped content"
        assert items[0].source == "<stdin>"
        assert items[0].source_type == SourceType.STDIN

    def test_implicit_stdin_when_no_sources(self):
        stream = io.StringIO("implicit piped")
        items = resolve_inputs((), stdin_stream=stream)
        assert len(items) == 1
        assert items[0].text == "implicit piped"

    def test_empty_stdin_raises(self):
        stream = io.StringIO("")
        with pytest.raises(InputError, match="empty"):
            resolve_inputs(("-",), stdin_stream=stream)

    def test_stdin_whitespace_only_raises(self):
        stream = io.StringIO("   \n\n  ")
        with pytest.raises(InputError, match="empty"):
            resolve_inputs(("-",), stdin_stream=stream)
