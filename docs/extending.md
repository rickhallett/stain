# Extending Stain

How to add a new detector to the Stain pipeline.

---

## Option 1: Manual Creation

### Directory Structure

Every detector lives in `detectors/D{N}_{snake_case_name}/`:

```
detectors/D7_example_detector/
  detector.yaml     # Metadata and pattern definitions
  prompt.md         # LLM prompt template
  CHANGELOG.md      # Version history
  versions/         # Archived prompt versions
```

### detector.yaml

Required fields:

```yaml
id: D7
name: "Example Detector"
version: "0.1.0"
weight: 1.0
enabled: true
description: "One sentence describing what this detector measures."
patterns:
  - name: pattern_name
    description: "What this pattern looks like in text"
  - name: another_pattern
    description: "Description of the second pattern"
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Format: `D{N}` where N is the next available integer |
| `name` | string | yes | Human-readable name |
| `version` | string | yes | Semver |
| `weight` | float | yes | Weight in composite score calculation. Default: 1.0 |
| `enabled` | bool | yes | Set to `false` to disable without removing |
| `description` | string | yes | One sentence describing the detector's focus |
| `patterns` | list | yes | At least one pattern with `name` and `description` |

### prompt.md

The prompt template is sent to the LLM with the target text appended. The prompt
must instruct the model to return JSON matching this schema:

```json
{
  "verdict": "ai | human | uncertain",
  "score": 0.0,
  "confidence": 0.0,
  "annotations": [
    {
      "pattern": "pattern_name",
      "text": "the matched span",
      "start": 0,
      "end": 42,
      "explanation": "Why this span matches the pattern"
    }
  ]
}
```

Key requirements for the prompt:

- Define each pattern from your `detector.yaml` with examples
- Specify the JSON output schema explicitly
- Instruct the model to return character offsets (`start`, `end`) for each annotation
- Include guidance on scoring: 0.0 means no patterns detected, 1.0 means the text
  is saturated with the patterns
- Set confidence based on how many patterns were found and how clear the matches are

### CHANGELOG.md

Track prompt revisions:

```markdown
## 0.1.0

- Initial prompt version
- Patterns: pattern_name, another_pattern
```

### versions/

When you revise a prompt, copy the previous `prompt.md` into `versions/` with a
version suffix (e.g., `prompt-0.1.0.md`). Prompts are tracked by SHA256 hash for
reproducibility.

---

## Option 2: Discovery Pipeline

The faster path. Run the discovery pipeline against text, and let it find patterns
the existing detectors miss:

```bash
# Run discovery on a file
stain discover post.txt

# Review hypotheses it generated
stain discover list

# Approve one -- this scaffolds the full detector directory
stain discover approve <hypothesis-id>
```

`stain discover approve` creates the directory structure, generates an initial
`detector.yaml` and `prompt.md`, and registers the detector. You will still want
to review and refine the generated prompt.

---

## Testing a New Detector

Run it against known samples:

```bash
# Single file
stain run --detector D7 --input samples/known-ai.txt

# Full corpus
stain run --detector D7

# Benchmark
stain benchmark run benchmarks/your-config.yaml
```

Compare results before and after:

```bash
stain benchmark compare results/benchmarks/run_before results/benchmarks/run_after
```

---

## Enabling and Disabling

Set `enabled: false` in `detector.yaml` to disable a detector without removing it.
The orchestrator skips disabled detectors during analysis.

You can also override weights in `stain.config.yaml`:

```yaml
detectors:
  D7:
    weight: 0.5
    enabled: true
```

---

## Pattern Naming Conventions

- Use `snake_case` for pattern names
- Names should be descriptive but concise (2-3 words)
- Avoid overlapping with patterns in existing detectors
- Each pattern should target a distinct, observable signal in the text
