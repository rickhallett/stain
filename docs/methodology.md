# Methodology

The thesis behind Stain's multi-agent detection architecture.

---

## The Problem with Single-Dimension Detection

Most AI detection tools treat the question as binary classification: AI or human.
They train a single model on a mixed corpus and output a probability. This fails
in predictable ways:

- **Overfitting to style.** A classifier trained on ChatGPT output fails on Claude
  output, and vice versa. Each model has different tells.
- **Blind spots.** A detector tuned for vocabulary patterns misses structural ones.
  A rhythm detector ignores rhetorical devices. One dimension cannot cover the full
  signal space.
- **Brittleness.** Paraphrasing, light editing, or mixing human and AI text defeats
  single-model classifiers. The signal is subtle and distributed; one-shot
  classification cannot capture it.
- **Opacity.** A single score with no explanation is useless. "73% AI" tells you
  nothing about what to look for or how to improve the text.

Stain takes a different approach: disaggregate the signal into independent
dimensions, measure each one separately, and combine the results.

## The Six Dimensions

Each detector examines a different axis of text quality. They are designed to be
orthogonal -- a text can score high on one dimension and low on another.

**D1: Rhetorical Pattern.** LLMs overuse specific rhetorical devices. Correctio
("Not X -- it's Y"), tricolon closers, false balance, escalation frames. These are
individually legitimate; their density is the signal.

**D2: Sentence Rhythm.** Human writers produce erratic sentence lengths -- clusters
of short sentences, then a long one, then medium. LLMs produce metronomic cadence:
predictable alternation, uniform paragraph structure, regular openers.

**D3: Lexical Diversity.** LLMs operate within a narrower working vocabulary per
register than human writers. They avoid synonyms, recycle phrases, flatten register
variation, and lean on filler vocabulary ("important", "significant", "crucial").

**D4: Hedging Density.** LLMs hedge compulsively. Qualifier stacking, epistemic
hedges ("it seems", "arguably"), non-committal framing, both-sides padding. The
model avoids definitive claims because RLHF penalises strong positions.

**D5: Structural Predictability.** Rigid introduction-body-conclusion structure.
Signpost narration ("Let me explain"). Numbered scaffolding. Rhetorical questions
as transitions. These are the structural crutches of text generated to a template.

**D6: Semantic Emptiness.** Sentences that occupy space without adding meaning.
Broadening closers ("and that's what makes this so important"). Filler transitions.
Restated premises. Empty emphasis. Circular conclusions that restate the intro.

## Why These Six

The dimensions map to different levels of linguistic analysis:

| Level | Detectors |
|-------|-----------|
| Surface lexical | D3 (vocabulary), D4 (hedging markers) |
| Sentence-level | D1 (rhetorical devices), D2 (rhythm) |
| Paragraph/document | D5 (structure), D6 (semantic content) |

Each level catches patterns the others miss. A text with diverse vocabulary (low D3)
might still have rigid structure (high D5). A text with natural rhythm (low D2)
might be saturated with hedging (high D4). The composite score captures the full
picture.

## Weighted Composite Scoring

The composite score is a weighted average of all detector scores:

```
composite = sum(score_i * weight_i) / sum(weight_i)
```

Default weights are 1.0 for all detectors. Weights are configurable per deployment
in `stain.config.yaml`. This allows tuning for specific domains -- technical
writing might weight D5 lower (structured text is expected), while opinion writing
might weight D4 higher (hedging is more suspect).

The composite score is **not** a probability of AI authorship. It is a pattern
density measure. A score of 0.7 means "this text is dense with patterns that
LLMs characteristically produce." A human writer who happens to use tricolon
closers and hedge compulsively will score high. That is correct behaviour --
the patterns are real regardless of authorship.

## Annotation Validation

Each detector returns character-level annotations: the exact span of text that
triggered a pattern match, with start/end offsets. This is where cheap models
break down.

Small or fast models frequently produce garbage offsets -- a span that does not
match the cited text, offsets that fall outside the input bounds, or overlapping
annotations. The annotation validation pipeline handles this:

1. **Exact match.** If the annotated text exists at the given offsets, accept it.
2. **Fuzzy repair.** If the text exists elsewhere in the input, recompute the
   correct offsets.
3. **Rejection.** If the text cannot be found anywhere in the input, mark the
   annotation as invalid and exclude it from rendering.

This allows Stain to use fast, cheap models (sub-1s latency) for detection while
maintaining accurate span highlighting. The validation rate is a quality signal:
a model that produces >20% invalid annotations is not trustworthy for that prompt.

## The Discovery Loop

Stain's six detectors represent the currently known signal space. But LLM output
patterns evolve as models change, and human reviewers may notice tells that no
existing detector covers.

The discovery pipeline closes this gap:

1. **Run all detectors** on a text to establish baseline coverage.
2. **Run a discovery prompt** that asks: "What patterns in this text suggest AI
   generation that the existing detectors did not catch?"
3. **Record hypotheses** -- candidate patterns with examples and rationale.
4. **Human review.** The operator reviews hypotheses, approves credible ones,
   rejects noise.
5. **Scaffold.** Approved hypotheses are promoted into new detector definitions
   with generated prompts.
6. **Benchmark.** The new detector is tested against the labelled corpus to
   validate that it improves classification.

This is a self-teaching loop: Stain uses its own gaps to generate training signal
for new detectors. The human stays in the loop for quality control.

```bash
stain discover post.txt        # Step 1-3
stain discover list            # Review hypotheses
stain discover approve <id>    # Step 4-5
stain benchmark run config.yaml  # Step 6
```

## Research Integration

The research pipeline (Arcana integration) adds an academic dimension:

```bash
stain research fetch "LLM detection linguistic features"
stain research extract <paper-id>
```

This fetches papers, extracts hypotheses about detectable patterns, and feeds them
into the same approval/promotion workflow as the discovery pipeline. The goal is
to ground Stain's detectors in published linguistic research, not just empirical
pattern-matching.

## Limitations

Stain has clear boundaries. Knowing them matters more than the scores it produces.

**Not a provenance tool.** Stain measures pattern density, not authorship. It
cannot tell you who wrote a text. A human who writes like an LLM will score high.
An LLM with strong prompting and editing will score low.

**Domain sensitivity.** Technical documentation, legal writing, and academic prose
have naturally high scores on D5 (structural predictability) and D4 (hedging).
These are not false positives -- the patterns are real -- but they require domain-
specific weight calibration.

**Model dependency.** Detection quality depends on the detector model's ability to
follow the prompt accurately and produce valid annotations. Model drift, API
changes, and provider outages affect results. Content-addressed benchmarking
(config hash + timestamp) ensures reproducibility across runs.

**Adversarial fragility.** A motivated adversary who knows Stain's detectors can
edit text to reduce pattern density. This is not a flaw -- if someone edits out
all the rhetorical crutches, hedging, and semantic emptiness, the text is
genuinely better. Stain is a writing quality tool as much as a detection tool.

**Short text.** Texts under ~200 words provide insufficient signal for reliable
scoring. Detector confidence drops and annotations are sparse. Stain works best
on paragraphs-to-pages scale text.

**Evolving baseline.** As LLMs improve, their output patterns change. Detectors
calibrated against GPT-4 era output may not catch patterns from future models.
The discovery loop and research pipeline exist to address this, but they require
ongoing human attention.
