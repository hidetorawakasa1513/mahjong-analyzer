# 麻雀王国 牌画素材

## 出典

- 素材ページ: https://www.mj-king.net/sozai/
- 萬子: https://www.mj-king.net/sozai/download/manzu2.html
- 筒子: https://www.mj-king.net/sozai/download/pinzu2.html
- 索子: https://www.mj-king.net/sozai/download/sozu2.html
- 字牌: https://www.mj-king.net/sozai/download/tupai2.html
- 取得日: 2026-10-15
- 著作権者: 麻雀王国掲載の牌画素材（ページ上で別作者表記は確認できず）

## 利用条件（取得時に確認）

各牌画ページの「使用にあたり」には、次の案内がある。

1. ご自由にお使いください。
2. 連絡は必要ありません（リンクもしくは出典表示は感謝いたします）。
3. 改造、再配布なども問題ありません。
4. 著作権を放棄するものではありません。

このリポジトリでは、出典URLを保持し、牌画素材カテゴリだけを利用する。LINEスタンプキャラ素材は利用していない。

## 取得範囲と対応

47×63ピクセルの「縦向き牌画1」（各ページの`*_2_1.zip`）から、通常の数牌27種と字牌7種を取得した。ZIP内のmacOSメタデータは含めず、元画像のGIFピクセルデータは改変していない。ファイル名はMJAI識別子に合わせているが、元ファイル名は次の規則で追跡できる。

- `1m.gif`〜`9m.gif` ← `p_ms1_1.gif`〜`p_ms9_1.gif`
- `1p.gif`〜`9p.gif` ← `p_ps1_1.gif`〜`p_ps9_1.gif`
- `1s.gif`〜`9s.gif` ← `p_ss1_1.gif`〜`p_ss9_1.gif`
- `E/S/W/N/P/F/C.gif` ← `p_ji_e_1.gif` / `p_ji_s_1.gif` / `p_ji_w_1.gif` / `p_ji_n_1.gif` / `p_no_1.gif` / `p_ji_h_1.gif` / `p_ji_c_1.gif`

## 赤五について

47×63の4セット（`manzu2_all.zip`、`pinzu2_all.zip`、`sozu2_all.zip`、`tupai2_all.zip`）には赤五画像が含まれていなかった。そのため通常5牌を別牌として割り当てず、`scripts/create_red_tiles.py`で元画像の牌面インクだけを赤系へ変換した派生画像を作成する。元の5牌GIFは変更しない。派生画像は麻雀王国の配布元画像そのものではなく、加工物であることを明記する。

## 加工・再配布

通常牌の原画像はリサイズ・再着色・合成せず、Streamlitで縦横比を維持して表示する。赤五派生画像だけは、次のコマンドで再生成する。

```bash
.venv/bin/python scripts/create_red_tiles.py
```

GitHubへの再配布は、上記のページ表示条件に基づくものとして出典情報を同梱する。利用条件が変更された場合は、以後の再配布可否を再確認する。
