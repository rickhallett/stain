"""Tests for detector plugin registry."""

import pytest
from pathlib import Path

from stain.registry import DetectorInfo, discover_detectors, load_detector_info


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


class TestDiscoverDetectors:
    def test_discovers_d1(self):
        detectors = discover_detectors()
        assert "D1" in detectors
        assert detectors["D1"].name == "Rhetorical Pattern"

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
