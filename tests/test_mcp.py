"""Tests for MCP server tool definitions."""

import json
import pytest
from unittest.mock import patch, MagicMock

from stain.mcp_server import get_tool_definitions, handle_tool_call


class TestToolDefinitions:
    def test_lists_tools(self):
        tools = get_tool_definitions()
        names = [t["name"] for t in tools]
        assert "analyse_text" in names
        assert "list_detectors" in names
        assert "get_detector_info" in names

    def test_analyse_text_has_schema(self):
        tools = get_tool_definitions()
        analyse = next(t for t in tools if t["name"] == "analyse_text")
        assert "text" in analyse["inputSchema"]["properties"]


class TestHandleToolCall:
    def test_analyse_text(self):
        from stain.models import CompositeResult, DetectorResult, Meta, Verdict
        mock_result = CompositeResult(
            stain_version="0.1.0",
            input_hash="sha256:test",
            input_length_chars=100,
            composite_score=0.65,
            detector_results=[
                DetectorResult(
                    detector_id="D1", detector_name="Test", version="0.1.0",
                    prompt_hash="sha256:t",
                    verdict=Verdict(score=0.65, confidence=0.8, summary="Test"),
                    meta=Meta(model="t/m", latency_ms=100, tokens_in=100, tokens_out=100),
                ),
            ],
            merged_annotations=[],
            meta={"total_latency_ms": 100, "total_tokens_in": 100, "total_tokens_out": 100},
        )
        with patch("stain.mcp_server.analyse", return_value=mock_result):
            result = handle_tool_call("analyse_text", {"text": "Hello world"})
        parsed = json.loads(result)
        assert parsed["composite_score"] == 0.65

    def test_list_detectors(self):
        result = handle_tool_call("list_detectors", {})
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert any(d["id"] == "D1" for d in parsed)

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            handle_tool_call("nonexistent_tool", {})
