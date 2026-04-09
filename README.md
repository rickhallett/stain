<p align="center">
  <h1 align="center">Stain</h1>
  <p align="center">
    Multi-agent text analysis pipeline that surfaces LLM generation patterns
    <br />
    <em>Detect AI slop through rhetorical pattern analysis, sentence rhythm, and lexical diversity.</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/litellm-provider%20agnostic-orange?logo=openai&logoColor=white" alt="litellm" />
  <img src="https://img.shields.io/badge/cerebras-qwen3%20235B-purple" alt="Cerebras" />
</p>

---

## What is Stain?

Stain analyses text for LLM generation patterns. Six detectors examine rhetorical structure, sentence rhythm, lexical diversity, and other linguistic signals to surface the tells that distinguish machine-generated prose from human writing.

The pipeline is provider-agnostic (all inference via litellm), content-addressed (every benchmark run is keyed by config hash + timestamp), and designed for repeatable evaluation across models.

## Detectors

| ID | Focus |
|----|-------|
| D1 | Rhetorical pattern analysis |
| D2 | Sentence rhythm and cadence |
| D3 | Lexical diversity |
| D4 | Structural markers |
| D5 | Hedging and qualification patterns |
| D6 | Composite signal aggregation |

Each detector has a versioned prompt in `detectors/`, tracked by SHA256 hash.

## Architecture

```
stain/
├── src/stain/
│   ├── cli.py              Entry point (Click)
│   ├── detector.py         Core detection logic
│   ├── discovery.py        Text source discovery
│   ├── benchmark.py        Repeatable model evaluation
│   ├── corpus.py           Corpus management
│   ├── generate.py         Synthetic text generation
│   ├── research.py         Research pipeline (integrates with Arcana)
│   ├── orchestrator.py     Multi-agent orchestration
│   ├── registry.py         Detector registry
│   ├── audit.py            Audit trail
│   └── models.py           Pydantic data models
├── detectors/              Versioned prompt files (D1–D6)
├── benchmarks/             YAML configs for repeatable evaluation
├── results/benchmarks/     Content-addressed benchmark output
├── devlog.yaml             Chronological decision log (append-only)
└── tests/
```

## Usage

```bash
# Install
uv sync

# Run analysis on a text file
stain analyse input.txt

# Run a benchmark
stain benchmark run benchmarks/cerebras-qwen3.yaml

# Compare benchmark runs
stain benchmark compare results/benchmarks/run_a results/benchmarks/run_b
```

## Model Selection

Cerebras Qwen3 235B is the default detector model. In a three-way benchmark it achieved 100% classification accuracy at θ=0.50, 0.371 separation, zero failures, sub-1s latency. See `devlog.yaml#004` for the full evaluation.

## Design Principles

- **Content-addressed outputs.** Benchmark runs keyed by config hash + timestamp. Prompts tracked by SHA256. Nothing silently overwritten.
- **Provider-agnostic inference.** All LLM calls through litellm. Swap models by changing a config string.
- **Validate model output.** Small models produce garbage offsets. The annotation validation pipeline repairs what it can and marks the rest.
- **Record artifacts by default.** If a decision was made, it should be traceable.

## Related

- [Tells / Sloptics](https://www.sloptics.dev/) — The field taxonomy of LLM output failure modes that Stain's detectors are calibrated against.
- [Arcana](https://github.com/rickhallett/arcana) — Multi-agent research pipeline. Stain's research module integrates with Arcana for document analysis.

## License

MIT
