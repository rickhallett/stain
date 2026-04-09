"""Tests for bulk corpus generation — LLM samples and human scraping."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from stain.corpus import Manifest, SampleEntry, load_manifest, save_manifest
from stain.generate import generate_llm_samples, DOMAIN_PROMPTS


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
