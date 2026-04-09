"""Stain CLI — run detectors against corpus or individual text."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stain import __version__
from stain.config import get_enabled_detectors, load_config
from stain.detector import DEFAULT_MODEL, run_detector
from stain.input import InputItem
from stain.models import CompositeResult, DetectorResult
from stain.benchmark import BenchmarkConfig, compare_runs, run_benchmark
from stain.orchestrator import analyse, _make_audit_logger
from stain.registry import discover_detectors

console = Console()
console_err = Console(stderr=True)

# Exit codes (Ring 2 spec)
EXIT_OK = 0          # Score below threshold
EXIT_FLAGGED = 1     # Score at or above threshold
EXIT_INPUT_ERROR = 2  # Bad input (file not found, empty, etc.)
EXIT_API_ERROR = 3   # LLM/API error


def _severity_color(severity: str) -> str:
    return {"high": "red", "medium": "yellow", "low": "green"}.get(severity, "white")


def _score_color(score: float) -> str:
    if score >= 0.7:
        return "red"
    if score >= 0.4:
        return "yellow"
    return "green"


@click.group()
@click.version_option(version=__version__)
def cli():
    """Stain — surface LLM generation patterns in text."""
    pass


@cli.command()
@click.option("--detector", "-d", default=None, help="Run a single detector (e.g. D1)")
@click.option("--input", "-i", "input_path", default=None, type=click.Path(exists=True), help="Analyse a single file")
@click.option("--config", "-c", "config_path", default=None, type=click.Path(exists=True), help="Config file path")
def run(detector: str | None, input_path: str | None, config_path: str | None):
    """Run detectors against corpus or a single file."""
    config = load_config(Path(config_path) if config_path else None)

    if detector:
        detector_ids = [detector.upper()]
    else:
        detector_ids = get_enabled_detectors(config)

    if not detector_ids:
        console.print("[red]No detectors enabled.[/red]")
        return

    # Collect input files
    if input_path:
        files = [Path(input_path)]
    else:
        corpus_dirs = [
            Path(config.get("corpus", {}).get("known_llm", "corpus/known_llm")),
            Path(config.get("corpus", {}).get("known_human", "corpus/known_human")),
        ]
        files = []
        for d in corpus_dirs:
            if d.exists():
                files.extend(sorted(d.glob("*.txt")))

        if not files:
            console.print("[yellow]No corpus files found.[/yellow]")
            return

    # Create run directory
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    results_dir = Path(config.get("results", {}).get("path", "results")) / run_id
    results_dir.mkdir(parents=True, exist_ok=True)

    model = config.get("models", {}).get("detector", DEFAULT_MODEL)
    audit_logger = _make_audit_logger(config)

    console.print(f"\n[bold]Stain run[/bold] {run_id}")
    console.print(f"Detectors: {', '.join(detector_ids)}")
    console.print(f"Files: {len(files)}")
    console.print(f"Model: {model}\n")

    # Run
    all_results: list[dict] = []
    for filepath in files:
        text = filepath.read_text()
        label = filepath.parent.name  # known_llm or known_human
        sample_id = filepath.stem

        console.print(f"  [{label}] {filepath.name} ", end="")

        file_results: list[DetectorResult] = []
        for did in detector_ids:
            result = run_detector(did, text, model=model, audit_logger=audit_logger)
            file_results.append(result)

        # Display inline score
        for r in file_results:
            color = _score_color(r.verdict.score)
            console.print(f"[{color}]{r.detector_id}={r.verdict.score:.2f}[/{color}] ", end="")
        console.print()

        # Save per-sample result
        output = {
            "sample_id": sample_id,
            "label": label,
            "file": str(filepath),
            "results": [r.model_dump() for r in file_results],
        }
        all_results.append(output)

        result_file = results_dir / f"{sample_id}.json"
        result_file.write_text(json.dumps(output, indent=2))

    # Write manifest
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "detectors": detector_ids,
        "file_count": len(files),
        "stain_version": __version__,
    }
    (results_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    console.print(f"\n[bold green]Results saved:[/bold green] {results_dir}/")


@cli.command("analyse")
@click.argument("sources", nargs=-1)
@click.option("--json", "output_json", is_flag=True, help="JSON output")
@click.option("--plain", is_flag=True, help="One-liner output")
@click.option("--score", "score_only", is_flag=True, help="Score only")
@click.option("--threshold", "-t", default=0.55, type=float, help="Exit code threshold (default: 0.55)")
@click.option("--config", "-c", "config_path", default=None, type=click.Path(exists=True))
def analyse_cmd(
    sources: tuple[str, ...],
    output_json: bool,
    plain: bool,
    score_only: bool,
    threshold: float,
    config_path: str | None,
):
    """Analyse text for LLM generation patterns.

    SOURCES can be file paths, glob patterns, URLs, or '-' for stdin.
    When no source is given and stdin is piped, reads from stdin.

    \b
    Examples:
      stain analyse post.txt
      pbpaste | stain analyse -
      stain analyse https://example.com/article
      stain analyse posts/*.txt --score
    """
    from stain.input import InputError, resolve_inputs
    from stain.output import OutputMode, detect_mode, format_json, format_plain, format_score

    config = load_config(Path(config_path) if config_path else None)
    mode = detect_mode(json_flag=output_json, plain_flag=plain, score_flag=score_only)

    # Resolve inputs
    try:
        items = resolve_inputs(sources, stdin_stream=click.get_text_stream("stdin"))
    except InputError as e:
        console_err.print(f"[red]Input error:[/red] {e}")
        raise SystemExit(EXIT_INPUT_ERROR)

    # Run analysis on each input
    max_score = 0.0
    results_list: list[tuple[InputItem, CompositeResult]] = []

    for item in items:
        try:
            if mode == OutputMode.RICH and len(items) > 1:
                console.print(f"\n[bold]{item.source}[/bold]")
            result = analyse(item.text, config=config)
            results_list.append((item, result))
            max_score = max(max_score, result.composite_score)
        except Exception as e:
            console_err.print(f"[red]Error analysing {item.source}:[/red] {e}")
            raise SystemExit(EXIT_API_ERROR)

    # Format output
    single = len(results_list) == 1

    for item, result in results_list:
        if mode == OutputMode.JSON:
            if single:
                click.echo(format_json(result))
            else:
                data = result.model_dump()
                data["source"] = item.source
                click.echo(json.dumps(data, indent=2))
        elif mode == OutputMode.PLAIN:
            prefix = "" if single else f"{item.source}: "
            click.echo(f"{prefix}{format_plain(result)}")
        elif mode == OutputMode.SCORE:
            prefix = "" if single else f"{item.source}: "
            click.echo(f"{prefix}{format_score(result)}")
        elif mode == OutputMode.RICH:
            _render_rich(result, item.text, item.source)

    # Exit code based on threshold
    if max_score >= threshold:
        raise SystemExit(EXIT_FLAGGED)
    raise SystemExit(EXIT_OK)


def _render_rich(result: CompositeResult, text: str, source: str):
    """Render rich TTY output for a single analysis result."""
    score_color = _score_color(result.composite_score)
    console.print()
    console.print(Panel(
        f"[bold {score_color}]Composite Score: {result.composite_score:.3f}[/bold {score_color}]"
        f"\n{result.input_length_chars} chars | {len(result.detector_results)} detector(s)",
        title=f"[bold]Stain Analysis[/bold] — {source}",
    ))

    table = Table(title="Detector Breakdown")
    table.add_column("Detector", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Annotations", justify="right")
    table.add_column("Summary")

    for dr in result.detector_results:
        sc = _score_color(dr.verdict.score)
        table.add_row(
            f"{dr.detector_id} {dr.detector_name}",
            f"[{sc}]{dr.verdict.score:.2f}[/{sc}]",
            f"{dr.verdict.confidence:.2f}",
            str(len(dr.verdict.annotations)),
            dr.verdict.summary[:80] + ("..." if len(dr.verdict.summary) > 80 else ""),
        )

    console.print(table)

    if result.merged_annotations and text:
        console.print("\n[bold]Flagged Spans[/bold]")
        for ma in result.merged_annotations:
            span_text = text[ma.span_start:ma.span_end]
            if len(span_text) > 100:
                span_text = span_text[:100] + "..."
            color = _severity_color(ma.max_severity.value)
            detectors = ", ".join(ma.detectors)
            console.print(f"  [{color}][{ma.max_severity.value}][/{color}] [{detectors}] chars {ma.span_start}-{ma.span_end}")
            console.print(f"    \"{span_text}\"")
            for did, expl in ma.explanations.items():
                console.print(f"    {did}: {expl}")
            console.print()

    console.print(f"[dim]Latency: {result.meta['total_latency_ms']}ms | "
                  f"Tokens: {result.meta['total_tokens_in']}in/{result.meta['total_tokens_out']}out[/dim]")


@cli.group()
def benchmark():
    """Run repeatable model benchmarks against corpus."""
    pass


@benchmark.command("run")
@click.argument("config_path", type=click.Path(exists=True))
def benchmark_run(config_path: str):
    """Run a benchmark from a YAML config file."""
    cfg = BenchmarkConfig.from_yaml(Path(config_path))
    run_benchmark(cfg)


@benchmark.command("compare")
@click.argument("run_dirs", nargs=-1, type=click.Path(exists=True))
def benchmark_compare(run_dirs: tuple[str, ...]):
    """Compare two or more benchmark runs side by side."""
    if len(run_dirs) < 2:
        console.print("[red]Provide at least 2 run directories to compare.[/red]")
        return
    compare_runs([Path(d) for d in run_dirs])


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
