"""Tests for detector plugin registry."""

import pytest
from pathlib import Path

from stain.registry import (
    DetectorInfo,
    clear_cache,
    discover_detectors,
    load_detector_info,
)


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    """Ensure each test starts with a fresh registry cache."""
    clear_cache()
    yield
    clear_cache()


class TestDetectorInfo:
    def test_load_d1(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.id == "D1"
        assert info.name == "Rhetorical Pattern"
        assert info.version == "0.1.0"
        assert info.weight == 1.0
        assert info.enabled is True
        assert len(info.patterns) == 7

    def test_prompt_loaded(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert "Rhetorical Pattern" in info.prompt
        assert "correctio" in info.prompt.lower() or "Correctio" in info.prompt

    def test_prompt_hash_deterministic(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.prompt_hash.startswith("sha256:")
        info2 = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.prompt_hash == info2.prompt_hash

    def test_missing_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            load_detector_info(Path("detectors/D99_nonexistent"))

    def test_malformed_yaml_raises(self, tmp_path):
        bad_dir = tmp_path / "D99_bad"
        bad_dir.mkdir()
        (bad_dir / "detector.yaml").write_text("not_a_mapping")
        (bad_dir / "prompt.md").write_text("test prompt")
        with pytest.raises(ValueError, match="not a valid YAML mapping"):
            load_detector_info(bad_dir)

    def test_missing_required_keys_raises(self, tmp_path):
        bad_dir = tmp_path / "D99_noname"
        bad_dir.mkdir()
        (bad_dir / "detector.yaml").write_text("weight: 1.0\n")
        (bad_dir / "prompt.md").write_text("test prompt")
        with pytest.raises(ValueError, match="missing required keys"):
            load_detector_info(bad_dir)


class TestDiscoverDetectors:
    def test_discovers_d1(self):
        detectors = discover_detectors()
        assert "D1" in detectors
        assert detectors["D1"].name == "Rhetorical Pattern"

    def test_discovers_all_six(self):
        detectors = discover_detectors(enabled_only=False)
        assert len(detectors) == 6
        for did in ["D1", "D2", "D3", "D4", "D5", "D6"]:
            assert did in detectors

    def test_discovers_only_enabled(self):
        all_detectors = discover_detectors(enabled_only=False)
        enabled = discover_detectors(enabled_only=True)
        assert len(enabled) <= len(all_detectors)
        for did, info in enabled.items():
            assert info.enabled is True

    def test_returns_dict_keyed_by_id(self):
        detectors = discover_detectors()
        for did, info in detectors.items():
            assert did == info.id

    def test_caching(self):
        d1 = discover_detectors()
        d2 = discover_detectors()
        # Same object from cache
        assert d1["D1"].prompt_hash == d2["D1"].prompt_hash

    def test_clear_cache(self):
        discover_detectors()
        clear_cache()
        # Should not error — just re-scans
        d = discover_detectors()
        assert "D1" in d

    def test_malformed_detector_skipped(self, tmp_path):
        """A malformed detector directory should be skipped, not crash discovery."""
        # Create a valid detector
        good = tmp_path / "D99_good"
        good.mkdir()
        (good / "detector.yaml").write_text("id: D99\nname: Good\n")
        (good / "prompt.md").write_text("test")

        # Create a malformed one (missing prompt.md)
        bad = tmp_path / "D98_bad"
        bad.mkdir()
        (bad / "detector.yaml").write_text("id: D98\nname: Bad\n")
        # No prompt.md!

        detectors = discover_detectors(detectors_dir=tmp_path, enabled_only=False)
        assert "D99" in detectors
        assert "D98" not in detectors

    def test_duplicate_id_raises(self, tmp_path):
        """Two detectors with the same ID should raise ValueError."""
        dir_a = tmp_path / "A_first"
        dir_a.mkdir()
        (dir_a / "detector.yaml").write_text("id: DX\nname: First\n")
        (dir_a / "prompt.md").write_text("prompt a")

        dir_b = tmp_path / "B_second"
        dir_b.mkdir()
        (dir_b / "detector.yaml").write_text("id: DX\nname: Second\n")
        (dir_b / "prompt.md").write_text("prompt b")

        with pytest.raises(ValueError, match="Duplicate detector ID"):
            discover_detectors(detectors_dir=tmp_path, enabled_only=False)
