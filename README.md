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

AI一致率と低推奨行動率は評価条件ごとに集計されます。低推奨行動率は`actual_probability < threshold`で計算し、欠損確率は分母から除外します。これは客観的な悪手率ではありません。Mortal Ratingは対局ごとに保存・表示し、複数対局の単純平均は行いません。モデル、GRP、reviewer、温度、ルールが不明な値は不明のまま保存します。

データベース、レビューJSON、個人牌譜、認証情報、モデル重みはGitへ追加しないでください。

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
