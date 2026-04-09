"""Audit logging — immutable record of every LLM interaction."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_DIR = Path(".stain/audit")


@dataclass
class AuditEntry:
    operation: str
    model: str
    prompt_hash: str
    input_hash: str
    input_length_chars: int
    timestamp: str = ""
    detector_id: str | None = None
    prompt_version: str | None = None
    response_hash: str | None = None
    parsed_score: float | None = None
    annotations_count: int = 0
    annotations_valid: int = 0
    annotations_invalid: int = 0
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model_response_id: str | None = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data, default=str)


class AuditLogger:
    """Append-only audit logger. Writes JSONL files organized by date."""

    def __init__(
        self,
        base_dir: Path = DEFAULT_AUDIT_DIR,
        enabled: bool = True,
        session_id: str | None = None,
    ):
        self.base_dir = base_dir
        self.enabled = enabled
        import uuid
        self._session_id = session_id or uuid.uuid4().hex[:12]
        self._file_handle = None
        self._current_date: str | None = None

    def log(self, entry: AuditEntry) -> None:
        if not self.enabled:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        date_dir = self.base_dir / today
        date_dir.mkdir(parents=True, exist_ok=True)

        log_file = date_dir / f"{self._session_id}.jsonl"
        with open(log_file, "a") as f:
            f.write(entry.to_json() + "\n")

    def close(self) -> None:
        pass


def hash_content(content: str) -> str:
    """SHA256 hash for audit trail content addressing."""
    return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
