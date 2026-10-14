# Mahjong Analyzer — Phase 1 Architecture

## Scope

Phase 1.5-A adds a local analysis pipeline to the Phase 1 CLI. It accepts an existing Tenhou/6 JSON file, invokes the already-built mjai-reviewer and Mortal processes, preserves local intermediate files, and imports the generated review JSON into SQLite. It does not log in to Mahjong Soul, download replays, or provide a GUI.

Phase 1.5-B adds local Tenhou `.mjlog` ingestion. `analyze-tenhou` accepts one file or a directory, validates raw XML/gzip XML, invokes the local Mahjong-Replay-Converter, applies only the verified Tenhou/6 compatibility normalization, and then reuses the existing reviewer/Mortal/import pipeline. A reviewer `--no-review` preflight is used to skip a matching saved review before Mortal starts. The source file SHA-256 and actual Tenhou game ID are retained for identity checks.

The normal operator workflow is implemented by `organize-tenhou`. It creates `inbox/`, `processed/`, and `failed/` below the configured raw replay root. A file is copied with hash verification and removed from `inbox/` only after SQLite success; failures retain a reason sidecar in `failed/`. Existing reviewed files can be migrated with `--migrate-existing` using reviewer preflight only, without starting Mortal. Destination name collisions never overwrite a different hash.

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

For `.mjlog` input the conversion and duplicate gate are:

```text
local .mjlog file/directory
      │
      ▼
XML/gzip validation → Mahjong-Replay-Converter → compatibility adapter
      │
      └── reviewer --no-review preflight → duplicate check → Mortal review
```

## Modules

- `mahjong_analyzer.schema`: SQLite connection, foreign keys, and schema version.
- `mahjong_analyzer.importer`: JSON validation, explicit metadata handling, SHA-256 identities, and transactional import.
- `mahjong_analyzer.metrics`: threshold calculation helpers.
- `mahjong_analyzer.report`: game listing, game detail, and condition-separated summaries.
- `mahjong_analyzer.cli`: `init-db`, import, listing, detail, and summary commands.
- `mahjong_analyzer.runner`: Tenhou/6 validation, mjai-reviewer/Mortal subprocess execution, intermediate output handling, and existing importer integration.
- `mahjong_analyzer.compat`: strict Tenhou/6 action validation and the Converter v0.2.3 concealed-kan marker normalization.
- `mahjong_analyzer.tenhou`: local `.mjlog` inspection, conversion, preflight duplicate detection, batch counts, and reuse of `runner`.
- `mahjong_analyzer.workflow`: inbox processing, hash-verified organization, failure sidecars, retry handling, and reviewed-file migration.

## Data model

`games` identifies the source game. `source_game_id` is used when the reviewer JSON or explicit CLI metadata supplies an identifier. `source_sha256` stores the raw local `.mjlog` hash when the Tenhou importer is used. `log_sha256` is only populated when `mjai_log` is present; it is not invented when the original log is unavailable.

`reviews` stores one review execution. `review_sha256` preserves the raw JSON identity. `review_identity_sha256` is a stable identity with reviewer timing fields such as `loading_time` and `review_time` excluded, so rerunning the same input and conditions does not create a duplicate only because execution time changed. Multiple model, temperature, or reviewer-version results for the same game remain separate. Unknown model/GRP identity remains `NULL`.

`decisions` stores one normalized entry per review. The actual action probability is read only from `details[actual_index].prob`. Missing or invalid values are stored as non-comparable with a reason and are excluded from the low-recommendation denominator.

All foreign keys are enabled. Each file import runs in one SQLite transaction. A validation or insert failure rolls back the complete file import.

## Metrics

- AI agreement rate: `total_matches / total_reviewed`; `N/A` when zero.
- Low-recommendation rate: `count(actual_probability < threshold) / comparable decisions`; default threshold `0.05`, configurable at reporting time. Equality with the threshold is not counted.
- Mortal Rating: stored and shown per review. It is not averaged or otherwise combined across games.

Summaries are grouped by engine, reviewer version, model tag/identity, GRP identity, temperature, and rule context. This prevents incompatible evaluation conditions from being silently mixed.

## Database location

The default is `local_data/mahjong_analyzer.sqlite3`, which is ignored by Git. Use `--database` to select another local path. `analyze-log` writes generated MJAI and review JSON to `local_data/analysis` by default; `analyze-tenhou` writes converter output, normalized Tenhou/6 JSON, preflight MJAI, review MJAI, and review JSON below `local_data/tenhou-analysis` by default. Use `--output-dir` to select another ignored local path. Input `.mjlog`, Tenhou/6, and review JSON files are read-only. A Tenhou duplicate requires matching game/source-log identity, seat, reviewer version, temperature, and model tag for a successfully stored Mortal review.
