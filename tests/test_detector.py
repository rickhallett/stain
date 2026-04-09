"""Tests for detector engine — span validation, JSON extraction, prompt loading."""

import json
import pytest

from stain.detector import (
    _extract_json,
    _extract_quotes,
    _find_in_text,
    _hash_prompt,
    _load_prompt,
    _validate_annotations,
)
from stain.models import Annotation


class TestExtractJson:
    def test_plain_json(self):
        raw = '{"key": "value"}'
        assert _extract_json(raw) == {"key": "value"}

    def test_fenced_json(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _extract_json(raw) == {"key": "value"}

    def test_fenced_no_lang(self):
        raw = '```\n{"key": "value"}\n```'
        assert _extract_json(raw) == {"key": "value"}

    def test_whitespace_padding(self):
        raw = '\n\n  {"key": "value"}  \n\n'
        assert _extract_json(raw) == {"key": "value"}

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")


class TestExtractQuotes:
    def test_double_quotes(self):
        text = 'The phrase "here is the thing" is common'
        quotes = _extract_quotes(text)
        assert "here is the thing" in quotes

    def test_single_quotes(self):
        text = "The phrase 'here is the thing' is common"
        quotes = _extract_quotes(text)
        assert "here is the thing" in quotes

    def test_short_quotes_filtered(self):
        text = 'Words like "the" and "a" are ignored'
        quotes = _extract_quotes(text)
        assert len(quotes) == 0

    def test_multiple_quotes_sorted_by_length(self):
        text = 'Both "short one" and "this is much longer phrase" appear'
        quotes = _extract_quotes(text)
        assert len(quotes) == 2
        assert len(quotes[0]) >= len(quotes[1])

    def test_smart_quotes(self):
        text = "The phrase \u201chere is the thing\u201d is common"
        quotes = _extract_quotes(text)
        assert "here is the thing" in quotes


class TestFindInText:
    def test_exact_match(self):
        result = _find_in_text("hello world", "say hello world today")
        assert result == (4, 15)

    def test_case_insensitive_fallback(self):
        result = _find_in_text("Hello World", "say hello world today")
        assert result is not None
        assert result == (4, 15)

    def test_no_match(self):
        result = _find_in_text("xyz", "abc def ghi")
        assert result is None


class TestValidateAnnotations:
    SAMPLE_TEXT = "This is a sample text for testing annotation spans and validation logic."

    def _annot(self, start, end, explanation="test"):
        return Annotation(
            span_start=start,
            span_end=end,
            pattern="correctio",
            severity="medium",
            explanation=explanation,
        )

    def test_valid_span_with_matching_explanation(self):
        # Explanation must contain quoted or verbatim text from the span
        # for the validator to confirm correctness
        annot = self._annot(
            0, 20,
            explanation='The phrase "This is a sample" opens the text',
        )
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert valid == 1
        assert invalid == 0
        assert annotations[0].span_valid is True

    def test_unverifiable_span_marked_invalid(self):
        # Explanation too short to verify — validator can't confirm, marks invalid
        annot = self._annot(0, 20, explanation="test")
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert invalid == 1
        assert annotations[0].span_valid is False

    def test_out_of_bounds_start(self):
        annot = self._annot(999, 1010)
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert invalid == 1
        assert annotations[0].span_valid is False

    def test_negative_start(self):
        annot = self._annot(-1, 10)
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert invalid == 1

    def test_start_after_end(self):
        annot = self._annot(20, 10)
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert invalid == 1

    def test_suspiciously_short_span(self):
        # Span of 2 chars — likely wrong indices
        annot = self._annot(0, 2)
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        # Should be flagged as invalid (too short, no quotes to repair from)
        assert invalid == 1

    def test_repair_from_quoted_text(self):
        # Span offsets are wrong, but explanation quotes text that exists in input
        annot = self._annot(
            999, 1010,
            explanation='Uses the phrase "sample text for testing" as a filler',
        )
        annotations, valid, invalid = _validate_annotations([annot], self.SAMPLE_TEXT)
        assert valid == 1
        assert annotations[0].span_valid is True
        # Check repaired offsets point to the quoted phrase
        repaired_text = self.SAMPLE_TEXT[annotations[0].span_start:annotations[0].span_end]
        assert "sample text for testing" in repaired_text

    def test_multiple_annotations(self):
        annots = [
            self._annot(0, 20, explanation='Opens with "This is a sample"'),  # valid
            self._annot(999, 1010),  # invalid, no repair possible
            self._annot(5, 30, explanation='Contains "a sample text for testing"'),  # valid
        ]
        annotations, valid, invalid = _validate_annotations(annots, self.SAMPLE_TEXT)
        assert valid == 2
        assert invalid == 1


class TestHashPrompt:
    def test_deterministic(self):
        h1 = _hash_prompt("test prompt")
        h2 = _hash_prompt("test prompt")
        assert h1 == h2

    def test_prefix(self):
        h = _hash_prompt("test")
        assert h.startswith("sha256:")

    def test_different_inputs(self):
        h1 = _hash_prompt("prompt A")
        h2 = _hash_prompt("prompt B")
        assert h1 != h2


class TestLoadPrompt:
    def test_load_d1(self):
        prompt = _load_prompt("D1")
        assert "Rhetorical Pattern" in prompt
        assert "correctio" in prompt.lower() or "Correctio" in prompt

    def test_unknown_detector_raises(self):
        with pytest.raises(ValueError, match="Unknown detector"):
            _load_prompt("D99")
