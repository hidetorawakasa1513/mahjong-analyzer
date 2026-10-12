# Mahjong Analyzer — Phase 1 Architecture

## Scope

Phase 1.5-A adds a local analysis pipeline to the Phase 1 CLI. It accepts an existing Tenhou/6 JSON file, invokes the already-built mjai-reviewer and Mortal processes, preserves local intermediate files, and imports the generated review JSON into SQLite. It does not log in to Mahjong Soul, download replays, or provide a GUI.

```text
Tenhou/6 JSON
      │
      ▼
analyze-log (safe subprocess argument vector)
      │
      ├── mjai JSON Lines + review JSON (local output)
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
- `mahjong_analyzer.runner`: Tenhou/6 validation, mjai-reviewer/Mortal subprocess execution, intermediate output handling, and existing importer integration.

## Data model

`games` identifies the source game. `source_game_id` is used when the reviewer JSON or explicit CLI metadata supplies an identifier. `log_sha256` is only populated when `mjai_log` is present; it is not invented when the original log is unavailable.

`reviews` stores one review execution. `review_sha256` preserves the raw JSON identity. `review_identity_sha256` is a stable identity with reviewer timing fields such as `loading_time` and `review_time` excluded, so rerunning the same input and conditions does not create a duplicate only because execution time changed. Multiple model, temperature, or reviewer-version results for the same game remain separate. Unknown model/GRP identity remains `NULL`.

`decisions` stores one normalized entry per review. The actual action probability is read only from `details[actual_index].prob`. Missing or invalid values are stored as non-comparable with a reason and are excluded from the low-recommendation denominator.

All foreign keys are enabled. Each file import runs in one SQLite transaction. A validation or insert failure rolls back the complete file import.

## Metrics

- AI agreement rate: `total_matches / total_reviewed`; `N/A` when zero.
- Low-recommendation rate: `count(actual_probability < threshold) / comparable decisions`; default threshold `0.05`, configurable at reporting time. Equality with the threshold is not counted.
- Mortal Rating: stored and shown per review. It is not averaged or otherwise combined across games.

Summaries are grouped by engine, reviewer version, model tag/identity, GRP identity, temperature, and rule context. This prevents incompatible evaluation conditions from being silently mixed.

## Database location

The default is `local_data/mahjong_analyzer.sqlite3`, which is ignored by Git. Use `--database` to select another local path. `analyze-log` writes generated MJAI and review JSON to `local_data/analysis` by default; use `--output-dir` to select another ignored local path. Input Tenhou/6 and review JSON files are read-only.
