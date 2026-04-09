"""Research pipeline — paper ingestion from Arcana, hypothesis extraction, merge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
