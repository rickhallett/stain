# Stain

**Pattern density profiler for LLM-generated text.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![litellm](https://img.shields.io/badge/litellm-provider%20agnostic-orange?logo=openai&logoColor=white)
![PyPI](https://img.shields.io/badge/pypi-stain--cli-green)

---

## What is Stain?

Stain is not an AI detector. It does not answer "was this written by AI?" It answers **"how much does this text sound like AI, and where?"** Six independent LLM-backed detectors examine rhetorical patterns, sentence rhythm, lexical diversity, hedging density, structural predictability, and semantic emptiness. The composite score measures pattern density, not provenance.

## Install

```bash
pip install stain-cli

# or with uv
uv pip install stain-cli
```

Set your API key in `.env` or environment:

```bash
export CEREBRAS_API_KEY=your-key-here
```

## Quickstart

```bash
# Analyse a file
stain analyse post.txt

# Pipe from stdin
cat essay.txt | stain analyse -

# Analyse a URL
stain analyse https://example.com/blog-post

# Score only (CI-friendly)
stain analyse post.txt --score

# HTML report opened in browser
stain analyse post.txt --serve

# JSON to stdout
stain analyse post.txt --json

# HTML to file
stain analyse post.txt --html > report.html
```

## Detectors

| ID | Name | What it measures |
|----|------|------------------|
| D1 | Rhetorical Pattern | Correctio, tricolon, false balance, escalation, anaphora, semantic couplets, pivot conjunctions |
| D2 | Sentence Rhythm | Length variance, cadence regularity, burstiness, paragraph symmetry, opener templates |
| D3 | Lexical Diversity | Type-token ratio, phrase recycling, register flattening, synonym avoidance, filler vocabulary |
| D4 | Hedging Density | Qualifier stacking, epistemic hedges, non-committal framing, both-sides padding, meta acknowledgment |
| D5 | Structural Predictability | Rigid intro-body-conclusion, signpost narration, numbered scaffolding, question setups, symmetrical paragraphs |
| D6 | Semantic Emptiness | Broadening closers, filler transitions, restated premises, empty emphasis, circular conclusions |

Each detector runs independently with a versioned prompt. Results are combined into a weighted composite score. See [docs/detectors.md](docs/detectors.md) for full pattern descriptions.

## Output Modes

| Flag | Mode | Description |
|------|------|-------------|
| *(default)* | rich | Coloured table with per-detector scores, annotations, highlighted spans |
| `--json` | json | Full result object. Falls back to this when stdout is not a TTY |
| `--plain` | plain | One-line summary per input |
| `--score` | score | Bare composite score. Useful for scripting and CI |
| `--html` | html | Self-contained HTML report to stdout |
| `--serve` | serve | Renders HTML report and opens it in the default browser |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Score below threshold (default: 0.55) |
| 1 | Score at or above threshold |
| 2 | Input error (file not found, empty input) |
| 3 | API/LLM error |

The threshold is configurable: `stain analyse post.txt --threshold 0.40`

## Discovery

Stain has a self-teaching loop. The discovery pipeline runs all six detectors against a text, then asks a separate LLM pass to identify **patterns the existing detectors missed**.

```bash
# Run discovery on a file
stain discover post.txt

# Run discovery across a corpus tier
stain discover --corpus ai

# Review hypotheses
stain discover list

# Approve a hypothesis (scaffolds a new detector)
stain discover approve <hypothesis-id>

# Promote approved patterns into the detector registry
stain discover promote
```

See [docs/methodology.md](docs/methodology.md) for the theory behind the self-teaching loop.

## Configuration

Config resolution is cascading:

1. Explicit path: `stain analyse post.txt --config my.yaml`
2. Local: `stain.config.yaml` in the current directory
3. User: `~/.config/stain/config.yaml`
4. Package defaults

Initialize user config:

```bash
stain init
```

Model selection uses litellm format (`provider/model`). The default detector model is `cerebras/qwen-3-235b-a22b-instruct-2507`.

## MCP Server

Stain exposes an MCP (Model Context Protocol) server for editor integrations:

```bash
stain mcp serve
```

## Documentation

- [Detector Reference](docs/detectors.md) -- full pattern descriptions for all six detectors
- [Extending Stain](docs/extending.md) -- how to create new detectors
- [Methodology](docs/methodology.md) -- the thesis behind multi-agent detection

## Related

- [Sloptics](https://www.sloptics.dev/) -- field taxonomy of LLM output failure modes
- [Arcana](https://github.com/rickhallett/arcana) -- multi-agent research pipeline

## License

MIT
