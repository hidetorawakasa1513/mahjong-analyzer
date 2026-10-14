# Phase 0 技術検証記録

- 検証日: 2026-10-12（Asia/Tokyo）
- 対象: [CODEX_SPEC.md](./CODEX_SPEC.md) の Phase 0 のみ
- 結論（初回調査時点）: 仕様と実装上の接続点は確認できたが、依存関係・モデル重みを導入していないため、Mortal のローカル推論および実牌譜1件の JSON レビューは未完了だった。後段の「Phase 0 実機検証追記」で、公開Tenhouサンプルによる条件付き検証結果を追記する。Phase 1 へはまだ進まない。

## 1. 検証環境

### 実機で確認したもの

実施コマンド:

```sh
sw_vers
uname -m
command -v python3 && python3 --version
command -v rustc || true
command -v cargo || true
git status --short
```

結果:

| 項目 | 結果 |
|---|---|
| OS | macOS 15.8.1 (Build 24H32) |
| CPU アーキテクチャ | `arm64`（Apple Silicon） |
| Python | `/opt/homebrew/bin/python3`, 3.14.2 |
| Rust / Cargo | 未導入（`command not found`） |
| リポジトリの変更 | なし |

依存関係のインストール、OS 全体の設定変更、認証情報の取得は実施していない。したがって「Apple Silicon で動作した」とは判定しない。

## 2. Mortal と mjai-reviewer の仕様

### Mortal

Mortal は日本麻雀用の深層強化学習 AI で、`mjai` の JSON Lines ストリームを入出力する。公式ドキュメントのビルド手順では、Python 環境、最新の Rust、`libriichi` のビルド、別途用意した学習済みモデルが必要とされている。モデル重みはソースリポジトリに含まれない。

Mortal のコードは AGPL-3.0-or-later。モデル重みの配布条件・版ごとの利用条件はモデルの配布元ごとに確認が必要であり、コードのライセンスだけから重みの再配布可否を推測しない。

### mjai-reviewer

現行 `master` の確認時点の `Cargo.toml` はバージョン `1.5.10`、ライセンス Apache-2.0。README は Mortal / akochan をバックエンドに使い、Tenhou形式または Mahjong Soul（雀魂/Jantama）ログをレビューするツールと説明している。README は一般利用について、雀魂は Web アプリを使えばダウンロード・インストール・拡張なしで扱えるとしているが、これはオンラインサービスであり、今回のローカル・オフライン要件そのものの代替ではない。

CLI の現行仕様（`src/opts.rs` と `src/main.rs` をソース確認）:

```text
mjai-reviewer -e mortal -i LOG.json -a PLAYER_ID --json -o REVIEW.json
```

- `-i/--in-file`: Tenhou `tenhou.net/6` 形式の JSON ファイル。`-` または省略相当で stdin。
- `-a/--player-id`: 0〜3。東1局時点の席を基準にした固定プレイヤーID。
- `-e/--engine mortal`: Mortal を選択。
- `--mortal-exe`: Mortal 実行ファイル（既定 `./mortal/mortal`）。
- `--mortal-cfg`: Mortal の設定ファイル（既定 `./mortal/config.toml`）。
- `--temperature`: 表示用 softmax 温度の既定値は `0.1`。ソースコメント上、行動順位と Rating は変更しない。
- `--json`: HTML ではなく JSON レポートを出力。
- `-o/--out-file`: 出力ファイル。未指定時はエンジンとログから既定名を生成。
- `--tenhou-out`: ダウンロードした Tenhou形式ログを保存。
- `--mjai-out`: 変換後の mjai JSON Lines を保存。
- Mortal では半荘（hanchan）のみを受け付ける。三麻や東風戦を初期対象にしない仕様と整合する。

## 3. Apple Silicon Mac での動作方法

### 調査で確認できた手順

公式 Mortal ドキュメントは macOS / Apple Silicon 専用の手順や動作保証を掲載していない。ただし、Rust プロジェクトを macOS arm64 でネイティブビルドする構成であり、ソース上の Apple Silicon 非対応という記述は見つからなかった。これは互換性の推測であり、実機成功の証拠ではない。

実施候補は、プロジェクト内の分離環境で次の順序になる。

1. Apple Silicon 用の Rust toolchain と Python 仮想環境を用意する。
2. Mortal の依存関係と、利用許諾を確認済みのモデル重みを用意する。
3. Mortal 公式手順に従って `cargo build -p libriichi --lib --release` 等を実行する。
4. mjai-reviewer を `cargo build --release` でビルドする。
5. `--mortal-exe` と `--mortal-cfg` を明示してレビューする。

mjai-reviewer README には akochan 用の macOS Homebrew 手順（`llvm libomp boost`）はあるが、Mortal の実行にそれを必要とするとは書かれていない。akachan の依存手順を Mortal に流用しない。

### 実機結果

Rust/Cargo がないため、Mortal と mjai-reviewer のビルド・起動・arm64 推論は未実施。Docker は Mortal 公式に推論用手順があるが、Docker Desktop / イメージ / モデル重みも未導入で、Apple Silicon 上での動作は未検証。次回、導入許可を得た場合にのみ検証する。

## 4. 雀魂 Web版の牌譜取得と変換

### 公式リポジトリで確認できた経路

`mjai-reviewer/mjsoul.adoc` は、ログを取得するローカル経路として次を案内している。

- ブラウザで Tampermonkey を導入し、作者の `downloadlogs.js` をユーザースクリプトとして登録。
- 雀魂にログインし、対象の牌譜を開いて読み込み後に `S` を押して保存。
- 保存された Tenhou形式相当の JSON を `mjai-reviewer -e mortal -i FILENAME -a ACTOR` に渡す。
- 別経路として Majsoul+ の “Save logs” mod も記載されている。

この文書は、過去にはログイン自動化・変換サービスもあったが、サービス停止・雀魂側の制限を記録している。また、別環境とサブアカウントの利用を強く推奨している。今回の仕様で禁止している自動ログイン、通信盗聴、認証トークン収集は実施しない。

### 変換の仕様

現行CLIのローカル入力は任意の雀魂独自JSONではなく、`tenhou.net/6` 形式。プログラムは次の順で処理する。

```text
tenhou.net/6 JSON
  -> convlog の RawLog / Log
  -> tenhou_to_mjai()
  -> mjai JSON Lines
  -> Mortal（MORTAL_REVIEW_MODE=1）
```

`--mjai-out PATH` を付けると、変換後の各イベントを1行1 JSONとして保存できる。従って、保存すべき入力は元の牌譜 JSON、変換確認用の mjai JSON Lines、レビュー JSON の3層である。

### 取得の検証結果

実ユーザーの雀魂牌譜ファイルはこの作業環境に提供されていない。ブラウザ操作・Tampermonkey・Majsoul+ の導入も、利用規約・アカウント影響が未確認のため実施していない。公開または合成の Tenhou形式サンプルを使った変換コマンド実行も、Rust/Cargo 未導入のため未実施。

したがって、雀魂 Web版から実際に取得したファイルが現行変換器で通ること、四麻段位戦の席IDを正しく選べることは未検証。現時点の安全な判断は「手動取得データを入力候補として保持するが、Phase 1 の importer 仕様を確定しない」である。

## 5. Mortal の解析結果を JSON で保存する方法

CLI で `--json` と `-o` を併用する。例えば:

```sh
mjai-reviewer \
  --engine mortal \
  --in-file ./logs/game.json \
  --player-id 2 \
  --mortal-exe ./mortal/mortal \
  --mortal-cfg ./mortal/config.toml \
  --temperature 0.1 \
  --json \
  --out-file ./local_data/reviews/game-p2.json \
  --no-open
```

`--no-open` は JSON ではブラウザを開かないため実質不要だが、HTMLへ切り替える場合の安全策として併記できる。CLI はレビュー中、Mortal を `MORTAL_REVIEW_MODE=1`、`MORTAL_CFG=<設定>` で起動し、mjaiイベントを stdin に送り、Mortal の各応答と最終メタデータを使って1つの `View` JSONを生成する。

現行の JSON 形状はソース上、最上位に `engine`, `game_length`, `version`, `player_id`, `mjai_log`, `review` 等があり、Mortalレビュー部分には少なくとも次がある。

```text
review.total_reviewed
review.total_matches
review.rating
review.temperature
review.model_tag
review.kyokus[].entries[]
review.relative_phi_matrix[]
```

各 `Entry` には `junme`, `tiles_left`, `state`, `expected`, `actual`, `is_equal`, `details`, `shanten`, `at_furiten`, `actual_index` などがある。`details[]` は `action`, `q_value`, `prob` を持つ。`details` は q_value 降順に並べ替えられ、`actual_index` はその並べ替え後の実際の行動位置を指す。

## 6. 3指標の取得・算出方法

### AI一致率

既存出力をそのまま使う。

```text
AI一致率 = review.total_matches / review.total_reviewed
```

`total_reviewed` は全イベント数ではない。Mortal の応答にメタデータがあり、候補行動が2つ以上ある意思決定だけがレビュー対象となる。候補がない、または1つだけの局面はスキップされる。0件は `N/A` とする。パーセント表示への変換だけを追加処理とし、分母を独自に作り直さない。

### 低推奨行動率

初期案の閾値5%は、Phase 0では「仮設定」とする。現行JSONでは、各レビュー対象 `Entry` の実際の行動の確率を次のように取り出せる。

```text
actual_prob = entry.details[entry.actual_index].prob
```

閾値 `t` に対して:

```text
低推奨行動率 = count(actual_prob < t) / count(actual_prob が存在する比較可能なEntry)
```

`actual_index` と `details` の対応は、現行 `mortal.rs` が同じ実際の行動ラベルを探して設定していることをソースで確認した。`q_value` の大小を独自解釈せず、確率は reviewer が温度 `temperature` で計算した `prob` を使う。

ただしこれは「悪手率」ではない。Mortal のモデル分布における実際の選択確率であり、softmax温度、モデルタグ、ルール条件が違えば横比較できない。欠損 `details` / `actual_index` は母数から除外し、除外数を保存する必要がある。kan選択など特殊な候補列も、実データでの対応確認後に含める。

### Mortal Rating

既存出力 `review.rating` をそのまま表示する。現行 `mortal.rs` の実装は、各比較可能局面について次を加算する。

- 一致時: `1`
- 不一致時: `(actual_q_value - min_q_value) / max(max_q_value - min_q_value, 1e-6)`

その後、

```text
rating = (raw_rating / total_reviewed) ^ 2
```

とする。半荘ごとの Rating を単純平均して「期間 Rating」と呼ぶ方法は、現行実装からは正当化できない。期間集計方法は、raw の十分統計量が出力されないため未確定。初期実装では各半荘の Rating、対象局面数、モデルタグ、温度を別々に保持する。

Mortal FAQ が説明する通り、Mortal はプレイ用の深層強化学習モデルで、q値・確率・Ratingは人間向けの因果説明や点棒損失の直接評価ではない。指標名に「AI一致」「低推奨」と明記し、絶対的な最善手や悪手と断定しない。

## 7. ライセンス・安全性

- Mortal のコード: AGPL-3.0-or-later。
- mjai-reviewer: Apache-2.0。
- Mortal のモデル重み: 版・配布元ごとに別途確認が必要。未確認の重みを取得・同梱しない。
- 個人牌譜、認証情報、Cookie、キャッシュ、モデル重みは Git 管理対象にしない。
- `mjsoul.adoc` のユーザースクリプト等を使う場合でも、雀魂の利用規約・外部サービスの取扱いは本調査で確認していない。規約・権利が不明な場合は取り込まない。

## 8. 未検証事項 / ブロッカー

### 未検証

1. この Apple Silicon 実機での Mortal arm64 ビルドと推論速度・メモリ使用量。
2. 現行モデル重みの入手、配置、利用・再配布条件。
3. 実際の雀魂 Web版手動取得ファイルの入手と `tenhou.net/6` 形式としての妥当性。
4. 実牌譜を `--mjai-out` で変換した結果。
5. 実牌譜1件を Mortal でレビューし、JSONファイルを生成すること。
6. 実データで `actual_index` が常に `details[actual_index]` の確率を指すこと（ソース上の実装は確認済みだが、実行結果は未確認）。
7. 三麻・東風戦・特殊ルールの扱い。
8. Ratingを複数半荘で統合する妥当な方法。

### ブロッカー

- Rust/Cargo がない。
- Mortal のモデル重みがない。
- 実牌譜サンプルがない。
- 依存関係導入には、仕様書に従い事前許可が必要。

## 9. 次に進むための最小検証

Phase 1 の実装前に、許可を得た分離ディレクトリで以下だけを行う。

1. Rust toolchain と Python 仮想環境を導入し、バージョンを記録する。
2. 利用条件を確認済みの Mortal モデルを配置する。
3. 公開 Tenhou形式サンプルで `mjai-reviewer --no-review --mjai-out` を実行し、変換を確認する。
4. `--json -o` で1件レビューし、`review.total_reviewed`、`total_matches`、`rating`、`temperature`、`model_tag`、`details[].prob` を保存する。
5. 可能ならユーザーが手動取得した雀魂四麻段位戦1件でも同じ手順を再実行する。

この5項目の成功後に初めて、入力アダプタや保存方式の設計を確定する。

## 10. 参照元

- [Mortal README](https://github.com/Equim-chan/Mortal/blob/main/README.md)
- [Mortal Build documentation](https://mortal.ekyu.moe/user/build.html)
- [Mortal Docker Quick Start](https://mortal.ekyu.moe/user/docker.html)
- [Mortal LICENSE](https://github.com/Equim-chan/Mortal/blob/main/LICENSE)
- [mjai-reviewer README](https://github.com/Equim-chan/mjai-reviewer/blob/master/README.md)
- [mjai-reviewer mjsoul.adoc](https://github.com/Equim-chan/mjai-reviewer/blob/master/mjsoul.adoc)
- [mjai-reviewer src/opts.rs](https://github.com/Equim-chan/mjai-reviewer/blob/master/src/opts.rs)
- [mjai-reviewer src/main.rs](https://github.com/Equim-chan/mjai-reviewer/blob/master/src/main.rs)
- [mjai-reviewer src/review/mortal.rs](https://github.com/Equim-chan/mjai-reviewer/blob/master/src/review/mortal.rs)
- [mjai-reviewer src/render.rs](https://github.com/Equim-chan/mjai-reviewer/blob/master/src/render.rs)
- [mjai-reviewer LICENSE](https://github.com/Equim-chan/mjai-reviewer/blob/master/LICENSE)

## 11. Phase 0 実機検証追記（2026-10-12）

前回の未検証事項に対して、依存関係を既存の親`.venv`から分離して実行した。親フォルダの`.venv`（Python 3.14.2）は変更していない。

### 導入・取得したもの

| 対象 | 結果 |
|---|---|
| Homebrew `rustup` | 1.29.1_1。Homebrew配下へ導入 |
| Rust toolchain | `stable-aarch64-apple-darwin`, rustc 1.99.0, cargo 1.99.0 |
| Python専用環境 | リポジトリ内 `.venv-mortal`, Python 3.12.12 |
| Python依存 | PyTorch 2.14.1, NumPy 2.5.4, tqdm 4.70.1, toml 0.10.2, tensorboard 2.21.0 |
| Mortalソース | `.phase0-work/Mortal`, commit `0cff2b52982be5b1163aa9a62fb01f03ce91e0d2` |
| mjai-reviewerソース | `.phase0-work/mjai-reviewer`, commit `2dc5ec5c8b28517cfb45f57eb21536d9a8f67aa9` |
| Mortal V4モデル | `Yuchen1457/mortal-582500` の `mortal_582500.pth` |
| GRPモデル | C3公開配布物の `grp-best.pth` |

モデル本体の配布ページはAGPL-3.0を表示し、Mortal作者から再配布許可を得た旨を記載している。manifest記載のSHA-256と実ファイルを照合した。

```text
mortal_582500.pth
738e0d6e3c0ce9671629554ad39abd147d2ffbac676e80b194c83f2acc0fea20

grp-best.pth
f769d4e9c57c635c97965e54a4c15278407d5cb0fde6abb1a26e67d79c6074b4
```

GRPはC3リポジトリがMITライセンスで公開している配布物を使用した。Mortal本体とGRPが同一学習 run の組み合わせであることは確認できないため、今回のRatingは「JSONから取得・算出できること」の実証値であり、公式モデルペアの比較値とは扱わない。

### 実行した主なコマンド

```sh
# Python専用環境
/opt/homebrew/bin/python3.12 -m venv .venv-mortal
.venv-mortal/bin/python -m pip install torch numpy tqdm toml tensorboard

# Rust/Python拡張。Python 3.12を明示することが重要
PYO3_PYTHON="$PWD/.venv-mortal/bin/python" \
  cargo build -p libriichi --lib --release
cp target/release/libriichi.dylib mortal/libriichi.so

# mjai-reviewer
cargo build --release
target/release/mjai-reviewer --version

# 公開Tenhouサンプルの取得・変換
target/release/mjai-reviewer --no-review \
  -t 2019050417gm-0029-0000-4f2a8622 \
  --tenhou-out ../logs/sample-tenhou.json \
  --mjai-out ../logs/sample.mjai

# JSONレビュー（CPU経路）
PYTHONPATH="$PWD/../Mortal/mortal" \
MORTAL_CFG="$PWD/../Mortal/mortal/config.toml" \
target/release/mjai-reviewer --engine mortal \
  --in-file ../logs/sample-tenhou.json --player-id 0 \
  --mortal-exe ../Mortal/mortal/mortal \
  --mortal-cfg "$MORTAL_CFG" --temperature 0.1 --json \
  --out-file ../logs/review.json --no-open
```

### ビルド・起動結果

- `libriichi`のビルド成功。`file`結果は `Mach-O 64-bit dynamically linked shared library arm64`。
- `PYTHONPATH`を設定して`import libriichi`に成功。
- 最初のビルドではCargoがPython 3.14を参照し、Python 3.12からのimportに失敗した。`PYO3_PYTHON`を指定して再ビルドすることで解決した。
- `mjai-reviewer` 1.5.10のビルド成功。`file`結果は `Mach-O 64-bit executable arm64`。
- Mortalラッパーの実行権限不足と、ラッパーが呼ぶ`python`のPATH不足を順に修正した。ソースコードの変更はしていない。
- PyTorchはMPSをビルド済みだが、`torch.backends.mps.is_available()`は`False`だった。今回のMortalレビューはMortal本体がCPUを明示する実装のため、CPUで実行した。

### 公開サンプルとJSON結果

公開Tenhouログ `2019050417gm-0029-0000-4f2a8622` を取得し、316行のmjai JSON Linesへ変換した。雀魂へのログインや自動取得は実施していない。

生成物はGit管理外の次の場所にある。

```text
.phase0-work/logs/sample-tenhou.json
.phase0-work/logs/sample.mjai
.phase0-work/logs/review.json
```

JSONのトップレベルには `engine`, `game_length`, `version`, `player_id`, `mjai_log`, `review` があり、`review`には`total_reviewed`, `total_matches`, `rating`, `temperature`, `model_tag`, `kyokus`, `relative_phi_matrix` が存在した。

実測値:

| 指標 | 値 | 根拠 |
|---|---:|---|
| 対象レビュー局面数 | 51 | `review.total_reviewed` |
| AI一致局面数 | 41 | `review.total_matches` |
| AI一致率 | 0.8039215686（80.39%） | `41 / 51` |
| 低推奨行動数 | 10 | `details[actual_index].prob < 0.05` |
| 低推奨行動率 | 0.1960784314（19.61%） | `10 / 51` |
| Mortal Rating | 0.8776929786 | `review.rating` |
| softmax温度 | 0.1 | `review.temperature` |
| モデルタグ | `mortal4-b40c192-t26082106` | `review.model_tag` |

`actual_index`で指定された`details`要素の`prob`を全51局面で取得できた。したがって、3指標の機械的な取得・算出経路は実JSONで確認済み。ただし低推奨行動率の5%は仕様書どおり暫定閾値であり、Ratingと同様にモデル・GRP・温度・ルール条件を固定しない比較には使わない。

### 残る未解決事項

1. Mortal V4本体と今回のGRP重みは別配布物であり、同一学習条件の公式ペアではない。
2. Apple SiliconのMPS推論は未検証。今回の成功条件はCPU推論で満たした。
3. 実際の雀魂Web版手動取得牌譜での変換・レビューは未検証。
4. `--mortal-exe`ラッパーの実行権限は、クローン先で毎回確認が必要。
5. モデルファイル・レビューJSONは`.gitignore`対象であり、公開・コミットしない。

### Phase 0判定

Apple Silicon arm64上で、分離Python環境、Rust拡張、mjai-reviewer、公開牌譜、Mortal CPU推論、JSON出力までの一連の動作を確認した。3指標も実JSONから取得できたため、Phase 0の実行環境検証は「条件付きで完了」とする。

ただし、モデルとGRPの組み合わせおよびMPSは未検証である。Phase 1のアプリ実装へ進まず、次はユーザーが許可したモデル構成を固定するか、同一配布元のMortal/GRPペアを確保する検証を行う。

## 12. Phase 0-C Step 3-A: Mahjong-Replay-Converter CLI実機検証（2026-10-12）

Mahjong-Replay-Converter v0.2.3を、雀魂に接続しない条件でローカルCLI検証した。既存の監査済みソースを再利用し、Commitは次の値と一致した。

```text
61f5ae1f36ee7419173cccb03fe8afdf81d57e28
```

### 隔離環境

- ソース監査ディレクトリ: `/private/tmp/mahjong-replay-converter-audit.TQpKqc/repo`
- Python環境: `/private/tmp/mahjong-replay-converter-cli.tEowlf/.venv`
- Python: 3.12.12
- Apple Silicon向けCPythonを使用
- 既存の`.venv-mortal`、プロジェクト内のPython環境、システムPythonは変更していない
- 生成したサンプル牌譜・設定・出力はすべて`/private/tmp`配下に置き、Git管理対象にしていない

### インストール

実行したコマンド:

```sh
python3.12 -m venv /private/tmp/mahjong-replay-converter-cli.tEowlf/.venv
/private/tmp/mahjong-replay-converter-cli.tEowlf/.venv/bin/python -m pip install \
  --no-input --no-cache-dir --index-url https://pypi.org/simple \
  -e /private/tmp/mahjong-replay-converter-audit.TQpKqc/repo
```

依存パッケージの取得先はPyPIのみで、インストール中に雀魂、Yostar、GitHub Releasesへのアクセスは発生しなかった。ビルドバックエンドは`hatchling`で、`ms-api`はローカルwheelビルドされた。

主要な導入バージョン:

| パッケージ | バージョン |
|---|---:|
| mahjong-replay-converter | 0.2.3 |
| aiohttp | 3.14.5 |
| flet / flet-desktop | 0.85.3 |
| keyring | 25.7.0 |
| ms-api | 0.11.100 |
| platformdirs | 4.13.0 |
| tensoul | 0.1.8 |
| websockets | 15.0.1 |
| protobuf | 7.36.2 |

### CLI検証

ヘルプ表示に成功した。

```sh
/private/tmp/mahjong-replay-converter-cli.tEowlf/.venv/bin/mahjong-replay-converter --help
/private/tmp/mahjong-replay-converter-cli.tEowlf/.venv/bin/mahjong-replay-converter convert-file --help
```

利用可能なサブコマンドは`convert`、`convert-file`、`send-code`である。`cli.py`のimport時に`updater`は読み込まれず、CLI検証中に自動更新処理は起動しなかった。

GUI側には`app.py`から起動時に`check_for_update()`を作成するフックがあり、更新が見つかった場合は`download_update()`と`apply_downloaded_update()`へ進む実装である。したがって、雀魂接続を伴わない検証と自動更新回避にはCLIの`convert-file`を使用し、GUIは起動しない。

### ローカル変換

リポジトリの検証ロジックに基づく合法な1局のMJAI JSON Linesを一時生成し、次を実行した。

```sh
export MAHJONG_REPLAY_CONVERTER_CONFIG_DIR=/private/tmp/mahjong-replay-converter-cli.tEowlf/config
/private/tmp/mahjong-replay-converter-cli.tEowlf/.venv/bin/mahjong-replay-converter \
  convert-file /private/tmp/mahjong-replay-converter-cli.tEowlf/input/legal.mjai.jsonl \
  --output /private/tmp/mahjong-replay-converter-cli.tEowlf/output \
  --format tenhou6
```

結果:

- CLI終了コード: 0
- 出力: `legal-2.json`（487 bytes）
- `ver`: `2.3`
- プレイヤー数: 4
- 局数: 1
- ルール表示: `四人東風戦`
- 牌譜参照ID: `local-legal-sample`
- MJAIからTenhou/6 JSONへの変換: 成功

最初に使用した簡略Tenhouテストデータは、同一牌の既知枚数が5枚を超えるため、CLIの厳密な検証で拒否された。これは入力データの問題であり、合法なMJAI入力では変換に成功した。

また、設定ディレクトリを指定しない場合、CLIは変換後の履歴保存のため既定のmacOS設定先`~/Library/Application Support/MahjongReplayConverter`へ書き込もうとした。隔離検証では`MAHJONG_REPLAY_CONVERTER_CONFIG_DIR`を指定して回避した。実運用でも設定・履歴・Keychainの保存先を事前に確認する必要がある。

### 今回確認できなかった事項

- `convert`による雀魂共有URLの取得。雀魂・Yostarへの接続は禁止したため未実施。
- Yostar認証、認証コード、Tokenの使用。
- GUI起動、GUI自動更新、DMGの実行。
- 実雀魂牌譜のTenhou/6変換。
- Mortal・mjai-reviewerへの接続。
- CLIの完全なpytestスイート。dev依存（pytest等）は今回の目的に不要なため導入していない。

### Step 3-A判定

雀魂へ接続しない分離環境で、Python 3.12、依存パッケージ、CLIヘルプ、ローカルMJAI→Tenhou/6変換まで確認できた。実牌譜取得は未実施であり、次の段階でのみユーザーの明示的な許可を得て検討する。

## 14. Phase 1.5-A: ローカル解析パイプライン実機検証（2026-10-12）

既存のPhase 0環境を再利用し、雀魂・Yostarへ接続せず、公開Tenhouサンプルをmjai-reviewerとMortalで解析してPhase 1 SQLiteへ保存した。

### 使用環境

- 入力: `.phase0-work/logs/sample-tenhou.json`
- mjai-reviewer: `.phase0-work/mjai-reviewer/target/release/mjai-reviewer`、1.5.10、arm64
- Mortal: `.phase0-work/Mortal/mortal/mortal`、CPU実行
- Mortal config: `.phase0-work/Mortal/mortal/config.toml`
- Mortal Python: 既存`.venv-mortal`、PyTorch 2.14.1
- 出力・SQLite: `/private/tmp/mahjong-analyzer-phase15.*`配下

### 実行コマンド

```sh
export PATH="$PWD/.venv-mortal/bin:$PATH"
.venv/bin/mahjong-analyzer analyze-log \
  .phase0-work/logs/sample-tenhou.json \
  --player-id 0 \
  --database /private/tmp/mahjong-analyzer-phase15.RUN/analysis.sqlite3 \
  --reviewer-exe "$PWD/.phase0-work/mjai-reviewer/target/release/mjai-reviewer" \
  --mortal-exe "$PWD/.phase0-work/Mortal/mortal/mortal" \
  --mortal-cfg "$PWD/.phase0-work/Mortal/mortal/config.toml" \
  --python-path "$PWD/.phase0-work/Mortal/mortal" \
  --output-dir /private/tmp/mahjong-analyzer-phase15.RUN/output
```

### 実測結果

- Tenhou/6 JSONのローカル検証: 成功
- mjai-reviewer起動: 成功
- Mortal CPU推論: 成功
- MJAI JSON Lines生成: 成功（16,198 bytes）
- レビューJSON生成: 成功（93,951 bytes）
- SQLite保存: 成功（games 1、reviews 1、decisions 51）
- 同一入力の再解析: `duplicate`となり、件数はgames 1、reviews 1、decisions 51のまま

3指標はPhase 0の実測値と一致した。

| 指標 | 実測値 |
|---|---:|
| total_reviewed | 51 |
| total_matches | 41 |
| AI一致率 | 41/51 = 0.8039215686 |
| 低推奨行動数 | 10 |
| 低推奨行動率（閾値0.05） | 10/51 = 0.1960784314 |
| Mortal Rating | 0.8776929786449009 |

レビューJSONの`loading_time`・`review_time`は実行ごとに変動するため、生JSON SHA-256だけでは再解析が重複することが判明した。生JSONハッシュを保持したまま、これらの揮発フィールドを除いた`review_identity_sha256`を追加して冪等化した。

### 自動テスト

```sh
.venv/bin/python -m pytest -q
```

実装後の単体テストは19件成功。subprocessの引数配列、`shell=False`、実行ファイル不在、Mortal終了失敗、破損レビューJSON、重複、SQLite未作成、入力検証をモックで確認した。

### 未検証事項

- 実際の雀魂牌譜、共有URL、認証、Yostar通信。
- MPS推論。今回もCPU経路のみ。
- 実ユーザーの牌譜に対するプレイヤー座席対応。
- Mortal/GRPモデルの配布条件が異なる構成での比較。

## 13. Phase 1 CLI基盤実装（2026-10-12）

Phase 1のうち、レビューJSONの取り込み・SQLite保存・基本3指標の集計を実装した。雀魂ログイン、共有URL取得、Mortal実行、Streamlit GUIは実装していない。

### 実装内容

- Python 3.12向けの`pyproject.toml`とCLIエントリポイントを追加。
- SQLiteの`games`、`reviews`、`decisions`、`schema_meta`を追加。
- `PRAGMA foreign_keys = ON`、スキーマバージョン、ファイル単位のトランザクションを使用。
- レビューJSONのUTF-8・必須フィールド・型・局面数・プレイヤーIDを検証。
- `details[actual_index].prob`を保存し、欠損・範囲外・不正値を比較不能として記録。
- レビューJSON SHA-256による再取り込み冪等性を実装。
- 同一対局の別レビューを保持し、既知の`mjai_log`内容ハッシュが異なる場合は競合として拒否。
- AI一致率と低推奨行動率を評価条件ごとに加重集計。
- Mortal Ratingはレビュー単位で保存・表示し、複数対局の単純平均は行わない。
- `init-db`、`import-review`、`import-reviews`、`list-games`、`show-game`、`summary`を追加。

### テスト結果

プロジェクト専用`.venv`（Python 3.12.12）にpytest 8.4.2を導入し、以下を実行した。

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests
.venv/bin/mahjong-analyzer --help
```

結果:

- pytest: 13件成功
- Pythonコンパイルチェック: 成功
- CLIヘルプ: 成功
- SQLite初期化、正常取り込み、不正JSON、必須項目欠損、重複、別レビュー、対局競合、誤ったID、0件、確率欠損、閾値変更、加重集計、条件分離、Rating非平均、ロールバックを検証。

テストデータは合成データであり、Phase 0で確認した実データ値`41/51`、`10/51`、`0.8776929786`を再現した実データ検証ではない。実レビューJSONがプロジェクト内に存在しないため、実データの再取り込みは未実施である。

### セキュリティ確認

- 個人牌譜、認証情報、Token、モデル重み、SQLite実データはリポジトリに追加していない。
- `.venv`、`local_data/`、SQLite拡張子を`.gitignore`対象にした。
- CLIに認証コード入力機能や雀魂への通信処理は追加していない。
- 元のレビューJSONは読み取り専用で扱い、変更しない。

## 14. Phase 0-C：天鳳実牌譜1半荘の取り込み検証（2026-10-14）

ユーザーが天鳳公式の牌譜検索・ダウンロードページから手動取得した、四人麻雀・半荘1件を入力に検証した。天鳳サーバーへの追加アクセス、牌譜URLからの再取得、認証処理は実施していない。

### 入力ファイルと形式確認

- 元ファイルはプロジェクト内の`data/raw/tenhou/`へ元バイト列のままコピーした。このディレクトリは`.gitignore`で除外されている。
- `file`およびgzipマジック（`1f 8b`）から、拡張子`.mjlog`の実体はgzip圧縮されたXMLと確認した。
- 展開後のルート要素は`<mjloggm ver="2.3">`。
- XMLには`INIT` 11件、`AGARI` 10件、`RYUUKYOKU` 1件があり、1半荘分のデータと判断できる。
- XMLの`UN`要素は4人分の名前・段位・レート・性別属性を持ち、`GO type="9"`、赤ドラ有効の四人東南戦だった。
- ファイル名の`tw=3`は、XMLの4人目（0始まりの座席ID 3）のプレイヤー情報と一致した。推測だけでなく、`UN n3`と変換後の`name[3]`を照合して対象プレイヤーIDを3と確定した。
- 変換後JSONの最終局の結果を反映した最終点数は、XMLの`owari`/最終得点と一致した。局数、和了・流局数、点数変化の完全なイベント意味検証は変換ツールの検証結果に依存するため、各打牌の手作業照合までは行っていない。

### 変換

監査済みのMahjong-Replay-Converter v0.2.3（固定コミット`61f5ae1f36ee7419173cccb03fe8afdf81d57e28`）のCLIを使用した。ローカルファイル変換は認証不要で、設定保存先だけを一時ディレクトリへ指定した。

```sh
MAHJONG_REPLAY_CONVERTER_CONFIG_DIR=/private/tmp/.../config \
  /private/tmp/.../.venv/bin/mahjong-replay-converter convert-file \
  data/raw/tenhou/<attached-game>.mjlog \
  --output /private/tmp/.../output --format tenhou6
```

Converterの出力はTenhou/6 JSONとして生成されたが、暗槓2件が`a24242424`・`a34343434`の形式だった。mjai-reviewer 1.5.10のTenhou/6パーサーは暗槓マーカーを4枚目位置（例：`242424a24`）に要求するため、元ファイルとConverter出力を保持したまま、解析用コピーの2箇所だけマーカー位置を補正した。この互換性補正は一回限りの検証処理であり、変換器本体やプロジェクトの解析コードは変更していない。

補正前のJSONをmjai-reviewerへ渡した場合は`invalid tile string: "a2"`で失敗した。補正後はMJAI JSON LinesとレビューJSONの生成に成功した。当時はConverter v0.2.3とmjai-reviewer 1.5.10の暗槓表記互換性が未解決の改善課題だったが、Phase 1.5-Bで解析前アダプターを追加した。

### Mortal解析とSQLite保存

既存の`analyze-log`を使用し、Mortal・mjai-reviewer・モデル・設定はPhase 0/1.5-Aで検証済みのものを再利用した。

```sh
export PATH="$PWD/.venv-mortal/bin:$PATH"
.venv/bin/mahjong-analyzer analyze-log \
  local_data/real-tenhou-<date>/<attached-game>.reviewer-compatible.json \
  --player-id 3 \
  --database local_data/real-tenhou-20261014/mahjong_analyzer.sqlite3 \
  --reviewer-exe .phase0-work/mjai-reviewer/target/release/mjai-reviewer \
  --mortal-exe .phase0-work/Mortal/mortal/mortal \
  --mortal-cfg .phase0-work/Mortal/mortal/config.toml \
  --python-path .phase0-work/Mortal/mortal \
  --output-dir local_data/real-tenhou-20261014/analysis
```

実測値は次のとおり。値はこのモデル・温度・ルール条件に限った結果であり、客観的な正解率・悪手率・失点とは解釈しない。

| 項目 | 実測値 |
|---|---:|
| 対象プレイヤーID | 3 |
| `total_reviewed` | 136 |
| `total_matches` | 103 |
| AI一致率 | 103/136 = 0.7573529412 |
| 低推奨行動数（`prob < 0.05`） | 30 |
| 低推奨行動率 | 30/136 = 0.2205882353 |
| Mortal Rating | 0.8974231516817629 |
| Mortalモデル | `mortal4-b40c192-t26082106` |
| reviewer | `mjai-reviewer 1.5.10` |
| 温度 | 0.1 |
| 実行デバイス | CPU |

レビューJSONの実測値とSQLiteの`reviews`・`decisions`を照合し、games 1件、reviews 1件、decisions 136件が一致した。`list-games`、`show-game`、`summary`でも確認できた。同じ入力を再実行した結果は`duplicate`で、登録件数は変化しなかった。

### 発生した問題と未解決事項

- Converter CLIの初回実行では、最近使ったファイルの保存先をユーザーのApplication Supportへ作成しようとして権限エラーになった。設定ディレクトリを`MAHJONG_REPLAY_CONVERTER_CONFIG_DIR`で一時領域へ指定することで解決した。
- Converter v0.2.3の暗槓Tenhou/6表記とmjai-reviewer 1.5.10の期待形式が一致しない。Phase 1.5-Bで、解析前の一時コピーに限定した一般化補正を実装した。
- 個人牌譜、変換JSON、MJAI、レビューJSON、SQLiteはプロジェクト内のGit管理外領域に保存している。公開ドキュメントにはプレイヤー名・個別局面・認証情報を記録していない。
- MortalのCPU解析は成功したが、MPS経路、他ルール、他モデルでの結果は未検証。

### テスト結果

```sh
.venv/bin/pytest
```

結果は19件成功。入力形式確認、ConverterによるTenhou/6 JSON生成、mjai-reviewer/Mortal実解析、JSONとSQLiteの指標照合、同一入力の重複防止を確認した。天鳳公式サイトへの追加通信は行っていない。

## 15. Phase 1.5-B：天鳳 `.mjlog` 自動取り込み・互換性補正（2026-10-14）

### 実施範囲

Phase 0-Cで確認したConverter v0.2.3、mjai-reviewer 1.5.10、Mortalの実行ファイルを再利用し、ローカルの`.mjlog`だけを入力にする経路を追加した。雀魂・天鳳サーバー、認証、共有URL、自動取得にはアクセスしていない。既存の個人牌譜、MJAI、レビューJSON、SQLiteはGit管理外のまま保持した。

### Tenhou/6イベント互換性調査

Converter v0.2.3の監査済みソースと、mjai-reviewer 1.5.10の`convlog/src/conv.rs`およびTenhouログパーサーを比較した。次の「Converter形式」はConverterがMJAIからTenhou/6へ出力する形式、「reviewer形式」はmjai-reviewer 1.5.10が受理するマーカー位置である。

| イベント | Converter出力の要点 | reviewerの期待 | 判定・保持性 |
|---|---|---|---|
| 暗槓 | `a` + 4枚、例 `a24242424` | `4枚目の直前`、例 `242424a24` | 構文不一致。アダプターでマーカーだけ移動し、4牌は保持 |
| 加槓 | `k`と4枚、既存ポンの出所に応じて`k`位置が0/2/4 | `k`位置0/2/4 | ソース上、一致。意味は牌と出所を保持 |
| 大明槓 | `m`位置0/2/6と4枚 | `m`位置0/2/6 | ソース上、一致。鳴いた相手を保持 |
| チー | `c`位置0と3枚 | `c`位置0、7文字 | ソース上、一致。チーは上家からのみ受理 |
| ポン | `p`位置0/2/4と3枚 | `p`位置0/2/4、7文字 | ソース上、一致。出所を位置で保持 |
| リーチ宣言・成立 | `rNN`を打牌列へ出力 | `rNN`をリーチ打牌として解釈し、直後の成立イベントを生成 | ソース上、一致。供託は局結果/点数差分側で保持 |
| ツモ切り | Tenhou/6の`60`（内部ではTsumogiri） | `60`をツモ切りとして後続ツモ牌で補完 | ソース上、一致 |
| 赤ドラ | Tenhou tile code 51/52/53 | 同じ牌コードを赤牌として変換 | ソース上、一致。実牌譜で赤牌を含むことも確認済み |
| 和了 | 結果配列の`和了`、点数差分、和了者/放銃者、詳細 | `Hora`と点数差分へ変換 | ソース上、一致。元結果の詳細を保持 |
| 流局 | 結果配列の流局状態と点数差分 | `Ryukyoku`と点数差分へ変換 | ソース上、一致 |
| 点数移動 | 結果配列の4人分差分 | `score_deltas`として保持 | ソース上、一致 |

加槓・大明槓・チー・ポン・リーチ・ツモ切り・和了・流局・赤牌について、mjai-reviewer付属の合成/回帰入力19件を`--no-review`で変換し、全件成功した。これはConverterの全分岐を実牌譜で再現したことを意味しないため、Converter出力と各イベントの意味の完全な網羅検証は未完了である。一方、mjai-reviewer側のパーサーが各形式を受理できることはローカルで確認した。

### 互換性アダプター

`src/mahjong_analyzer/compat.py`を追加した。入力Tenhou/6をディープコピーし、アクション欄の型、牌コード、マーカー、文字数を検証する。暗槓についてのみ、Converter v0.2.3の`aXXXXXXXX`を、同じ8桁の牌コードを保った`XXXXXXaXX`へ変換する。すでに`a`が位置6にある入力は再変換しない。未知のマーカー位置や牌コードはエラーにして、推測による補正をしない。元`.mjlog`、Converter原出力、変換後の意味上の牌順は変更せず、解析用Tenhou/6コピーだけを生成する。

### `.mjlog`取り込み経路

`mahjong-analyzer analyze-tenhou FILE_OR_DIR`を追加した。処理順は、gzip/XML検証、1半荘・四人麻雀の構造確認、Converterのローカル実行、互換性補正、mjai-reviewerの`--no-review`変換、重複判定、未登録時だけ既存の`analyze_log`（mjai-reviewer + Mortal + importer）である。subprocessは`shell=False`の引数配列で起動し、Converterの設定保存先は出力ディレクトリ配下へ隔離する。

重複判定はMortal起動前に行う。ゲームID、元`.mjlog` SHA-256、変換後MJAIの正規化SHA-256を補助的に照合し、座席、reviewerバージョン、温度、モデルタグ、Mortalレビューの正常保存済み状態を条件にする。同じゲームでも座席や解析条件が違えば別レビューとして扱える。ディレクトリ入力では各ファイルを独立に処理し、入力数、検出数、新規解析数、重複スキップ数、失敗数、登録判断数をJSONで表示する。空の/不正な入力や複数対局を含むファイルは安全側にエラーとする。

### 実機検証

既存の天鳳実牌譜1件を、既存DBを変更せず一時DBで実行した。

```sh
.venv/bin/mahjong-analyzer analyze-tenhou data/raw/tenhou \
  --player-id 3 --database /private/tmp/<temporary>.sqlite3 \
  --converter-exe /private/tmp/<converter-venv>/bin/mahjong-replay-converter \
  --reviewer-exe .phase0-work/mjai-reviewer/target/release/mjai-reviewer \
  --mortal-exe .phase0-work/Mortal/mortal/mortal \
  --mortal-cfg .phase0-work/Mortal/mortal/config.toml \
  --python-path .phase0-work/Mortal/mortal \
  --model-tag mortal4-b40c192-t26082106 \
  --output-dir /private/tmp/<output>
```

初回は`input_files=1, detected_games=1, analyzed_games=1, skipped_duplicates=0, failures=0, registered_decisions=136`となり、一時DBにgames 1件、reviews 1件、decisions 136件が登録された。再実行は`analyzed_games=0, skipped_duplicates=1, failures=0, registered_decisions=0`となった。既存DBに対しては、旧実装時のゲームID表記が異なる状態でも、変換後MJAIの正規化ハッシュによりMortalを起動せず`skipped_duplicates=1`となり、既存のgames 1件・reviews 1件・decisions 136件を維持した。

一時DBで生成されたレビューは、従来の手動補正版と同じく`total_reviewed=136`、`total_matches=103`、Mortal Rating `0.8974231516817629`であった。AI一致率、低推奨行動率はそれぞれ`103/136`、`30/136`（閾値`prob < 0.05`）である。これは使用モデル、温度、ルール、CPU実行条件に依存し、客観的な正解率・悪手率・失点を意味しない。

### テスト

- `.venv/bin/pytest -q`: 23件成功。
- mjai-reviewer付属Tenhou/6回帰入力19件を`--no-review`でローカル変換: 19件成功。
- 既存実牌譜の一時DB取り込み: 成功。
- 同じ入力の再実行: Mortal前に1件スキップ、登録件数不変。
- 既存DBへの再取り込み: Mortal前に1件スキップ、既存件数不変。
- 天鳳サーバー、雀魂、Yostar、認証情報への通信: 実施していない。

### 未解決事項

- Converter v0.2.3の全イベントを、Converter自身の出力で個別に生成して意味比較する検証は未完了。今回の非暗槓イベントはソース比較とreviewer回帰入力での受理確認までである。
- `games`の旧行には旧実装由来の`source_game_id`が残る場合がある。既存データを削除・初期化せずに検出するため、現実装はMJAIハッシュをフォールバックに使用する。
- 1つの`.mjlog`に複数半荘が含まれる形式、三人麻雀、未対応のルール表記は未対応として拒否する。
- 新しい実牌譜での第2段階検証は未実施。ユーザーが新しいファイルを提供した後に実行する。

## 16. 天鳳牌譜の自動整理・取り込みワークフロー（2026-10-14）

### フォルダとCLI

`data/raw/tenhou/`配下に次の3フォルダを作成する`organize-tenhou`コマンドを追加した。

```text
data/raw/tenhou/
├── inbox/
├── processed/
└── failed/
```

通常は天鳳公式ページから手動保存した`.mjlog`を`inbox/`へ置き、既存のConverter、互換性アダプター、mjai-reviewer、Mortal、SQLite経路を次のコマンドで実行する。

```sh
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou --player-id 3 \
  --database local_data/mahjong_analyzer.sqlite3 \
  --converter-exe /path/to/mahjong-replay-converter \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --python-path /path/to/Mortal/mortal \
  --model-tag mortal4-b40c192-t26082106 \
  --output-dir local_data/tenhou-analysis
```

### 整理の安全性

- SQLite登録が成功するまで原本を`processed/`へ移動しない。
- 移動は一時ファイルへコピーし、SHA-256を検証してから原本を除去する。
- `processed/`に同名・同内容がある場合でも、SQLiteに同一条件の正常レビューがあることを確認してからinbox側コピーを除去する。
- 同名・異内容は上書きせず、SHA-256先頭12文字を含む別名へ保存する。
- 変換、解析、SQLite登録の失敗は原本を`failed/`へ移動し、`.error.json`へ理由とSHA-256を記録する。
- 移動に失敗した場合は原本を保持し、`held`として報告する。
- `--retry-failed`で`failed/`の原本を再試行できる。失敗した場合はfailedに残す。

DB上のレビュー重複とファイル重複は分離して扱う。同一ゲームIDでも保存済みの`source_sha256`と異なる入力は自動スキップせず、上書きもしない。旧DB行で`source_sha256`が未設定の場合は、MJAIログの正規化SHA-256を照合できた場合だけ既存レビューとみなす。

### 既存牌譜の移行

既に解析済みだった天鳳実牌譜1件を、`--migrate-existing`で再解析せずに移行した。reviewerの事前変換、既存レビューとモデル・温度・座席の照合、SHA-256のバックフィルだけを行い、Mortalは起動していない。

```sh
.venv/bin/mahjong-analyzer organize-tenhou \
  --root data/raw/tenhou \
  --migrate-existing data/raw/tenhou/<existing>.mjlog \
  --player-id 3 --database local_data/real-tenhou-20261014/mahjong_analyzer.sqlite3 \
  --converter-exe /path/to/mahjong-replay-converter \
  --reviewer-exe /path/to/mjai-reviewer \
  --mortal-exe /path/to/Mortal/mortal/mortal \
  --mortal-cfg /path/to/Mortal/mortal/config.toml \
  --model-tag mortal4-b40c192-t26082106
```

結果は`processed/`への移動成功、元ファイルSHA-256の一致、games 1件・reviews 1件・decisions 136件の維持、`source_sha256`の記録であった。既存レビューや判断レコードは削除・再登録していない。個人牌譜のファイル名や内容は公開ドキュメントへ追加していない。

### テスト

- pytest: 30件成功。
- 空のinboxによる3フォルダ自動作成: 成功。
- 新規解析成功後のprocessed移動: 成功。
- 登録済み同一SHA-256のMortal前スキップとinboxコピー整理: 成功。
- 解析失敗時のfailed移動と理由ログ: 成功。
- 同名・異内容の上書き防止: 成功。
- 既存牌譜の再解析なし移行: 成功。
- `git diff --check`: 成功。

新しい実牌譜の取り込みはまだ実施していない。自動ダウンロード、スクレイピング、ログイン、認証情報取得も実施していない。

## 17. 天鳳プレイヤー情報保存・座席自動判定（2026-10-14）

### ローカル設定

`local_data/config.json`を追加し、天鳳アカウント識別子と本人プレイヤー名を保存した。このファイルは`local_data/`全体の`.gitignore`規則によりGit管理外であり、公開README、コード、テスト、技術文書には個人ID・プレイヤー名を記録していない。天鳳IDはログイン、認証、牌譜取得には使用しない。

2件の既存`.mjlog`をローカル解析した結果、XMLの`UN`要素にはアカウントIDではなく4人分の名前属性が存在した。両ファイルで同じ本人名が確認でき、既存ファイルは座席3、新規ファイルは座席0だった。アカウントIDとXML内のIDを直接対応付けることはできないため、座席判定は設定名との完全一致で行う。

### 座席判定

`mahjong_analyzer.identity`を追加し、`UN n0`〜`n3`をURLデコードして設定の`player_name`と完全一致させる。候補が0件または複数件の場合は`IdentityResolutionError`として保留し、部分一致は行わない。手動`--player-id`が指定された場合もXML判定と一致しなければ保留する。

ファイル名の`tw=0`、`tw=3`、`_tw3`はビュー指定として抽出し、XMLから確定した本人座席と照合する。一致しない場合、不正な値の場合は保留する。`tw=`がない場合は、XMLの本人名を一意に判定できれば処理可能である。`tw=`だけで本人を決定しない。

保留ファイルは通常の解析失敗と区別し、`failed/`へ原本を移動したうえで`.hold.json`に理由を記録する。Mortalは起動しない。設定不在・本人名未設定・曖昧一致・`tw=`不一致を同じ保留経路で再試行可能にした。

### CLIと件数表示

`organize-tenhou`と`analyze-tenhou`の`--player-id`を任意指定にし、通常は`--config local_data/config.json`から自動判定する。従来の手動指定は互換性のため残し、設定とXMLの照合を通過する場合だけ利用できる。

重複ファイルのSHA-256事前判定より前にXMLの対局IDと本人座席を確定するため、入力2件が同一内容の重複1件と新規1件の場合でも`detected_games=2`として表示される。出力には従来の項目に加え、`db_registered_games`、`db_registered_reviews`、`db_registered_decisions`、`duplicate_files`を追加した。

### 回帰検証

- pytest: 39件成功。
- 4つの座席ID（0〜3）の完全一致判定: 成功。
- URLデコード済みプレイヤー名: 成功。
- 本人名の不一致・複数一致・設定不備: 保留エラーを確認。
- `tw=`一致・不一致・欠落: 成功。`tw=`不一致は保留。
- 手動座席とXML判定の矛盾: 保留。
- 個人設定を用いた既存2半荘の自動座席判定: 成功。2件ともDB登録済みとしてMortal前にスキップ。
- 実DBの最終件数: games 2、reviews 2、decisions 301を維持。
- 新しい実牌譜の追加解析、既存DBの初期化、外部アクセス: 今回は実施していない。

## 16. Phase 2-B 第1段階：局面コンテキスト抽出（2026-10-14）

Phase 2-Aの設計に基づき、保存済みレビューJSONのMJAIイベント列から判断コンテキストを抽出する機能を実装した。Mortal、mjai-reviewer、天鳳サーバーへの接続は行っていない。既存の`games`、`reviews`、`decisions`を保持し、`decision_contexts`を追加する安全なスキーマ更新とした。

### 実装

- `decision_contexts`を追加し、`UNIQUE(decision_id, extractor_version)`、外部キー、状態・行動・巡目・向聴数・リーチ・点数・イベント位置を保存する。
- `extract-contexts` CLIを追加した。
- レビューJSONのMJAI列を局単位に分割し、行動内容・座席・牌・`tiles_left`・イベント順で対応づける。
- `none`は直前の他家打牌に対する非行動機会として一意に対応できる場合だけ保存し、見送りの分母へ追加しない。
- `reach_accepted`を基準に成立済みリーチを追跡し、局開始点へリーチ支払いと結果差分を時系列適用して判断直前点数を求める。
- Reviewerが出力した向聴数、判断時点の手牌・副露を保存する。独自の向聴数計算は導入していない。

### 検証結果

既存の実データを一時SQLiteへ複製して検証した。games 2、reviews 2、decisions 301は維持され、decision_contexts 301件が生成された。実イベント対応251件、非行動機会対応50件、部分復元0件、対応不能0件だった。向聴数・巡目・点数・順位・点差は全301件で取得できた。再抽出は重複扱いとなり、decision_contexts件数は増加しなかった。

### 未解決事項

順位は暫定的にスコア降順の競技順位で算出している。天鳳固有の同点タイブレーク、全ルール差異を含む点数再構成、全境界ケースでの`junme`定義は未確定である。Phase 2-Bの集計では、これらを確定するまで順位値を公式順位として解釈しない。

## 17. Phase 2-B 第2段階：状況別集計・条件検索（2026-10-14）

### 実装内容

- `mahjong_analyzer.analytics`を追加し、`decision_contexts`を再利用する集計・検索処理を独立させた。
- `analyze-contexts`で全体、巡目帯、向聴数、他家リーチ人数、順位、点数差、行動種類、場風、親子、局番号、本場を集計できるようにした。
- `search-decisions`で複数条件をAND結合し、`decision_id`、MJAIイベント位置、行動、Mortal第一候補、推奨確率をページング取得できるようにした。
- 動的なSQL列名は許可リストから選択し、値はパラメータバインディングした。集計・検索CLIはDB初期化を行わず読み取り専用で接続する。
- Mortal Ratingはレビュー単位のまま返し、状況別・対局間の単純平均は行わない。`none`は保存済み判断として扱うが、見送り機会を新規推定しない。

### 実DBの読み取り検証

既存の実DBに対してMortalを再実行せず検証した。`games=2`、`reviews=2`、`decisions=301`、`decision_contexts=301`を維持した。評価条件が異なる2レビューは別グループとして保持され、全体の判断数を合算すると301件、AI一致数は227件、低推奨確率（0.05未満）は64件だった。既存`summary`の結果と一致した。

分類件数の合計は、巡目帯301、向聴数301、他家リーチ人数301、順位301、行動種類301、場風301、親子301、局番号301、本場301、トップとの差301だった。順位は同点を`unknown`として集計した。実DBでは同点を含むため、順位を天鳳公式順位として解釈していない。

代表的な分類件数は次のとおりである。評価条件ごとの内訳はCLI JSONで確認できる。

| 軸 | 確認結果 |
|---|---|
| 巡目帯 | 序盤156、中盤118、終盤23、未知4 |
| 向聴数 | 聴牌22、1向聴80、2向聴116、3向聴以上83 |
| 他家リーチ | なし238、1人55、2人以上8 |
| 順位 | 2位143、3位93、4位50、未知40（条件別内訳の合計から算出） |
| 行動種類 | discard 230、none 50、pon 6、chi 4、riichi 5、hora 4、ankan 1、kakan 1 |

上表の順位・行動・点数差は評価条件ごとの行を合算した値であり、欠損を推測で補っていない。トップとの差の初期区分は`0`、`behind:4000-7999`、`behind:8000-11999`、`behind:12000+`で、実DBではそれぞれ34、30、49、188件だった。符号は「トップから離されている」を負値としている。

条件検索の代表例（中盤、3位、トップとの差-8,000以下、他家リーチ1人、南場）は10件を取得でき、安定した`decision_id`順で返った。検索結果は局面復習へ渡す識別情報を含む。

### テストと未解決事項

合成SQLiteを使ったテストで、分類境界、符号付き点数差、同点順位の`unknown`、分母0のNULL、`none`の集計、AND検索、ページング、SQLインジェクション入力の非混入を確認した。既存テストと合わせて46件成功した。実DBは読み取り専用で扱い、Mortal・天鳳サーバー・外部サービスへ接続していない。

未解決事項は、天鳳固有の同点順位規則、異なるルール条件の点数差解釈、Ratingの状況別指標化である。これらはPhase 2-Cの復習表示や将来の比較設計で確定する。

## 18. Phase 2-C①：復習用局面データ取得（2026-10-14）

### 実装

- `mahjong_analyzer.review.get_review_scene()`と`show-decision` CLIを追加した。
- `decision_id`から`decision_contexts`、登録済みレビューJSON、MJAIイベント列を照合して局面を再構築する。
- 通常行動は対応イベント前、`none`は参照した他家打牌を公開した後の状態を返す。`none`を鳴き見送りと断定しない。
- 手牌・副露・向聴数・本人リーチ状態はレビュー判断状態、河・公開副露・リーチ成立・ドラ表示牌はMJAI再生から取得する。
- Mortalの実際の行動、第一候補、候補確率、Q値、評価条件をレビューJSONから返す。Q値は点数損失へ変換しない。
- レビューJSONはSHA-256または登録時の安定識別子で照合し、元`.mjlog`はSHA-256照合できた場合のみ参照パスを返す。

### 既存301判断の読み取り検証

既存DBを変更せず、2つの登録レビューJSONと`data/raw/tenhou/processed/`の元牌譜を指定して301判断を検証した。

| 項目 | 件数 |
|---|---:|
| 局面取得成功 | 301 |
| 完全復元 | 301 |
| 部分復元 | 0 |
| 不整合・取得不能 | 0 |
| 通常行動 | 251 |
| `none`判断 | 50 |
| 点数整合 | 301 |
| MJAIイベント位置 | 301 |
| 元牌譜SHA-256参照可能 | 301 |

全301件で公開河、公開副露、リーチ状態、ドラ表示牌、Mortal判断情報を取得できた。レビューJSONのMJAIイベント番号は0始まりで、元XMLのノード番号とは別物として出力する。局面取得は元`.mjlog`を変更せず、SQLiteへの追加書き込みも行っていない。

### テストと未解決事項

合成MJAIと一時SQLiteで通常打牌、`none`、公開河、候補確率、同点順位のNULL化、JSONシリアライズ、レビュー不一致を検証した。既存テストと合わせて49件成功した。

未解決事項は、Phase 2-C②での画像表示・局面ナビゲーション、さらに多様なイベント境界（鳴き直後、嶺上ツモ、リーチ宣言直前）の表示仕様である。今回のバックエンドでは公開イベントを再生できる範囲を返し、推測による補完は行っていない。
