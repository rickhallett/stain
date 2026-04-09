"""Tests for audit logging."""

import json
import tempfile
from pathlib import Path

import pytest

from stain.audit import AuditLogger, AuditEntry


class TestAuditEntry:
    def test_create_entry(self):
        entry = AuditEntry(
            operation="detector_call",
            detector_id="D1",
            model="test/model",
            prompt_hash="sha256:abc123",
            prompt_version="0.1.0",
            input_hash="sha256:def456",
            input_length_chars=100,
            response_hash="sha256:ghi789",
            parsed_score=0.72,
            annotations_count=5,
            annotations_valid=4,
            annotations_invalid=1,
            latency_ms=890,
            tokens_in=512,
            tokens_out=340,
        )
        assert entry.operation == "detector_call"
        assert entry.parsed_score == 0.72

    def test_to_json_roundtrip(self):
        entry = AuditEntry(
            operation="detector_call",
            detector_id="D1",
            model="test/model",
            prompt_hash="sha256:abc",
            prompt_version="0.1.0",
            input_hash="sha256:def",
            input_length_chars=50,
        )
        line = entry.to_json()
        parsed = json.loads(line)
        assert parsed["operation"] == "detector_call"
        assert parsed["detector_id"] == "D1"
        assert "timestamp" in parsed


class TestAuditLogger:
    def test_log_creates_file(self, tmp_path):
        logger = AuditLogger(base_dir=tmp_path)
        entry = AuditEntry(
            operation="test_op",
            model="test/model",
            prompt_hash="sha256:abc",
            input_hash="sha256:def",
            input_length_chars=10,
        )
        logger.log(entry)

        date_dirs = list(tmp_path.iterdir())
        assert len(date_dirs) == 1
        jsonl_files = list(date_dirs[0].glob("*.jsonl"))
        assert len(jsonl_files) >= 1

    def test_log_appends(self, tmp_path):
        logger = AuditLogger(base_dir=tmp_path)
        for i in range(3):
            entry = AuditEntry(
                operation=f"op_{i}",
                model="test/model",
                prompt_hash="sha256:abc",
                input_hash="sha256:def",
                input_length_chars=10,
            )
            logger.log(entry)

        date_dirs = list(tmp_path.iterdir())
        jsonl_files = list(date_dirs[0].glob("*.jsonl"))
        lines = jsonl_files[0].read_text().strip().split("\n")
        assert len(lines) == 3

    def test_disabled_logger_noops(self, tmp_path):
        logger = AuditLogger(base_dir=tmp_path, enabled=False)
        entry = AuditEntry(
            operation="test_op",
            model="test/model",
            prompt_hash="sha256:abc",
            input_hash="sha256:def",
            input_length_chars=10,
        )
        logger.log(entry)

        date_dirs = list(tmp_path.iterdir())
        assert len(date_dirs) == 0
