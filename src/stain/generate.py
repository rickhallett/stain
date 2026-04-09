"""Bulk corpus generation — LLM text samples and human blog scraping."""

from __future__ import annotations

import itertools
import logging
import uuid
from pathlib import Path

import litellm
import trafilatura

from stain.corpus import Manifest, SampleEntry, load_manifest, save_manifest


logger = logging.getLogger(__name__)


DOMAIN_PROMPTS = {
    "linkedin": (
        "Write a LinkedIn post (200-400 words) about professional growth, "
        "career transitions, or workplace insights. Write in first person as "
        "a mid-career professional. Include a personal anecdote."
    ),
    "blog": (
        "Write a blog post (300-500 words) about technology, productivity, "
        "or personal development. Write in a conversational tone with a clear "
        "thesis and supporting points."
    ),
    "marketing": (
        "Write marketing copy (200-400 words) for a SaaS product. Include "
        "value propositions, social proof language, and a call to action. "
        "Write in second person addressing the reader directly."
    ),
    "thought": (
        "Write a thought leadership piece (300-500 words) about trends in "
        "AI, remote work, or digital transformation. Take a contrarian or "
        "nuanced position. Use data references and industry terminology."
    ),
    "essay": (
        "Write a personal essay (300-500 words) reflecting on a life "
        "experience, a lesson learned, or a philosophical observation. "
        "Write in first person with emotional honesty."
    ),
}


def generate_llm_samples(
    count: int,
    domains: list[str],
    model: str,
    temperatures: list[float],
    output_dir: Path,
) -> list[SampleEntry]:
    """Generate LLM text samples with varied parameters.

    Distributes samples across domains and temperatures round-robin style.
    Saves files to output_dir/known_llm/ and updates the manifest.
    """
    llm_dir = output_dir / "known_llm"
    llm_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.yaml"
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
    else:
        manifest = Manifest(tier=output_dir.name)

    combos = list(itertools.product(domains, temperatures))
    entries: list[SampleEntry] = []

    for i in range(count):
        domain, temp = combos[i % len(combos)]
        prompt = DOMAIN_PROMPTS.get(domain, DOMAIN_PROMPTS["blog"])

        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp,
            max_tokens=1024,
        )
        text = response.choices[0].message.content

        short_id = uuid.uuid4().hex[:8]
        filename = f"llm_{domain}_{short_id}.txt"
        filepath = llm_dir / filename
        filepath.write_text(text)

        entry = SampleEntry(
            id=filepath.stem,
            label="llm",
            source="generated",
            domain=domain,
            file=f"known_llm/{filename}",
            model=model,
            temperature=temp,
        )
        entries.append(entry)
        manifest.samples.append(entry)
        save_manifest(manifest, manifest_path)

    return entries


AUTHOR_SOURCES = {
    "sivers": [
        "https://sive.rs/obvious",
        "https://sive.rs/hellyeah",
        "https://sive.rs/nospeedlimit",
        "https://sive.rs/expire",
        "https://sive.rs/local",
    ],
    "pg": [
        "http://paulgraham.com/mean.html",
        "http://paulgraham.com/ds.html",
        "http://paulgraham.com/startupideas.html",
    ],
    "godin": [
        "https://seths.blog/2012/06/organized-bravery/",
        "https://seths.blog/2010/01/quieting-the-lizard-brain/",
    ],
    "jclear": [
        "https://jamesclear.com/marginal-gains",
        "https://jamesclear.com/habit-stacking",
    ],
}

WAYBACK_PREFIX = "https://web.archive.org/web/2019/"


def scrape_human_samples(
    urls: list[str],
    output_dir: Path,
    source: str,
    domain: str,
    wayback_fallback: bool = False,
) -> list[SampleEntry]:
    """Scrape human-written text from URLs.

    Uses trafilatura for HTML-to-text extraction. If wayback_fallback
    is True, retries failed URLs through the Internet Archive.
    """
    human_dir = output_dir / "known_human"
    human_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.yaml"
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
    else:
        manifest = Manifest(tier=output_dir.name)

    entries: list[SampleEntry] = []

    for url in urls:
        text = _fetch_and_extract(url)

        if text is None and wayback_fallback:
            wayback_url = WAYBACK_PREFIX + url
            text = _fetch_and_extract(wayback_url)

        if text is None:
            logger.warning(f"Failed to extract text from: {url}")
            continue

        short_id = uuid.uuid4().hex[:8]
        slug = url.split("/")[-1].split(".")[0] or short_id
        slug = slug[:40]
        filename = f"human_{slug}_{short_id}.txt"
        filepath = human_dir / filename

        header = f"# Source: {url} | Domain: {domain}\n\n"
        filepath.write_text(header + text)

        entry = SampleEntry(
            id=filepath.stem,
            label="human",
            source=source,
            domain=domain,
            file=f"known_human/{filename}",
        )
        entries.append(entry)
        manifest.samples.append(entry)
        save_manifest(manifest, manifest_path)

    return entries


def _fetch_and_extract(url: str) -> str | None:
    """Fetch URL and extract text. Returns None on failure."""
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        return None
    text = trafilatura.extract(downloaded)
    if not text or not text.strip():
        return None
    return text
