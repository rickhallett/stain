"""Detector plugin registry — discovers detectors from filesystem.

Caches discovery results for the lifetime of the process. Call
clear_cache() to force re-scan (e.g. after adding a new detector).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import importlib.resources

import yaml


logger = logging.getLogger(__name__)


def _find_detectors_dir() -> Path:
    """Find detectors directory — local first, then package data."""
    local = Path("detectors")
    if local.is_dir():
        return local
    try:
        pkg_data = importlib.resources.files("stain") / "data" / "detectors"
        if pkg_data.is_dir():
            return Path(str(pkg_data))
    except (TypeError, FileNotFoundError):
        pass
    return local


DETECTORS_DIR = _find_detectors_dir()

# Module-level cache: populated on first discover_detectors() call
_cache: dict[str, "DetectorInfo"] | None = None


@dataclass
class PatternInfo:
    name: str
    description: str


@dataclass
class DetectorInfo:
    id: str
    name: str
    version: str
    weight: float
    enabled: bool
    description: str
    patterns: list[PatternInfo]
    prompt: str
    prompt_hash: str
    path: Path

    @property
    def dir_name(self) -> str:
        return self.path.name


_REQUIRED_YAML_KEYS = {"id", "name"}


def load_detector_info(detector_dir: Path) -> DetectorInfo:
    """Load detector metadata and prompt from a detector directory.

    Raises FileNotFoundError if directory/files missing,
    ValueError if detector.yaml is malformed.
    """
    if not detector_dir.exists():
        raise FileNotFoundError(f"Detector directory not found: {detector_dir}")

    yaml_path = detector_dir / "detector.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"detector.yaml not found in {detector_dir}")

    prompt_path = detector_dir / "prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt.md not found in {detector_dir}")

    with open(yaml_path) as f:
        meta = yaml.safe_load(f)

    if not isinstance(meta, dict):
        raise ValueError(f"detector.yaml in {detector_dir} is not a valid YAML mapping")

    missing = _REQUIRED_YAML_KEYS - set(meta.keys())
    if missing:
        raise ValueError(f"detector.yaml in {detector_dir} missing required keys: {missing}")

    prompt = prompt_path.read_text()
    prompt_hash = f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"

    patterns = [
        PatternInfo(name=p["name"], description=p["description"])
        for p in meta.get("patterns", [])
    ]

    return DetectorInfo(
        id=meta["id"],
        name=meta["name"],
        version=meta.get("version", "0.1.0"),
        weight=meta.get("weight", 1.0),
        enabled=meta.get("enabled", True),
        description=meta.get("description", ""),
        patterns=patterns,
        prompt=prompt,
        prompt_hash=prompt_hash,
        path=detector_dir,
    )


def discover_detectors(
    detectors_dir: Path = DETECTORS_DIR,
    enabled_only: bool = True,
) -> dict[str, DetectorInfo]:
    """Scan detectors directory and return all discovered detectors.

    Results are cached after the first call. Use clear_cache() to force
    re-scan (e.g. after adding a new detector at runtime).

    Malformed detector directories are logged and skipped, not fatal.
    Duplicate detector IDs raise ValueError.

    Args:
        detectors_dir: Root directory containing detector subdirectories.
        enabled_only: If True, only return detectors with enabled=True.

    Returns:
        Dict mapping detector ID to DetectorInfo.
    """
    global _cache

    if _cache is None:
        _cache = _scan_detectors(detectors_dir)

    if enabled_only:
        return {did: info for did, info in _cache.items() if info.enabled}
    return dict(_cache)


def _scan_detectors(detectors_dir: Path) -> dict[str, DetectorInfo]:
    """Internal: scan filesystem and build detector cache."""
    result: dict[str, DetectorInfo] = {}

    if not detectors_dir.exists():
        return result

    for sub in sorted(detectors_dir.iterdir()):
        if not sub.is_dir():
            continue
        yaml_path = sub / "detector.yaml"
        if not yaml_path.exists():
            continue

        try:
            info = load_detector_info(sub)
        except (FileNotFoundError, ValueError, KeyError, yaml.YAMLError) as e:
            logger.warning("Skipping malformed detector in %s: %s", sub, e)
            continue

        if info.id in result:
            raise ValueError(
                f"Duplicate detector ID '{info.id}' found in "
                f"{result[info.id].path} and {sub}"
            )

        result[info.id] = info

    return result


def clear_cache() -> None:
    """Clear the detector registry cache, forcing re-scan on next call."""
    global _cache
    _cache = None
