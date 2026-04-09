"""Tests for bulk corpus generation — LLM samples and human scraping."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from stain.corpus import Manifest, SampleEntry, load_manifest, save_manifest
from stain.generate import generate_llm_samples, DOMAIN_PROMPTS, scrape_human_samples, AUTHOR_SOURCES


class TestGenerateLlmSamples:
    def _setup_tier(self, tmp_path):
        """Create a bulk tier with empty manifest."""
        tier_dir = tmp_path / "bulk"
        (tier_dir / "known_llm").mkdir(parents=True)
        save_manifest(Manifest(tier="bulk", samples=[]), tier_dir / "manifest.yaml")
        return tier_dir

    def test_generates_correct_count(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is generated LLM text for testing purposes."

        with patch("stain.generate.litellm.completion", return_value=mock_response):
            entries = generate_llm_samples(
                count=3,
                domains=["linkedin"],
                model="test/model",
                temperatures=[0.7],
                output_dir=tier_dir,
            )
        assert len(entries) == 3
        files = list((tier_dir / "known_llm").glob("*.txt"))
        assert len(files) == 3

    def test_manifest_updated(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated content for manifest testing."

        with patch("stain.generate.litellm.completion", return_value=mock_response):
            generate_llm_samples(
                count=2,
                domains=["blog"],
                model="test/model",
                temperatures=[0.7],
                output_dir=tier_dir,
            )
        m = load_manifest(tier_dir / "manifest.yaml")
        assert len(m.samples) == 2
        assert all(s.label == "llm" for s in m.samples)
        assert all(s.domain == "blog" for s in m.samples)

    def test_multiple_domains_distributed(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text for domain distribution testing."

        with patch("stain.generate.litellm.completion", return_value=mock_response):
            entries = generate_llm_samples(
                count=6,
                domains=["linkedin", "blog", "marketing"],
                model="test/model",
                temperatures=[0.7],
                output_dir=tier_dir,
            )
        domains = [e.domain for e in entries]
        assert "linkedin" in domains
        assert "blog" in domains
        assert "marketing" in domains

    def test_multiple_temperatures(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Content generated at various temperature settings."

        with patch("stain.generate.litellm.completion", return_value=mock_response):
            entries = generate_llm_samples(
                count=4,
                domains=["linkedin"],
                model="test/model",
                temperatures=[0.3, 0.7],
                output_dir=tier_dir,
            )
        temps = [e.temperature for e in entries]
        assert 0.3 in temps
        assert 0.7 in temps

    def test_domain_prompts_defined(self):
        assert "linkedin" in DOMAIN_PROMPTS
        assert "blog" in DOMAIN_PROMPTS
        assert "marketing" in DOMAIN_PROMPTS


class TestScrapeHumanSamples:
    def _setup_tier(self, tmp_path):
        tier_dir = tmp_path / "gold"
        (tier_dir / "known_human").mkdir(parents=True)
        save_manifest(Manifest(tier="gold", samples=[]), tier_dir / "manifest.yaml")
        return tier_dir

    def test_scrape_from_urls(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)

        with patch("stain.generate.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Real human blog post content here.</body></html>"
            mock_traf.extract.return_value = "Real human blog post content here."
            entries = scrape_human_samples(
                urls=["https://example.com/post1", "https://example.com/post2"],
                output_dir=tier_dir,
                source="example.com",
                domain="blog",
            )
        assert len(entries) == 2
        files = list((tier_dir / "known_human").glob("*.txt"))
        assert len(files) == 2

    def test_manifest_updated_after_scrape(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)

        with patch("stain.generate.trafilatura") as mock_traf:
            mock_traf.fetch_url.return_value = "<html><body>Blog content.</body></html>"
            mock_traf.extract.return_value = "Blog content for manifest update testing."
            scrape_human_samples(
                urls=["https://example.com/post1"],
                output_dir=tier_dir,
                source="example.com",
                domain="blog",
            )
        m = load_manifest(tier_dir / "manifest.yaml")
        assert len(m.samples) == 1
        assert m.samples[0].label == "human"

    def test_failed_fetch_skipped(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)

        with patch("stain.generate.trafilatura") as mock_traf:
            mock_traf.fetch_url.side_effect = [None, "<html><body>Good post.</body></html>"]
            mock_traf.extract.return_value = "Good post content for testing."
            entries = scrape_human_samples(
                urls=["https://example.com/fail", "https://example.com/ok"],
                output_dir=tier_dir,
                source="example.com",
                domain="blog",
            )
        assert len(entries) == 1

    def test_wayback_fallback(self, tmp_path):
        tier_dir = self._setup_tier(tmp_path)

        with patch("stain.generate.trafilatura") as mock_traf:
            mock_traf.fetch_url.side_effect = [None, "<html><body>Archived content.</body></html>"]
            mock_traf.extract.return_value = "Archived content from the Wayback Machine."
            entries = scrape_human_samples(
                urls=["https://example.com/old-post"],
                output_dir=tier_dir,
                source="example.com",
                domain="blog",
                wayback_fallback=True,
            )
        assert len(entries) == 1
        calls = mock_traf.fetch_url.call_args_list
        assert any("web.archive.org" in str(c) for c in calls)

    def test_author_sources_defined(self):
        assert "sivers" in AUTHOR_SOURCES
        assert "pg" in AUTHOR_SOURCES
