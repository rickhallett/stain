# Detector Reference

Stain ships six independent detectors, each examining a different dimension of
text. Every detector runs as a separate LLM call with a versioned prompt. Results
are combined into a weighted composite score.

---

## D1: Rhetorical Pattern

**Version:** 0.1.0
**Weight:** 1.0

Identifies overrepresented rhetorical devices that LLMs reach for by default.

| Pattern | Description |
|---------|-------------|
| `correctio` | "Not X -- it's Y" rhetorical pivot |
| `tricolon_closer` | Three-part lists for rhetorical emphasis |
| `false_balance` | Hedged both-sides framing that commits to nothing |
| `escalation_frame` | Artificial urgency or revelation markers |
| `anaphora` | Repeated sentence openings for emphasis |
| `semantic_couplet` | Paired near-synonyms for emphasis |
| `pivot_conjunction` | Dramatic turn markers signalling manufactured insight |

---

## D2: Sentence Rhythm

**Version:** 0.1.0
**Weight:** 1.0

Measures sentence length variance, paragraph cadence regularity, and burstiness.
Human writers are erratic; LLMs are metronomic.

| Pattern | Description |
|---------|-------------|
| `uniform_length` | Sentences cluster within a narrow length band |
| `predictable_cadence` | Alternating short-long pattern repeats mechanically |
| `low_burstiness` | Absence of sudden length spikes or clusters of very short sentences |
| `paragraph_symmetry` | Paragraphs have suspiciously similar sentence counts and lengths |
| `opener_regularity` | Sentence openings follow a repeating structural template |

---

## D3: Lexical Diversity

**Version:** 0.1.0
**Weight:** 1.0

Scores vocabulary range, type-token ratio, and repetition of phrasing. LLM output
tends toward a narrower working vocabulary within a given register.

| Pattern | Description |
|---------|-------------|
| `low_type_token` | Low ratio of unique words to total words |
| `phrase_recycling` | Same multi-word phrases reused across paragraphs |
| `register_flattening` | Vocabulary stays in a narrow formality band without variation |
| `synonym_avoidance` | Repeated use of the same word where synonyms would be natural |
| `filler_vocabulary` | Overuse of generic modifiers and connectors |

---

## D4: Hedging Density

**Version:** 0.1.0
**Weight:** 1.0

Detects qualifier stacking, epistemic hedges, and non-committal framing that LLMs
use to avoid definitive claims.

| Pattern | Description |
|---------|-------------|
| `qualifier_stacking` | Multiple qualifiers in a single sentence or paragraph |
| `epistemic_hedge` | Phrases expressing unnecessary uncertainty: "it seems", "arguably", "one might say" |
| `non_committal_framing` | Positions presented without the author committing to them |
| `both_sides_padding` | Equal weight to opposing views when one is clearly favoured |
| `meta_acknowledgment` | Acknowledging complexity as a substitute for resolving it: "it's complicated", "there are many factors" |

---

## D5: Structural Predictability

**Version:** 0.1.0
**Weight:** 1.0

Analyses macro-structure: introduction-body-conclusion adherence, paragraph-level
predictability, signpost meta-narration.

| Pattern | Description |
|---------|-------------|
| `rigid_ibc` | Strict introduction-body-conclusion structure with clear delineation |
| `signpost_narration` | Meta-commentary directing the reader: "Let me explain", "Here's why" |
| `numbered_scaffolding` | Explicit enumeration used as structural crutch: "First... Second... Third..." |
| `question_setup` | Rhetorical questions used as section headers or transitions |
| `symmetrical_paragraphs` | Paragraphs follow a uniform internal template |

---

## D6: Semantic Emptiness

**Version:** 0.1.0
**Weight:** 1.0

Identifies phrases and sentences that occupy syntactic space without adding meaning.

| Pattern | Description |
|---------|-------------|
| `broadening_closer` | Final sentences that widen scope without adding: "and that's what makes this so important" |
| `filler_transition` | Transition phrases that add no information: "With that said", "Moving on" |
| `restated_premise` | Repeating an earlier point in different words without advancing the argument |
| `empty_emphasis` | Intensifiers that add no meaning: "truly", "really", "absolutely", "fundamentally" |
| `circular_conclusion` | Conclusion that merely restates the introduction |

---

## Scoring

Each detector returns:

- **verdict**: `ai`, `human`, or `uncertain`
- **score**: 0.0 (human) to 1.0 (AI) pattern density
- **confidence**: 0.0 to 1.0
- **annotations**: array of span-level pattern matches with character offsets

The composite score is a weighted average of all detector scores. Default weights
are 1.0 for all detectors. Adjust weights in `stain.config.yaml` under the
`detectors` key.
