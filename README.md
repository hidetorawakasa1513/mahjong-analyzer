# Mahjong Analyzer

雀魂の牌譜を活用して、自分の打牌傾向や弱点を分析するツールです。

## 目的

- Mortalを利用した打牌評価
- AI一致率・低推奨行動率・Mortal Ratingの可視化
- 対局データの蓄積
- 弱点の分析
- 過去の打牌との比較による成長の可視化

## 技術構成

- Python
- Mortal
- mjai-reviewer
- SQLite（標準ライブラリ）
- pytest（開発時）
- Streamlit（将来予定）

## 開発状況

Phase 0の技術検証を終え、Phase 1のCLI基盤を実装しています。雀魂へのログイン・自動取得・GUIは対象外です。

## Phase 1 CLI

Python 3.12の分離環境でインストールします。

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

データベースを初期化します。

```bash
.venv/bin/mahjong-analyzer init-db
```

Mortal/mjai-reviewerのJSONを1件取り込みます。対局IDと対象プレイヤーがJSONに含まれない場合だけ、明示的に指定してください。元JSONは変更されません。

```bash
.venv/bin/mahjong-analyzer import-review path/to/review.json \
  --database local_data/mahjong_analyzer.sqlite3 \
  --game-id GAME_ID --player-id 0
```

複数ファイルを取り込む場合:

```bash
.venv/bin/mahjong-analyzer import-reviews path/to/reviews/ \
  --database local_data/mahjong_analyzer.sqlite3
```

確認・集計:

```bash
.venv/bin/mahjong-analyzer list-games --database local_data/mahjong_analyzer.sqlite3
.venv/bin/mahjong-analyzer show-game 1 --database local_data/mahjong_analyzer.sqlite3
.venv/bin/mahjong-analyzer summary --database local_data/mahjong_analyzer.sqlite3
.venv/bin/mahjong-analyzer summary --threshold 0.10 --database local_data/mahjong_analyzer.sqlite3
```

## Phase 1.5-A: ローカル牌譜解析

雀魂へ接続せず、ローカルに保存済みのTenhou/6 JSONを既存のmjai-reviewer・Mortalへ渡して解析できます。実行ファイルとMortal設定は明示指定します。

```bash
export PATH="$PWD/.venv-mortal/bin:$PATH"
.venv/bin/mahjong-analyzer analyze-log path/to/game.json \
  --player-id 0 \
  --database local_data/mahjong_analyzer.sqlite3 \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --python-path /path/to/Mortal/mortal \
  --output-dir local_data/analysis
```

`--player-id`はTenhouの座席番号で、0が東家、1が下家、2が対面、3が上家です。入力Tenhou/6の`ref`がレビューJSONに引き継がれない場合に備え、入力の`ref`を対局IDとして保存します。対局IDが入力にない場合は`--game-id`を指定してください。`--python-path`はMortalラッパーが使用するPythonモジュールの場所です。

解析結果としてMJAI JSON LinesとレビューJSONを`--output-dir`へ保存し、レビューJSONは既存のPhase 1インポーターでSQLiteへ登録します。再実行時は`loading_time`・`review_time`を除いた安定識別子で重複判定します。入力ファイル・中間ファイル・SQLiteはGit管理対象外にしてください。

失敗時はレビューJSONの検証・SQLite登録前に停止します。subprocessは`shell=False`の引数配列で起動し、雀魂、Yostar、認証情報にはアクセスしません。

AI一致率と低推奨行動率は評価条件ごとに集計されます。低推奨行動率は`actual_probability < threshold`で計算し、欠損確率は分母から除外します。これは客観的な悪手率ではありません。Mortal Ratingは対局ごとに保存・表示し、複数対局の単純平均は行いません。モデル、GRP、reviewer、温度、ルールが不明な値は不明のまま保存します。

データベース、レビューJSON、個人牌譜、認証情報、モデル重みはGitへ追加しないでください。

## Phase 1.5-B: 天鳳 `.mjlog` のローカル取り込み

天鳳公式ページから手動保存した `.mjlog` または gzip XML のみを入力にできます。雀魂・天鳳サーバーへのアクセスやログインは行いません。入力ファイルは読み取り専用で扱い、Converter出力と解析結果はGit管理外の出力先へ保存します。

単一ファイルの例:

```bash
export PATH="$PWD/.venv-mortal/bin:$PATH"
.venv/bin/mahjong-analyzer analyze-tenhou path/to/game.mjlog \
  --config local_data/config.json \
  --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /path/to/mahjong-replay-converter \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --python-path /path/to/Mortal/mortal \
  --model-tag mortal4-b40c192-t26082106 \
  --output-dir local_data/tenhou-analysis
```

複数ファイルはディレクトリを指定します。既存レビューと、ゲームIDまたは入力ログ/MJAIログ・座席・reviewerバージョン・温度・モデル条件が一致する対局は、Mortal起動前にスキップします。結果には入力数、検出数、新規解析数、重複スキップ数、失敗数、登録判断数がJSONで表示されます。

Converter v0.2.3の暗槓表記だけは、mjai-reviewer 1.5.10の期待するマーカー位置と異なるため、解析用コピーに限って厳密に正規化します。未知の表記は拒否し、元の `.mjlog` とConverter原出力は変更しません。

## 天鳳牌譜の通常運用（自動整理）

通常は、次のフォルダを作成して運用します。

```text
data/raw/tenhou/
├── inbox/       # 新しく手動ダウンロードしたファイルを置く
├── processed/   # SQLite登録まで成功した原本
└── failed/      # 失敗した原本と理由ログ
```

### 初回設定と座席自動判定

本人の天鳳IDとプレイヤー名は、Git管理外の`local_data/config.json`に保存します。天鳳IDはログインや牌譜取得には使用しません。プレイヤー名は`.mjlog`の`UN`要素をURLデコードし、4人の名前と完全一致する1席を本人席として判定します。ファイル名の`tw=0`や`_tw3`はビュー情報としてXML判定結果と照合し、不一致・欠落した本人名・複数一致はMortalを起動せず保留します。

設定の存在だけを確認する場合は、ファイル内容を標準出力へ表示せず次のように確認できます。

```bash
test -s local_data/config.json && echo "Tenhou local identity config exists"
```

通常運用では`--player-id`を指定せず、`--config`の設定から座席を自動判定します。`--player-id`を明示した場合も、設定・XMLの本人席と一致しなければ処理を停止します。

天鳳から手動ダウンロードした`.mjlog`を`inbox/`へ置き、次のコマンドを実行します。

```bash
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou \
  --config local_data/config.json \
  --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /path/to/mahjong-replay-converter \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --python-path /path/to/Mortal/mortal \
  --model-tag mortal4-b40c192-t26082106 \
  --output-dir local_data/tenhou-analysis
```

登録済みの同一内容は、本人席を確定した後にSHA-256とSQLiteの正常レビューを確認してから解析せず整理します。同名でも内容が異なるファイルは上書きせず、SHA-256付きの別名にします。解析や登録に失敗したファイルは`failed/`へ移動し、`.error.json`に理由を記録します。本人を特定できない保留は`.hold.json`に理由を記録し、通常の失敗と区別します。移動に失敗した場合は元ファイルを保持して`held`として報告します。

過去に解析済みで、現在`data/raw/tenhou/`直下にある原本を再解析せず移行する場合は、`--migrate-existing PATH`を指定します。この処理はreviewerの事前変換とSQLite照合だけを行い、Mortalを起動しません。

```bash
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou \
  --migrate-existing data/raw/tenhou/old-game.mjlog \
  --config local_data/config.json --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /path/to/mahjong-replay-converter \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --model-tag mortal4-b40c192-t26082106
```

失敗後に再試行する場合は`--retry-failed`を追加します。自動ダウンロード、スクレイピング、ログイン、認証情報の取得は行いません。

## Phase 2-B 第1段階: 局面コンテキスト抽出

保存済みのレビューJSONから、Mortalを再実行せずに判断時点の局面情報を抽出し、既存の`decisions`に紐づく`decision_contexts`へ保存できます。元の`games`、`reviews`、`decisions`は変更しません。

```bash
.venv/bin/mahjong-analyzer extract-contexts local_data/tenhou-analysis/analysis/ \
  --database local_data/mahjong_analyzer.sqlite3 \
  --extractor-version phase2-context-v1
```

抽出対象はレビューJSONのMJAIイベント列です。実イベントは局内順序、行動、座席、牌、`tiles_left`で対応づけます。`actual.type == "none"`は、直前の他家打牌に対するレビュー上の非行動機会として一意に復元できる場合だけ`non_action_opportunity`として保存し、鳴きの見送り件数と断定しません。曖昧な場合は`unmapped`になります。

`decision_contexts`には、局・本場・巡目、本人の手牌と副露、Reviewerの向聴数、成立済み他家リーチ、判断直前の4人の点数、順位・点差、行動カテゴリ、MJAIイベント位置、抽出器バージョンを保存します。抽出器を更新するときは`--extractor-version`を変更して旧結果を保持します。個人牌譜、レビューJSON、SQLiteはGit管理対象外です。

## Phase 2-B 第2段階: 状況別集計と判断検索

保存済みの`decision_contexts`を読み取り、Mortalを再実行せずに状況別の集計と複数条件検索を行えます。集計CLIは既存DBを初期化せず、読み取り専用で接続します。

```bash
.venv/bin/mahjong-analyzer analyze-contexts \
  --database local_data/mahjong_analyzer.sqlite3 \
  --dimension turn_phase --format text

.venv/bin/mahjong-analyzer analyze-contexts \
  --database local_data/mahjong_analyzer.sqlite3 \
  --dimension score_diff --score-diff-target top \
  --score-bins 0,4000,8000,12000 --format json
```

利用できる集計軸は、全体、巡目帯、向聴数、他家リーチ人数、順位、点数差、行動種類、場風、親子、局番号、本場です。巡目帯は初期値を序盤1〜6・中盤7〜12・終盤13巡目以降とし、`--early-end`と`--mid-end`で変更できます。点数差は符号付きで、トップとの差は「離されている」場合を負値として扱います。区間境界は`--score-bins`で変更できます。

条件検索は指定した条件をANDで適用します。例えば次は「中盤・3位・トップとの差が8,000点以上・他家リーチ1人・南場」を検索します。

```bash
.venv/bin/mahjong-analyzer search-decisions \
  --database local_data/mahjong_analyzer.sqlite3 \
  --turn-phase mid --rank 3 --filter-score-target top --score-max -8000 \
  --riichi-count 1 --bakaze S --format json --limit 100
```

検索結果には`decision_id`、局・イベント位置、行動種類、本人の選択、Mortal第一候補、選択行動の推奨確率、評価条件を含めます。`--offset`と`--limit`で安定したページングができます。AI一致率と低推奨行動率は有効な値だけを分母にし、分母0は`null`です。Mortal Ratingは評価条件ごとのレビュー単位で返し、状況別・対局間で平均しません。同点順位は天鳳固有ルールが未確定のため`unknown`として扱います。`none`判断は保存された判断として集計しますが、見送り機会の新規推定は行いません。

## Phase 2-C①: 復習用局面の取得

`search-decisions`で得た`decision_id`から、判断直前の手牌・副露、公開河、公開副露、成立済みリーチ、ドラ表示牌、点数、Mortal候補を取得できます。レビューJSONのMJAIイベント列を再走査し、通常行動はイベント処理前、`none`は参照した他家打牌を公開した後の状態として返します。

```bash
.venv/bin/mahjong-analyzer show-decision \
  --database local_data/real-tenhou-20261014/mahjong_analyzer.sqlite3 \
  --decision-id 123 \
  --review-root local_data \
  --source-root data/raw/tenhou \
  --format json
```

レビューJSONを自動探索せず明示する場合は`--review-json PATH`を指定できます。レビューJSONのSHA-256または安定識別子をSQLiteのレビュー記録と照合します。MJAIのイベント番号はレビューJSON内の`mjai_log`の0始まり番号であり、元XMLのノード番号ではありません。元`.mjlog`の参照可能性、局面状態、点数整合性は`status`と`status_reasons`で確認できます。非公開の他家手牌や未公開の山牌は出力しません。順位は同点時に`null`です。

## Phase 2-C②: 復習候補一覧

保存済みの判断から、復習を優先する候補を一覧できます。候補抽出は読み取り専用で、Mortalを再実行しません。

```bash
.venv/bin/mahjong-analyzer review-candidates \
  --database local_data/mahjong_analyzer.sqlite3 \
  --sort low-probability --limit 10 --format text

.venv/bin/mahjong-analyzer review-candidates \
  --database local_data/mahjong_analyzer.sqlite3 \
  --sort disagreement --disagreement-only --limit 20 --format json

.venv/bin/mahjong-analyzer review-candidates \
  --database local_data/mahjong_analyzer.sqlite3 \
  --sort recent --turn-phase mid --filter-score-target top \
  --score-max -8000 --riichi-count 1 --limit 10 --format json
```

`--sort low-probability`は本人の選択確率の昇順（NULLは末尾）、`--sort disagreement`はAI不一致を先頭、`--sort recent`は対局日時の新しい順です。日時がない場合はファイル更新日時を使わず、対局IDと判断IDによる安定順にフォールバックします。`--disagreement-only`で不一致だけに絞れます。既存の巡目、向聴数、リーチ人数、順位、点数差、場風、親子、行動種類、評価条件のフィルタをANDで利用できます。

候補には`decision_id`、局面要約、行動、Mortal第一候補、AI一致、不一致、推奨確率、MJAIイベント位置、復元状態が含まれます。候補の詳細は既存の`show-decision --decision-id ID`で確認してください。推奨確率は復習優先度の参考値であり、損失額や客観的な悪手スコアではありません。`none`判断も除外せず、非行動判断として一覧に含めます。

## Phase 3-A〜3-B①: Streamlitダッシュボード

ダッシュボード用依存関係はoptional dependencyとして分離しています。

```bash
.venv/bin/pip install -e '.[dashboard]'
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

`local_data/config.json`の`dashboard`設定からSQLite・レビューJSON・元牌譜のパスを読み込みます。設定ファイルはGit管理外です。SQLiteは読み取り専用で開き、DBが存在しない場合は作成せずエラーを表示します。

ホーム、状況別分析、復習候補、局面詳細の4画面を提供します。状況別分析と復習候補では評価条件を選択し、条件が一致するデータだけを扱います。統計は分子・分母を合算して比率を計算し、判断数・AI一致率・低推奨選択率を切り替えてグラフ表示できます。分析分類と条件は復習候補へ引き継がれ、候補はページ番号で閲覧できます。対局日時がDBにない場合は「日時不明」と表示し、ファイル更新日時や対局IDから補完しません。牌画像・麻雀卓表示・復習メモはPhase 3-B②の対象です。

## 麻雀牌SVG素材プレビュー

MJAIの牌識別子に対応する37種類の自作SVGは`assets/tiles/`にあります。既存の全牌セットを再生成する場合は次を実行します。

```bash
.venv/bin/python scripts/generate_tile_assets.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory assets/tiles
```

ブラウザで`http://127.0.0.1:8765/preview.html`を開くと分類別一覧を確認できます。

現実寄りデザインの代表牌16種は、全牌生成器とは分離した試作生成器で更新します。デザイン確認時は次を実行してください。

```bash
.venv/bin/python scripts/generate_tile_prototypes.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory assets/tiles
```

`http://127.0.0.1:8765/prototype-preview.html`で萬子・筒子・索子・字牌・赤牌を標準／小サイズで確認できます。試作段階では16種だけを更新し、Streamlitの局面詳細画面には組み込みません。

## 今後の予定

1. Mortalとmjai-reviewerの動作検証（完了・条件付き）
2. CLIによるレビューJSONの取り込み・SQLite保存（Phase 1・実装済み）
3. 実牌譜の安全な手動取り込み検証
4. 弱点・成長分析
5. ダッシュボードの実装

## 開発方針

Mortalに実装されている機能は最大限活用し、
不足している機能だけを独自に実装します。

初期段階では、無料・ローカル環境での動作を目指します。
