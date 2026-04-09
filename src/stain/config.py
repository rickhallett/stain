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


def get_enabled_detectors(config: dict[str, Any]) -> list[str]:
    """Return list of enabled detector IDs."""
    return [
        did for did, dcfg in config.get("detectors", {}).items()
        if dcfg.get("enabled", False)
    ]


def get_detector_weight(config: dict[str, Any], detector_id: str) -> float:
    """Get weight for a detector."""
    return config.get("detectors", {}).get(detector_id, {}).get("weight", 1.0)


def get_enabled_detectors_from_registry() -> list[str]:
    """Return enabled detector IDs from filesystem registry."""
    return list(discover_detectors(enabled_only=True).keys())
