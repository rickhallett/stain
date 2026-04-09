"""Tests for config loader."""

from pathlib import Path

import pytest

from stain.config import get_detector_weight, get_enabled_detectors, load_config


class TestLoadConfig:
    def test_load_default(self):
        config = load_config()
        assert "models" in config
        assert "detectors" in config

    def test_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))


class TestGetEnabledDetectors:
    def test_only_d1_enabled(self):
        config = load_config()
        enabled = get_enabled_detectors(config)
        assert "D1" in enabled
        # D2-D6 are disabled in Phase 1
        assert "D2" not in enabled

    def test_empty_config(self):
        enabled = get_enabled_detectors({})
        assert enabled == []


class TestGetDetectorWeight:
    def test_d1_weight(self):
        config = load_config()
        weight = get_detector_weight(config, "D1")
        assert weight == 1.0

    def test_missing_detector_default(self):
        weight = get_detector_weight({}, "D99")
        assert weight == 1.0
