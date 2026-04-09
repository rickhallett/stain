"""Tests for HTML report generation."""

import pytest
from stain.html import render_html_report
from stain.models import (
    Annotation, CompositeResult, DetectorResult, MergedAnnotation,
    Meta, Severity, Verdict,
)


def _make_result():
    return CompositeResult(
        stain_version="0.1.0",
        input_hash="sha256:test",
        input_length_chars=100,
        composite_score=0.65,
        detector_results=[
            DetectorResult(
                detector_id="D1",
                detector_name="Rhetorical Pattern",
                version="0.1.0",
                prompt_hash="sha256:test",
                verdict=Verdict(
                    score=0.72, confidence=0.85, summary="High pattern density",
                    annotations=[
                        Annotation(span_start=0, span_end=20, pattern="correctio",
                                   severity="high", explanation="Test explanation"),
                    ],
                ),
                meta=Meta(model="test/model", latency_ms=200, tokens_in=400, tokens_out=300),
            ),
        ],
        merged_annotations=[
            MergedAnnotation(
                span_start=0, span_end=20, detectors=["D1"],
                max_severity=Severity.HIGH, explanations={"D1": "Test explanation"},
            ),
        ],
        meta={"total_latency_ms": 200, "total_tokens_in": 400, "total_tokens_out": 300},
    )


class TestRenderHtml:
    def test_returns_valid_html(self):
        html = render_html_report(_make_result(), "This is sample text for HTML report testing.")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_composite_score(self):
        html = render_html_report(_make_result(), "Test text for score display.")
        assert "0.650" in html or "0.65" in html

    def test_contains_detector_info(self):
        html = render_html_report(_make_result(), "Test text for detector info display.")
        assert "D1" in html
        assert "Rhetorical Pattern" in html

    def test_contains_annotated_text(self):
        text = "This is sample text for annotation overlay testing."
        result = _make_result()
        html = render_html_report(result, text)
        assert "annotation" in html.lower() or "ann" in html.lower()

    def test_self_contained_no_external_deps(self):
        html = render_html_report(_make_result(), "Test text.")
        assert "https://" not in html
        assert "http://" not in html

    def test_empty_annotations(self):
        result = _make_result()
        result.merged_annotations = []
        html = render_html_report(result, "Clean text with no annotations.")
        assert "<!DOCTYPE html>" in html
