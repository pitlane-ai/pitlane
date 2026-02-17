# pitlane YAML Schema

This doc is generated from the Pydantic models.

## Top-level keys

- `assistants`: mapping of assistant names to config.
- `tasks`: list of task definitions.

## Assistant Config

- `adapter`: string (required) - one of: claude-code, cline, codex, mistral-vibe, opencode
- `args`: object (optional) - adapter-specific arguments
- `skills`: array (optional) - list of skill references

## Assertions

- `file_exists`: string
- `file_contains`: { path, pattern }
- `command_succeeds`: string
- `command_fails`: string
- `bleu`: { actual, expected, metric, min_score }
- `rouge`: { actual, expected, metric, min_score }
- `bertscore`: { actual, expected, metric, min_score }
- `cosine_similarity`: { actual, expected, metric, min_score }
