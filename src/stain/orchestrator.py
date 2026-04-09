"""Orchestrator — dispatches detectors and aggregates results."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stain import __version__
from stain.audit import AuditLogger
from stain.config import get_detector_weight, get_enabled_detectors, load_config
from stain.detector import DEFAULT_MODEL, run_detector
from stain.models import (
    CompositeResult,
    DetectorResult,
    MergedAnnotation,
    Severity,
)


SEVERITY_ORDER = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _merge_annotations(results: list[DetectorResult]) -> list[MergedAnnotation]:
    """Merge overlapping annotation spans across detectors."""
    # Collect all annotations with their detector source
    all_annots: list[tuple[str, Any]] = []
    for result in results:
        for annot in result.verdict.annotations:
            all_annots.append((result.detector_id, annot))

    if not all_annots:
        return []

    # Sort by span_start
    all_annots.sort(key=lambda x: (x[1].span_start, x[1].span_end))

    merged: list[MergedAnnotation] = []
    for detector_id, annot in all_annots:
        # Check if this overlaps with the last merged annotation
        if merged and annot.span_start < merged[-1].span_end:
            last = merged[-1]
            # Extend the span
            last.span_end = max(last.span_end, annot.span_end)
            if detector_id not in last.detectors:
                last.detectors.append(detector_id)
            last.explanations[detector_id] = annot.explanation
            if SEVERITY_ORDER[annot.severity] > SEVERITY_ORDER[last.max_severity]:
                last.max_severity = annot.severity
        else:
            merged.append(
                MergedAnnotation(
                    span_start=annot.span_start,
                    span_end=annot.span_end,
                    detectors=[detector_id],
                    max_severity=annot.severity,
                    explanations={detector_id: annot.explanation},
                )
            )

    return merged


def _make_audit_logger(config: dict[str, Any]) -> AuditLogger:
    """Create an AuditLogger from config settings."""
    audit_cfg = config.get("audit", {})
    return AuditLogger(
        base_dir=Path(audit_cfg.get("path", ".stain/audit")),
        enabled=audit_cfg.get("enabled", True),
    )


def analyse(
    input_text: str,
    config: dict[str, Any] | None = None,
    detector_ids: list[str] | None = None,
) -> CompositeResult:
    """Run enabled detectors against input text and produce composite result."""
    if config is None:
        config = load_config()

    if detector_ids is None:
        detector_ids = get_enabled_detectors(config)

    model = config.get("models", {}).get("detector", DEFAULT_MODEL)
    audit_logger = _make_audit_logger(config)

    start = time.monotonic()
    results: list[DetectorResult] = []

    for did in detector_ids:
        result = run_detector(did, input_text, model=model, audit_logger=audit_logger)
        results.append(result)

    total_latency = int((time.monotonic() - start) * 1000)

    # Weighted composite score
    total_weight = 0.0
    weighted_sum = 0.0
    for result in results:
        weight = get_detector_weight(config, result.detector_id)
        weighted_sum += result.verdict.score * weight
        total_weight += weight

    composite_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Merge annotations
    merged = _merge_annotations(results)

    # Total cost estimate
    total_in = sum(r.meta.tokens_in for r in results)
    total_out = sum(r.meta.tokens_out for r in results)

    input_hash = f"sha256:{hashlib.sha256(input_text.encode()).hexdigest()[:16]}"

    return CompositeResult(
        stain_version=__version__,
        input_hash=input_hash,
        input_length_chars=len(input_text),
        composite_score=round(composite_score, 3),
        detector_results=results,
        merged_annotations=merged,
        meta={
            "total_latency_ms": total_latency,
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
