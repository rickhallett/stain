"""Tests for discovery pipeline — hypotheses, store, runner, scaffold."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

from stain.discovery import (
    DiscoveryError,
    DiscoveryResult,
    Hypothesis,
    HypothesisStore,
    load_hypothesis_store,
    save_hypothesis_store,
    save_discovery_run,
    run_discovery,
    _load_discovery_prompt,
    _format_detector_results,
    _build_pattern_catalogue,
    discover_file,
    discover_corpus,
    scaffold_detector,
    promote_detector,
)
from stain.models import DetectorResult, Meta, Verdict


def _make_detector_result(detector_id="D1", score=0.7):
    return DetectorResult(
        detector_id=detector_id,
        detector_name=f"Test {detector_id}",
        version="0.1.0",
        prompt_hash="sha256:test",
        verdict=Verdict(score=score, confidence=0.8, summary="Test summary"),
        meta=Meta(model="test/model", latency_ms=100, tokens_in=100, tokens_out=100),
    )


class TestHypothesis:
    def test_create_hypothesis(self):
        h = Hypothesis(
            pattern_name="manufactured_consensus",
            description="Phrases implying broad agreement without evidence",
            confidence=0.7,
            suggested_detector="New detector",
        )
        assert h.pattern_name == "manufactured_consensus"
        assert h.status == "pending"
        assert h.occurrence_count == 0
        assert h.first_seen != ""

    def test_default_timestamps(self):
        h = Hypothesis(
            pattern_name="test",
            description="test",
            confidence=0.5,
            suggested_detector="test",
        )
        assert h.first_seen != ""
        assert h.last_seen != ""


class TestHypothesisStore:
    def test_empty_store(self):
        store = HypothesisStore()
        assert len(store.hypotheses) == 0

    def test_merge_new_hypothesis(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "test_pattern", "description": "desc", "confidence": 0.7, "suggested_detector": "New"}]
        new, updated = store.merge(raw, "test.txt")
        assert new == 1
        assert updated == 0
        assert "test_pattern" in store.hypotheses
        assert store.hypotheses["test_pattern"].occurrence_count == 1

    def test_merge_existing_increments_count(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "test_pattern", "description": "desc", "confidence": 0.6, "suggested_detector": "New"}]
        store.merge(raw, "file1.txt")
        new, updated = store.merge(raw, "file2.txt")
        assert new == 0
        assert updated == 1
        assert store.hypotheses["test_pattern"].occurrence_count == 2

    def test_merge_updates_confidence_to_max(self):
        store = HypothesisStore()
        store.merge([{"pattern_name": "pat_conf", "description": "d", "confidence": 0.5, "suggested_detector": "New"}], "f1.txt")
        store.merge([{"pattern_name": "pat_conf", "description": "d", "confidence": 0.8, "suggested_detector": "New"}], "f2.txt")
        assert store.hypotheses["pat_conf"].confidence == 0.8

    def test_merge_does_not_lower_confidence(self):
        store = HypothesisStore()
        store.merge([{"pattern_name": "pat_keep", "description": "d", "confidence": 0.9, "suggested_detector": "New"}], "f1.txt")
        store.merge([{"pattern_name": "pat_keep", "description": "d", "confidence": 0.3, "suggested_detector": "New"}], "f2.txt")
        assert store.hypotheses["pat_keep"].confidence == 0.9


class TestMergeValidation:
    def test_malformed_hypothesis_skipped(self):
        store = HypothesisStore()
        raw = [
            "not a dict",
            {"no_pattern_name_key": True},
            {"pattern_name": "valid_one", "description": "d", "confidence": 0.5, "suggested_detector": "New"},
        ]
        new, updated = store.merge(raw, "f.txt")
        assert new == 1
        assert "valid_one" in store.hypotheses

    def test_path_traversal_name_rejected(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "../../../etc/passwd", "description": "d", "confidence": 0.5, "suggested_detector": "New"}]
        new, _ = store.merge(raw, "f.txt")
        assert new == 0
        assert len(store.hypotheses) == 0

    def test_name_with_dots_rejected(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "foo.bar", "description": "d", "confidence": 0.5, "suggested_detector": "New"}]
        new, _ = store.merge(raw, "f.txt")
        assert new == 0

    def test_uppercase_name_rejected(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "FooBar", "description": "d", "confidence": 0.5, "suggested_detector": "New"}]
        new, _ = store.merge(raw, "f.txt")
        assert new == 0

    def test_empty_name_rejected(self):
        store = HypothesisStore()
        raw = [{"pattern_name": "", "description": "d", "confidence": 0.5, "suggested_detector": "New"}]
        new, _ = store.merge(raw, "f.txt")
        assert new == 0


class TestScaffoldValidation:
    def test_scaffold_path_traversal_raises(self, tmp_path):
        store = HypothesisStore()
        # Bypass merge validation to test scaffold's own guard
        store.hypotheses["../evil"] = Hypothesis(
            pattern_name="../evil", description="d", confidence=0.5, suggested_detector="New",
        )
        save_hypothesis_store(store, tmp_path / "h.yaml")
        with pytest.raises(DiscoveryError, match="Invalid pattern name"):
            scaffold_detector("../evil", store=store, store_path=tmp_path / "h.yaml", detectors_dir=tmp_path)


class TestPromoteValidation:
    def test_promote_ambiguous_raises(self, tmp_path):
        (tmp_path / "D7_first").mkdir()
        (tmp_path / "D7_first" / "detector.yaml").write_text("id: D7\nname: A\nenabled: false\n")
        (tmp_path / "D7_second").mkdir()
        (tmp_path / "D7_second" / "detector.yaml").write_text("id: D7\nname: B\nenabled: false\n")
        with pytest.raises(DiscoveryError, match="Ambiguous"):
            promote_detector("D7", detectors_dir=tmp_path)


class TestStoreIO:
    def test_save_and_load(self, tmp_path):
        store = HypothesisStore()
        store.merge([{"pattern_name": "test_p", "description": "desc", "confidence": 0.7, "suggested_detector": "New"}], "f.txt")
        path = tmp_path / "hypotheses.yaml"
        save_hypothesis_store(store, path)
        loaded = load_hypothesis_store(path)
        assert "test_p" in loaded.hypotheses
        assert loaded.hypotheses["test_p"].confidence == 0.7

    def test_load_missing_returns_empty(self, tmp_path):
        store = load_hypothesis_store(tmp_path / "nonexistent.yaml")
        assert len(store.hypotheses) == 0

    def test_saved_yaml_readable(self, tmp_path):
        store = HypothesisStore()
        store.merge([{"pattern_name": "p1", "description": "d1", "confidence": 0.6, "suggested_detector": "New"}], "f.txt")
        path = tmp_path / "hypotheses.yaml"
        save_hypothesis_store(store, path)
        raw = yaml.safe_load(path.read_text())
        assert "p1" in raw["hypotheses"]


class TestDiscoveryRun:
    def test_save_run(self, tmp_path):
        result = DiscoveryResult(
            timestamp="2026-04-09T12:00:00+00:00",
            source="test.txt",
            model="test/model",
            hypotheses=[{"pattern_name": "test", "description": "d", "confidence": 0.5}],
        )
        path = save_discovery_run(result, base_dir=tmp_path)
        assert path.is_file()
        loaded = json.loads(path.read_text())
        assert loaded["source"] == "test.txt"
        assert len(loaded["hypotheses"]) == 1


class TestLoadPrompt:
    def test_load_discovery_prompt(self):
        prompt = _load_discovery_prompt()
        assert "Discovery Agent" in prompt
        assert "hypotheses" in prompt

    def test_missing_prompt_raises(self):
        with patch("stain.discovery.AGENTS_DIR", Path("/nonexistent")):
            with pytest.raises(DiscoveryError, match="not found"):
                _load_discovery_prompt()


class TestFormatDetectorResults:
    def test_format_includes_scores(self):
        results = [_make_detector_result("D1", 0.72)]
        formatted = _format_detector_results(results)
        assert "D1" in formatted
        assert "0.72" in formatted

    def test_format_multiple_detectors(self):
        results = [_make_detector_result("D1", 0.7), _make_detector_result("D2", 0.3)]
        formatted = _format_detector_results(results)
        assert "D1" in formatted
        assert "D2" in formatted


class TestBuildPatternCatalogue:
    def test_catalogue_includes_d1(self):
        catalogue = _build_pattern_catalogue()
        assert "D1" in catalogue
        assert "correctio" in catalogue.lower() or "Correctio" in catalogue


class TestRunDiscovery:
    def test_run_discovery_returns_hypotheses(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "hypotheses": [
                {
                    "pattern_name": "test_pattern",
                    "description": "A test pattern",
                    "examples_found": ["example text"],
                    "confidence": 0.7,
                    "suggested_detector": "New detector",
                }
            ]
        })

        with patch("stain.discovery.litellm.completion", return_value=mock_response):
            results = run_discovery(
                input_text="Some text to analyse",
                detector_results=[_make_detector_result()],
                model="test/model",
                pattern_catalogue="D1: correctio",
            )
        assert len(results) == 1
        assert results[0]["pattern_name"] == "test_pattern"

    def test_run_discovery_empty_hypotheses(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"hypotheses": []}'

        with patch("stain.discovery.litellm.completion", return_value=mock_response):
            results = run_discovery(
                input_text="Normal text",
                detector_results=[],
                model="test/model",
                pattern_catalogue="",
            )
        assert results == []


class TestDiscoverFile:
    def test_discover_file_returns_result(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Some text to analyse for patterns in the discovery pipeline.")

        mock_composite = MagicMock()
        mock_composite.detector_results = [_make_detector_result()]

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = json.dumps({
            "hypotheses": [{"pattern_name": "found_pattern", "description": "d", "confidence": 0.6, "suggested_detector": "New"}]
        })

        with patch("stain.discovery.analyse", return_value=mock_composite), \
             patch("stain.discovery.litellm.completion", return_value=mock_llm):
            result = discover_file(f, discovery_dir=tmp_path / "disc")
        assert result.source == str(f)
        assert len(result.hypotheses) == 1

    def test_discover_file_saves_run(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Text for testing that discovery runs get persisted to disk.")
        disc_dir = tmp_path / "disc"

        mock_composite = MagicMock()
        mock_composite.detector_results = []

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = '{"hypotheses": []}'

        with patch("stain.discovery.analyse", return_value=mock_composite), \
             patch("stain.discovery.litellm.completion", return_value=mock_llm):
            discover_file(f, discovery_dir=disc_dir)
        runs = list((disc_dir / "runs").glob("*.json"))
        assert len(runs) == 1

    def test_discover_file_merges_into_store(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Text for testing that hypotheses get merged into the store.")
        disc_dir = tmp_path / "disc"

        mock_composite = MagicMock()
        mock_composite.detector_results = []

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = json.dumps({
            "hypotheses": [{"pattern_name": "new_thing", "description": "d", "confidence": 0.7, "suggested_detector": "New"}]
        })

        with patch("stain.discovery.analyse", return_value=mock_composite), \
             patch("stain.discovery.litellm.completion", return_value=mock_llm):
            discover_file(f, discovery_dir=disc_dir)
        store = load_hypothesis_store(disc_dir / "hypotheses.yaml")
        assert "new_thing" in store.hypotheses


class TestDiscoverCorpus:
    def test_discover_corpus_processes_files(self, tmp_path):
        tier_dir = tmp_path / "corpus" / "gold"
        (tier_dir / "known_llm").mkdir(parents=True)
        (tier_dir / "known_llm" / "s1.txt").write_text("Sample one for corpus discovery test.")
        (tier_dir / "known_llm" / "s2.txt").write_text("Sample two for corpus discovery test.")

        mock_composite = MagicMock()
        mock_composite.detector_results = []

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = '{"hypotheses": []}'

        config = {"corpus": {"path": str(tmp_path / "corpus")}}

        with patch("stain.discovery.analyse", return_value=mock_composite), \
             patch("stain.discovery.litellm.completion", return_value=mock_llm):
            results = discover_corpus("gold", config=config, discovery_dir=tmp_path / "disc")
        assert len(results) == 2


class TestScaffoldDetector:
    def _make_store_with_hypothesis(self, tmp_path):
        store = HypothesisStore()
        store.merge([{
            "pattern_name": "manufactured_consensus",
            "description": "Phrases implying broad agreement without evidence",
            "confidence": 0.7,
            "suggested_detector": "New detector",
        }], "test.txt")
        path = tmp_path / "hypotheses.yaml"
        save_hypothesis_store(store, path)
        return store, path

    def test_scaffold_creates_directory(self, tmp_path):
        store, store_path = self._make_store_with_hypothesis(tmp_path)
        detectors_dir = tmp_path / "detectors"
        detectors_dir.mkdir()
        (detectors_dir / "D1_test").mkdir()
        (detectors_dir / "D1_test" / "detector.yaml").write_text("id: D1\nname: Test\n")
        (detectors_dir / "D1_test" / "prompt.md").write_text("test")

        detector_id, path = scaffold_detector(
            "manufactured_consensus",
            store=store,
            store_path=store_path,
            detectors_dir=detectors_dir,
        )
        assert detector_id == "D2"
        assert (path / "detector.yaml").is_file()
        assert (path / "prompt.md").is_file()
        assert (path / "CHANGELOG.md").is_file()

    def test_scaffold_sets_enabled_false(self, tmp_path):
        store, store_path = self._make_store_with_hypothesis(tmp_path)
        detectors_dir = tmp_path / "detectors"
        detectors_dir.mkdir()
        (detectors_dir / "D1_test").mkdir()
        (detectors_dir / "D1_test" / "detector.yaml").write_text("id: D1\nname: Test\n")
        (detectors_dir / "D1_test" / "prompt.md").write_text("test")

        _, path = scaffold_detector(
            "manufactured_consensus", store=store,
            store_path=store_path, detectors_dir=detectors_dir,
        )
        raw = yaml.safe_load((path / "detector.yaml").read_text())
        assert raw["enabled"] is False

    def test_scaffold_updates_hypothesis_status(self, tmp_path):
        store, store_path = self._make_store_with_hypothesis(tmp_path)
        detectors_dir = tmp_path / "detectors"
        detectors_dir.mkdir()
        (detectors_dir / "D1_test").mkdir()
        (detectors_dir / "D1_test" / "detector.yaml").write_text("id: D1\nname: Test\n")
        (detectors_dir / "D1_test" / "prompt.md").write_text("test")

        scaffold_detector(
            "manufactured_consensus", store=store,
            store_path=store_path, detectors_dir=detectors_dir,
        )
        reloaded = load_hypothesis_store(store_path)
        assert reloaded.hypotheses["manufactured_consensus"].status == "approved"

    def test_scaffold_unknown_hypothesis_raises(self, tmp_path):
        store = HypothesisStore()
        with pytest.raises(DiscoveryError, match="not found"):
            scaffold_detector("nonexistent", store=store, detectors_dir=tmp_path)


class TestPromoteDetector:
    def test_promote_enables_detector(self, tmp_path):
        d_dir = tmp_path / "D7_test_pattern"
        d_dir.mkdir()
        (d_dir / "detector.yaml").write_text("id: D7\nname: Test\nenabled: false\n")
        (d_dir / "prompt.md").write_text("test")
        promote_detector("D7", detectors_dir=tmp_path)
        raw = yaml.safe_load((d_dir / "detector.yaml").read_text())
        assert raw["enabled"] is True

    def test_promote_missing_detector_raises(self, tmp_path):
        with pytest.raises(DiscoveryError, match="not found"):
            promote_detector("D99", detectors_dir=tmp_path)
