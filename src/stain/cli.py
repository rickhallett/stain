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
        gold_dir = Path(config.get("corpus", {}).get("gold", "corpus/gold"))
        corpus_dirs = [gold_dir / "known_human", gold_dir / "known_llm"]
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


# ---------------------------------------------------------------------------
# Corpus commands
# ---------------------------------------------------------------------------

def _corpus_dir() -> Path:
    """Get corpus root directory from config."""
    config = load_config()
    return Path(config.get("corpus", {}).get("path", "corpus"))


@cli.group()
def corpus():
    """Manage corpus tiers and samples."""
    pass


@corpus.command("stats")
def corpus_stats_cmd():
    """Show sample counts per tier."""
    from stain.corpus import corpus_stats as _corpus_stats

    root = _corpus_dir()
    stats = _corpus_stats(root)

    table = Table(title="Corpus Stats")
    table.add_column("Tier", style="bold")
    table.add_column("Human", justify="right")
    table.add_column("LLM", justify="right")
    table.add_column("Total", justify="right")

    for tier_name in ["gold", "bulk"]:
        if tier_name in stats:
            t = stats[tier_name]
            table.add_row(tier_name, str(t.get("human", 0)), str(t.get("llm", 0)), str(t["total"]))

    if "ambiguous" in stats:
        table.add_row("ambiguous", "-", "-", str(stats["ambiguous"]["total"]))

    console.print(table)
    console.print(f"\n[bold]Total samples:[/bold] {stats.get('total', 0)}")


@corpus.command("validate")
def corpus_validate_cmd():
    """Check manifests match filesystem, detect duplicates."""
    from stain.corpus import corpus_validate as _corpus_validate

    root = _corpus_dir()
    issues = _corpus_validate(root)

    if not issues:
        console.print("[green]Corpus is valid. No issues found.[/green]")
    else:
        console.print(f"[red]Found {len(issues)} issue(s):[/red]")
        for issue in issues:
            console.print(f"  - {issue}")
        raise SystemExit(1)


@corpus.command("label")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--as", "label", required=True, type=click.Choice(["human", "llm"]))
@click.option("--tier", default="gold", type=click.Choice(["gold", "bulk"]))
@click.option("--source", required=True, help="Content origin")
@click.option("--domain", required=True, help="Content domain (blog, linkedin, etc.)")
def corpus_label_cmd(file_path: str, label: str, tier: str, source: str, domain: str):
    """Label an ambiguous sample and promote to a tier."""
    from stain.corpus import corpus_label as _corpus_label

    root = _corpus_dir()
    entry = _corpus_label(
        corpus_dir=root,
        file_path=Path(file_path),
        label=label,
        tier=tier,
        source=source,
        domain=domain,
    )
    console.print(f"[green]Labelled {entry.id} as {label} in {tier}[/green]")


@corpus.command("generate")
@click.option("--type", "sample_type", required=True, type=click.Choice(["llm", "human"]))
@click.option("--count", default=10, type=int, help="Number of samples")
@click.option("--domain", default="linkedin,blog,marketing", help="Comma-separated domains")
@click.option("--model", default=None, help="LLM model (litellm format)")
@click.option("--temp", default="0.7", help="Comma-separated temperatures")
@click.option("--tier", default="bulk", type=click.Choice(["gold", "bulk"]))
@click.option("--sources", default=None, help="Author keys or URLs (comma-separated, for --type human)")
@click.option("--wayback/--no-wayback", default=True, help="Try Wayback Machine fallback")
def corpus_generate_cmd(
    sample_type: str,
    count: int,
    domain: str,
    model: str | None,
    temp: str,
    tier: str,
    sources: str | None,
    wayback: bool,
):
    """Generate bulk corpus samples.

    \b
    Examples:
      stain corpus generate --type llm --count 50 --domain linkedin,blog
      stain corpus generate --type human --sources sivers,pg --tier gold
    """
    from stain.generate import generate_llm_samples, scrape_human_samples, AUTHOR_SOURCES

    config = load_config()
    root = _corpus_dir()
    output_dir = root / tier
    domains = [d.strip() for d in domain.split(",")]
    temperatures = [float(t.strip()) for t in temp.split(",")]

    if model is None:
        model = config.get("models", {}).get("detector", DEFAULT_MODEL)

    if sample_type == "llm":
        with console.status(f"[bold]Generating {count} LLM samples..."):
            entries = generate_llm_samples(
                count=count,
                domains=domains,
                model=model,
                temperatures=temperatures,
                output_dir=output_dir,
            )
        console.print(f"[green]Generated {len(entries)} LLM samples in {tier}/[/green]")

    elif sample_type == "human":
        if not sources:
            console.print("[red]--sources required for human generation (e.g. --sources sivers,pg)[/red]")
            raise SystemExit(2)

        urls: list[str] = []
        source_name = "mixed"
        for src in sources.split(","):
            src = src.strip()
            if src in AUTHOR_SOURCES:
                urls.extend(AUTHOR_SOURCES[src])
                source_name = src
            elif src.startswith(("http://", "https://")):
                urls.append(src)
            else:
                console.print(f"[yellow]Unknown source: {src}. Known: {', '.join(AUTHOR_SOURCES.keys())}[/yellow]")

        if not urls:
            console.print("[red]No valid URLs resolved from sources.[/red]")
            raise SystemExit(2)

        with console.status(f"[bold]Scraping {len(urls)} URLs..."):
            entries = scrape_human_samples(
                urls=urls[:count],
                output_dir=output_dir,
                source=source_name,
                domain=domains[0],
                wayback_fallback=wayback,
            )
        console.print(f"[green]Scraped {len(entries)} human samples in {tier}/[/green]")


# ---------------------------------------------------------------------------
# Discovery commands
# ---------------------------------------------------------------------------

def _discovery_dir() -> Path:
    """Get discovery directory."""
    return Path("discovery")


class _DiscoverGroup(click.Group):
    """Group that treats unknown 'subcommands' as file path arguments."""

    def invoke(self, ctx: click.Context):
        if not ctx._protected_args:
            # No positional args — run group callback (invoke_without_command)
            return super().invoke(ctx)

        # Peek at the first positional arg
        cmd_name = ctx._protected_args[0]
        if cmd_name in self.commands:
            # Known subcommand — let Click dispatch normally
            return super().invoke(ctx)

        # Not a subcommand — treat it as a source file path.
        # Pull it out of protected_args so Click doesn't try to resolve it.
        source = ctx._protected_args.pop(0)
        ctx.ensure_object(dict)["_discover_source"] = source
        # Clear protected args so Click takes the invoke_without_command path
        ctx.args = [*ctx._protected_args, *ctx.args]
        ctx._protected_args = []
        return super().invoke(ctx)


@cli.group(cls=_DiscoverGroup, invoke_without_command=True)
@click.option("--corpus", "corpus_tier", default=None, help="Run across corpus tier")
@click.option("--model", "disc_model", default=None, help="Discovery model override")
@click.pass_context
def discover(ctx, corpus_tier: str | None, disc_model: str | None):
    """Run discovery pipeline to find new patterns.

    \b
    Examples:
      stain discover post.txt
      stain discover --corpus gold
    """
    if ctx.invoked_subcommand is not None:
        return

    from stain.discovery import discover_file, discover_corpus

    disc_dir = _discovery_dir()
    config = load_config()

    source = ctx.ensure_object(dict).get("_discover_source")

    if corpus_tier:
        with console.status(f"[bold]Running discovery across {corpus_tier} corpus..."):
            results = discover_corpus(corpus_tier, config=config, discovery_model=disc_model, discovery_dir=disc_dir)
        total_hyp = sum(len(r.hypotheses) for r in results)
        console.print(f"[green]Processed {len(results)} files, found {total_hyp} hypothesis instances[/green]")

    elif source:
        source_path = Path(source)
        if not source_path.is_file():
            console.print(f"[red]File not found: {source}[/red]")
            raise SystemExit(2)
        with console.status("[bold]Running detectors + discovery..."):
            result = discover_file(source_path, config=config, discovery_model=disc_model, discovery_dir=disc_dir)
        console.print(f"[green]Found {len(result.hypotheses)} hypotheses[/green]")
        for h in result.hypotheses:
            console.print(f"  - [bold]{h['pattern_name']}[/bold] (confidence: {h.get('confidence', '?')})")
            console.print(f"    {h.get('description', '')}")
    else:
        console.print("[yellow]Provide a file or use --corpus[/yellow]")
        raise SystemExit(2)


@discover.command("list")
def discover_list():
    """Show all discovered pattern hypotheses."""
    from stain.discovery import load_hypothesis_store

    disc_dir = _discovery_dir()
    store = load_hypothesis_store(disc_dir / "hypotheses.yaml")

    if not store.hypotheses:
        console.print("[dim]No hypotheses found. Run 'stain discover <file>' first.[/dim]")
        return

    table = Table(title="Discovery Hypotheses")
    table.add_column("Pattern", style="bold")
    table.add_column("Confidence", justify="right")
    table.add_column("Occurrences", justify="right")
    table.add_column("Status")
    table.add_column("Description")

    for name, h in sorted(store.hypotheses.items(), key=lambda x: -x[1].occurrence_count):
        status_color = {"pending": "yellow", "approved": "blue", "promoted": "green", "rejected": "dim"}.get(h.status, "white")
        table.add_row(
            name,
            f"{h.confidence:.2f}",
            str(h.occurrence_count),
            f"[{status_color}]{h.status}[/{status_color}]",
            h.description[:60] + ("..." if len(h.description) > 60 else ""),
        )

    console.print(table)


@discover.command("approve")
@click.argument("pattern_name")
def discover_approve(pattern_name: str):
    """Scaffold a new detector from an approved hypothesis."""
    from stain.discovery import scaffold_detector, load_hypothesis_store

    disc_dir = _discovery_dir()
    store = load_hypothesis_store(disc_dir / "hypotheses.yaml")

    try:
        detector_id, path = scaffold_detector(
            pattern_name, store=store,
            store_path=disc_dir / "hypotheses.yaml",
        )
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Scaffolded {detector_id} at {path}/[/green]")
    console.print("[dim]Edit the prompt.md, then benchmark before promoting.[/dim]")


@discover.command("promote")
@click.argument("detector_id")
def discover_promote(detector_id: str):
    """Enable a scaffolded detector."""
    from stain.discovery import promote_detector

    try:
        promote_detector(detector_id.upper())
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    console.print(f"[green]{detector_id.upper()} enabled[/green]")
