"""Tests for discovery pipeline — hypotheses, store, runner, scaffold."""

import json
import pytest
from pathlib import Path

import yaml

from stain.discovery import (
    DiscoveryError,
    DiscoveryResult,
    Hypothesis,
    HypothesisStore,
    load_hypothesis_store,
    save_hypothesis_store,
    save_discovery_run,
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
        store.merge([{"pattern_name": "p", "description": "d", "confidence": 0.5, "suggested_detector": "New"}], "f1.txt")
        store.merge([{"pattern_name": "p", "description": "d", "confidence": 0.8, "suggested_detector": "New"}], "f2.txt")
        assert store.hypotheses["p"].confidence == 0.8

    def test_merge_does_not_lower_confidence(self):
        store = HypothesisStore()
        store.merge([{"pattern_name": "p", "description": "d", "confidence": 0.9, "suggested_detector": "New"}], "f1.txt")
        store.merge([{"pattern_name": "p", "description": "d", "confidence": 0.3, "suggested_detector": "New"}], "f2.txt")
        assert store.hypotheses["p"].confidence == 0.9


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
