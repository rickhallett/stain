"""Tests for orchestrator — annotation merging and composite scoring."""

from stain.models import Annotation, DetectorResult, Meta, MergedAnnotation, Severity, Verdict
from stain.orchestrator import _merge_annotations


def _make_result(detector_id, score, annotations=None):
    return DetectorResult(
        detector_id=detector_id,
        detector_name=f"Test {detector_id}",
        version="0.1.0",
        prompt_hash="sha256:test",
        verdict=Verdict(
            score=score,
            confidence=0.8,
            summary="Test",
            annotations=annotations or [],
        ),
        meta=Meta(model="test/model", latency_ms=100, tokens_in=100, tokens_out=100),
    )


def _make_annot(start, end, pattern="correctio", severity="medium", explanation="test"):
    return Annotation(
        span_start=start,
        span_end=end,
        pattern=pattern,
        severity=severity,
        explanation=explanation,
    )


class TestMergeAnnotations:
    def test_no_annotations(self):
        results = [_make_result("D1", 0.5)]
        merged = _merge_annotations(results)
        assert merged == []

    def test_non_overlapping(self):
        results = [
            _make_result("D1", 0.5, [_make_annot(0, 10)]),
            _make_result("D2", 0.6, [_make_annot(20, 30)]),
        ]
        merged = _merge_annotations(results)
        assert len(merged) == 2
        assert merged[0].detectors == ["D1"]
        assert merged[1].detectors == ["D2"]

    def test_overlapping_spans_merge(self):
        results = [
            _make_result("D1", 0.5, [_make_annot(0, 15, explanation="from D1")]),
            _make_result("D2", 0.6, [_make_annot(10, 25, explanation="from D2")]),
        ]
        merged = _merge_annotations(results)
        assert len(merged) == 1
        assert set(merged[0].detectors) == {"D1", "D2"}
        assert merged[0].span_start == 0
        assert merged[0].span_end == 25
        assert "D1" in merged[0].explanations
        assert "D2" in merged[0].explanations

    def test_severity_escalation(self):
        results = [
            _make_result("D1", 0.5, [_make_annot(0, 20, severity="low")]),
            _make_result("D2", 0.6, [_make_annot(5, 15, severity="high")]),
        ]
        merged = _merge_annotations(results)
        assert len(merged) == 1
        assert merged[0].max_severity == Severity.HIGH

    def test_same_detector_multiple_annotations(self):
        results = [
            _make_result("D1", 0.7, [
                _make_annot(0, 10),
                _make_annot(50, 60),
            ]),
        ]
        merged = _merge_annotations(results)
        assert len(merged) == 2
