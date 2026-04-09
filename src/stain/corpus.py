"""Corpus management — manifest model, I/O, stats, validation, labeling."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class CorpusError(Exception):
    """Corpus operation error."""
    pass


@dataclass
class SampleEntry:
    id: str
    label: str              # "human" or "llm"
    source: str             # origin (e.g. "sive.rs", "generated")
    domain: str             # content domain (e.g. "blog", "linkedin")
    file: str               # relative path within tier dir
    added: str = ""         # ISO date, auto-filled if empty
    model: str | None = None        # for LLM-generated samples
    temperature: float | None = None

    def __post_init__(self):
        if not self.added:
            self.added = date.today().isoformat()


@dataclass
class Manifest:
    tier: str               # "gold" or "bulk"
    samples: list[SampleEntry] = field(default_factory=list)


def save_manifest(manifest: Manifest, path: Path) -> None:
    """Write manifest to YAML file."""
    data = {
        "tier": manifest.tier,
        "samples": [
            {k: v for k, v in asdict(s).items() if v is not None}
            for s in manifest.samples
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def load_manifest(path: Path) -> Manifest:
    """Load manifest from YAML file."""
    if not path.is_file():
        raise CorpusError(f"Manifest not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or "tier" not in raw:
        raise CorpusError(f"Invalid manifest format: {path}")
    samples = [SampleEntry(**s) for s in raw.get("samples", [])]
    return Manifest(tier=raw["tier"], samples=samples)
