"""Tests for research pipeline — papers, Arcana client, extraction, merge."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

from stain.research import (
    Paper,
    PaperIndex,
    ResearchError,
    load_paper_index,
    save_paper_index,
    fetch_papers_from_arcana,
    extract_hypotheses_from_paper,
    _load_research_prompt,
    research_fetch,
    research_extract,
    research_update,
    load_research_config,
)


class TestPaper:
    def test_create_paper(self):
        p = Paper(
            paper_id="job_abc123",
            title="Detecting LLM Text via Stylometry",
            source="arcana",
            text="Full extracted text of the paper...",
        )
        assert p.paper_id == "job_abc123"
        assert p.source == "arcana"
        assert p.extracted is False

    def test_paper_with_metadata(self):
        p = Paper(
            paper_id="job_xyz",
            title="AI Writing Patterns",
            source="arcana",
            text="Paper text content",
            doc_type="pdf",
            filename="paper.pdf",
        )
        assert p.doc_type == "pdf"
        assert p.filename == "paper.pdf"


class TestPaperIndex:
    def test_empty_index(self):
        idx = PaperIndex()
        assert len(idx.papers) == 0

    def test_add_paper(self):
        idx = PaperIndex()
        p = Paper(paper_id="j1", title="Test", source="arcana", text="content")
        idx.papers["j1"] = p
        assert "j1" in idx.papers

    def test_save_and_load(self, tmp_path):
        idx = PaperIndex()
        idx.papers["j1"] = Paper(
            paper_id="j1", title="Test Paper", source="arcana", text="content",
        )
        path = tmp_path / "index.yaml"
        save_paper_index(idx, path)
        loaded = load_paper_index(path)
        assert "j1" in loaded.papers
        assert loaded.papers["j1"].title == "Test Paper"

    def test_load_missing_returns_empty(self, tmp_path):
        idx = load_paper_index(tmp_path / "nonexistent.yaml")
        assert len(idx.papers) == 0


class TestFetchFromArcana:
    def test_fetch_papers(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "job_001", "filename": "paper1.pdf", "status": "complete", "doc_type": "pdf"},
            {"id": "job_002", "filename": "paper2.pdf", "status": "complete", "doc_type": "pdf"},
        ]

        mock_detail1 = MagicMock()
        mock_detail1.status_code = 200
        mock_detail1.json.return_value = {
            "id": "job_001", "filename": "paper1.pdf", "status": "complete",
            "report": {"answer": "Extracted text from paper 1 about LLM detection patterns."},
        }

        mock_detail2 = MagicMock()
        mock_detail2.status_code = 200
        mock_detail2.json.return_value = {
            "id": "job_002", "filename": "paper2.pdf", "status": "complete",
            "report": {"answer": "Extracted text from paper 2 about stylometry."},
        }

        with patch("stain.research.httpx.get") as mock_get:
            mock_get.side_effect = [mock_response, mock_detail1, mock_detail2]
            papers = fetch_papers_from_arcana("http://localhost:8000")
        assert len(papers) == 2
        assert papers[0].paper_id == "job_001"
        assert "LLM detection" in papers[0].text

    def test_fetch_skips_incomplete_jobs(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "job_001", "filename": "p.pdf", "status": "processing", "doc_type": "pdf"},
            {"id": "job_002", "filename": "q.pdf", "status": "complete", "doc_type": "pdf"},
        ]

        mock_detail = MagicMock()
        mock_detail.status_code = 200
        mock_detail.json.return_value = {
            "id": "job_002", "filename": "q.pdf", "status": "complete",
            "report": {"answer": "Paper content here."},
        }

        with patch("stain.research.httpx.get") as mock_get:
            mock_get.side_effect = [mock_response, mock_detail]
            papers = fetch_papers_from_arcana("http://localhost:8000")
        assert len(papers) == 1

    def test_fetch_connection_error_raises(self):
        with patch("stain.research.httpx.get", side_effect=Exception("Connection refused")):
            with pytest.raises(ResearchError, match="connect"):
                fetch_papers_from_arcana("http://localhost:9999")

    def test_fetch_rejects_path_traversal_id(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "../../../etc/passwd", "filename": "evil.pdf", "status": "complete", "doc_type": "pdf"},
            {"id": "safe_job_01", "filename": "good.pdf", "status": "complete", "doc_type": "pdf"},
        ]
        mock_detail = MagicMock()
        mock_detail.status_code = 200
        mock_detail.json.return_value = {
            "id": "safe_job_01", "filename": "good.pdf", "status": "complete",
            "report": {"answer": "Safe paper content."},
        }
        with patch("stain.research.httpx.get") as mock_get:
            mock_get.side_effect = [mock_response, mock_detail]
            papers = fetch_papers_from_arcana("http://localhost:8000")
        assert len(papers) == 1
        assert papers[0].paper_id == "safe_job_01"


class TestLoadResearchPrompt:
    def test_load_prompt(self):
        prompt = _load_research_prompt()
        assert "Research Extraction" in prompt
        assert "hypotheses" in prompt

    def test_missing_prompt_raises(self):
        with patch("stain.research.AGENTS_DIR", Path("/nonexistent")):
            with pytest.raises(ResearchError, match="not found"):
                _load_research_prompt()


class TestExtractHypotheses:
    def test_extract_returns_hypotheses(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "hypotheses": [{
                "pattern_name": "syntactic_entropy",
                "description": "LLMs produce lower syntactic entropy than humans",
                "examples_found": ["The paper demonstrates..."],
                "confidence": 0.8,
                "suggested_detector": "New detector",
            }]
        })

        paper = Paper(paper_id="j1", title="Test", source="arcana", text="Paper about LLM detection...")

        with patch("stain.research.litellm.completion", return_value=mock_response):
            hypotheses = extract_hypotheses_from_paper(paper, model="test/model")
        assert len(hypotheses) == 1
        assert hypotheses[0]["pattern_name"] == "syntactic_entropy"

    def test_extract_empty_paper(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"hypotheses": []}'

        paper = Paper(paper_id="j2", title="Unrelated", source="arcana", text="Not about LLM detection")

        with patch("stain.research.litellm.completion", return_value=mock_response):
            hypotheses = extract_hypotheses_from_paper(paper, model="test/model")
        assert hypotheses == []


class TestLoadResearchConfig:
    def test_load_config(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("arcana:\n  url: http://test:8000\nmodel: test/model\n")
        config = load_research_config(cfg_path)
        assert config["arcana"]["url"] == "http://test:8000"

    def test_load_missing_returns_defaults(self, tmp_path):
        config = load_research_config(tmp_path / "nonexistent.yaml")
        assert "arcana" in config
        assert config["arcana"]["url"] == "http://localhost:8000"


class TestResearchFetch:
    def test_fetch_saves_to_index(self, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "j1", "filename": "paper.pdf", "status": "complete", "doc_type": "pdf"},
        ]
        mock_detail = MagicMock()
        mock_detail.status_code = 200
        mock_detail.json.return_value = {
            "id": "j1", "filename": "paper.pdf", "status": "complete",
            "report": {"answer": "Paper content about LLM detection."},
        }

        with patch("stain.research.httpx.get") as mock_get:
            mock_get.side_effect = [mock_response, mock_detail]
            count = research_fetch(
                arcana_url="http://test:8000",
                research_dir=tmp_path,
            )
        assert count == 1
        idx = load_paper_index(tmp_path / "index.yaml")
        assert "j1" in idx.papers

    def test_fetch_skips_already_fetched(self, tmp_path):
        idx = PaperIndex()
        idx.papers["j1"] = Paper(paper_id="j1", title="Old", source="arcana", text="old content")
        save_paper_index(idx, tmp_path / "index.yaml")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "j1", "filename": "paper.pdf", "status": "complete", "doc_type": "pdf"},
        ]

        with patch("stain.research.httpx.get") as mock_get:
            mock_get.side_effect = [mock_response]
            count = research_fetch(arcana_url="http://test:8000", research_dir=tmp_path)
        assert count == 0


class TestResearchExtract:
    def test_extract_marks_papers(self, tmp_path):
        idx = PaperIndex()
        idx.papers["j1"] = Paper(paper_id="j1", title="Test", source="arcana", text="Paper about detection.")
        save_paper_index(idx, tmp_path / "index.yaml")

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = json.dumps({
            "hypotheses": [{"pattern_name": "test_hyp", "description": "d", "confidence": 0.6, "suggested_detector": "New"}]
        })

        with patch("stain.research.litellm.completion", return_value=mock_llm):
            new, total = research_extract(
                model="test/model",
                research_dir=tmp_path,
                discovery_dir=tmp_path / "disc",
            )
        assert new >= 0
        reloaded = load_paper_index(tmp_path / "index.yaml")
        assert reloaded.papers["j1"].extracted is True

    def test_extract_saves_extraction_json(self, tmp_path):
        idx = PaperIndex()
        idx.papers["j1"] = Paper(paper_id="j1", title="Test", source="arcana", text="Content.")
        save_paper_index(idx, tmp_path / "index.yaml")

        mock_llm = MagicMock()
        mock_llm.choices = [MagicMock()]
        mock_llm.choices[0].message.content = '{"hypotheses": []}'

        with patch("stain.research.litellm.completion", return_value=mock_llm):
            research_extract(model="test/model", research_dir=tmp_path, discovery_dir=tmp_path / "disc")
        extractions = list((tmp_path / "extractions").glob("*.json"))
        assert len(extractions) == 1
