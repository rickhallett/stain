"""Detector plugin registry — discovers detectors from filesystem."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DETECTORS_DIR = Path("detectors")


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


def load_detector_info(detector_dir: Path) -> DetectorInfo:
    """Load detector metadata and prompt from a detector directory."""
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

    Args:
        detectors_dir: Root directory containing detector subdirectories.
        enabled_only: If True, only return detectors with enabled=True.

    Returns:
        Dict mapping detector ID to DetectorInfo.
    """
    result: dict[str, DetectorInfo] = {}

    if not detectors_dir.exists():
        return result

    for sub in sorted(detectors_dir.iterdir()):
        if not sub.is_dir():
            continue
        yaml_path = sub / "detector.yaml"
        if not yaml_path.exists():
            continue

        info = load_detector_info(sub)
        if enabled_only and not info.enabled:
            continue
        result[info.id] = info

    return result
