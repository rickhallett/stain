"""Benchmark harness — repeatable model evaluation against corpus.

Runs a benchmark config (model × detectors × corpus) and writes
immutable, content-addressed results to results/benchmarks/.

Usage:
    stain benchmark run benchmarks/qwen235b.yaml
    stain benchmark run benchmarks/groq_70b.yaml
    stain benchmark compare results/benchmarks/<hash_a> results/benchmarks/<hash_b>
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from stain import __version__
from stain.audit import AuditLogger
from stain.detector import run_detector

console = Console()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkConfig:
    """What to run."""
    name: str
    model: str
    detectors: list[str]
    corpus_dirs: list[str]
    max_retries: int = 3
    retry_delay: float = 5.0
    delay_between: float = 0.5  # seconds between calls

    def config_hash(self) -> str:
        """Deterministic hash of the config for content-addressing."""
        blob = json.dumps({
            "name": self.name,
            "model": self.model,
            "detectors": sorted(self.detectors),
            "corpus_dirs": sorted(self.corpus_dirs),
        }, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    @classmethod
    def from_yaml(cls, path: Path) -> "BenchmarkConfig":
        with open(path) as f:
            raw = yaml.safe_load(f)
        corpus_tier = raw.get("corpus_tier")
        corpus_dirs = resolve_corpus_dirs(
            tier=corpus_tier,
            corpus_root=raw.get("corpus_root", "corpus"),
            explicit_dirs=raw.get("corpus_dirs"),
        )
        return cls(
            name=raw["name"],
            model=raw["model"],
            detectors=raw.get("detectors", ["D1"]),
            corpus_dirs=corpus_dirs,
            max_retries=raw.get("max_retries", 3),
            retry_delay=raw.get("retry_delay", 5.0),
            delay_between=raw.get("delay_between", 0.5),
        )


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------

@dataclass
class SampleResult:
    file: str
    label: str                    # known_human | known_llm
    detector_id: str
    score: float | None = None
    confidence: float | None = None
    annotations_total: int = 0
    annotations_valid: int = 0
    annotations_invalid: int = 0
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
    raw_annotations: list[dict] = field(default_factory=list)


@dataclass
class BenchmarkRun:
    config_hash: str
    config: dict
    stain_version: str
    timestamp: str
    run_duration_ms: int
    samples: list[dict]
    summary: dict


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def resolve_corpus_dirs(
    tier: str | None,
    corpus_root: str = "corpus",
    explicit_dirs: list[str] | None = None,
) -> list[str]:
    """Resolve corpus directories from tier name or explicit paths.

    If explicit_dirs is set, returns those directly.
    If tier is set, returns [corpus_root/tier/known_human, corpus_root/tier/known_llm].
    Otherwise defaults to gold tier.
    """
    if explicit_dirs:
        return explicit_dirs
    if tier:
        root = Path(corpus_root)
        return [
            str(root / tier / "known_human"),
            str(root / tier / "known_llm"),
        ]
    return [f"{corpus_root}/gold/known_human", f"{corpus_root}/gold/known_llm"]


def _collect_files(corpus_dirs: list[str]) -> list[Path]:
    files = []
    for d in corpus_dirs:
        p = Path(d)
        if p.exists():
            files.extend(sorted(p.glob("*.txt")))
    return files


def _run_with_retry(
    detector_id: str,
    text: str,
    model: str,
    max_retries: int,
    retry_delay: float,
    audit_logger: AuditLogger | None = None,
):
    """Run detector with exponential backoff on rate limits."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return run_detector(detector_id, text, model=model, audit_logger=audit_logger)
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "rate limit" in err_str or "ratelimit" in type(e).__name__.lower():
                wait = retry_delay * (2 ** attempt)
                console.print(f"    [dim]⏳ rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})[/dim]")
                time.sleep(wait)
            elif "too large" in err_str or "context" in err_str:
                raise  # context window exceeded, no retry
            else:
                raise
    raise last_err  # type: ignore[misc]


def run_benchmark(config: BenchmarkConfig) -> Path:
    """Execute a benchmark run and write results to disk.

    Returns the path to the results directory.
    """
    files = _collect_files(config.corpus_dirs)
    if not files:
        raise FileNotFoundError(f"No .txt files found in {config.corpus_dirs}")

    cfg_hash = config.config_hash()
    ts = datetime.now(timezone.utc)
    run_id = f"{ts.strftime('%Y%m%d_%H%M%S')}_{cfg_hash}"
    out_dir = Path("results/benchmarks") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold]Benchmark:[/bold] {config.name}")
    console.print(f"[bold]Model:[/bold]     {config.model}")
    console.print(f"[bold]Detectors:[/bold] {', '.join(config.detectors)}")
    console.print(f"[bold]Corpus:[/bold]    {len(files)} files")
    console.print(f"[bold]Config:[/bold]    {cfg_hash}")
    console.print()

    audit_logger = AuditLogger(enabled=True)

    run_start = time.monotonic()
    samples: list[SampleResult] = []

    for i, filepath in enumerate(files):
        text = filepath.read_text()
        label = filepath.parent.name

        for det_id in config.detectors:
            sr = SampleResult(
                file=filepath.name,
                label=label,
                detector_id=det_id,
            )
            try:
                r = _run_with_retry(
                    det_id, text, config.model,
                    config.max_retries, config.retry_delay,
                    audit_logger=audit_logger,
                )
                sr.score = r.verdict.score
                sr.confidence = r.verdict.confidence
                sr.annotations_total = len(r.verdict.annotations)
                sr.annotations_valid = r.verdict.annotations_valid
                sr.annotations_invalid = r.verdict.annotations_invalid
                sr.latency_ms = r.meta.latency_ms
                sr.tokens_in = r.meta.tokens_in
                sr.tokens_out = r.meta.tokens_out
                sr.raw_annotations = [a.model_dump(mode="json") for a in r.verdict.annotations]

                flag = "🟢" if label == "known_human" else "🔴"
                v = "✅" if sr.annotations_invalid == 0 else f"⚠️  {sr.annotations_invalid} bad"
                console.print(
                    f"  {flag} {sr.score:.2f} ({sr.confidence:.2f}) "
                    f"{v} {sr.latency_ms:>5}ms  {det_id} {filepath.name}"
                )
            except Exception as e:
                sr.error = str(e)[:300]
                console.print(f"  ❌ {det_id} {filepath.name}: {sr.error[:100]}")

            samples.append(sr)

            if i < len(files) - 1 or det_id != config.detectors[-1]:
                time.sleep(config.delay_between)

    run_duration_ms = int((time.monotonic() - run_start) * 1000)

    # Build summary
    summary = _build_summary(samples, config)

    # Write results
    run_data = BenchmarkRun(
        config_hash=cfg_hash,
        config=asdict(config),
        stain_version=__version__,
        timestamp=ts.isoformat(),
        run_duration_ms=run_duration_ms,
        samples=[asdict(s) for s in samples],
        summary=summary,
    )

    (out_dir / "run.json").write_text(json.dumps(asdict(run_data), indent=2))
    (out_dir / "config.yaml").write_text(yaml.dump(asdict(config), default_flow_style=False))

    # Print summary
    _print_summary(summary, config, run_duration_ms)

    console.print(f"\n[bold green]Results saved:[/bold green] {out_dir}/")
    return out_dir


# ---------------------------------------------------------------------------
# Summary / stats
# ---------------------------------------------------------------------------

def _build_summary(samples: list[SampleResult], config: BenchmarkConfig) -> dict:
    ok = [s for s in samples if s.score is not None]
    failed = [s for s in samples if s.error is not None]

    human = [s for s in ok if s.label == "known_human"]
    llm = [s for s in ok if s.label == "known_llm"]

    def _stats(group: list[SampleResult]) -> dict:
        if not group:
            return {}
        scores = [s.score for s in group]  # type: ignore[misc]
        latencies = [s.latency_ms for s in group]
        return {
            "n": len(group),
            "score_mean": round(statistics.mean(scores), 4),
            "score_median": round(statistics.median(scores), 4),
            "score_stdev": round(statistics.stdev(scores), 4) if len(scores) > 1 else 0.0,
            "score_min": min(scores),
            "score_max": max(scores),
            "confidence_mean": round(statistics.mean(s.confidence for s in group), 4),  # type: ignore[arg-type]
            "latency_mean_ms": round(statistics.mean(latencies)),
            "latency_median_ms": round(statistics.median(latencies)),
            "latency_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0,
            "latency_min_ms": min(latencies),
            "latency_max_ms": max(latencies),
            "tokens_in_total": sum(s.tokens_in for s in group),
            "tokens_out_total": sum(s.tokens_out for s in group),
            "annotations_valid": sum(s.annotations_valid for s in group),
            "annotations_invalid": sum(s.annotations_invalid for s in group),
        }

    human_stats = _stats(human)
    llm_stats = _stats(llm)

    separation = None
    if human_stats and llm_stats:
        separation = round(llm_stats["score_mean"] - human_stats["score_mean"], 4)

    # Classification accuracy at various thresholds
    thresholds = {}
    for t in [0.40, 0.45, 0.50, 0.55, 0.60]:
        correct = 0
        total = len(ok)
        for s in ok:
            predicted_llm = s.score >= t  # type: ignore[operator]
            actual_llm = s.label == "known_llm"
            if predicted_llm == actual_llm:
                correct += 1
        thresholds[str(t)] = round(correct / total, 4) if total else 0.0

    return {
        "model": config.model,
        "total_samples": len(samples),
        "successful": len(ok),
        "failed": len(failed),
        "human": human_stats,
        "llm": llm_stats,
        "separation": separation,
        "classification_accuracy": thresholds,
    }


def _print_summary(summary: dict, config: BenchmarkConfig, run_duration_ms: int):
    console.print()

    table = Table(title=f"[bold]{config.name}[/bold] — {config.model}")
    table.add_column("Metric", style="bold")
    table.add_column("Human", justify="right")
    table.add_column("LLM", justify="right")

    h = summary.get("human", {})
    l = summary.get("llm", {})

    rows = [
        ("n", "n"),
        ("Score (mean)", "score_mean"),
        ("Score (median)", "score_median"),
        ("Score (stdev)", "score_stdev"),
        ("Score (range)", None),
        ("Confidence (mean)", "confidence_mean"),
        ("Latency mean (ms)", "latency_mean_ms"),
        ("Latency p95 (ms)", "latency_p95_ms"),
        ("Tokens in", "tokens_in_total"),
        ("Tokens out", "tokens_out_total"),
        ("Annotations valid", "annotations_valid"),
        ("Annotations invalid", "annotations_invalid"),
    ]

    for label, key in rows:
        if key is None:
            hv = f"{h.get('score_min', '-')}-{h.get('score_max', '-')}" if h else "-"
            lv = f"{l.get('score_min', '-')}-{l.get('score_max', '-')}" if l else "-"
        else:
            hv = str(h.get(key, "-"))
            lv = str(l.get(key, "-"))
        table.add_row(label, hv, lv)

    console.print(table)

    if summary.get("separation") is not None:
        sep = summary["separation"]
        color = "green" if sep >= 0.3 else "yellow" if sep >= 0.15 else "red"
        console.print(f"\n[bold]Separation:[/bold] [{color}]{sep:.4f}[/{color}]")

    if summary.get("classification_accuracy"):
        console.print("\n[bold]Classification Accuracy by Threshold:[/bold]")
        for t, acc in summary["classification_accuracy"].items():
            color = "green" if acc >= 0.9 else "yellow" if acc >= 0.75 else "red"
            console.print(f"  θ={t}  [{color}]{acc:.1%}[/{color}]")

    console.print(f"\n[dim]Run duration: {run_duration_ms/1000:.1f}s | "
                  f"Failed: {summary['failed']}/{summary['total_samples']}[/dim]")


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def compare_runs(dirs: list[Path]):
    """Compare multiple benchmark runs side by side."""
    runs = []
    for d in dirs:
        run_file = d / "run.json"
        if not run_file.exists():
            console.print(f"[red]No run.json in {d}[/red]")
            continue
        with open(run_file) as f:
            runs.append(json.load(f))

    if len(runs) < 2:
        console.print("[red]Need at least 2 runs to compare[/red]")
        return

    table = Table(title="[bold]Benchmark Comparison[/bold]")
    table.add_column("Metric", style="bold")
    for r in runs:
        table.add_column(r["config"]["name"], justify="right")

    metrics = [
        ("Model", lambda r: r["summary"]["model"]),
        ("Samples", lambda r: str(r["summary"]["successful"])),
        ("Failed", lambda r: str(r["summary"]["failed"])),
        ("", lambda r: ""),
        ("Human score (mean)", lambda r: f"{r['summary']['human'].get('score_mean', '-')}"),
        ("Human score (stdev)", lambda r: f"{r['summary']['human'].get('score_stdev', '-')}"),
        ("LLM score (mean)", lambda r: f"{r['summary']['llm'].get('score_mean', '-')}"),
        ("LLM score (stdev)", lambda r: f"{r['summary']['llm'].get('score_stdev', '-')}"),
        ("Separation", lambda r: f"{r['summary'].get('separation', '-')}"),
        ("", lambda r: ""),
        ("Latency mean (ms)", lambda r: f"{r['summary']['llm'].get('latency_mean_ms', '-')}"),
        ("Latency p95 (ms)", lambda r: f"{r['summary']['llm'].get('latency_p95_ms', '-')}"),
        ("", lambda r: ""),
        ("Annotations valid", lambda r: str(
            r['summary']['human'].get('annotations_valid', 0) +
            r['summary']['llm'].get('annotations_valid', 0)
        )),
        ("Annotations invalid", lambda r: str(
            r['summary']['human'].get('annotations_invalid', 0) +
            r['summary']['llm'].get('annotations_invalid', 0)
        )),
        ("", lambda r: ""),
        ("Accuracy θ=0.50", lambda r: f"{r['summary']['classification_accuracy'].get('0.5', '-')}"),
        ("Accuracy θ=0.55", lambda r: f"{r['summary']['classification_accuracy'].get('0.55', '-')}"),
    ]

    for label, fn in metrics:
        if not label:
            table.add_row("─" * 20, *["─" * 12] * len(runs))
        else:
            table.add_row(label, *[fn(r) for r in runs])

    console.print(table)
