"""Configuration loader with cascading resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from stain.registry import discover_detectors


DEFAULT_CONFIG = {
    "models": {
        "detector": "cerebras/qwen-3-235b-a22b-instruct-2507",
        "orchestrator": "anthropic/claude-sonnet-4-5-20250514",
    },
    "corpus": {
        "path": "corpus/",
        "gold": "corpus/gold/",
        "bulk": "corpus/bulk/",
        "ambiguous": "corpus/ambiguous/",
    },
    "results": {"path": "results/"},
    "audit": {"enabled": True, "verbosity": "hashes", "path": ".stain/audit"},
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config with cascading resolution.

    Resolution order:
    1. Explicit path (if given)
    2. Local stain.config.yaml (CWD)
    3. ~/.config/stain/config.yaml (user)
    4. Package defaults
    """
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)

    # Local config
    local = Path("stain.config.yaml")
    if local.is_file():
        with open(local) as f:
            return yaml.safe_load(f)

    # User config
    user = Path.home() / ".config" / "stain" / "config.yaml"
    if user.is_file():
        with open(user) as f:
            return yaml.safe_load(f)

    # Package defaults
    return DEFAULT_CONFIG.copy()


def get_enabled_detectors(config: dict[str, Any] | None = None) -> list[str]:
    """Return list of enabled detector IDs from the filesystem registry."""
    return list(discover_detectors(enabled_only=True).keys())


def get_detector_weight(config: dict[str, Any] | None, detector_id: str) -> float:
    """Get weight for a detector from the filesystem registry."""
    detectors = discover_detectors(enabled_only=False)
    if detector_id in detectors:
        return detectors[detector_id].weight
    return 1.0
