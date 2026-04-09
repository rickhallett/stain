"""Tests for output formatting — JSON, plain, score modes + TTY auto-detection."""

import json
import pytest
from unittest.mock import patch

from stain.models import CompositeResult, DetectorResult, Meta, Verdict
from stain.output import OutputMode, detect_mode, format_json, format_plain, format_score


def _make_result(composite_score=0.65):
    return CompositeResult(
        stain_version="0.1.0",
        input_hash="sha256:abc123",
        input_length_chars=500,
        composite_score=composite_score,
        detector_results=[
            DetectorResult(
                detector_id="D1",
                detector_name="Rhetorical Pattern",
                version="0.1.0",
                prompt_hash="sha256:def456",
                verdict=Verdict(
                    score=0.72, confidence=0.85, summary="High pattern density",
                ),
                meta=Meta(
                    model="test/model", latency_ms=200,
                    tokens_in=400, tokens_out=300,
                ),
            ),
            DetectorResult(
                detector_id="D2",
                detector_name="Sentence Rhythm",
                version="0.1.0",
                prompt_hash="sha256:ghi789",
                verdict=Verdict(
                    score=0.58, confidence=0.70, summary="Moderate uniformity",
                ),
                meta=Meta(
                    model="test/model", latency_ms=150,
                    tokens_in=400, tokens_out=250,
                ),
            ),
        ],
        merged_annotations=[],
        meta={"total_latency_ms": 350, "total_tokens_in": 800, "total_tokens_out": 550},
    )


class TestFormatJson:
    def test_valid_json_output(self):
        result = _make_result()
        output = format_json(result)
        parsed = json.loads(output)
        assert parsed["composite_score"] == 0.65
        assert len(parsed["detector_results"]) == 2

    def test_roundtrip(self):
        result = _make_result()
        output = format_json(result)
        parsed = json.loads(output)
        restored = CompositeResult(**parsed)
        assert restored.composite_score == result.composite_score


class TestFormatPlain:
    def test_contains_score_and_detectors(self):
        result = _make_result()
        output = format_plain(result)
        assert "0.650" in output
        assert "D1" in output
        assert "D2" in output

    def test_single_line(self):
        result = _make_result()
        output = format_plain(result)
        assert "\n" not in output


class TestFormatScore:
    def test_score_only(self):
        result = _make_result(composite_score=0.723)
        output = format_score(result)
        assert output == "0.723"

    def test_no_extra_text(self):
        result = _make_result()
        output = format_score(result)
        float(output)  # Should not raise


class TestDetectMode:
    def test_explicit_json_flag(self):
        assert detect_mode(json_flag=True) == OutputMode.JSON

    def test_explicit_plain_flag(self):
        assert detect_mode(plain_flag=True) == OutputMode.PLAIN

    def test_explicit_score_flag(self):
        assert detect_mode(score_flag=True) == OutputMode.SCORE

    def test_tty_defaults_to_rich(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            assert detect_mode() == OutputMode.RICH

    def test_pipe_defaults_to_json(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            assert detect_mode() == OutputMode.JSON
