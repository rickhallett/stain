"""Configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stain.registry import discover_detectors


DEFAULT_CONFIG_PATH = Path("stain.config.yaml")


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config from YAML file."""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_enabled_detectors(config: dict[str, Any] | None = None) -> list[str]:
    """Return list of enabled detector IDs from the filesystem registry."""
    return list(discover_detectors(enabled_only=True).keys())


def get_detector_weight(config: dict[str, Any] | None, detector_id: str) -> float:
    """Get weight for a detector from the filesystem registry."""
    detectors = discover_detectors(enabled_only=False)
    if detector_id in detectors:
        return detectors[detector_id].weight
    return 1.0
