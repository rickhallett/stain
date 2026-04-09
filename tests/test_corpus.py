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
    corpus_stats,
    corpus_validate,
)


def _make_tier(tmp_path, tier_name, human_count=2, llm_count=3):
    """Create a tier directory with files and manifest."""
    tier_dir = tmp_path / tier_name
    human_dir = tier_dir / "known_human"
    llm_dir = tier_dir / "known_llm"
    human_dir.mkdir(parents=True)
    llm_dir.mkdir(parents=True)

    samples = []
    for i in range(human_count):
        fname = f"human_{i:02d}.txt"
        (human_dir / fname).write_text(f"Human text sample {i}")
        samples.append(SampleEntry(
            id=f"human_{i:02d}", label="human", source="test",
            domain="blog", file=f"known_human/{fname}",
        ))
    for i in range(llm_count):
        fname = f"llm_{i:02d}.txt"
        (llm_dir / fname).write_text(f"LLM text sample {i}")
        samples.append(SampleEntry(
            id=f"llm_{i:02d}", label="llm", source="generated",
            domain="linkedin", file=f"known_llm/{fname}",
        ))

    m = Manifest(tier=tier_name, samples=samples)
    save_manifest(m, tier_dir / "manifest.yaml")
    return tier_dir


class TestCorpusStats:
    def test_stats_counts(self, tmp_path):
        _make_tier(tmp_path, "gold", human_count=3, llm_count=5)
        _make_tier(tmp_path, "bulk", human_count=10, llm_count=20)
        stats = corpus_stats(tmp_path)
        assert stats["gold"]["human"] == 3
        assert stats["gold"]["llm"] == 5
        assert stats["gold"]["total"] == 8
        assert stats["bulk"]["human"] == 10
        assert stats["bulk"]["llm"] == 20
        assert stats["bulk"]["total"] == 30
        assert stats["total"] == 38

    def test_stats_empty_tier(self, tmp_path):
        _make_tier(tmp_path, "gold", human_count=0, llm_count=0)
        stats = corpus_stats(tmp_path)
        assert stats["gold"]["total"] == 0

    def test_stats_missing_tier_skipped(self, tmp_path):
        _make_tier(tmp_path, "gold", human_count=2, llm_count=3)
        stats = corpus_stats(tmp_path)
        assert stats["gold"]["total"] == 5
        assert "bulk" not in stats or stats.get("bulk", {}).get("total", 0) == 0


class TestCorpusValidate:
    def test_valid_corpus(self, tmp_path):
        _make_tier(tmp_path, "gold", human_count=2, llm_count=3)
        issues = corpus_validate(tmp_path)
        assert len(issues) == 0

    def test_missing_file_detected(self, tmp_path):
        tier_dir = _make_tier(tmp_path, "gold", human_count=1, llm_count=0)
        (tier_dir / "known_human" / "human_00.txt").unlink()
        issues = corpus_validate(tmp_path)
        assert any("missing" in issue.lower() for issue in issues)

    def test_orphan_file_detected(self, tmp_path):
        tier_dir = _make_tier(tmp_path, "gold", human_count=1, llm_count=0)
        (tier_dir / "known_human" / "orphan.txt").write_text("orphan content")
        issues = corpus_validate(tmp_path)
        assert any("orphan" in issue.lower() or "not in manifest" in issue.lower() for issue in issues)

    def test_duplicate_id_detected(self, tmp_path):
        tier_dir = tmp_path / "gold"
        human_dir = tier_dir / "known_human"
        human_dir.mkdir(parents=True)
        (human_dir / "dupe.txt").write_text("content")
        m = Manifest(tier="gold", samples=[
            SampleEntry(id="dupe", label="human", source="test", domain="blog", file="known_human/dupe.txt"),
            SampleEntry(id="dupe", label="human", source="test", domain="blog", file="known_human/dupe.txt"),
        ])
        save_manifest(m, tier_dir / "manifest.yaml")
        issues = corpus_validate(tmp_path)
        assert any("duplicate" in issue.lower() for issue in issues)


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
