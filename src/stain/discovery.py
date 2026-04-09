"""Discovery pipeline — hypothesis model, store, runner, scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DISCOVERY_DIR = Path("discovery")
AGENTS_DIR = Path("agents")


class DiscoveryError(Exception):
    """Discovery operation error."""
    pass


@dataclass
class Hypothesis:
    pattern_name: str
    description: str
    confidence: float
    suggested_detector: str
    status: str = "pending"
    first_seen: str = ""
    last_seen: str = ""
    occurrence_count: int = 0

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.first_seen:
            self.first_seen = now
        if not self.last_seen:
            self.last_seen = now


@dataclass
class DiscoveryResult:
    """Raw output from a single discovery run."""
    timestamp: str
    source: str
    model: str
    hypotheses: list[dict]


@dataclass
class HypothesisStore:
    hypotheses: dict[str, Hypothesis] = field(default_factory=dict)

    def merge(self, raw_hypotheses: list[dict], source: str) -> tuple[int, int]:
        """Merge hypotheses from a run. Returns (new_count, updated_count)."""
        now = datetime.now(timezone.utc).isoformat()
        new_count = 0
        updated_count = 0

        for h in raw_hypotheses:
            name = h["pattern_name"]
            if name in self.hypotheses:
                existing = self.hypotheses[name]
                existing.occurrence_count += 1
                existing.last_seen = now
                existing.confidence = max(existing.confidence, h.get("confidence", 0))
                updated_count += 1
            else:
                self.hypotheses[name] = Hypothesis(
                    pattern_name=name,
                    description=h.get("description", ""),
                    confidence=h.get("confidence", 0.5),
                    suggested_detector=h.get("suggested_detector", "New detector"),
                    first_seen=now,
                    last_seen=now,
                    occurrence_count=1,
                )
                new_count += 1

        return new_count, updated_count


def load_hypothesis_store(path: Path | None = None) -> HypothesisStore:
    """Load hypothesis store from YAML. Returns empty store if not found."""
    if path is None:
        path = DISCOVERY_DIR / "hypotheses.yaml"
    if not path.is_file():
        return HypothesisStore()
    raw = yaml.safe_load(path.read_text())
    if not raw or "hypotheses" not in raw:
        return HypothesisStore()
    store = HypothesisStore()
    for name, data in raw["hypotheses"].items():
        store.hypotheses[name] = Hypothesis(**data)
    return store


def save_hypothesis_store(store: HypothesisStore, path: Path | None = None) -> None:
    """Save hypothesis store to YAML."""
    if path is None:
        path = DISCOVERY_DIR / "hypotheses.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "hypotheses": {
            name: asdict(h) for name, h in store.hypotheses.items()
        }
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def save_discovery_run(result: DiscoveryResult, base_dir: Path | None = None) -> Path:
    """Save raw discovery run output as JSON."""
    if base_dir is None:
        base_dir = DISCOVERY_DIR / "runs"
    base_dir.mkdir(parents=True, exist_ok=True)
    ts = result.timestamp.replace(":", "-").replace("+", "_")
    path = base_dir / f"{ts}.json"
    path.write_text(json.dumps(asdict(result), indent=2))
    return path
