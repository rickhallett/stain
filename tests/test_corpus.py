"""Tests for corpus management — manifests, stats, validation, labeling."""

import pytest
from pathlib import Path

import yaml

from stain.corpus import (
    SampleEntry,
    Manifest,
    load_manifest,
    save_manifest,
    CorpusError,
)


class TestSampleEntry:
    def test_create_human_sample(self):
        entry = SampleEntry(
            id="human_sivers_obvious_2010",
            label="human",
            source="sive.rs",
            domain="blog",
            file="known_human/human_sivers_obvious_2010.txt",
        )
        assert entry.label == "human"
        assert entry.model is None

    def test_create_llm_sample(self):
        entry = SampleEntry(
            id="llm_linkedin_01",
            label="llm",
            source="generated",
            domain="linkedin",
            file="known_llm/llm_linkedin_01.txt",
            model="cerebras/qwen-3-235b",
            temperature=0.7,
        )
        assert entry.label == "llm"
        assert entry.model == "cerebras/qwen-3-235b"


class TestManifest:
    def test_create_manifest(self):
        m = Manifest(tier="gold", samples=[])
        assert m.tier == "gold"
        assert len(m.samples) == 0

    def test_add_sample(self):
        m = Manifest(tier="gold", samples=[])
        entry = SampleEntry(
            id="test_sample",
            label="human",
            source="test",
            domain="blog",
            file="known_human/test.txt",
        )
        m.samples.append(entry)
        assert len(m.samples) == 1

    def test_find_sample_by_id(self):
        entry = SampleEntry(
            id="test_sample",
            label="human",
            source="test",
            domain="blog",
            file="known_human/test.txt",
        )
        m = Manifest(tier="gold", samples=[entry])
        found = next((s for s in m.samples if s.id == "test_sample"), None)
        assert found is not None
        assert found.source == "test"


class TestManifestIO:
    def test_save_and_load(self, tmp_path):
        m = Manifest(
            tier="gold",
            samples=[
                SampleEntry(
                    id="sample_01",
                    label="human",
                    source="test",
                    domain="blog",
                    file="known_human/sample_01.txt",
                ),
            ],
        )
        manifest_path = tmp_path / "manifest.yaml"
        save_manifest(m, manifest_path)
        loaded = load_manifest(manifest_path)
        assert loaded.tier == "gold"
        assert len(loaded.samples) == 1
        assert loaded.samples[0].id == "sample_01"

    def test_load_missing_raises(self):
        with pytest.raises(CorpusError, match="not found"):
            load_manifest(Path("/nonexistent/manifest.yaml"))

    def test_saved_yaml_is_readable(self, tmp_path):
        m = Manifest(
            tier="bulk",
            samples=[
                SampleEntry(
                    id="llm_01",
                    label="llm",
                    source="generated",
                    domain="linkedin",
                    file="known_llm/llm_01.txt",
                    model="test/model",
                    temperature=0.7,
                ),
            ],
        )
        manifest_path = tmp_path / "manifest.yaml"
        save_manifest(m, manifest_path)
        raw = yaml.safe_load(manifest_path.read_text())
        assert raw["tier"] == "bulk"
        assert raw["samples"][0]["model"] == "test/model"
