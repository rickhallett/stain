# Stain Roadmap — Concentric Rings Design

**Author:** Kai Hallett (Oceanheart.ai)
**Date:** 2026-04-09
**Status:** Approved
**Approach:** Concentric Rings — harden the core, extend outward

---

## Context

Stain v0.1.0 (Phase 1 POC) proved the thesis: a single detector (D1 Rhetorical Pattern) achieves 100% classification accuracy at θ=0.50 with 0.371 separation across a 23-sample corpus using Cerebras Qwen3 235B at sub-second latency.

This document defines the roadmap from POC to battle-hardened, data-saturated, developer-native, terminal-centric, AI-integrated power tool.

### Design Decisions

- **Personal tool first.** Optimise for the operator's workflow. UX for external users comes last (Ring 6).
- **Primary use case:** Auditing other people's text — clients, contractors, LinkedIn posts. Stain quantifies what the slopodar detects intuitively.
- **All input paths:** File, stdin, URL. Whatever gets text into the pipe fastest.
- **All 6 detectors are load-bearing**, plus the system must be extensible with arbitrary new detectors.
- **Discovery pipeline:** Pipe Stain output into LLM rounds to surface new pattern categories.
- **Research pipeline:** Ingest arXiv papers, extract hypotheses, generate candidate detector specs.
- **Human-in-the-loop:** Machine proposes, operator approves. Nothing enters the active detector suite without sign-off.
- **Stratified corpus:** Automated bulk corpus for statistical confidence, hand-curated gold corpus as ground truth.

---

## Cross-Cutting Concerns

These three apply across all rings. They are infrastructure that Ring 1 builds and every subsequent ring inherits.

### 1. Prompt Registry

Every LLM call in Stain loads its prompt from a versioned file. Zero prompt strings in Python code.

Convention:
```
detectors/
├── D1_rhetorical_pattern/
│   ├── prompt.md               # System prompt, semver in frontmatter
│   ├── detector.yaml           # ID, name, version, weight, pattern catalogue
│   └── versions/               # Historical prompt versions
agents/
├── discovery/
│   ├── prompt.md
│   ├── agent.yaml              # Role, model tier, output schema
│   └── versions/
├── research_extract/
│   ├── prompt.md
│   ├── agent.yaml
│   └── versions/
├── research_relevance/
│   ├── prompt.md
│   ├── agent.yaml
│   └── versions/
└── corpus_generate/
    ├── prompt.md
    ├── agent.yaml
    └── versions/
```

Every prompt file:
- SHA256 hash tracked per invocation
- Semver in frontmatter
- `versions/` directory for history
- Associated YAML declares model tier, output schema, weight

The Python prompt loader is a single generic function: point it at a directory, it finds `prompt.md`. No detector-specific maps. No agent-specific maps.

### 2. Audit Logging

Every LLM interaction is logged immutably. Full provenance chain from input text to final verdict.

```
.stain/
├── audit/
│   ├── {YYYY-MM-DD}/
│   │   └── {timestamp}_{operation}_{hash}.jsonl
│   └── index.yaml
└── audit.yaml                  # Config: retention, verbosity, storage path
```

Each log entry captures:
- Timestamp, operation type, detector/agent ID
- Model used, prompt hash, prompt version
- Input hash, input length
- Request content hash (or full content at `full` verbosity)
- Response hash, parsed score, annotation counts, validity
- Latency, token counts, model response ID

Verbosity levels:
- `full` — raw request/response content (debugging)
- `hashes` — hashes only, no raw content (default)
- `off` — disabled (not recommended)

Applies to every LLM call: detector runs, discovery agent, research extraction, corpus generation. Same schema, different `operation` field.

**What this enables:**
- Any annotation traceable to exact prompt version, model, and input
- Bias detection via aggregated scoring patterns
- Regression hunting across prompt versions
- Cost tracking across all operations
- Combined with git: prompt version (git) + audit log (runtime) = complete reproducibility

### 3. Multi-Model Validation

No single model's biases should become Stain's biases. Promotion decisions are validated across at least 2 model families from different training lineages.

```yaml
# stain.config.yaml
validation:
  enabled: true
  min_models: 2
  models:
    primary: cerebras/qwen-3-235b-a22b-instruct-2507
    validators:
      - groq/llama-3.3-70b-versatile
      - anthropic/claude-haiku-4-5-20251001
  require_for:
    - detector_benchmark
    - discovery_hypothesis
    - corpus_label
  skip_for:
    - interactive_analyse
    - corpus_generate
```

Consensus modes:
- **Unanimous** — all models agree (detector promotion)
- **Majority** — ≥ 2 of 3 agree (discovery hypotheses)
- **Divergence report** — run all, report disagreements without gating (research)

Model families must have distinct training lineages (not two Llama variants). Current candidates: Qwen (Cerebras) + Llama (Groq) + one of {Claude, Mistral, DeepSeek}.

A `stain validate` command runs primary + validators and reports divergence. Divergence metrics logged to audit trail. Alerts when model agreement drops below configurable threshold.

---

## Ring 1: Complete Detection Engine

**Goal:** Full 6-detector suite running through a plugin architecture. Each detector independently benchmarked. Adding new detectors requires zero code changes.

### Detector Plugin System

The engine discovers detectors by scanning `detectors/*/detector.yaml`. The hardcoded `DETECTOR_DIR_MAP` and `DETECTOR_NAMES` dicts in `detector.py` are replaced by dynamic discovery.

`detector.yaml` schema:
```yaml
id: D1
name: "Rhetorical Pattern"
version: "0.1.0"
weight: 1.0
enabled: true
patterns:
  - name: correctio
    description: "Not X — it's Y pivot"
  - name: tricolon_closer
    description: "Three-part rhetorical list"
  # ...
```

Adding a new detector = create a directory with `prompt.md` + `detector.yaml`. The engine picks it up automatically.

### Detector Build Order

Each detector is written, benchmarked against the full corpus, and must achieve ≥0.30 separation before the next one starts:

1. **D2 Sentence Rhythm** — Sentence length variance, paragraph cadence regularity, burstiness. Humans are erratic; LLMs are metronomic.
2. **D3 Lexical Diversity** — Type-token ratio, vocabulary narrowness within register.
3. **D4 Hedging Density** — Qualifier stacking, epistemic hedges, non-committal framing.
4. **D5 Structural Predictability** — Macro-structure adherence, signpost meta-narration.
5. **D6 Semantic Emptiness** — Phrases occupying syntactic space without adding meaning.

### Composite Scoring Update

With 6 detectors:
- Inter-detector correlation analysis after all 6 are running
- Redundant detectors get weights reduced automatically
- Composite confidence = weighted harmonic mean of individual confidences

---

## Ring 2: Input & Output Hardening

**Goal:** Stain becomes a Unix citizen. Pipe it, script it, chain it.

### Input Paths

```bash
stain analyse post.txt                              # File (existing)
pbpaste | stain analyse -                           # Stdin
stain analyse https://linkedin.com/posts/someone/   # URL (fetch + strip HTML)
stain analyse posts/*.txt                           # Multiple files
```

URL fetching uses a lightweight HTML-to-text extractor (trafilatura or readability-lxml). Extract article body, discard chrome.

### Output Modes

```bash
stain analyse post.txt                # Rich (default when TTY)
stain analyse post.txt --json         # JSON (default when piped)
stain analyse post.txt --plain        # Minimal one-liner
stain analyse post.txt --score        # Score only (for scripting)
```

Auto-detection: TTY → rich, piped → JSON. Explicit flags always override.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Score below threshold |
| 1 | Score at or above threshold |
| 2 | Input error |
| 3 | API/model error |

Default threshold: `--threshold 0.55` (from benchmark data). Overridable.

### Pipe Composability

```bash
stain analyse post.txt --json | jq '.detector_results[] | {detector: .detector_name, score: .verdict.score}'
for f in posts/*.txt; do echo "$f: $(stain analyse "$f" --score)"; done
stain analyse post.txt --json | stain discover --from-analysis -
```

---

## Ring 3: Corpus Infrastructure

**Goal:** Scale from 23 samples to hundreds, stratified into two tiers.

### Two-Tier Corpus

```
corpus/
├── gold/                       # Hand-curated, operator-labelled
│   ├── known_human/
│   ├── known_llm/
│   └── manifest.yaml
├── bulk/                       # Machine-generated, spot-checked
│   ├── known_human/
│   ├── known_llm/
│   └── manifest.yaml
├── ambiguous/
└── corpus.yaml
```

Current `known_human/` and `known_llm/` migrate into `gold/`. Gold set is the final exam.

### Bulk Corpus Generator

```bash
stain corpus generate --type llm --count 50 --domain linkedin,blog,marketing
stain corpus generate --type human --count 50 --sources sivers,pg,archive
stain corpus generate --type llm --count 20 --model claude-haiku --temp 0.3,0.7,1.0
```

LLM generation varies: model, temperature, domain, prompt specificity.
Human scraping: pre-2020 blog posts from configurable author lists, Internet Archive fallback.

### Corpus Management CLI

```bash
stain corpus stats                                          # Show counts per tier
stain corpus label corpus/ambiguous/file.txt --as human     # Promote to gold
stain corpus validate                                       # Check manifests, dedup
stain benchmark run config.yaml --corpus gold               # Benchmark against tier
```

---

## Ring 4: Discovery Pipeline

**Goal:** Stain analyses its own output to surface pattern categories the existing detectors don't cover.

### The Loop

```
INPUT TEXT → EXISTING DETECTORS → STRUCTURED RESULTS
    → DISCOVERY AGENT (Sonnet-tier) → CANDIDATE HYPOTHESES
    → OPERATOR REVIEW → CANDIDATE DETECTOR SPEC
    → AUTOMATED BENCHMARK (≥0.30 separation on gold)
    → PROMOTION
```

The discovery agent receives: original text, all detector verdicts, the active pattern catalogue. Its job: find what detectors missed.

Hypothesis output schema:
```json
{
  "hypotheses": [
    {
      "pattern_name": "manufactured_consensus",
      "description": "Phrases implying broad agreement without evidence",
      "examples_found": ["...spans..."],
      "confidence": 0.7,
      "suggested_detector": "New detector or extension of existing"
    }
  ]
}
```

### CLI

```bash
stain discover post.txt                          # Run detectors + meta-analysis
stain discover --corpus gold                     # Aggregate across corpus
stain discover list                              # Show unreviewed candidates
stain discover approve "manufactured_consensus"  # Scaffold candidate detector
stain discover promote D7                        # Enable after benchmark passes
```

### Hypothesis Persistence

```
discovery/
├── hypotheses.yaml              # All candidates, status
├── runs/{timestamp}.json        # Raw discovery output per run
└── evidence/{pattern_name}/     # Collected evidence across runs
```

Hypotheses accumulate. Frequency and recurrence surfaced in `stain discover list`.

---

## Ring 5: Research Pipeline

**Goal:** Ingest academic literature, extract testable hypotheses, feed into discovery pipeline.

### Architecture

```
arXiv / Semantic Scholar API → FETCH + FILTER
    → PAPER STORE → EXTRACTION AGENT (Sonnet-tier, prompt from agents/research_extract/prompt.md)
    → CANDIDATE HYPOTHESES (same schema as Ring 4)
    → MERGE WITH DISCOVERY HYPOTHESES → OPERATOR REVIEW
```

### Paper Store

```
research/
├── papers/{arxiv_id}.json       # Metadata
├── extractions/{arxiv_id}.json  # Extracted hypotheses
├── notebooks/                   # Jupyter research notes (from Ring 1 onward)
│   ├── 001_benchmark_analysis.ipynb
│   ├── 002_detector_correlation.ipynb
│   └── ...
├── index.yaml                   # Master index
└── config.yaml                  # Search terms, sources
```

### Research Notebooks

Jupyter notebooks serve as living research documents from the start. Each notebook combines narrative, code, and visualisation in a format that can be exported to blog posts (nbconvert → markdown) or presentations (RISE / reveal.js).

Notebook conventions:
- Numbered prefix for ordering: `001_`, `002_`, etc.
- Self-contained: each notebook re-runs against current data
- Git-tracked alongside the code they analyse
- Used for: benchmark analysis, detector evaluation, corpus studies, discovery findings, paper reviews

Search strategy: "LLM-generated text detection", "AI writing stylometry", etc. Filter by post-2022, cited ≥5, contains methodology.

### CLI

```bash
stain research fetch                 # Pull new papers
stain research extract               # Run extraction on unprocessed papers
stain research list                  # Show research-derived hypotheses
stain research show 2312.12345       # Paper detail
stain research update                # Full pipeline: fetch → extract → list
```

### Merge with Discovery

Research and discovery hypotheses share the same schema and review queue:

```
PENDING HYPOTHESES:
  [discovery] manufactured_consensus — seen in 8/50 samples
  [research]  syntactic_entropy — from arXiv:2312.12345
```

Same approval flow: approve → scaffold → benchmark → promote.

---

## Ring 6: Distribution & Visualization

**Goal:** Make Stain usable by others. Only after battle-tested by its creator.

### Distribution

```bash
pip install stain-cli
# or
uv tool install stain-cli
```

First run `stain init` creates `~/.config/stain/config.yaml`, prompts for API key, copies default detector suite.

Config resolution: local `stain.config.yaml` → `~/.config/stain/config.yaml` → package defaults.

### MCP Server

```bash
stain mcp serve
```

Exposes tools: `analyse_text`, `analyse_file`, `list_detectors`, `get_detector_info`. For editor integration (VS Code, Cursor, Claude Code).

### Browser Visualization

```bash
stain analyse post.txt --html > report.html
stain analyse post.txt --serve    # Opens localhost:8420
```

Self-contained HTML: colour-coded annotation overlay, per-span tooltips, composite score dashboard, per-detector breakdown. Inline CSS/JS, no external dependencies, works offline.

### Documentation

- `README.md` — install, quickstart, examples
- `docs/detectors.md` — what each detector looks for
- `docs/extending.md` — how to write a new detector
- `docs/methodology.md` — why multi-agent, the slopodar thesis

---

## Dependency Graph

```
Ring 1 ─── Ring 2 ─── Ring 3 ─── Ring 4 ─── Ring 5 ─── Ring 6
  │                     │          │          │
  │                     │          └──────────┘
  │                     │          (hypotheses merge)
  │                     │
  │                     └── bulk corpus feeds benchmark
  │
  └── plugin system used by all subsequent rings

Cross-cutting (from Ring 1 onward):
  ├── Prompt Registry
  ├── Audit Logging
  └── Multi-Model Validation
```

Each ring is independently valuable. The operator has a better tool after completing any ring.

---

## Open Questions

1. **Validator model selection.** Third model family TBD — benchmark Anthropic Haiku, Mistral, and DeepSeek to find the best cost/accuracy/latency balance.
2. **Audit log storage.** JSONL files are simple but may need rotation/compression at high volume. Evaluate after Ring 3 corpus scaling reveals actual log volume.
3. **Discovery agent model tier.** Specified as Sonnet-tier. May need evaluation — if Qwen 235B handles meta-analysis well, the cost saving is significant.
4. **Inter-detector correlation.** How to measure and auto-reduce weights for redundant detectors. Deferred to after Ring 1 completion when all 6 detectors produce data.
5. **Multi-modal beyond text.** Spec covers text only. Image/video content analysis is a potential future extension but out of scope for this roadmap.
6. **Adversarial robustness.** As LLMs improve, detection becomes harder. The discovery + research pipelines are the hedge — continuously surfacing new signals as old ones degrade.
