"""Discovery pipeline — hypothesis model, store, runner, scaffold."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
import yaml


DISCOVERY_DIR = Path("discovery")
AGENTS_DIR = Path("agents")

# Pattern names must be safe for filesystem use — lowercase alphanumeric + underscores only
VALID_PATTERN_NAME = re.compile(r"^[a-z][a-z0-9_]{1,60}$")

logger = logging.getLogger(__name__)


def analyse(text: str, config: dict | None = None, **kwargs):
    """Thin shim — delegates to orchestrator.analyse; exists here so tests can patch stain.discovery.analyse."""
    from stain.orchestrator import analyse as _analyse
    return _analyse(text, config=config, **kwargs)


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
            if not isinstance(h, dict) or "pattern_name" not in h:
                logger.warning(f"Skipping malformed hypothesis: {h!r}")
                continue
            name = h["pattern_name"]
            if not isinstance(name, str) or not VALID_PATTERN_NAME.match(name):
                logger.warning(f"Skipping hypothesis with invalid name: {name!r}")
                continue
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


def discover_file(
    file_path: Path,
    config: dict | None = None,
    discovery_model: str | None = None,
    discovery_dir: Path | None = None,
) -> DiscoveryResult:
    """Full pipeline: run detectors + discovery on a single file."""
    from stain.config import load_config

    if config is None:
        config = load_config()
    if discovery_dir is None:
        discovery_dir = DISCOVERY_DIR

    text = file_path.read_text()
    composite = analyse(text, config=config)
    catalogue = _build_pattern_catalogue()

    model = discovery_model or config.get("models", {}).get(
        "orchestrator", "anthropic/claude-sonnet-4-5-20250514"
    )
    raw_hypotheses = run_discovery(text, composite.detector_results, model, catalogue)

    now = datetime.now(timezone.utc).isoformat()
    result = DiscoveryResult(
        timestamp=now,
        source=str(file_path),
        model=model,
        hypotheses=raw_hypotheses,
    )

    save_discovery_run(result, base_dir=discovery_dir / "runs")
    store = load_hypothesis_store(discovery_dir / "hypotheses.yaml")
    store.merge(raw_hypotheses, str(file_path))
    save_hypothesis_store(store, discovery_dir / "hypotheses.yaml")

    return result


def discover_corpus(
    tier: str,
    config: dict | None = None,
    discovery_model: str | None = None,
    discovery_dir: Path | None = None,
) -> list[DiscoveryResult]:
    """Run discovery across all files in a corpus tier."""
    from stain.config import load_config

    if config is None:
        config = load_config()

    corpus_root = Path(config.get("corpus", {}).get("path", "corpus"))
    tier_dir = corpus_root / tier

    results = []
    for subdir in ["known_human", "known_llm"]:
        dir_path = tier_dir / subdir
        if not dir_path.is_dir():
            continue
        for f in sorted(dir_path.glob("*.txt")):
            result = discover_file(
                f, config=config,
                discovery_model=discovery_model,
                discovery_dir=discovery_dir,
            )
            results.append(result)

    return results


PROMPT_TEMPLATE = '''# {name} Detector

You are analysing text to identify the "{pattern_name}" pattern — a potential
marker of LLM-generated content.

## Pattern Definition

{description}

## What to Look For

Scan the input text for instances of this pattern. For each instance:
1. Identify the exact span in the text (character offsets)
2. Classify the severity (high/medium/low)
3. Explain why this instance matches the pattern

## Scoring

- **0.0-0.3**: No significant instances found
- **0.3-0.6**: Some instances present but could be natural
- **0.6-1.0**: Strong presence suggesting LLM generation

## Output Format

Return a JSON object:

```json
{{
  "verdict": {{
    "score": 0.0,
    "confidence": 0.0,
    "summary": "Brief assessment of pattern presence",
    "annotations": [
      {{
        "span_start": 0,
        "span_end": 100,
        "pattern": "{pattern_name}",
        "severity": "medium",
        "explanation": "Why this span matches the pattern"
      }}
    ]
  }}
}}
```
'''


def scaffold_detector(
    pattern_name: str,
    store: HypothesisStore | None = None,
    store_path: Path | None = None,
    detectors_dir: Path | None = None,
) -> tuple[str, Path]:
    """Create detector directory from hypothesis. Returns (detector_id, path)."""
    from stain.registry import DETECTORS_DIR

    if detectors_dir is None:
        detectors_dir = DETECTORS_DIR
    if store is None:
        store = load_hypothesis_store(store_path)

    if not VALID_PATTERN_NAME.match(pattern_name):
        raise DiscoveryError(f"Invalid pattern name: {pattern_name!r}. Must match [a-z][a-z0-9_]{{1,60}}.")
    if pattern_name not in store.hypotheses:
        raise DiscoveryError(f"Hypothesis not found: {pattern_name}")

    hyp = store.hypotheses[pattern_name]

    # Find next detector ID by scanning directory names
    existing_ids = []
    for d in detectors_dir.iterdir():
        if d.is_dir() and d.name[0] == "D" and "_" in d.name:
            try:
                existing_ids.append(int(d.name.split("_")[0][1:]))
            except ValueError:
                continue
    next_num = max(existing_ids, default=0) + 1
    next_id = f"D{next_num}"

    # Create directory
    dir_name = f"{next_id}_{pattern_name}"
    detector_dir = detectors_dir / dir_name
    detector_dir.mkdir(parents=True)

    # detector.yaml
    name = pattern_name.replace("_", " ").title()
    yaml_content = {
        "id": next_id,
        "name": name,
        "version": "0.1.0",
        "weight": 1.0,
        "enabled": False,
        "description": hyp.description,
        "patterns": [
            {"name": pattern_name, "description": hyp.description}
        ],
    }
    (detector_dir / "detector.yaml").write_text(
        yaml.dump(yaml_content, default_flow_style=False, sort_keys=False)
    )

    # prompt.md
    prompt_text = PROMPT_TEMPLATE.format(
        name=name,
        pattern_name=pattern_name,
        description=hyp.description,
    )
    (detector_dir / "prompt.md").write_text(prompt_text)

    # CHANGELOG + version
    (detector_dir / "CHANGELOG.md").write_text(
        f"# {next_id} Changelog\n\n## v0.1.0\n- Scaffolded from discovery hypothesis\n"
    )
    versions_dir = detector_dir / "versions"
    versions_dir.mkdir()
    (versions_dir / "v0.1.0.md").write_text(
        f"# v0.1.0\nScaffolded from discovery hypothesis: {pattern_name}\n"
    )

    # Update hypothesis status
    hyp.status = "approved"
    save_hypothesis_store(store, store_path)

    return next_id, detector_dir


def promote_detector(detector_id: str, detectors_dir: Path | None = None) -> None:
    """Enable a detector by setting enabled: true."""
    from stain.registry import DETECTORS_DIR, clear_cache

    if detectors_dir is None:
        detectors_dir = DETECTORS_DIR

    matches = [d for d in detectors_dir.iterdir() if d.is_dir() and d.name.startswith(f"{detector_id}_")]
    if not matches:
        raise DiscoveryError(f"Detector directory not found for {detector_id}")
    if len(matches) > 1:
        names = [m.name for m in matches]
        raise DiscoveryError(f"Ambiguous: multiple directories match {detector_id}: {names}")

    yaml_path = matches[0] / "detector.yaml"
    raw = yaml.safe_load(yaml_path.read_text())
    raw["enabled"] = True
    yaml_path.write_text(yaml.dump(raw, default_flow_style=False, sort_keys=False))

    clear_cache()


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
