"""Tests for Pydantic output contract models."""

import pytest
from pydantic import ValidationError

from stain.models import (
    Annotation,
    CompositeResult,
    DetectorResult,
    MergedAnnotation,
    Meta,
    Severity,
    Verdict,
)


def _make_annotation(**overrides):
    defaults = {
        "span_start": 0,
        "span_end": 10,
        "pattern": "correctio",
        "severity": "high",
        "explanation": "Test explanation",
    }
    defaults.update(overrides)
    return Annotation(**defaults)


def _make_verdict(**overrides):
    defaults = {
        "score": 0.5,
        "confidence": 0.8,
        "summary": "Test summary",
        "annotations": [],
    }
    defaults.update(overrides)
    return Verdict(**defaults)


def _make_meta(**overrides):
    defaults = {
        "model": "test/model",
        "latency_ms": 100,
        "tokens_in": 500,
        "tokens_out": 300,
    }
    defaults.update(overrides)
    return Meta(**defaults)


class TestAnnotation:
    def test_valid_annotation(self):
        a = _make_annotation()
        assert a.span_start == 0
        assert a.span_end == 10
        assert a.severity == Severity.HIGH
        assert a.span_valid is True

    def test_span_valid_default(self):
        a = _make_annotation()
        assert a.span_valid is True

    def test_span_valid_explicit(self):
        a = _make_annotation(span_valid=False)
        assert a.span_valid is False

    def test_all_severities(self):
        for sev in ("high", "medium", "low"):
            a = _make_annotation(severity=sev)
            assert a.severity == Severity(sev)


class TestVerdict:
    def test_valid_verdict(self):
        v = _make_verdict()
        assert v.score == 0.5
        assert v.confidence == 0.8
        assert v.annotations == []

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            _make_verdict(score=-0.1)
        with pytest.raises(ValidationError):
            _make_verdict(score=1.1)

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            _make_verdict(confidence=-0.1)
        with pytest.raises(ValidationError):
            _make_verdict(confidence=1.1)

    def test_edge_scores(self):
        v0 = _make_verdict(score=0.0, confidence=0.0)
        assert v0.score == 0.0
        v1 = _make_verdict(score=1.0, confidence=1.0)
        assert v1.score == 1.0

    def test_annotations_valid_invalid_counts(self):
        v = _make_verdict(annotations_valid=5, annotations_invalid=2)
        assert v.annotations_valid == 5
        assert v.annotations_invalid == 2


class TestDetectorResult:
    def test_full_result(self):
        result = DetectorResult(
            detector_id="D1",
            detector_name="Rhetorical Pattern",
            version="0.1.0",
            prompt_hash="sha256:abc123",
            verdict=_make_verdict(),
            meta=_make_meta(),
        )
        assert result.detector_id == "D1"
        assert result.version == "0.1.0"

    def test_json_roundtrip(self):
        result = DetectorResult(
            detector_id="D1",
            detector_name="Rhetorical Pattern",
            version="0.1.0",
            prompt_hash="sha256:abc123",
            verdict=_make_verdict(
                annotations=[_make_annotation()]
            ),
            meta=_make_meta(),
        )
        data = result.model_dump()
        restored = DetectorResult(**data)
        assert restored.detector_id == result.detector_id
        assert restored.verdict.score == result.verdict.score
        assert len(restored.verdict.annotations) == 1


class TestCompositeResult:
    def test_composite_score_bounds(self):
        with pytest.raises(ValidationError):
            CompositeResult(
                stain_version="0.1.0",
                input_hash="sha256:test",
                input_length_chars=100,
                composite_score=1.5,
                detector_results=[],
                meta={},
            )
