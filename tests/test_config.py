"""Tests for config loader."""

from pathlib import Path

import pytest

from stain.config import get_detector_weight, get_enabled_detectors, load_config
from stain.registry import clear_cache


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    clear_cache()
    yield
    clear_cache()


class TestLoadConfig:
    def test_load_default(self):
        config = load_config()
        assert "models" in config

    def test_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))


class TestGetEnabledDetectors:
    def test_all_detectors_enabled(self):
        config = load_config()
        enabled = get_enabled_detectors(config)
        assert "D1" in enabled
        assert "D2" in enabled
        assert "D3" in enabled
        assert "D4" in enabled
        assert "D5" in enabled
        assert "D6" in enabled

    def test_returns_list(self):
        enabled = get_enabled_detectors()
        assert isinstance(enabled, list)
        assert len(enabled) >= 1


class TestConfigResolution:
    def test_local_config_preferred(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        local = tmp_path / "stain.config.yaml"
        local.write_text("models:\n  detector: local/model\n")
        config = load_config()
        assert config["models"]["detector"] == "local/model"

    def test_user_config_fallback(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # no local config here
        user_dir = tmp_path / ".config" / "stain"
        user_dir.mkdir(parents=True)
        (user_dir / "config.yaml").write_text("models:\n  detector: user/model\n")
        monkeypatch.setenv("HOME", str(tmp_path))
        config = load_config()
        assert config["models"]["detector"] == "user/model"

    def test_defaults_when_no_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        config = load_config()
        assert "models" in config
        assert config["models"]["detector"] != ""

    def test_explicit_path_overrides_all(self, tmp_path):
        explicit = tmp_path / "custom.yaml"
        explicit.write_text("models:\n  detector: explicit/model\n")
        config = load_config(explicit)
        assert config["models"]["detector"] == "explicit/model"


class TestGetDetectorWeight:
    def test_d1_weight(self):
        config = load_config()
        weight = get_detector_weight(config, "D1")
        assert weight == 1.0

    def test_missing_detector_default(self):
        weight = get_detector_weight({}, "D99")
        assert weight == 1.0
