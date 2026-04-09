"""Detector engine — runs LLM-backed detector prompts against input text.

Uses litellm for provider-agnostic inference. Model names follow the
litellm format: "provider/model" (e.g. "groq/llama-3.3-70b-versatile",
"anthropic/claude-haiku-4-5-20251001").
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

import litellm
from dotenv import load_dotenv

from stain.audit import AuditEntry, AuditLogger, hash_content
from stain.models import DetectorResult, Meta, Verdict
from stain.registry import DETECTORS_DIR, discover_detectors


logger = logging.getLogger(__name__)

# Load .env for API keys (CEREBRAS_API_KEY, GROQ_API_KEY, etc.)
load_dotenv()

# Suppress litellm's noisy logging by default
litellm.suppress_debug_info = True

DEFAULT_MODEL = "cerebras/qwen-3-235b-a22b-instruct-2507"
DEFAULT_TIMEOUT = 30  # seconds


def _hash_prompt(prompt_text: str) -> str:
    """SHA256 hash of the prompt for versioning."""
    return f"sha256:{hashlib.sha256(prompt_text.encode()).hexdigest()[:16]}"


def _load_prompt(detector_id: str) -> str:
    """Load the system prompt for a detector via registry."""
    detectors = discover_detectors(enabled_only=False)
    if detector_id not in detectors:
        raise ValueError(f"Detector {detector_id} not found in {DETECTORS_DIR}")
    return detectors[detector_id].prompt


def _extract_json(raw_text: str) -> dict:
    """Extract JSON from response, stripping markdown fences if present."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        newline_idx = cleaned.find("\n")
        if newline_idx == -1:
            # No newline — strip the backticks and hope for the best
            cleaned = cleaned[3:]
        else:
            cleaned = cleaned[newline_idx + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _validate_annotations(
    annotations: list, input_text: str,
) -> tuple[list, int, int]:
    """Validate and repair annotation span offsets against the input text.

    Checks each annotation's span_start/span_end against the actual input.
    If offsets are clearly wrong (out of bounds, nonsensically small for the
    explanation text), attempts a fuzzy recovery by searching the input for
    keywords from the explanation. Annotations that can't be salvaged are
    kept but marked span_valid=False.

    Returns (annotations, valid_count, invalid_count).
    """
    text_len = len(input_text)
    valid = 0
    invalid = 0

    for annot in annotations:
        # Basic bounds check
        if (
            annot.span_start < 0
            or annot.span_end < 0
            or annot.span_start >= text_len
            or annot.span_end > text_len
            or annot.span_start >= annot.span_end
        ):
            # Offsets are out of bounds — try to recover
            repaired = _try_repair_span(annot, input_text)
            if repaired:
                annot.span_start, annot.span_end = repaired
                annot.span_valid = True
                valid += 1
            else:
                annot.span_valid = False
                invalid += 1
            continue

        # Plausibility check: span should be at least a few chars
        span_len = annot.span_end - annot.span_start
        if span_len < 3:
            # Suspiciously short — likely word/line indices, not char offsets
            repaired = _try_repair_span(annot, input_text)
            if repaired:
                annot.span_start, annot.span_end = repaired
                annot.span_valid = True
                valid += 1
            else:
                annot.span_valid = False
                invalid += 1
            continue

        # Content plausibility: check that the spanned text has *some*
        # relationship to the explanation. If the explanation quotes text
        # that doesn't appear in the span, the offsets are probably wrong.
        span_text = input_text[annot.span_start:annot.span_end]
        quotes = _extract_quotes(annot.explanation)
        if quotes:
            repaired = _repair_from_quotes(quotes, span_text, input_text)
            if repaired is True:
                # Quotes found in span — offsets are correct
                annot.span_valid = True
                valid += 1
                continue
            elif repaired:
                # Quotes found elsewhere — offsets repaired
                annot.span_start, annot.span_end = repaired
                annot.span_valid = True
                valid += 1
                continue

        # Fallback: search for verbatim phrases from the explanation
        key_match = _extract_key_phrases(annot.explanation, input_text)
        if key_match:
            annot.span_start, annot.span_end = key_match
            annot.span_valid = True
            valid += 1
        else:
            # Nothing matchable — mark invalid, keep original offsets
            annot.span_valid = False
            invalid += 1

    return annotations, valid, invalid


def _try_repair_span(
    annot, input_text: str,
) -> tuple[int, int] | None:
    """Attempt to find the correct span by searching for quoted text
    or key phrases from the explanation in the input."""
    quotes = _extract_quotes(annot.explanation)
    for quote in quotes:
        match = _find_in_text(quote, input_text)
        if match:
            return match
    return None


def _find_in_text(needle: str, haystack: str) -> tuple[int, int] | None:
    """Find needle in haystack, trying exact then case-insensitive."""
    idx = haystack.find(needle)
    if idx != -1:
        return (idx, idx + len(needle))
    idx = haystack.lower().find(needle.lower())
    if idx != -1:
        return (idx, idx + len(needle))
    return None


def _repair_from_quotes(
    quotes: list[str], span_text: str, input_text: str,
) -> tuple[int, int] | bool | None:
    """Check if any quoted phrase appears in the span.

    Returns:
        True           — quote found in span, offsets are correct
        (start, end)   — quote found elsewhere, use these corrected offsets
        None           — quote not found anywhere in input
    """
    for quote in quotes:
        if quote.lower() in span_text.lower():
            return True  # Offsets are correct

    # Quotes don't match the span — offsets are wrong. Find in full text.
    for quote in quotes:
        match = _find_in_text(quote, input_text)
        if match:
            return match

    return None


def _extract_key_phrases(explanation: str, input_text: str) -> tuple[int, int] | None:
    """Extract long substrings from the explanation that appear verbatim
    in the input text. Handles cases where the model paraphrases rather
    than quoting."""
    input_lower = input_text.lower()
    # Try progressively shorter substrings of the explanation
    # that might be verbatim from the input
    words = explanation.split()
    best: tuple[int, int] | None = None
    best_len = 0

    # Sliding window: try phrases of decreasing length
    for window in range(min(len(words), 12), 3, -1):
        for start in range(len(words) - window + 1):
            phrase = " ".join(words[start:start + window])
            # Strip trailing punctuation that might not be in the input
            phrase_clean = phrase.rstrip(".,;:!?")
            if len(phrase_clean) < 15:
                continue
            idx = input_lower.find(phrase_clean.lower())
            if idx != -1 and len(phrase_clean) > best_len:
                best = (idx, idx + len(phrase_clean))
                best_len = len(phrase_clean)
        if best:
            return best  # Found a long match, good enough

    return None


def _extract_quotes(text: str) -> list[str]:
    """Pull quoted strings from explanation text, longest first."""
    quotes = []
    in_quote = False
    quote_char = None
    current: list[str] = []

    for ch in text:
        if not in_quote and ch in ("'", '"', "\u2018", "\u2019", "\u201c", "\u201d"):
            in_quote = True
            quote_char = ch
            current = []
        elif in_quote:
            # Match closing quote (handle smart quotes)
            closers = {
                "'": ("'",), '"': ('"',),
                "\u2018": ("\u2019",), "\u201c": ("\u201d",),
                "\u2019": ("\u2019",), "\u201d": ("\u201d",),
            }
            if ch in closers.get(quote_char, (quote_char,)):
                q = "".join(current).strip()
                if len(q) >= 5:  # skip trivially short quotes
                    quotes.append(q)
                in_quote = False
            else:
                current.append(ch)

    # Return longest first — longer quotes are more reliable anchors
    quotes.sort(key=len, reverse=True)
    return quotes


class DetectorError(Exception):
    """Raised when a detector call fails (API error, parse error, etc.)."""

    def __init__(self, detector_id: str, message: str):
        self.detector_id = detector_id
        super().__init__(f"{detector_id}: {message}")


def run_detector(
    detector_id: str,
    input_text: str,
    model: str = DEFAULT_MODEL,
    audit_logger: AuditLogger | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> DetectorResult:
    """Run a single detector against input text and return structured result.

    Args:
        detector_id: Which detector to run (D1-D6+).
        input_text: The text to analyse.
        model: litellm model string.
        audit_logger: Optional audit logger for recording the interaction.
        timeout: Timeout in seconds for the LLM call.

    Raises:
        DetectorError: If the LLM call fails or returns unparseable output.
    """
    detectors = discover_detectors(enabled_only=False)
    if detector_id not in detectors:
        raise ValueError(f"Detector {detector_id} not found in {DETECTORS_DIR}")

    info = detectors[detector_id]
    prompt_text = info.prompt
    prompt_hash = info.prompt_hash
    detector_name = info.name

    start = time.monotonic()
    try:
        response = litellm.completion(
            model=model,
            max_tokens=2048,
            timeout=timeout,
            messages=[
                {"role": "system", "content": prompt_text},
                {
                    "role": "user",
                    "content": (
                        "Analyse the following text and return your structured "
                        "JSON verdict.\n\n---\n\n" + input_text
                    ),
                },
            ],
        )
    except Exception as e:
        raise DetectorError(detector_id, f"LLM call failed: {e}") from e

    latency_ms = int((time.monotonic() - start) * 1000)

    # Parse response with validation
    raw_text = response.choices[0].message.content
    try:
        raw_json = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        raise DetectorError(
            detector_id, f"Failed to parse JSON from response: {e}"
        ) from e

    if "verdict" not in raw_json:
        raise DetectorError(
            detector_id,
            f"Response missing 'verdict' key. Got keys: {list(raw_json.keys())}",
        )

    try:
        verdict = Verdict(**raw_json["verdict"])
    except Exception as e:
        raise DetectorError(
            detector_id, f"Invalid verdict structure: {e}"
        ) from e

    # Validate annotation spans against actual input text
    verdict.annotations, valid, invalid = _validate_annotations(
        verdict.annotations, input_text,
    )
    verdict.annotations_valid = valid
    verdict.annotations_invalid = invalid

    # litellm normalises usage across providers
    usage = response.usage

    if audit_logger:
        audit_logger.log(AuditEntry(
            operation="detector_call",
            detector_id=detector_id,
            model=model,
            prompt_hash=prompt_hash,
            prompt_version=info.version,
            input_hash=hash_content(input_text),
            input_length_chars=len(input_text),
            response_hash=hash_content(raw_text),
            parsed_score=verdict.score,
            annotations_count=len(verdict.annotations),
            annotations_valid=valid,
            annotations_invalid=invalid,
            latency_ms=latency_ms,
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
        ))

    return DetectorResult(
        detector_id=detector_id,
        detector_name=detector_name,
        version=info.version,
        prompt_hash=prompt_hash,
        verdict=verdict,
        meta=Meta(
            model=model,
            latency_ms=latency_ms,
            tokens_in=usage.prompt_tokens,
            tokens_out=usage.completion_tokens,
        ),
    )
