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
