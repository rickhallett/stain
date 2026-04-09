"""Pydantic models for detector output contracts."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Annotation(BaseModel):
    span_start: int
    span_end: int
    pattern: str
    severity: Severity
    explanation: str
    span_valid: bool = True  # set by post-validation


class Verdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    annotations: list[Annotation] = Field(default_factory=list)
    annotations_valid: int = 0    # count of span-validated annotations
    annotations_invalid: int = 0  # count of annotations with bad offsets


class Meta(BaseModel):
    model: str
    latency_ms: int
    tokens_in: int
    tokens_out: int


class DetectorResult(BaseModel):
    detector_id: str
    detector_name: str
    version: str
    prompt_hash: str
    verdict: Verdict
    meta: Meta


class MergedAnnotation(BaseModel):
    span_start: int
    span_end: int
    detectors: list[str]
    max_severity: Severity
    explanations: dict[str, str]


class CompositeResult(BaseModel):
    stain_version: str
    input_hash: str
    input_length_chars: int
    composite_score: float = Field(ge=0.0, le=1.0)
    detector_results: list[DetectorResult]
    merged_annotations: list[MergedAnnotation] = Field(default_factory=list)
    meta: dict
