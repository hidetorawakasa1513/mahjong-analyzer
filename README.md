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
  --player-id 3 \
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
