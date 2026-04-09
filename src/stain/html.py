"""HTML report generator — self-contained, offline-capable analysis reports."""

from __future__ import annotations

import html as html_lib
from stain.models import CompositeResult, MergedAnnotation, Severity


def _score_class(score: float) -> str:
    if score >= 0.7:
        return "score-high"
    if score >= 0.4:
        return "score-medium"
    return "score-low"


def _severity_class(severity: Severity) -> str:
    return f"ann-{severity.value}"


def _build_annotated_text(text: str, annotations: list[MergedAnnotation]) -> str:
    """Build HTML text with annotation spans and tooltips."""
    if not annotations:
        return f"<p>{html_lib.escape(text)}</p>"

    sorted_anns = sorted(annotations, key=lambda a: a.span_start)

    parts = []
    last_end = 0

    for ann in sorted_anns:
        start = max(ann.span_start, last_end)
        if start > last_end:
            parts.append(html_lib.escape(text[last_end:start]))

        end = ann.span_end
        span_text = html_lib.escape(text[start:end])
        severity = ann.max_severity.value
        detectors = ", ".join(ann.detectors)
        explanations = " | ".join(f"{k}: {v}" for k, v in ann.explanations.items())
        tooltip = html_lib.escape(f"[{severity}] {detectors} -- {explanations}")

        parts.append(
            f'<span class="ann {_severity_class(ann.max_severity)}" '
            f'data-tooltip="{tooltip}">{span_text}</span>'
        )
        last_end = end

    if last_end < len(text):
        parts.append(html_lib.escape(text[last_end:]))

    return "".join(parts)


def render_html_report(result: CompositeResult, text: str) -> str:
    """Render a self-contained HTML report from analysis results."""
    score_cls = _score_class(result.composite_score)

    detector_rows = ""
    for dr in result.detector_results:
        sc = _score_class(dr.verdict.score)
        detector_rows += (
            f"<tr>"
            f"<td><strong>{dr.detector_id}</strong> {html_lib.escape(dr.detector_name)}</td>"
            f'<td class="{sc}">{dr.verdict.score:.2f}</td>'
            f"<td>{dr.verdict.confidence:.2f}</td>"
            f"<td>{len(dr.verdict.annotations)}</td>"
            f"<td>{html_lib.escape(dr.verdict.summary[:120])}</td>"
            f"</tr>\n"
        )

    annotated = _build_annotated_text(text, result.merged_annotations)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stain Analysis Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 900px; margin: 0 auto; padding: 2rem; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #f0f6fc; margin-bottom: 0.5rem; }}
h2 {{ color: #f0f6fc; margin: 1.5rem 0 0.75rem; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }}
.header {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.score-high {{ color: #f85149; }}
.score-medium {{ color: #d29922; }}
.score-low {{ color: #3fb950; }}
.composite {{ font-size: 2.5rem; font-weight: bold; }}
.meta {{ color: #8b949e; font-size: 0.9rem; margin-top: 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
th {{ background: #161b22; color: #f0f6fc; text-align: left; padding: 0.75rem; border: 1px solid #30363d; }}
td {{ padding: 0.75rem; border: 1px solid #30363d; }}
tr:hover {{ background: #161b22; }}
.text-container {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
                   padding: 1.5rem; line-height: 1.8; white-space: pre-wrap; font-size: 0.95rem; }}
.ann {{ position: relative; cursor: help; border-radius: 2px; padding: 1px 0; }}
.ann-high {{ background: rgba(248, 81, 73, 0.2); border-bottom: 2px solid #f85149; }}
.ann-medium {{ background: rgba(210, 153, 34, 0.2); border-bottom: 2px solid #d29922; }}
.ann-low {{ background: rgba(63, 185, 80, 0.2); border-bottom: 2px solid #3fb950; }}
.ann:hover::after {{ content: attr(data-tooltip); position: absolute; bottom: 100%; left: 0;
                     background: #1f2937; color: #e5e7eb; padding: 0.5rem 0.75rem; border-radius: 6px;
                     font-size: 0.8rem; white-space: normal; max-width: 400px; z-index: 10;
                     border: 1px solid #374151; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
.footer {{ color: #8b949e; font-size: 0.8rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #30363d; }}
</style>
</head>
<body>
<div class="header">
  <h1>Stain Analysis Report</h1>
  <div class="composite {score_cls}">{result.composite_score:.3f}</div>
  <div class="meta">{result.input_length_chars} chars | {len(result.detector_results)} detector(s) |
    {result.meta.get('total_latency_ms', 0)}ms |
    {result.meta.get('total_tokens_in', 0)} tokens in / {result.meta.get('total_tokens_out', 0)} out</div>
</div>

<h2>Detector Breakdown</h2>
<table>
<tr><th>Detector</th><th>Score</th><th>Confidence</th><th>Annotations</th><th>Summary</th></tr>
{detector_rows}
</table>

<h2>Annotated Text</h2>
<div class="text-container">{annotated}</div>

<div class="footer">
  Generated by Stain v{result.stain_version}
</div>
</body>
</html>"""
