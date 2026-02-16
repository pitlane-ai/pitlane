# YAML Configuration

## Assertion Types

### Deterministic (Preferred)
- `file_exists: "path"` - Check file presence
- `file_contains: {file: "path", pattern: "regex"}` - Regex match in file
- `command_succeeds: "cmd"` - Command exits 0
- `command_fails: "cmd"` - Command exits non-zero

### Similarity-Based (When exact matching isn't feasible)
- `bleu: {reference_file: "ref", candidate_file: "out", threshold: 0.5}` - BLEU score (0.0-1.0)
- `rouge: {reference_file: "ref", candidate_file: "out", threshold: 0.5}` - ROUGE score (0.0-1.0)
- `bertscore: {reference_file: "ref", candidate_file: "out", threshold: 0.8}` - BERT similarity (0.0-1.0)
- `cosine_similarity: {reference_file: "ref", candidate_file: "out", threshold: 0.85}` - Embedding similarity (0.0-1.0)

## Best Practices

- Prefer deterministic assertions (more stable and reproducible)
- Keep fixtures small (faster iteration)
- Set appropriate timeouts (balance patience vs fast failure)