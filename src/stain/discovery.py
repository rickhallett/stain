"""Discovery pipeline — hypothesis model, store, runner, scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
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


def _load_discovery_prompt() -> str:
    """Load the discovery agent system prompt."""
    path = AGENTS_DIR / "discovery" / "prompt.md"
    if not path.is_file():
        raise DiscoveryError(f"Discovery prompt not found: {path}")
    return path.read_text()


def _format_detector_results(results: list) -> str:
    """Format detector results for the discovery agent's context."""
    lines = []
    for r in results:
        lines.append(f"### {r.detector_id}: {r.detector_name}")
        lines.append(f"Score: {r.verdict.score:.2f} | Confidence: {r.verdict.confidence:.2f}")
        lines.append(f"Summary: {r.verdict.summary}")
        if r.verdict.annotations:
            lines.append("Annotations:")
            for a in r.verdict.annotations:
                lines.append(f"  - [{a.pattern}] {a.explanation[:100]}")
        lines.append("")
    return "\n".join(lines)


def _build_pattern_catalogue() -> str:
    """Build text summary of all patterns across all detectors."""
    from stain.registry import discover_detectors
    detectors = discover_detectors(enabled_only=False)
    lines = []
    for did, info in sorted(detectors.items()):
        lines.append(f"### {did}: {info.name}")
        for p in info.patterns:
            lines.append(f"  - {p.name}: {p.description}")
        lines.append("")
    return "\n".join(lines)


def run_discovery(
    input_text: str,
    detector_results: list,
    model: str,
    pattern_catalogue: str,
) -> list[dict]:
    """Run discovery agent against text + detector output. Returns raw hypotheses."""
    from stain.detector import _extract_json

    prompt = _load_discovery_prompt()

    detector_summary = _format_detector_results(detector_results)

    user_message = (
        "## Original Text\n\n"
        f"{input_text}\n\n"
        "## Existing Detector Results\n\n"
        f"{detector_summary}\n\n"
        "## Current Pattern Catalogue\n\n"
        f"{pattern_catalogue}\n\n"
        "---\n\n"
        "Analyse the text above. Find patterns the existing detectors missed. "
        "Return your hypotheses as structured JSON."
    )

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=2048,
        timeout=60,
    )

    raw_text = response.choices[0].message.content
    parsed = _extract_json(raw_text)
    return parsed.get("hypotheses", [])
