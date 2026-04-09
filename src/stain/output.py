"""Output formatting — JSON, plain, score modes + TTY auto-detection."""

from __future__ import annotations

import json
import sys
from enum import Enum

from stain.models import CompositeResult


class OutputMode(str, Enum):
    RICH = "rich"
    JSON = "json"
    PLAIN = "plain"
    SCORE = "score"


def detect_mode(
    json_flag: bool = False,
    plain_flag: bool = False,
    score_flag: bool = False,
) -> OutputMode:
    """Determine output mode from flags or TTY auto-detection.

    Explicit flags take priority. When no flag is set:
    TTY -> rich, piped -> JSON.
    """
    if json_flag:
        return OutputMode.JSON
    if plain_flag:
        return OutputMode.PLAIN
    if score_flag:
        return OutputMode.SCORE
    if sys.stdout.isatty():
        return OutputMode.RICH
    return OutputMode.JSON


def format_json(result: CompositeResult) -> str:
    """Full JSON dump of the composite result."""
    return json.dumps(result.model_dump(), indent=2)


def format_plain(result: CompositeResult) -> str:
    """One-liner: composite score + per-detector scores."""
    parts = [f"score={result.composite_score:.3f}"]
    for dr in result.detector_results:
        parts.append(f"{dr.detector_id}={dr.verdict.score:.2f}")
    return " | ".join(parts)


def format_score(result: CompositeResult) -> str:
    """Score only — for scripting."""
    return f"{result.composite_score:.3f}"
