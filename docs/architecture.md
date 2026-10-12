# Mahjong Analyzer — Phase 1 Architecture

## Scope

Phase 1 provides a local, CLI-only storage and reporting layer for Mortal/mjai-reviewer JSON output. It does not log in to Mahjong Soul, download replays, run Mortal, or provide a GUI.

```text
review JSON files
      │
      ▼
normalizer (validate and extract known fields)
      │
      ▼
SQLite: games ── reviews ── decisions
      │
      ▼
metrics/report (condition-separated aggregation)
      │
      ▼
CLI JSON/text output
```

## Modules

- `mahjong_analyzer.schema`: SQLite connection, foreign keys, and schema version.
- `mahjong_analyzer.importer`: JSON validation, explicit metadata handling, SHA-256 identities, and transactional import.
- `mahjong_analyzer.metrics`: threshold calculation helpers.
- `mahjong_analyzer.report`: game listing, game detail, and condition-separated summaries.
- `mahjong_analyzer.cli`: `init-db`, import, listing, detail, and summary commands.

## Data model

`games` identifies the source game. `source_game_id` is used when the reviewer JSON or explicit CLI metadata supplies an identifier. `log_sha256` is only populated when `mjai_log` is present; it is not invented when the original log is unavailable.

`reviews` stores one review execution. The raw JSON hash makes repeated imports idempotent while allowing multiple model, temperature, or reviewer-version results for the same game. Unknown model/GRP identity remains `NULL`.

`decisions` stores one normalized entry per review. The actual action probability is read only from `details[actual_index].prob`. Missing or invalid values are stored as non-comparable with a reason and are excluded from the low-recommendation denominator.

All foreign keys are enabled. Each file import runs in one SQLite transaction. A validation or insert failure rolls back the complete file import.

## Metrics

- AI agreement rate: `total_matches / total_reviewed`; `N/A` when zero.
- Low-recommendation rate: `count(actual_probability < threshold) / comparable decisions`; default threshold `0.05`, configurable at reporting time. Equality with the threshold is not counted.
- Mortal Rating: stored and shown per review. It is not averaged or otherwise combined across games.

Summaries are grouped by engine, reviewer version, model tag/identity, GRP identity, temperature, and rule context. This prevents incompatible evaluation conditions from being silently mixed.

## Database location

The default is `local_data/mahjong_analyzer.sqlite3`, which is ignored by Git. Use `--database` to select another local path. Review JSON files are read-only; the importer does not modify them.
