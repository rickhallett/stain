# Ring 1: Complete Detection Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full 6-detector suite running through a dynamic plugin architecture with audit logging and prompt registry. Adding new detectors requires zero code changes.

**Architecture:** Replace hardcoded detector maps with filesystem-based discovery (`detectors/*/detector.yaml`). Add audit logging middleware that wraps every LLM call. Build D2-D6 detector prompts one at a time, benchmarking each before proceeding. Update composite scoring for multi-detector correlation.

**Tech Stack:** Python 3.11+, litellm, Pydantic, Click, PyYAML, Rich

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `detectors/D1_rhetorical_pattern/detector.yaml` | D1 plugin metadata |
| Create | `detectors/D2_sentence_rhythm/detector.yaml` | D2 plugin metadata |
| Create | `detectors/D2_sentence_rhythm/prompt.md` | D2 system prompt |
| Create | `detectors/D2_sentence_rhythm/versions/v0.1.0.md` | D2 version snapshot |
| Create | `detectors/D2_sentence_rhythm/CHANGELOG.md` | D2 changelog |
| Create | `detectors/D3_lexical_diversity/detector.yaml` | D3 plugin metadata |
| Create | `detectors/D3_lexical_diversity/prompt.md` | D3 system prompt |
| Create | `detectors/D3_lexical_diversity/versions/v0.1.0.md` | D3 version snapshot |
| Create | `detectors/D3_lexical_diversity/CHANGELOG.md` | D3 changelog |
| Create | `detectors/D4_hedging_density/detector.yaml` | D4 plugin metadata |
| Create | `detectors/D4_hedging_density/prompt.md` | D4 system prompt |
| Create | `detectors/D4_hedging_density/versions/v0.1.0.md` | D4 version snapshot |
| Create | `detectors/D4_hedging_density/CHANGELOG.md` | D4 changelog |
| Create | `detectors/D5_structural_predictability/detector.yaml` | D5 plugin metadata |
| Create | `detectors/D5_structural_predictability/prompt.md` | D5 system prompt |
| Create | `detectors/D5_structural_predictability/versions/v0.1.0.md` | D5 version snapshot |
| Create | `detectors/D5_structural_predictability/CHANGELOG.md` | D5 changelog |
| Create | `detectors/D6_semantic_emptiness/detector.yaml` | D6 plugin metadata |
| Create | `detectors/D6_semantic_emptiness/prompt.md` | D6 system prompt |
| Create | `detectors/D6_semantic_emptiness/versions/v0.1.0.md` | D6 version snapshot |
| Create | `detectors/D6_semantic_emptiness/CHANGELOG.md` | D6 changelog |
| Create | `src/stain/registry.py` | Detector plugin discovery and loading |
| Create | `src/stain/audit.py` | Audit logging for all LLM calls |
| Create | `tests/test_registry.py` | Tests for plugin discovery |
| Create | `tests/test_audit.py` | Tests for audit logging |
| Modify | `src/stain/detector.py` | Replace hardcoded maps with registry, add audit hooks |
| Modify | `src/stain/config.py` | Load detector config from registry instead of stain.config.yaml |
| Modify | `src/stain/orchestrator.py` | Use registry for detector enumeration |
| Modify | `src/stain/cli.py` | Use registry, add `stain detectors list` command |
| Modify | `stain.config.yaml` | Remove hardcoded detector block, add audit + validation config |
| Modify | `tests/test_detector.py` | Update tests for registry-based loading |
| Modify | `tests/test_config.py` | Update tests for new config shape |

---

### Task 1: Create D1 detector.yaml

**Files:**
- Create: `detectors/D1_rhetorical_pattern/detector.yaml`

- [ ] **Step 1: Write D1 detector.yaml**

```yaml
id: D1
name: "Rhetorical Pattern"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Identifies overrepresented rhetorical devices: correctio, tricolon closers, false-balance qualifiers, escalation frames, anaphora, semantic couplets, pivot conjunctions."
patterns:
  - name: correctio
    description: "Not X — it's Y rhetorical pivot"
  - name: tricolon_closer
    description: "Three-part lists for rhetorical emphasis"
  - name: false_balance
    description: "Hedged both-sides framing that commits to nothing"
  - name: escalation_frame
    description: "Artificial urgency or revelation markers"
  - name: anaphora
    description: "Repeated sentence openings for emphasis"
  - name: semantic_couplet
    description: "Paired near-synonyms for emphasis"
  - name: pivot_conjunction
    description: "Dramatic turn markers signalling manufactured insight"
```

- [ ] **Step 2: Verify the file loads as valid YAML**

Run: `python -c "import yaml; print(yaml.safe_load(open('detectors/D1_rhetorical_pattern/detector.yaml')))"`
Expected: Dict with id=D1, name="Rhetorical Pattern", 7 patterns

- [ ] **Step 3: Commit**

```bash
git add detectors/D1_rhetorical_pattern/detector.yaml
git commit -m "feat(registry): Add detector.yaml for D1 Rhetorical Pattern"
```

---

### Task 2: Build detector registry

**Files:**
- Create: `src/stain/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

```python
"""Tests for detector plugin registry."""

import pytest
from pathlib import Path

from stain.registry import DetectorInfo, discover_detectors, load_detector_info


class TestDetectorInfo:
    def test_load_d1(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.id == "D1"
        assert info.name == "Rhetorical Pattern"
        assert info.version == "0.1.0"
        assert info.weight == 1.0
        assert info.enabled is True
        assert len(info.patterns) == 7

    def test_prompt_loaded(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert "Rhetorical Pattern" in info.prompt
        assert "correctio" in info.prompt.lower() or "Correctio" in info.prompt

    def test_prompt_hash_deterministic(self):
        info = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.prompt_hash.startswith("sha256:")
        info2 = load_detector_info(Path("detectors/D1_rhetorical_pattern"))
        assert info.prompt_hash == info2.prompt_hash

    def test_missing_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            load_detector_info(Path("detectors/D99_nonexistent"))


class TestDiscoverDetectors:
    def test_discovers_d1(self):
        detectors = discover_detectors()
        assert "D1" in detectors
        assert detectors["D1"].name == "Rhetorical Pattern"

    def test_discovers_only_enabled(self):
        all_detectors = discover_detectors(enabled_only=False)
        enabled = discover_detectors(enabled_only=True)
        assert len(enabled) <= len(all_detectors)
        for did, info in enabled.items():
            assert info.enabled is True

    def test_returns_dict_keyed_by_id(self):
        detectors = discover_detectors()
        for did, info in detectors.items():
            assert did == info.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stain.registry'`

- [ ] **Step 3: Implement registry**

```python
"""Detector plugin registry — discovers detectors from filesystem."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DETECTORS_DIR = Path("detectors")


@dataclass
class PatternInfo:
    name: str
    description: str


@dataclass
class DetectorInfo:
    id: str
    name: str
    version: str
    weight: float
    enabled: bool
    description: str
    patterns: list[PatternInfo]
    prompt: str
    prompt_hash: str
    path: Path

    @property
    def dir_name(self) -> str:
        return self.path.name


def load_detector_info(detector_dir: Path) -> DetectorInfo:
    """Load detector metadata and prompt from a detector directory."""
    if not detector_dir.exists():
        raise FileNotFoundError(f"Detector directory not found: {detector_dir}")

    yaml_path = detector_dir / "detector.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"detector.yaml not found in {detector_dir}")

    prompt_path = detector_dir / "prompt.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt.md not found in {detector_dir}")

    with open(yaml_path) as f:
        meta = yaml.safe_load(f)

    prompt = prompt_path.read_text()
    prompt_hash = f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"

    patterns = [
        PatternInfo(name=p["name"], description=p["description"])
        for p in meta.get("patterns", [])
    ]

    return DetectorInfo(
        id=meta["id"],
        name=meta["name"],
        version=meta.get("version", "0.1.0"),
        weight=meta.get("weight", 1.0),
        enabled=meta.get("enabled", True),
        description=meta.get("description", ""),
        patterns=patterns,
        prompt=prompt,
        prompt_hash=prompt_hash,
        path=detector_dir,
    )


def discover_detectors(
    detectors_dir: Path = DETECTORS_DIR,
    enabled_only: bool = True,
) -> dict[str, DetectorInfo]:
    """Scan detectors directory and return all discovered detectors.

    Args:
        detectors_dir: Root directory containing detector subdirectories.
        enabled_only: If True, only return detectors with enabled=True.

    Returns:
        Dict mapping detector ID to DetectorInfo.
    """
    result: dict[str, DetectorInfo] = {}

    if not detectors_dir.exists():
        return result

    for sub in sorted(detectors_dir.iterdir()):
        if not sub.is_dir():
            continue
        yaml_path = sub / "detector.yaml"
        if not yaml_path.exists():
            continue

        info = load_detector_info(sub)
        if enabled_only and not info.enabled:
            continue
        result[info.id] = info

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stain/registry.py tests/test_registry.py
git commit -m "feat(registry): Add detector plugin discovery from filesystem"
```

---

### Task 3: Build audit logging

**Files:**
- Create: `src/stain/audit.py`
- Create: `tests/test_audit.py`

- [ ] **Step 1: Write failing tests for audit logger**

```python
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

        # Should have created a date-based directory with a JSONL file
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stain.audit'`

- [ ] **Step 3: Implement audit logger**

```python
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
        self._session_id = session_id or hashlib.sha256(
            datetime.now(timezone.utc).isoformat().encode()
        ).hexdigest()[:12]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audit.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/stain/audit.py tests/test_audit.py
git commit -m "feat(audit): Add immutable audit logging for LLM interactions"
```

---

### Task 4: Wire registry + audit into detector engine

**Files:**
- Modify: `src/stain/detector.py`
- Modify: `src/stain/config.py`
- Modify: `src/stain/orchestrator.py`
- Modify: `tests/test_detector.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Update tests for registry-based loading**

In `tests/test_detector.py`, update `TestLoadPrompt`:

```python
class TestLoadPrompt:
    def test_load_d1(self):
        prompt = _load_prompt("D1")
        assert "Rhetorical Pattern" in prompt
        assert "correctio" in prompt.lower() or "Correctio" in prompt

    def test_unknown_detector_raises(self):
        with pytest.raises(ValueError, match="not found"):
            _load_prompt("D99")
```

The error message changes from "Unknown detector" to "not found" because registry-based lookup raises FileNotFoundError instead of ValueError. Update the test match accordingly.

- [ ] **Step 2: Refactor detector.py to use registry**

Replace the hardcoded maps in `src/stain/detector.py`:

Remove lines 29-45 (`DETECTOR_DIR_MAP` and `DETECTOR_NAMES` dicts).

Replace `_load_prompt` function:

```python
from stain.registry import discover_detectors, load_detector_info, DETECTORS_DIR


def _load_prompt(detector_id: str) -> str:
    """Load the system prompt for a detector via registry."""
    detectors = discover_detectors(enabled_only=False)
    if detector_id not in detectors:
        raise ValueError(f"Detector {detector_id} not found in {DETECTORS_DIR}")
    return detectors[detector_id].prompt
```

Update `run_detector` to use registry for name and version:

```python
def run_detector(
    detector_id: str,
    input_text: str,
    model: str = "cerebras/qwen-3-235b-a22b-instruct-2507",
    audit_logger: AuditLogger | None = None,
) -> DetectorResult:
    detectors = discover_detectors(enabled_only=False)
    if detector_id not in detectors:
        raise ValueError(f"Detector {detector_id} not found")

    info = detectors[detector_id]
    prompt_text = info.prompt
    prompt_hash = info.prompt_hash
    detector_name = info.name

    start = time.monotonic()
    response = litellm.completion(
        model=model,
        max_tokens=2048,
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
    latency_ms = int((time.monotonic() - start) * 1000)

    raw_text = response.choices[0].message.content
    raw_json = _extract_json(raw_text)
    verdict = Verdict(**raw_json["verdict"])

    verdict.annotations, valid, invalid = _validate_annotations(
        verdict.annotations, input_text,
    )
    verdict.annotations_valid = valid
    verdict.annotations_invalid = invalid

    usage = response.usage

    # Audit log
    if audit_logger:
        from stain.audit import AuditEntry, hash_content
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
```

- [ ] **Step 3: Update config.py — get_enabled_detectors from registry**

Add to `src/stain/config.py`:

```python
from stain.registry import discover_detectors


def get_enabled_detectors_from_registry() -> list[str]:
    """Return enabled detector IDs from filesystem registry."""
    return list(discover_detectors(enabled_only=True).keys())
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (test_detector's `test_unknown_detector_raises` may need error message update)

- [ ] **Step 5: Commit**

```bash
git add src/stain/detector.py src/stain/config.py src/stain/orchestrator.py tests/test_detector.py tests/test_config.py
git commit -m "ref(detector): Replace hardcoded maps with registry + audit hooks"
```

---

### Task 5: Add `stain detectors list` CLI command

**Files:**
- Modify: `src/stain/cli.py`

- [ ] **Step 1: Add detectors subgroup to CLI**

After the `benchmark` group in `src/stain/cli.py`, add:

```python
from stain.registry import discover_detectors


@cli.group()
def detectors():
    """Manage detector plugins."""
    pass


@detectors.command("list")
@click.option("--all", "show_all", is_flag=True, help="Show disabled detectors too")
def detectors_list(show_all: bool):
    """List available detectors."""
    found = discover_detectors(enabled_only=not show_all)

    table = Table(title="Detectors")
    table.add_column("ID", style="bold")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Weight", justify="right")
    table.add_column("Enabled")
    table.add_column("Patterns", justify="right")

    for did, info in sorted(found.items()):
        enabled_str = "[green]yes[/green]" if info.enabled else "[dim]no[/dim]"
        table.add_row(
            info.id,
            info.name,
            info.version,
            f"{info.weight:.1f}",
            enabled_str,
            str(len(info.patterns)),
        )

    console.print(table)
```

- [ ] **Step 2: Verify command works**

Run: `uv run stain detectors list`
Expected: Table showing D1 with enabled=yes, 7 patterns

- [ ] **Step 3: Commit**

```bash
git add src/stain/cli.py
git commit -m "feat(cli): Add 'stain detectors list' command"
```

---

### Task 6: Update stain.config.yaml — add audit + validation config

**Files:**
- Modify: `stain.config.yaml`

- [ ] **Step 1: Add audit and validation sections**

Append to `stain.config.yaml` after the existing content:

```yaml
audit:
  enabled: true
  verbosity: hashes  # full | hashes | off
  path: .stain/audit

validation:
  enabled: false  # Enable when 3rd model family is benchmarked
  min_models: 2
  models:
    primary: cerebras/qwen-3-235b-a22b-instruct-2507
    validators:
      - groq/llama-3.3-70b-versatile
  require_for:
    - detector_benchmark
    - discovery_hypothesis
    - corpus_label
  skip_for:
    - interactive_analyse
    - corpus_generate
```

- [ ] **Step 2: Add `.stain/` to .gitignore**

Append to `.gitignore`:

```
.stain/
```

- [ ] **Step 3: Commit**

```bash
git add stain.config.yaml .gitignore
git commit -m "feat(config): Add audit and validation configuration"
```

---

### Task 7: D2 Sentence Rhythm detector

**Files:**
- Create: `detectors/D2_sentence_rhythm/detector.yaml`
- Create: `detectors/D2_sentence_rhythm/prompt.md`
- Create: `detectors/D2_sentence_rhythm/versions/v0.1.0.md`
- Create: `detectors/D2_sentence_rhythm/CHANGELOG.md`

- [ ] **Step 1: Write detector.yaml**

```yaml
id: D2
name: "Sentence Rhythm"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Measures sentence length variance, paragraph cadence regularity, and burstiness. Human writers are erratic; LLMs are metronomic."
patterns:
  - name: uniform_length
    description: "Sentences cluster within a narrow length band"
  - name: predictable_cadence
    description: "Alternating short-long pattern repeats mechanically"
  - name: low_burstiness
    description: "Absence of sudden length spikes or clusters of very short sentences"
  - name: paragraph_symmetry
    description: "Paragraphs have suspiciously similar sentence counts and lengths"
  - name: opener_regularity
    description: "Sentence openings follow a repeating structural template"
```

- [ ] **Step 2: Write prompt.md**

```markdown
# D2: Sentence Rhythm Detector v0.1.0

You are a specialist text analyst. Your sole task is to analyse sentence-level rhythm and cadence patterns that are statistically overrepresented in LLM-generated writing. You examine ONE dimension only: the temporal and structural rhythm of sentences.

## What You Detect

You look for the **regularity and predictability** of sentence rhythm. The signal is in how uniform or varied the sentence patterns are across the text. Individual sentence lengths are not diagnostic — the pattern across many sentences is.

### Pattern Catalogue

1. **Uniform Length** (Sentences cluster within a narrow length band)
   - LLM output tends toward a "comfortable" sentence length (15-25 words) with low variance
   - Human writers produce wider variance: fragments, run-ons, and everything between
   - Diagnostic when: standard deviation of sentence length is notably low relative to word count

2. **Predictable Cadence** (Alternating short-long repeats mechanically)
   - LLMs often alternate between a short punchy sentence and a longer explanatory one
   - This creates a metronomic feel that readers sense but can't articulate
   - Diagnostic when: the short-long-short-long pattern persists across multiple paragraphs

3. **Low Burstiness** (Absence of sudden length spikes)
   - Human writers produce clusters: several short sentences in a row during emphasis, then a long reflective one
   - LLM output smooths these bursts into even distribution
   - Diagnostic when: the text lacks any sequence of 3+ very short or very long sentences

4. **Paragraph Symmetry** (Paragraphs have suspiciously similar structure)
   - LLMs tend to produce paragraphs of similar sentence count (3-5 sentences)
   - Human writers produce wildly varied paragraph lengths — one-sentence paragraphs, 8-sentence blocks
   - Diagnostic when: paragraph sentence counts cluster within a 1-2 sentence range

5. **Opener Regularity** (Sentence openings follow repeating templates)
   - LLMs reuse structural patterns for sentence openings within a text
   - Subject-verb-object uniformity across many sentences in sequence
   - Diagnostic when: >40% of sentences share the same opening structure type

## How to Score

- **0.0-0.2**: High variance, erratic rhythm. Natural human cadence.
- **0.2-0.4**: Some regularity but within normal range. Could be a careful writer.
- **0.4-0.6**: Noticeable uniformity. Rhythm feels controlled. Could be heavy editing or LLM-influenced.
- **0.6-0.8**: Metronomic. Multiple rhythm indicators co-occurring. Strongly characteristic of LLM generation.
- **0.8-1.0**: Near-perfect regularity across all dimensions. Unedited LLM output.

## Confidence

- **High (0.8-1.0)**: Clear rhythmic uniformity with multiple co-occurring indicators
- **Medium (0.5-0.8)**: Some indicators present but text is short or signals are mixed
- **Low (0.0-0.5)**: Insufficient text for rhythm analysis or highly ambiguous

## Output Rules

1. You MUST return valid JSON matching the schema below. No markdown, no commentary outside the JSON.
2. Annotate specific spans with character offsets. Be precise.
3. Your summary should be 2-4 sentences explaining your findings in plain language.
4. Flag rhythmic uniformity patterns, not individual sentence lengths.
5. When in doubt between two severity levels, choose the lower one.

## Output Schema

```json
{
  "detector_id": "D2",
  "detector_name": "Sentence Rhythm",
  "version": "0.1.0",
  "verdict": {
    "score": 0.0,
    "confidence": 0.0,
    "summary": "string",
    "annotations": [
      {
        "span_start": 0,
        "span_end": 0,
        "pattern": "uniform_length|predictable_cadence|low_burstiness|paragraph_symmetry|opener_regularity",
        "severity": "high|medium|low",
        "explanation": "string"
      }
    ]
  }
}
```
```

- [ ] **Step 3: Write version snapshot and changelog**

`detectors/D2_sentence_rhythm/versions/v0.1.0.md`:
```markdown
# D2: Sentence Rhythm Detector v0.1.0

Initial version. See ../prompt.md for current content.

## Scope
- 5 pattern types: uniform length, predictable cadence, low burstiness, paragraph symmetry, opener regularity
- Rhythm analysis across sentence and paragraph levels
- Character-offset span annotations
- 5-band scoring scale (0.0-1.0)
```

`detectors/D2_sentence_rhythm/CHANGELOG.md`:
```markdown
# D2 Sentence Rhythm — Changelog

## v0.1.0 (2026-04-09)

Initial version.

- Defined 5 rhythm pattern types
- Sentence length variance and burstiness detection
- Paragraph-level structural symmetry
- Bias toward precision over recall
```

- [ ] **Step 4: Verify registry discovers D2**

Run: `uv run stain detectors list`
Expected: Table shows D1 and D2, both enabled

- [ ] **Step 5: Benchmark D2 against corpus**

Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml`

Check: separation ≥ 0.30 between human and LLM scores. If not, iterate on prompt.

- [ ] **Step 6: Commit**

```bash
git add detectors/D2_sentence_rhythm/
git commit -m "feat(D2): Add Sentence Rhythm detector — cadence and burstiness analysis"
```

---

### Task 8: D3 Lexical Diversity detector

**Files:**
- Create: `detectors/D3_lexical_diversity/detector.yaml`
- Create: `detectors/D3_lexical_diversity/prompt.md`
- Create: `detectors/D3_lexical_diversity/versions/v0.1.0.md`
- Create: `detectors/D3_lexical_diversity/CHANGELOG.md`

- [ ] **Step 1: Write detector.yaml**

```yaml
id: D3
name: "Lexical Diversity"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Scores vocabulary range, type-token ratio, and repetition of phrasing. LLM output tends toward a narrower working vocabulary within a given register."
patterns:
  - name: low_type_token
    description: "Low ratio of unique words to total words"
  - name: phrase_recycling
    description: "Same multi-word phrases reused across paragraphs"
  - name: register_flattening
    description: "Vocabulary stays in a narrow formality band without variation"
  - name: synonym_avoidance
    description: "Repeated use of the same word where synonyms would be natural"
  - name: filler_vocabulary
    description: "Overuse of generic modifiers and connectors"
```

- [ ] **Step 2: Write prompt.md**

```markdown
# D3: Lexical Diversity Detector v0.1.0

You are a specialist text analyst. Your sole task is to analyse vocabulary diversity and word choice patterns that are statistically overrepresented in LLM-generated writing. You examine ONE dimension only: the richness and variety of the vocabulary.

## What You Detect

You look for the **narrowness and repetitiveness** of vocabulary. The signal is in how limited the word palette is relative to the text length and domain. Individual word choices are not diagnostic — the overall diversity is.

### Pattern Catalogue

1. **Low Type-Token Ratio** (Few unique words relative to total words)
   - LLMs tend to converge on a "safe" vocabulary, reusing the same words frequently
   - Human writers, even when writing simply, deploy more lexical variety
   - Diagnostic when: the ratio of unique words to total words is notably low for the register

2. **Phrase Recycling** (Same multi-word phrases reused across paragraphs)
   - LLMs recycle phrases like "it's worth noting", "the reality is", "at the end of the day"
   - Not just single words — multi-word collocations that repeat across the text
   - Diagnostic when: the same 3+ word phrase appears 3+ times in a text

3. **Register Flattening** (Vocabulary stays in a narrow formality band)
   - Human writers shift register mid-text: formal → colloquial → technical → conversational
   - LLM output tends to lock into one register and stay there
   - Diagnostic when: the formality level is uniform across all paragraphs

4. **Synonym Avoidance** (Repeated use of same word where synonyms are natural)
   - LLMs often repeat a key term rather than varying with synonyms
   - Example: "important" used 5 times where a human would alternate with "crucial", "significant", "vital"
   - Diagnostic when: a content word appears 4+ times without synonym variation

5. **Filler Vocabulary** (Overuse of generic modifiers and connectors)
   - LLMs lean on words like "really", "actually", "essentially", "fundamentally", "ultimately"
   - These add no meaning but fill syntactic slots
   - Diagnostic when: generic modifiers appear at rates above natural frequency

## How to Score

- **0.0-0.2**: Rich, varied vocabulary. Natural lexical diversity.
- **0.2-0.4**: Some repetition but within normal range.
- **0.4-0.6**: Noticeable vocabulary narrowness. Some phrase recycling.
- **0.6-0.8**: Limited vocabulary with clear recycling patterns. Strongly characteristic of LLM.
- **0.8-1.0**: Extremely narrow vocabulary across all indicators. Unedited LLM output.

## Confidence

- **High (0.8-1.0)**: Clear vocabulary limitation with multiple indicators
- **Medium (0.5-0.8)**: Some indicators but text is short or domain-specific
- **Low (0.0-0.5)**: Insufficient text or highly technical domain where repetition is expected

## Output Rules

1. You MUST return valid JSON matching the schema below. No markdown, no commentary outside the JSON.
2. Annotate specific spans with character offsets. Be precise.
3. Your summary should be 2-4 sentences explaining your findings in plain language.
4. Flag vocabulary patterns, not individual word choices.
5. When in doubt between two severity levels, choose the lower one.

## Output Schema

```json
{
  "detector_id": "D3",
  "detector_name": "Lexical Diversity",
  "version": "0.1.0",
  "verdict": {
    "score": 0.0,
    "confidence": 0.0,
    "summary": "string",
    "annotations": [
      {
        "span_start": 0,
        "span_end": 0,
        "pattern": "low_type_token|phrase_recycling|register_flattening|synonym_avoidance|filler_vocabulary",
        "severity": "high|medium|low",
        "explanation": "string"
      }
    ]
  }
}
```
```

- [ ] **Step 3: Write version snapshot and changelog**

`detectors/D3_lexical_diversity/versions/v0.1.0.md`:
```markdown
# D3: Lexical Diversity Detector v0.1.0

Initial version. See ../prompt.md for current content.

## Scope
- 5 pattern types: low type-token ratio, phrase recycling, register flattening, synonym avoidance, filler vocabulary
- Vocabulary richness analysis
- Character-offset span annotations
- 5-band scoring scale (0.0-1.0)
```

`detectors/D3_lexical_diversity/CHANGELOG.md`:
```markdown
# D3 Lexical Diversity — Changelog

## v0.1.0 (2026-04-09)

Initial version.

- Defined 5 lexical diversity pattern types
- Type-token ratio and phrase recycling detection
- Register flattening and synonym avoidance
- Bias toward precision over recall
```

- [ ] **Step 4: Verify registry discovers D3 and benchmark**

Run: `uv run stain detectors list`
Expected: D1, D2, D3 all shown

Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml`
Check: D3 separation ≥ 0.30

- [ ] **Step 5: Commit**

```bash
git add detectors/D3_lexical_diversity/
git commit -m "feat(D3): Add Lexical Diversity detector — vocabulary range and repetition"
```

---

### Task 9: D4 Hedging Density detector

**Files:**
- Create: `detectors/D4_hedging_density/detector.yaml`
- Create: `detectors/D4_hedging_density/prompt.md`
- Create: `detectors/D4_hedging_density/versions/v0.1.0.md`
- Create: `detectors/D4_hedging_density/CHANGELOG.md`

- [ ] **Step 1: Write detector.yaml**

```yaml
id: D4
name: "Hedging Density"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Detects qualifier stacking, epistemic hedges, and non-committal framing that LLMs use to avoid definitive claims."
patterns:
  - name: qualifier_stacking
    description: "Multiple qualifiers in a single sentence or paragraph"
  - name: epistemic_hedge
    description: "Phrases expressing unnecessary uncertainty: 'it seems', 'arguably', 'one might say'"
  - name: non_committal_framing
    description: "Positions presented without the author committing to them"
  - name: both_sides_padding
    description: "Equal weight to opposing views when one is clearly favoured"
  - name: meta_acknowledgment
    description: "Acknowledging complexity as a substitute for resolving it: 'it's complicated', 'there are many factors'"
```

- [ ] **Step 2: Write prompt.md**

```markdown
# D4: Hedging Density Detector v0.1.0

You are a specialist text analyst. Your sole task is to analyse hedging and qualification patterns that are statistically overrepresented in LLM-generated writing. You examine ONE dimension only: the density and distribution of non-committal language.

## What You Detect

You look for the **accumulation and stacking** of hedging language. The signal is in how frequently the author avoids definitive claims. Individual hedges are normal in careful writing — the diagnostic is in their density, co-occurrence, and deployment at critical junctures.

### Pattern Catalogue

1. **Qualifier Stacking** (Multiple qualifiers in a single construction)
   - "It's perhaps worth considering that this might potentially be..."
   - LLMs stack qualifiers to an unnatural degree, far beyond careful academic hedging
   - Diagnostic when: 2+ qualifiers in a single sentence, or 5+ across a paragraph

2. **Epistemic Hedges** (Expressing unnecessary uncertainty)
   - "It seems like", "One could argue", "It's arguably the case that"
   - LLMs use these to avoid making claims they might be wrong about
   - Diagnostic when: epistemic hedges appear at paragraph openings or in thesis statements

3. **Non-Committal Framing** (Presenting positions without commitment)
   - "Some might say...", "There's an argument to be made that..."
   - The author presents an idea but never owns it
   - Diagnostic when: the text contains multiple positions but the author commits to none

4. **Both-Sides Padding** (Equal weight to opposing views when one is favoured)
   - "On one hand... on the other hand..." without resolution
   - LLMs default to false balance rather than taking a position
   - Diagnostic when: opposing views are presented with identical rhetorical weight

5. **Meta-Acknowledgment** (Acknowledging complexity instead of resolving it)
   - "This is a nuanced topic", "There are many factors at play"
   - Statements about the difficulty of the topic that replace actual analysis
   - Diagnostic when: complexity acknowledgments appear without subsequent depth

## How to Score

- **0.0-0.2**: Direct, committed writing. Normal hedge density.
- **0.2-0.4**: Some hedging but appropriate for the register (academic, legal, etc.).
- **0.4-0.6**: Noticeable non-committal framing. Multiple hedge types present.
- **0.6-0.8**: Heavy hedging. Author avoids definitive claims systematically. Strongly characteristic of LLM.
- **0.8-1.0**: Pervasive hedging across every paragraph. Unedited LLM output.

## Confidence

- **High (0.8-1.0)**: Clear hedge density with multiple co-occurring types
- **Medium (0.5-0.8)**: Hedging present but could be deliberate (academic writing, legal disclaimers)
- **Low (0.0-0.5)**: Short text, domain where hedging is expected, or mixed signals

## Output Rules

1. You MUST return valid JSON matching the schema below. No markdown, no commentary outside the JSON.
2. Annotate specific spans with character offsets. Be precise.
3. Your summary should be 2-4 sentences explaining your findings in plain language.
4. Flag density and stacking, not isolated hedges.
5. When in doubt between two severity levels, choose the lower one.

## Output Schema

```json
{
  "detector_id": "D4",
  "detector_name": "Hedging Density",
  "version": "0.1.0",
  "verdict": {
    "score": 0.0,
    "confidence": 0.0,
    "summary": "string",
    "annotations": [
      {
        "span_start": 0,
        "span_end": 0,
        "pattern": "qualifier_stacking|epistemic_hedge|non_committal_framing|both_sides_padding|meta_acknowledgment",
        "severity": "high|medium|low",
        "explanation": "string"
      }
    ]
  }
}
```
```

- [ ] **Step 3: Write version snapshot and changelog**

`detectors/D4_hedging_density/versions/v0.1.0.md`:
```markdown
# D4: Hedging Density Detector v0.1.0

Initial version. See ../prompt.md for current content.

## Scope
- 5 pattern types: qualifier stacking, epistemic hedges, non-committal framing, both-sides padding, meta-acknowledgment
- Hedge density and stacking analysis
- Character-offset span annotations
- 5-band scoring scale (0.0-1.0)
```

`detectors/D4_hedging_density/CHANGELOG.md`:
```markdown
# D4 Hedging Density — Changelog

## v0.1.0 (2026-04-09)

Initial version.

- Defined 5 hedging pattern types
- Qualifier stacking and epistemic hedge detection
- Non-committal framing and false balance
- Bias toward precision over recall
```

- [ ] **Step 4: Verify and benchmark**

Run: `uv run stain detectors list` — expect D1-D4
Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml` — check D4 separation ≥ 0.30

- [ ] **Step 5: Commit**

```bash
git add detectors/D4_hedging_density/
git commit -m "feat(D4): Add Hedging Density detector — qualifier stacking and epistemic hedges"
```

---

### Task 10: D5 Structural Predictability detector

**Files:**
- Create: `detectors/D5_structural_predictability/detector.yaml`
- Create: `detectors/D5_structural_predictability/prompt.md`
- Create: `detectors/D5_structural_predictability/versions/v0.1.0.md`
- Create: `detectors/D5_structural_predictability/CHANGELOG.md`

- [ ] **Step 1: Write detector.yaml**

```yaml
id: D5
name: "Structural Predictability"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Analyses macro-structure: introduction-body-conclusion adherence, paragraph-level predictability, signpost meta-narration."
patterns:
  - name: rigid_ibc
    description: "Strict introduction-body-conclusion structure with clear delineation"
  - name: signpost_narration
    description: "Meta-commentary directing the reader: 'Let me explain', 'Here's why'"
  - name: numbered_scaffolding
    description: "Explicit enumeration used as structural crutch: 'First... Second... Third...'"
  - name: question_setup
    description: "Rhetorical questions used as section headers or transitions"
  - name: symmetrical_paragraphs
    description: "Paragraphs follow a uniform internal template"
```

- [ ] **Step 2: Write prompt.md**

```markdown
# D5: Structural Predictability Detector v0.1.0

You are a specialist text analyst. Your sole task is to analyse macro-structural patterns that are statistically overrepresented in LLM-generated writing. You examine ONE dimension only: how predictable the text's organisation and structural scaffolding is.

## What You Detect

You look for **structural templates and predictable organisation**. The signal is in how rigidly the text follows conventional structures and how explicitly it signposts its own organisation. Individual structural choices are not diagnostic — the predictability of the overall pattern is.

### Pattern Catalogue

1. **Rigid IBC** (Introduction-Body-Conclusion with clear delineation)
   - LLMs default to a clean three-act structure even when the content doesn't warrant it
   - Human writers are more likely to start in medias res, skip introductions, or trail off
   - Diagnostic when: the text follows intro→body→conclusion as if following a template

2. **Signpost Narration** (Meta-commentary directing the reader)
   - "Let me break this down", "Here's the thing", "Let me explain why"
   - LLMs narrate their own structure rather than letting it emerge
   - Diagnostic when: signposts appear at paragraph boundaries, especially 2+ instances

3. **Numbered Scaffolding** (Explicit enumeration as structural crutch)
   - "First... Second... Third..." or "There are three reasons..."
   - LLMs reach for numbered lists more than natural prose warrants
   - Diagnostic when: enumeration is used for points that don't require ordering

4. **Question Setup** (Rhetorical questions as section transitions)
   - "So what does this mean?" "But why does this matter?"
   - LLMs use questions to create artificial engagement at predictable intervals
   - Diagnostic when: questions appear at the start of paragraphs as transition devices

5. **Symmetrical Paragraphs** (Uniform internal template across paragraphs)
   - Topic sentence → supporting detail → example → transition
   - LLMs apply the same paragraph template repeatedly within a text
   - Diagnostic when: 3+ paragraphs follow an identical internal structure

## How to Score

- **0.0-0.2**: Unpredictable structure. Organic organisation.
- **0.2-0.4**: Some conventional structure but not rigid.
- **0.4-0.6**: Noticeably templated. Multiple structural indicators.
- **0.6-0.8**: Rigid structural scaffolding across the text. Strongly characteristic of LLM.
- **0.8-1.0**: Completely predictable macro-structure. Unedited LLM output.

## Confidence

- **High (0.8-1.0)**: Clear structural template with multiple indicators
- **Medium (0.5-0.8)**: Some structure but could be deliberate (professional writing, essays)
- **Low (0.0-0.5)**: Very short text, or genre where structure is expected (academic papers)

## Output Rules

1. You MUST return valid JSON matching the schema below. No markdown, no commentary outside the JSON.
2. Annotate specific spans with character offsets. Be precise.
3. Your summary should be 2-4 sentences explaining your findings in plain language.
4. Flag structural predictability across the whole text, not individual structural choices.
5. When in doubt between two severity levels, choose the lower one.

## Output Schema

```json
{
  "detector_id": "D5",
  "detector_name": "Structural Predictability",
  "version": "0.1.0",
  "verdict": {
    "score": 0.0,
    "confidence": 0.0,
    "summary": "string",
    "annotations": [
      {
        "span_start": 0,
        "span_end": 0,
        "pattern": "rigid_ibc|signpost_narration|numbered_scaffolding|question_setup|symmetrical_paragraphs",
        "severity": "high|medium|low",
        "explanation": "string"
      }
    ]
  }
}
```
```

- [ ] **Step 3: Write version snapshot and changelog**

`detectors/D5_structural_predictability/versions/v0.1.0.md`:
```markdown
# D5: Structural Predictability Detector v0.1.0

Initial version. See ../prompt.md for current content.

## Scope
- 5 pattern types: rigid IBC, signpost narration, numbered scaffolding, question setup, symmetrical paragraphs
- Macro-structure and organisation analysis
- Character-offset span annotations
- 5-band scoring scale (0.0-1.0)
```

`detectors/D5_structural_predictability/CHANGELOG.md`:
```markdown
# D5 Structural Predictability — Changelog

## v0.1.0 (2026-04-09)

Initial version.

- Defined 5 structural predictability pattern types
- Macro-structure template detection
- Signpost narration and scaffolding analysis
- Bias toward precision over recall
```

- [ ] **Step 4: Verify and benchmark**

Run: `uv run stain detectors list` — expect D1-D5
Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml` — check D5 separation ≥ 0.30

- [ ] **Step 5: Commit**

```bash
git add detectors/D5_structural_predictability/
git commit -m "feat(D5): Add Structural Predictability detector — macro-structure template detection"
```

---

### Task 11: D6 Semantic Emptiness detector

**Files:**
- Create: `detectors/D6_semantic_emptiness/detector.yaml`
- Create: `detectors/D6_semantic_emptiness/prompt.md`
- Create: `detectors/D6_semantic_emptiness/versions/v0.1.0.md`
- Create: `detectors/D6_semantic_emptiness/CHANGELOG.md`

- [ ] **Step 1: Write detector.yaml**

```yaml
id: D6
name: "Semantic Emptiness"
version: "0.1.0"
weight: 1.0
enabled: true
description: "Identifies phrases and sentences that occupy syntactic space without adding meaning. Broadening closers, filler transitions, restated premises."
patterns:
  - name: broadening_closer
    description: "Final sentences that widen scope without adding: 'and that's what makes this so important'"
  - name: filler_transition
    description: "Transition phrases that add no information: 'With that said', 'Moving on'"
  - name: restated_premise
    description: "Repeating an earlier point in different words without advancing the argument"
  - name: empty_emphasis
    description: "Intensifiers that add no meaning: 'truly', 'really', 'absolutely', 'fundamentally'"
  - name: circular_conclusion
    description: "Conclusion that merely restates the introduction"
```

- [ ] **Step 2: Write prompt.md**

```markdown
# D6: Semantic Emptiness Detector v0.1.0

You are a specialist text analyst. Your sole task is to identify phrases and sentences that occupy syntactic space without contributing meaning. You examine ONE dimension only: semantic content density.

## What You Detect

You look for **text that sounds meaningful but adds nothing**. The signal is in sentences and phrases that could be removed without any loss of information. Individual filler words are not diagnostic — the density of semantically empty constructions across the text is.

### Pattern Catalogue

1. **Broadening Closers** (Final sentences that widen scope without adding)
   - "And that's what makes this so important"
   - "This is exactly what the world needs right now"
   - LLMs end paragraphs and posts with grandiose closers that contain no specific information
   - Diagnostic when: closing sentences generalize rather than conclude with specifics

2. **Filler Transitions** (Connecting phrases that add no information)
   - "With that said", "That being said", "Moving on", "Now let's talk about"
   - These exist only to bridge paragraphs — removing them loses nothing
   - Diagnostic when: 3+ filler transitions in a text, especially at paragraph boundaries

3. **Restated Premises** (Repeating earlier points in different words)
   - Saying "communication is key" in paragraph 1 and "the importance of clear communication cannot be overstated" in paragraph 4
   - LLMs pad text by restating rather than advancing
   - Diagnostic when: the same idea appears in 2+ places with only surface-level variation

4. **Empty Emphasis** (Intensifiers that add no meaning)
   - "Truly remarkable", "Really important", "Absolutely essential", "Fundamentally different"
   - These modifiers feel emphatic but carry no additional information
   - Diagnostic when: empty intensifiers appear at higher density than natural writing

5. **Circular Conclusions** (Ending by restating the beginning)
   - The conclusion merely rephrases the introduction or thesis statement
   - LLMs default to "bookend" structures that feel complete but add nothing
   - Diagnostic when: the final paragraph's core claim is semantically identical to the first paragraph's

## How to Score

- **0.0-0.2**: Dense, information-rich writing. Every sentence advances the argument.
- **0.2-0.4**: Minor filler but mostly substantive.
- **0.4-0.6**: Noticeable padding. Some sentences removable without loss.
- **0.6-0.8**: Significant semantic emptiness. Multiple paragraphs contain vacuous content. Strongly characteristic of LLM.
- **0.8-1.0**: Pervasive emptiness. Most paragraphs contain at least one sentence that says nothing. Unedited LLM output.

## Confidence

- **High (0.8-1.0)**: Clear semantic emptiness with multiple indicators
- **Medium (0.5-0.8)**: Some emptiness but could be rhetorical choice (motivational writing, speeches)
- **Low (0.0-0.5)**: Very short text or genre where emphasis is expected

## Output Rules

1. You MUST return valid JSON matching the schema below. No markdown, no commentary outside the JSON.
2. Annotate specific spans with character offsets. Be precise.
3. Your summary should be 2-4 sentences explaining your findings in plain language.
4. Flag density of empty constructions, not individual filler words.
5. When in doubt between two severity levels, choose the lower one.

## Output Schema

```json
{
  "detector_id": "D6",
  "detector_name": "Semantic Emptiness",
  "version": "0.1.0",
  "verdict": {
    "score": 0.0,
    "confidence": 0.0,
    "summary": "string",
    "annotations": [
      {
        "span_start": 0,
        "span_end": 0,
        "pattern": "broadening_closer|filler_transition|restated_premise|empty_emphasis|circular_conclusion",
        "severity": "high|medium|low",
        "explanation": "string"
      }
    ]
  }
}
```
```

- [ ] **Step 3: Write version snapshot and changelog**

`detectors/D6_semantic_emptiness/versions/v0.1.0.md`:
```markdown
# D6: Semantic Emptiness Detector v0.1.0

Initial version. See ../prompt.md for current content.

## Scope
- 5 pattern types: broadening closers, filler transitions, restated premises, empty emphasis, circular conclusions
- Semantic content density analysis
- Character-offset span annotations
- 5-band scoring scale (0.0-1.0)
```

`detectors/D6_semantic_emptiness/CHANGELOG.md`:
```markdown
# D6 Semantic Emptiness — Changelog

## v0.1.0 (2026-04-09)

Initial version.

- Defined 5 semantic emptiness pattern types
- Content density and filler detection
- Broadening closer and circular conclusion analysis
- Bias toward precision over recall
```

- [ ] **Step 4: Verify and benchmark**

Run: `uv run stain detectors list` — expect D1-D6, all enabled
Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml` — check D6 separation ≥ 0.30

- [ ] **Step 5: Commit**

```bash
git add detectors/D6_semantic_emptiness/
git commit -m "feat(D6): Add Semantic Emptiness detector — content density and filler analysis"
```

---

### Task 12: Update benchmark config for all detectors + enable in stain.config.yaml

**Files:**
- Modify: `benchmarks/cerebras_qwen235b.yaml`
- Modify: `stain.config.yaml`

- [ ] **Step 1: Update benchmark config to include all detectors**

In `benchmarks/cerebras_qwen235b.yaml`, change:

```yaml
detectors: [D1]
```

to:

```yaml
detectors: [D1, D2, D3, D4, D5, D6]
```

- [ ] **Step 2: Remove hardcoded detector block from stain.config.yaml**

The `detectors:` block in `stain.config.yaml` is now redundant — detector metadata lives in `detector.yaml` files. Remove the `detectors:` section entirely from `stain.config.yaml`. The registry handles discovery and enablement.

- [ ] **Step 3: Run full 6-detector benchmark**

Run: `uv run stain benchmark run benchmarks/cerebras_qwen235b.yaml`

Check:
- All 6 detectors produce results for all 23 corpus files
- Each detector achieves separation ≥ 0.30
- Total failures ≤ 2/138 (23 files × 6 detectors)

- [ ] **Step 4: Commit**

```bash
git add benchmarks/cerebras_qwen235b.yaml stain.config.yaml
git commit -m "feat: Enable all 6 detectors in benchmark and config"
```

---

### Task 13: Inter-detector correlation analysis + devlog

**Files:**
- Modify: `devlog.yaml`

- [ ] **Step 1: Run benchmark and collect per-detector scores**

After the full 6-detector benchmark run, examine the results to identify which detectors correlate (fire together on the same samples) and which provide independent signal.

- [ ] **Step 2: Record findings in devlog**

Append to `devlog.yaml`:

```yaml
- id: "011"
  date: "2026-04-XX"  # Use actual date
  title: "Ring 1 complete — 6-detector benchmark results"
  type: finding
  context: |
    All 6 detectors built and benchmarked. First full-suite evaluation
    against the 23-sample corpus.
  finding: |
    [Record actual benchmark results here: per-detector scores,
    separation, correlation between detectors, composite accuracy,
    any detectors that underperformed the ≥0.30 threshold]
  artifacts:
    - results/benchmarks/{run_id}/
```

- [ ] **Step 3: Commit**

```bash
git add devlog.yaml
git commit -m "docs: Record Ring 1 completion benchmark in devlog"
```

---

## Self-Review

**Spec coverage:**
- ✅ Detector plugin system (Tasks 1-2)
- ✅ Audit logging (Task 3)
- ✅ Prompt registry — achieved via registry.py loading prompt.md from each detector dir (Task 2)
- ✅ Wiring into existing code (Task 4)
- ✅ CLI for detector listing (Task 5)
- ✅ Config updates (Task 6)
- ✅ D2-D6 detectors (Tasks 7-11)
- ✅ Full benchmark run (Task 12)
- ✅ Correlation analysis (Task 13)
- ✅ Multi-model validation config added (Task 6) — actual validation runs deferred to when 3rd model benchmarked

**Placeholder scan:** Task 13 step 2 contains `[Record actual benchmark results here]` — this is intentional because the results don't exist yet. The engineer fills this in from actual benchmark output.

**Type consistency:** `DetectorInfo` used consistently across registry.py, detector.py, and cli.py. `AuditEntry` and `AuditLogger` used consistently across audit.py and detector.py. `discover_detectors()` returns `dict[str, DetectorInfo]` everywhere.
