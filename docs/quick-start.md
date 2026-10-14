# Mahjong Analyzer クイックスタート

## 前提

Python 3.12と、ローカルに用意したmjai-reviewer・Mortal・利用条件を確認済みのモデル重みが必要です。牌譜は天鳳公式ページから手動で保存してください。自動ログイン・自動取得は行いません。

## 1. 環境を作る

```bash
cd /path/to/mahjong-analyzer
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,dashboard]'
```

## 2. 牌譜を置いて解析する

`.mjlog`を`data/raw/tenhou/inbox/`へ置き、パスを実環境のものへ置き換えて実行します。

```bash
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

登録済みの同一条件はMortal起動前にスキップされ、成功した原本は`processed/`へ移動します。失敗・本人席を確定できない保留は、理由とともに`failed/`または保留状態として残ります。

## 3. ダッシュボードを開く

```bash
.venv/bin/streamlit run app.py --server.address 127.0.0.1
```

指標確認は次のコマンドでも行えます。

```bash
.venv/bin/mahjong-analyzer summary \
  --database local_data/mahjong_analyzer.sqlite3 --threshold 0.05
```

詳細な引数、障害対応、バックアップと公開前確認は [`operation-guide.md`](operation-guide.md) を参照してください。設計上の判断は [`technical-notes.md`](technical-notes.md) と [`architecture.md`](architecture.md) に記載しています。
