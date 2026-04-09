"""Research pipeline — paper ingestion from Arcana, hypothesis extraction, merge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import re

import httpx
import litellm
import yaml

from stain.discovery import (
    HypothesisStore,
    load_hypothesis_store,
    save_hypothesis_store,
    VALID_PATTERN_NAME,
)
from stain.detector import _extract_json


logger = logging.getLogger(__name__)

RESEARCH_DIR = Path("research")
AGENTS_DIR = Path("agents")

# Paper IDs must be safe for filesystem use
VALID_PAPER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class ResearchError(Exception):
    """Research pipeline error."""
    pass


@dataclass
class Paper:
    paper_id: str
    title: str
    source: str
    text: str
    extracted: bool = False
    doc_type: str = ""
    filename: str = ""
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()


@dataclass
class PaperIndex:
    papers: dict[str, Paper] = field(default_factory=dict)


def save_paper_index(index: PaperIndex, path: Path | None = None) -> None:
    """Save paper index to YAML."""
    if path is None:
        path = RESEARCH_DIR / "index.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "papers": {
            pid: {k: v for k, v in asdict(p).items()} for pid, p in index.papers.items()
        }
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def load_paper_index(path: Path | None = None) -> PaperIndex:
    """Load paper index from YAML. Returns empty index if not found."""
    if path is None:
        path = RESEARCH_DIR / "index.yaml"
    if not path.is_file():
        return PaperIndex()
    raw = yaml.safe_load(path.read_text())
    if not raw or "papers" not in raw:
        return PaperIndex()
    index = PaperIndex()
    for pid, data in raw["papers"].items():
        index.papers[pid] = Paper(**data)
    return index


def fetch_papers_from_arcana(
    arcana_url: str,
    existing_ids: set[str] | None = None,
) -> list[Paper]:
    """Fetch processed papers from Arcana's API."""
    if existing_ids is None:
        existing_ids = set()

    try:
        resp = httpx.get(f"{arcana_url}/api/jobs", timeout=30)
    except Exception as e:
        raise ResearchError(f"Failed to connect to Arcana at {arcana_url}: {e}") from e

    if resp.status_code != 200:
        raise ResearchError(f"Arcana returned status {resp.status_code}")

    jobs = resp.json()
    papers = []

    for job in jobs:
        job_id = job.get("id", "")
        status = job.get("status", "")

        if status != "complete":
            continue
        if job_id in existing_ids:
            continue
        if not VALID_PAPER_ID.match(job_id):
            logger.warning(f"Skipping job with unsafe ID: {job_id!r}")
            continue

        try:
            detail_resp = httpx.get(f"{arcana_url}/api/jobs/{job_id}", timeout=30)
        except Exception:
            logger.warning(f"Failed to fetch detail for job {job_id}")
            continue

        if detail_resp.status_code != 200:
            continue

        detail = detail_resp.json()
        report = detail.get("report") or {}
        text = report.get("answer", "")

        if not text:
            continue

        paper = Paper(
            paper_id=job_id,
            title=detail.get("filename", job_id),
            source="arcana",
            text=text,
            doc_type=job.get("doc_type", ""),
            filename=job.get("filename", ""),
        )
        papers.append(paper)

    return papers


def _load_research_prompt() -> str:
    """Load the research extraction agent system prompt."""
    path = AGENTS_DIR / "research_extract" / "prompt.md"
    if not path.is_file():
        raise ResearchError(f"Research extraction prompt not found: {path}")
    return path.read_text()


def extract_hypotheses_from_paper(
    paper: Paper,
    model: str,
) -> list[dict]:
    """Run extraction agent against a paper. Returns raw hypotheses."""
    prompt = _load_research_prompt()

    user_message = (
        f"## Paper: {paper.title}\n\n"
        f"Source: {paper.source} ({paper.paper_id})\n\n"
        f"---\n\n{paper.text}"
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


DEFAULT_RESEARCH_CONFIG = {
    "arcana": {"url": "http://localhost:8000"},
    "model": "anthropic/claude-sonnet-4-5-20250514",
    "search_terms": [],
}


def load_research_config(path: Path | None = None) -> dict:
    """Load research config. Returns defaults if not found."""
    if path is None:
        path = RESEARCH_DIR / "config.yaml"
    if not path.is_file():
        return DEFAULT_RESEARCH_CONFIG.copy()
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        return DEFAULT_RESEARCH_CONFIG.copy()
    config = DEFAULT_RESEARCH_CONFIG.copy()
    config.update(raw)
    return config


def research_fetch(
    arcana_url: str,
    research_dir: Path | None = None,
) -> int:
    """Fetch new papers from Arcana. Returns count of new papers."""
    if research_dir is None:
        research_dir = RESEARCH_DIR

    index = load_paper_index(research_dir / "index.yaml")
    existing_ids = set(index.papers.keys())

    papers = fetch_papers_from_arcana(arcana_url, existing_ids=existing_ids)

    for paper in papers:
        index.papers[paper.paper_id] = paper
        papers_dir = research_dir / "papers"
        papers_dir.mkdir(parents=True, exist_ok=True)
        paper_file = papers_dir / f"{paper.paper_id}.json"
        paper_file.write_text(json.dumps(asdict(paper), indent=2))

    save_paper_index(index, research_dir / "index.yaml")
    return len(papers)


def research_extract(
    model: str,
    research_dir: Path | None = None,
    discovery_dir: Path | None = None,
) -> tuple[int, int]:
    """Run extraction on unprocessed papers. Returns (new_hypotheses, total_papers)."""
    if research_dir is None:
        research_dir = RESEARCH_DIR
    if discovery_dir is None:
        from stain.discovery import DISCOVERY_DIR
        discovery_dir = DISCOVERY_DIR

    index = load_paper_index(research_dir / "index.yaml")
    unprocessed = [p for p in index.papers.values() if not p.extracted]

    extractions_dir = research_dir / "extractions"
    extractions_dir.mkdir(parents=True, exist_ok=True)

    store = load_hypothesis_store(discovery_dir / "hypotheses.yaml")
    total_new = 0

    processed = 0
    for paper in unprocessed:
        try:
            raw_hypotheses = extract_hypotheses_from_paper(paper, model=model)
        except Exception as e:
            logger.warning(f"Extraction failed for {paper.paper_id}: {e}")
            continue

        extraction_file = extractions_dir / f"{paper.paper_id}.json"
        extraction_file.write_text(json.dumps({
            "paper_id": paper.paper_id,
            "title": paper.title,
            "model": model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypotheses": raw_hypotheses,
        }, indent=2))

        new, _ = store.merge(raw_hypotheses, f"research:{paper.paper_id}")
        total_new += new

        paper.extracted = True
        processed += 1

        # Save incrementally — hypotheses first (the valuable data),
        # then index (marking extracted). If we crash between the two,
        # worst case is re-extracting a paper, not losing hypotheses.
        save_hypothesis_store(store, discovery_dir / "hypotheses.yaml")
        save_paper_index(index, research_dir / "index.yaml")

    return total_new, processed


def research_update(
    research_dir: Path | None = None,
    discovery_dir: Path | None = None,
) -> dict:
    """Full pipeline: fetch -> extract -> return stats."""
    if research_dir is None:
        research_dir = RESEARCH_DIR

    config = load_research_config(research_dir / "config.yaml")
    arcana_url = config.get("arcana", {}).get("url", "http://localhost:8000")
    model = config.get("model", "anthropic/claude-sonnet-4-5-20250514")

    fetched = research_fetch(arcana_url, research_dir=research_dir)
    new_hyp, extracted = research_extract(
        model=model, research_dir=research_dir, discovery_dir=discovery_dir,
    )

    return {"fetched": fetched, "extracted": extracted, "new_hypotheses": new_hyp}
