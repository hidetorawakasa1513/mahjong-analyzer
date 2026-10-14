# Mahjong Analyzer 運用ガイド

## 1. 初回セットアップ

プロジェクト内の分離環境を使います。システムPythonや`.venv-mortal`は変更しません。

```bash
cd /path/to/mahjong-analyzer
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
# Streamlitを使う場合だけ追加
.venv/bin/python -m pip install -e '.[dashboard]'
```

Mortal、mjai-reviewer、Mahjong-Replay-Converter、利用条件を確認済みのモデル重みは別途ローカルに用意し、コマンドの絶対パスで指定します。モデル重みをリポジトリへコピーしないでください。

## 2. ローカル設定

Git管理外の`local_data/config.json`に本人識別情報を置きます。実データを含まない形の例です。

```json
{
  "tenhou": {
    "account_id": "YOUR_LOCAL_ACCOUNT_ID",
    "player_name": "YOUR_PLAYER_NAME"
  },
  "dashboard": {
    "database": "local_data/mahjong_analyzer.sqlite3",
    "review_root": "local_data",
    "source_root": "data/raw/tenhou"
  }
}
```

`account_id`は牌譜取得には使いません。座席判定は`.mjlog`のプレイヤー名と`player_name`を完全一致させ、ファイル名の`tw=`情報とも照合します。不一致・複数一致・欠落時は解析を開始しません。設定の存在だけを確認する場合は内容を表示せず次を実行します。

```bash
test -s local_data/config.json && echo "Tenhou local identity config exists"
```

## 3. 新しい天鳳牌譜を取り込む

1. 天鳳公式ページから手動保存した、自分の四人麻雀・段位戦の`.mjlog`を用意します。
2. `data/raw/tenhou/inbox/`へコピーします。
3. 次のコマンドで未解析分だけを処理します。

```bash
export PATH="$PWD/.venv-mortal/bin:$PATH"
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou \
  --config local_data/config.json \
  --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /absolute/path/to/mahjong-replay-converter \
  --reviewer-exe /absolute/path/to/mjai-reviewer \
  --mortal-exe /absolute/path/to/Mortal/mortal/mortal \
  --mortal-cfg /absolute/path/to/Mortal/mortal/config.toml \
  --python-path /absolute/path/to/Mortal/mortal \
  --model-tag MODEL_TAG \
  --output-dir local_data/tenhou-analysis
```

入力数、検出数、新規解析数、重複スキップ数、失敗数、保留数、移動数、登録判断数が表示されます。Mortal起動前にゲームID・座席・SHA-256・レビュー条件が一致する正常レビューを照合します。

処理結果は次のように整理されます。

- `inbox/`: 未処理。
- `processed/`: SQLite登録まで成功した原本、または正常登録済みと確認できた重複原本。
- `failed/`: 形式変換、解析、SQLite登録などに失敗した原本と`.error.json`。
- 保留: 本人席などを安全に確定できない原本と`.hold.json`。

ファイル移動に失敗した場合は原本を失わず、`held`として報告します。同名でも内容が異なるファイルは上書きしません。

## 4. 既存の`.mjlog`を移行する

すでに解析済みの原本を再解析せず整理する場合は、`--migrate-existing`を使います。reviewerの事前照合だけを行い、Mortalは起動しません。

```bash
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou \
  --migrate-existing data/raw/tenhou/old-game.mjlog \
  --config local_data/config.json \
  --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /absolute/path/to/mahjong-replay-converter \
  --reviewer-exe /absolute/path/to/mjai-reviewer \
  --mortal-exe /absolute/path/to/Mortal/mortal/mortal \
  --mortal-cfg /absolute/path/to/Mortal/mortal/config.toml \
  --model-tag MODEL_TAG
```

失敗ファイルの再試行は、原因と原本を確認したうえで`organize-tenhou`に`--retry-failed`を追加します。

## 5. DBと指標の確認

```bash
.venv/bin/mahjong-analyzer list-games --database local_data/mahjong_analyzer.sqlite3
.venv/bin/mahjong-analyzer summary --database local_data/mahjong_analyzer.sqlite3 --threshold 0.05
.venv/bin/mahjong-analyzer show-game GAME_ID --database local_data/mahjong_analyzer.sqlite3
```

コンテキスト抽出後は次のCLIを使えます。

```bash
.venv/bin/mahjong-analyzer extract-contexts local_data/tenhou-analysis/analysis/ \
  --database local_data/mahjong_analyzer.sqlite3 \
  --extractor-version phase2-context-v1

.venv/bin/mahjong-analyzer analyze-contexts \
  --database local_data/mahjong_analyzer.sqlite3 \
  --dimension turn_phase --format text

.venv/bin/mahjong-analyzer search-decisions \
  --database local_data/mahjong_analyzer.sqlite3 \
  --turn-phase mid --rank 3 --filter-score-target top --score-max -8000 \
  --riichi-count 1 --bakaze S --format json --limit 100
```

分母0の指標は0%とせず`null`／計算不能として扱います。Ratingはレビュー単位で確認し、対局間で単純平均しません。

## 6. Streamlitを起動する

```bash
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

ダッシュボードは`local_data/config.json`の`dashboard`パスを読み、SQLiteを読み取り専用で開きます。ホーム、状況別分析、復習候補、局面詳細を表示します。データベースが存在しない場合に新規作成はしません。

## 7. Tenhou/6 JSONを直接解析する場合

`.mjlog`変換を使わず、既存のTenhou/6 JSONを入力する場合は`analyze-log`を使います。

```bash
.venv/bin/mahjong-analyzer analyze-log path/to/game.json \
  --player-id 0 \
  --database local_data/mahjong_analyzer.sqlite3 \
  --reviewer-exe /absolute/path/to/mjai-reviewer \
  --mortal-exe /absolute/path/to/Mortal/mortal/mortal \
  --mortal-cfg /absolute/path/to/Mortal/mortal/config.toml \
  --python-path /absolute/path/to/Mortal/mortal \
  --output-dir local_data/analysis
```

## 8. 安全運用と障害対応

- 雀魂・天鳳への自動アクセス、ログイン、Cookie取得、認証トークン取得は行いません。
- `local_data/`、`data/`、モデル重み、レビューJSON、SQLiteはGitへ追加しません。
- 元牌譜とConverter原出力は変更しません。
- Streamlitは読み取り専用です。実データのバックアップはGitとは別の安全な場所で行います。
- `git status`、`git diff --cached`、`git ls-files`で公開対象を確認します。

本人席を解決できない場合は、設定の`player_name`、`.mjlog`の名前、`tw=`を照合してください。推測で`--player-id`を指定しません。既存対局が再解析される場合は、モデルタグ、温度、reviewer条件、ゲームID、座席が同一か確認します。暗槓表記エラーは、既知のConverter v0.2.3とmjai-reviewer 1.5.10の差だけをアダプターが補正します。未知の形式は停止します。
