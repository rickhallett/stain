"""Integration tests for the analyse CLI command."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from stain.cli import cli
from stain.models import CompositeResult, DetectorResult, Meta, Verdict


def _mock_analyse(score=0.65):
    """Return a mock CompositeResult with a given composite score."""
    return CompositeResult(
        stain_version="0.1.0",
        input_hash="sha256:test",
        input_length_chars=100,
        composite_score=score,
        detector_results=[
            DetectorResult(
                detector_id="D1",
                detector_name="Rhetorical Pattern",
                version="0.1.0",
                prompt_hash="sha256:test",
                verdict=Verdict(score=score, confidence=0.8, summary="Test"),
                meta=Meta(model="test/model", latency_ms=100, tokens_in=100, tokens_out=100),
            ),
        ],
        merged_annotations=[],
        meta={"total_latency_ms": 100, "total_tokens_in": 100, "total_tokens_out": 100},
    )


class TestAnalyseExitCodes:
    def test_below_threshold_exits_0(self, tmp_path):
        f = tmp_path / "clean.txt"
        f.write_text("This is a normal human-written text with enough content to analyse.")
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.30)):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f)])
            assert result.exit_code == 0

    def test_above_threshold_exits_1(self, tmp_path):
        f = tmp_path / "slop.txt"
        f.write_text("This is AI generated text that should be flagged by the detectors.")
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.70)):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f)])
            assert result.exit_code == 1

    def test_custom_threshold(self, tmp_path):
        f = tmp_path / "mid.txt"
        f.write_text("This text scores in the middle range for detection patterns.")
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.40)):
            runner = CliRunner()
            # Default threshold 0.55 -> exit 0
            result = runner.invoke(cli, ["analyse", str(f)])
            assert result.exit_code == 0
            # Lower threshold -> exit 1
            result = runner.invoke(cli, ["analyse", str(f), "--threshold", "0.35"])
            assert result.exit_code == 1

    def test_missing_file_exits_2(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["analyse", "/nonexistent/file.txt"])
        assert result.exit_code == 2

    def test_api_error_exits_3(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to analyse that will trigger an API error in the mock.")
        with patch("stain.cli.analyse", side_effect=Exception("API timeout")):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f)])
            assert result.exit_code == 3


class TestAnalyseOutputModes:
    def test_json_flag(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to analyse and check the JSON output format works.")
        with patch("stain.cli.analyse", return_value=_mock_analyse()):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f), "--json"])
            parsed = json.loads(result.output)
            assert "composite_score" in parsed

    def test_plain_flag(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to analyse and verify the plain output mode works.")
        with patch("stain.cli.analyse", return_value=_mock_analyse()):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f), "--plain"])
            assert "score=" in result.output
            assert "D1=" in result.output

    def test_score_flag(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to analyse and check that score-only output works.")
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.723)):
            runner = CliRunner()
            result = runner.invoke(cli, ["analyse", str(f), "--score"])
            assert result.output.strip() == "0.723"


class TestAnalyseStdin:
    def test_stdin_with_dash(self):
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.30)):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["analyse", "-", "--score"],
                input="Piped text content for analysis via stdin.",
            )
            assert result.exit_code == 0


class TestAnalyseMultipleFiles:
    def test_multiple_files_score_output(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("First file content with enough text to be analysed properly.")
        f2.write_text("Second file content that also has sufficient length for analysis.")
        with patch("stain.cli.analyse", return_value=_mock_analyse(score=0.50)):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["analyse", str(f1), str(f2), "--score"],
            )
            lines = result.output.strip().split("\n")
            assert len(lines) == 2
