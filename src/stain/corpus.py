"""Corpus management — manifest model, I/O, stats, validation, labeling."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Any
import shutil

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


TIER_NAMES = ["gold", "bulk"]


def corpus_stats(corpus_dir: Path) -> dict:
    """Return sample counts per tier and label."""
    result: dict[str, Any] = {}
    grand_total = 0

    for tier_name in TIER_NAMES:
        tier_path = corpus_dir / tier_name
        manifest_path = tier_path / "manifest.yaml"
        if not manifest_path.is_file():
            continue

        manifest = load_manifest(manifest_path)
        human = sum(1 for s in manifest.samples if s.label == "human")
        llm = sum(1 for s in manifest.samples if s.label == "llm")
        total = human + llm
        result[tier_name] = {"human": human, "llm": llm, "total": total}
        grand_total += total

    ambiguous_dir = corpus_dir / "ambiguous"
    if ambiguous_dir.is_dir():
        ambig_count = len(list(ambiguous_dir.glob("*.txt")))
        result["ambiguous"] = {"total": ambig_count}
        grand_total += ambig_count

    result["total"] = grand_total
    return result


def corpus_validate(corpus_dir: Path) -> list[str]:
    """Validate corpus integrity. Returns list of issue descriptions."""
    issues: list[str] = []

    for tier_name in TIER_NAMES:
        tier_path = corpus_dir / tier_name
        manifest_path = tier_path / "manifest.yaml"
        if not manifest_path.is_file():
            continue

        manifest = load_manifest(manifest_path)

        # Check for duplicate IDs
        seen_ids: dict[str, int] = {}
        for s in manifest.samples:
            seen_ids[s.id] = seen_ids.get(s.id, 0) + 1
        for sid, count in seen_ids.items():
            if count > 1:
                issues.append(f"[{tier_name}] Duplicate ID: {sid} ({count} entries)")

        # Check manifest entries have files
        manifest_files: set[str] = set()
        for s in manifest.samples:
            manifest_files.add(s.file)
            full_path = tier_path / s.file
            if not full_path.is_file():
                issues.append(f"[{tier_name}] Missing file: {s.file} (ID: {s.id})")

        # Check for orphan files
        for subdir in ["known_human", "known_llm"]:
            dir_path = tier_path / subdir
            if not dir_path.is_dir():
                continue
            for f in sorted(dir_path.glob("*.txt")):
                rel = f"{subdir}/{f.name}"
                if rel not in manifest_files:
                    issues.append(f"[{tier_name}] Orphan file not in manifest: {rel}")

    return issues


def corpus_label(
    corpus_dir: Path,
    file_path: Path,
    label: str,
    tier: str,
    source: str,
    domain: str,
) -> SampleEntry:
    """Move a file to a tier with a label.

    Args:
        corpus_dir: Root corpus directory.
        file_path: Path to the file to label.
        label: "human" or "llm".
        tier: Target tier ("gold" or "bulk").
        source: Origin of the content.
        domain: Content domain (blog, linkedin, etc.).

    Returns:
        The new SampleEntry added to the manifest.
    """
    if not file_path.is_file():
        raise CorpusError(f"File not found: {file_path}")
    if label not in ("human", "llm"):
        raise CorpusError(f"Invalid label: {label}. Must be 'human' or 'llm'.")
    if tier not in TIER_NAMES:
        raise CorpusError(f"Invalid tier: {tier}. Must be one of {TIER_NAMES}.")

    label_dir = "known_human" if label == "human" else "known_llm"
    target_dir = corpus_dir / tier / label_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_path.name

    shutil.move(str(file_path), str(target_path))

    entry = SampleEntry(
        id=file_path.stem,
        label=label,
        source=source,
        domain=domain,
        file=f"{label_dir}/{file_path.name}",
    )

    manifest_path = corpus_dir / tier / "manifest.yaml"
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
    else:
        manifest = Manifest(tier=tier)
    manifest.samples.append(entry)
    save_manifest(manifest, manifest_path)

    return entry
