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
- `mahjong_analyzer.identity`: local identity configuration, exact decoded player-name matching, manual-seat cross-checking, and `tw=` view validation.
- `mahjong_analyzer.analytics`: read-only context aggregation, parameterized multi-condition decision search, configurable turn/score buckets, and structured JSON results for future UI reuse.
- `mahjong_analyzer.review`: decision-id based scene retrieval, review JSON/MJAI event replay, public-information reconstruction, and Mortal candidate packaging for future review UI.
- `mahjong_analyzer.review_candidates`: reusable candidate listing with shared context filters, stable sorting, pagination, and review-scene identifiers.
- `app.py` / `mahjong_analyzer.dashboard.data`: optional Streamlit read-only dashboard adapter. It delegates all calculations, candidate selection, and scene reconstruction to existing APIs. Local `dashboard` paths are loaded from the ignored config file; account fields are not read by the dashboard.

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

The default is `local_data/mahjong_analyzer.sqlite3`, which is ignored by Git. Use `--database` to select another local path. `local_data/config.json` is also ignored by Git and stores the local Tenhou account identifier and player name. `analyze-log` writes generated MJAI and review JSON to `local_data/analysis` by default; `analyze-tenhou` writes converter output, normalized Tenhou/6 JSON, preflight MJAI, review MJAI, and review JSON below `local_data/tenhou-analysis` by default. Use `--output-dir` to select another ignored local path. Input `.mjlog`, Tenhou/6, and review JSON files are read-only. A Tenhou duplicate requires matching game/source-log identity, resolved seat, reviewer version, temperature, and model tag for a successfully stored Mortal review.

## Phase 2-B 第1段階

保存済みレビューJSONのMJAIイベント列を読み取り、`decision_contexts`へ局面コンテキストを抽出する。Mortalは再実行しない。既存の`decisions`は変更せず、`UNIQUE(decision_id, extractor_version)`で抽出器の更新と再計算を分離する。

`source_event_index`はレビューJSON内のMJAI配列の論理位置で、`source_round_event_index`は局内位置である。実イベントは順序・行動内容・`tiles_left`を使って対応づける。`none`は非行動機会として対応できた場合だけ`mapping_kind=non_action_opportunity`で保存し、見送りの分母へ自動追加しない。

`decision_contexts`には、判断直前の本人手牌・副露、Reviewer向聴数、`reach_accepted`に基づく成立済みリーチ、局開始点からリーチ支払いと結果差分を順序適用した4人の点数、スコア降順の競技順位と点差を保存する。同点順位の天鳳固有ルールは未確定のため、採用ポリシーを抽出器の記録対象とし、将来変更可能にする。復元不能な値はNULLと状態理由を保存する。

## Phase 2-C①

`review.get_review_scene()`は、登録済みの`decision_id`からレビューJSON内のMJAIログと`decision_contexts`を再利用して局面を構成する。通常の行動は対応イベントの処理前、`none`の非行動機会は参照された公開打牌を含む時点を返す。手牌・副露はレビューの判断状態を使用し、河・公開副露・リーチ状態・ドラ表示牌はMJAIを判断時点まで再生して作る。返却データにはイベント基準、元牌譜SHA-256、レビューJSON参照、状態理由を含める。

元牌譜が存在する場合はSHA-256照合済みの参照を返す。復元自体はレビューJSONに保存されたMJAIから可能だが、元`.mjlog`がない場合も推測で補完せず、参照不可として明示する。非公開手牌・未公開山牌を公開情報の構造へ含めない。MortalのQ値や確率は評価値として返し、点数損失へ変換しない。

## Phase 2-C②

`review_candidates.list_review_candidates()`は`analytics`の共通フィルタ・後処理を再利用し、`low-probability`、`disagreement`、`recent`の3モードで候補を返す。日時不明の対局はファイル更新時刻を使わず、対局ID・判断IDの安定順にフォールバックする。NULLの推奨確率は低確率順の末尾とする。不一致優先は保存済みの`is_equal`定義を使用し、`none`を除外しない。返却結果は`show-decision`へ渡せる`decision_id`を含む。

## Phase 3-A

Streamlitの`app.py`は、ホーム、状況別分析、復習候補、局面詳細を提供する薄い表示層である。`dashboard.data.connect_readonly()`はSQLite URIの`mode=ro`と`query_only`でDBを開き、既存APIの`summary`、`aggregate_contexts`、`list_review_candidates`、`get_review_scene`を呼び出す。DB、レビューJSON、元牌譜のパスはローカル画面から指定し、外部通信は行わない。画面状態は`st.session_state`でページ、分析条件、選択した`decision_id`を保持する。牌画像や卓面レイアウトは後続Phaseへ分離する。

## Phase 3-B①

`local_data/config.json`の`dashboard`ブロックは、SQLite・レビューJSON・元牌譜の相対パスをプロジェクトルート基準で解決する。既存の天鳳アカウント設定は読み書きしない。分析・候補画面は`ContextFilters`のモデル、reviewer、温度、モデル識別子、GRP識別子、ルール条件を選択し、`aggregate_contexts()`と`list_review_candidates()`へ渡す。`rule_context`のNULL条件はSQLの`IS NULL`として扱い、別条件との混在を防ぐ。画面表示では日本語ラベルへ変換し、統計比率は分子・分母を合算して算出する。

## Phase 2-B 第2段階

`analytics`は`games`、`reviews`、`decisions`、`decision_contexts`を結合して読み取り、評価条件（エンジン、reviewer、モデル、GRP、温度、ルール）ごとに結果を分離する。`analyze-contexts`は状況別集計、`search-decisions`はAND条件検索を提供する。SQL値はパラメータバインディングし、動的な列名は許可リストから選択する。

AI一致率と低推奨行動率は有効な分母を個別に計算し、分母0はNULLで返す。Ratingはレビュー単位の`ratings_by_review`として保持し、状況別に平均しない。順位は同点を`unknown`とし、点数差は`top`を`gap_to_first`へ写像して符号を維持する。検索結果は`decision_id`と`source_event_index`を含み、Phase 2-Cの局面復習から再利用できる。
