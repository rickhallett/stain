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


class TestAnalyseMultiFileJson:
    def test_multi_file_json_includes_source(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("First file with sufficient content to run through the analyser.")
        f2.write_text("Second file also with enough text for the analyser to process.")
        with patch("stain.cli.analyse", return_value=_mock_analyse()):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["analyse", str(f1), str(f2), "--json"],
            )
            assert "source" in result.output


class TestCorpusStats:
    def test_stats_output(self, tmp_path):
        from stain.corpus import Manifest, SampleEntry, save_manifest
        gold_dir = tmp_path / "gold"
        (gold_dir / "known_human").mkdir(parents=True)
        (gold_dir / "known_llm").mkdir(parents=True)
        (gold_dir / "known_human" / "h1.txt").write_text("human text")
        (gold_dir / "known_llm" / "l1.txt").write_text("llm text")
        (gold_dir / "known_llm" / "l2.txt").write_text("llm text 2")
        save_manifest(Manifest(tier="gold", samples=[
            SampleEntry(id="h1", label="human", source="test", domain="blog", file="known_human/h1.txt"),
            SampleEntry(id="l1", label="llm", source="gen", domain="blog", file="known_llm/l1.txt"),
            SampleEntry(id="l2", label="llm", source="gen", domain="blog", file="known_llm/l2.txt"),
        ]), gold_dir / "manifest.yaml")

        with patch("stain.cli._corpus_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["corpus", "stats"])
            assert result.exit_code == 0
            assert "gold" in result.output.lower()


class TestCorpusValidate:
    def test_validate_clean(self, tmp_path):
        from stain.corpus import Manifest, SampleEntry, save_manifest
        gold_dir = tmp_path / "gold"
        (gold_dir / "known_human").mkdir(parents=True)
        (gold_dir / "known_human" / "h1.txt").write_text("text")
        save_manifest(Manifest(tier="gold", samples=[
            SampleEntry(id="h1", label="human", source="test", domain="blog", file="known_human/h1.txt"),
        ]), gold_dir / "manifest.yaml")

        with patch("stain.cli._corpus_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["corpus", "validate"])
            assert result.exit_code == 0


class TestDiscoverList:
    def test_list_empty(self, tmp_path):
        with patch("stain.cli._discovery_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["discover", "list"])
            assert result.exit_code == 0
            assert "no" in result.output.lower() or "0" in result.output

    def test_list_shows_hypotheses(self, tmp_path):
        from stain.discovery import HypothesisStore, save_hypothesis_store
        store = HypothesisStore()
        store.merge([{"pattern_name": "test_p", "description": "Test desc", "confidence": 0.7, "suggested_detector": "New"}], "f.txt")
        save_hypothesis_store(store, tmp_path / "hypotheses.yaml")

        with patch("stain.cli._discovery_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["discover", "list"])
            assert result.exit_code == 0
            assert "test_p" in result.output


class TestDiscoverRun:
    def test_discover_file_cli(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to run through the full discovery pipeline for testing.")

        mock_composite = MagicMock()
        mock_composite.detector_results = []

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = '{"hypotheses": []}'

        with patch("stain.discovery.analyse", return_value=mock_composite), \
             patch("stain.discovery.litellm.completion", return_value=mock_llm), \
             patch("stain.cli._discovery_dir", return_value=tmp_path / "disc"):
            runner = CliRunner()
            result = runner.invoke(cli, ["discover", str(f)])
            assert result.exit_code == 0


class TestCorpusGenerate:
    def test_generate_llm_invokes(self, tmp_path):
        from stain.corpus import Manifest, save_manifest
        bulk_dir = tmp_path / "bulk"
        (bulk_dir / "known_llm").mkdir(parents=True)
        save_manifest(Manifest(tier="bulk", samples=[]), bulk_dir / "manifest.yaml")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text for CLI test."

        with patch("stain.generate.litellm.completion", return_value=mock_response), \
             patch("stain.cli._corpus_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "corpus", "generate",
                "--type", "llm",
                "--count", "2",
                "--domain", "linkedin",
            ])
            assert result.exit_code == 0


class TestResearchList:
    def test_list_empty(self, tmp_path):
        with patch("stain.cli._research_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["research", "list"])
            assert result.exit_code == 0

    def test_list_shows_papers(self, tmp_path):
        from stain.research import Paper, PaperIndex, save_paper_index
        idx = PaperIndex()
        idx.papers["j1"] = Paper(
            paper_id="j1", title="LLM Detection Study",
            source="arcana", text="content", extracted=True,
        )
        save_paper_index(idx, tmp_path / "index.yaml")

        with patch("stain.cli._research_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["research", "list"])
            assert result.exit_code == 0
            assert "LLM Detection" in result.output


class TestResearchFetchCli:
    def test_fetch_cli(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("stain.research.httpx.get", return_value=mock_resp), \
             patch("stain.cli._research_dir", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["research", "fetch"])
            assert result.exit_code == 0
