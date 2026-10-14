"""Safe HTML rendering for decision-time review scenes.

The renderer receives an already reconstructed scene and never queries SQLite.
It embeds only allow-listed local tile assets, so the Streamlit page does not
make per-tile network requests or accept arbitrary file paths.
"""

from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from typing import Any

from ..table_view import compact_table_data, tile_ids_from_action
from ..tile_assets import tile_asset


def _text(value: Any, fallback: str = "不明") -> str:
    return html.escape(fallback if value is None or value == "" else str(value))


def _percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "不明"
    return f"{float(value):.2%}"


def _raw_probability(value: Any) -> str:
    return "未取得" if not isinstance(value, (int, float)) else f"{float(value):.8f}"


def _tile_data(tile_id: str, asset_root: Path) -> tuple[str, bool]:
    asset = tile_asset(tile_id, asset_root=asset_root)
    path = asset.path if asset.path.is_file() else asset_root / "missing.svg"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return "", False
    mime = mimetypes.guess_type(path.name)[0] or "image/gif"
    return f"data:{mime};base64,{encoded}", asset.supported


def _img(tile_id: str, asset_root: Path, classes: str = "", title: str | None = None) -> str:
    src, supported = _tile_data(tile_id, asset_root)
    if not src:
        return f'<span class="ma-unavailable">{_text(tile_id)}</span>'
    label = title or tile_id
    suffix = "" if supported else "（未収録）"
    return (f'<img class="ma-tile {html.escape(classes)}" src="{src}" '
            f'alt="{_text(label)}{suffix}" title="{_text(label)}{suffix}">')


def _action_text(action: Any) -> str:
    if not isinstance(action, dict):
        return "不明"
    labels = {"dahai": "打牌", "chi": "チー", "pon": "ポン", "ankan": "暗槓",
              "kakan": "加槓", "daiminkan": "大明槓", "reach": "リーチ", "hora": "和了"}
    kind = labels.get(action.get("type"), action.get("type", "不明"))
    pai = action.get("pai") or ""
    return f"{kind} {pai}".strip()


def _highlight_class(tile_id: str, actual: set[str], expected: set[str]) -> str:
    is_actual = tile_id in actual
    is_expected = tile_id in expected
    if is_actual and is_expected:
        return "ma-both"
    if is_actual:
        return "ma-actual"
    if is_expected:
        return "ma-recommended"
    return ""


def _highlight_ids(action: Any) -> set[str]:
    # Do not highlight a physical tile for non-discard decisions.
    if not isinstance(action, dict) or action.get("type") not in {"dahai"}:
        return set()
    return {value for value in tile_ids_from_action(action) if isinstance(value, str)}


def _river(items: list[dict[str, Any]], asset_root: Path, position: str) -> str:
    parts: list[str] = []
    for item in items:
        tile_id = item.get("pai")
        if not isinstance(tile_id, str):
            continue
        classes = ["ma-river-tile"]
        if item.get("tsumogiri") is True:
            classes.append("ma-tsumogiri")
        if item.get("riichi_declaration") is True:
            classes.append("ma-riichi")
        if item.get("claimed") is True:
            classes.append("ma-claimed")
        parts.append(_img(tile_id, asset_root, " ".join(classes)))
    rows = max(1, min(3, (len(parts) + 5) // 6))
    return f'<div data-testid="river-{position}" class="ma-river ma-river-area ma-river-rows-{rows} ma-river-{position}" aria-label="{position}の河">{"".join(parts)}</div>'


def _called_side(meld: dict[str, Any]) -> str | None:
    """Return the called tile's side from the actor's viewpoint."""
    actor = meld.get("actor")
    target = meld.get("target")
    if not isinstance(actor, int) or not isinstance(target, int):
        return None
    # From the actor's viewpoint: kamicha=left, toimen=center, shimocha=right.
    return {3: "left", 2: "center", 1: "right"}.get((target - actor) % 4)


def _meld(meld: dict[str, Any], asset_root: Path) -> str:
    kind = meld.get("type")
    ids = tile_ids_from_action(meld)
    if kind == "ankan" and isinstance(meld.get("consumed"), list):
        pieces = [_img(value, asset_root, "ma-meld-tile") for value in meld["consumed"] if isinstance(value, str)]
        if len(pieces) == 4:
            pieces[1] = '<span class="ma-kan-back" title="暗槓：裏面表現は未収録">裏</span>'
            pieces[2] = '<span class="ma-kan-back" title="暗槓：裏面表現は未収録">裏</span>'
    else:
        called_side = _called_side(meld)
        called_index = 0 if isinstance(meld.get("target"), int) and ids else None
        entries = [(value, index == called_index) for index, value in enumerate(ids)]
        if called_index is not None and called_side == "left":
            entries = [entries[called_index]] + [entry for index, entry in enumerate(entries) if index != called_index]
        elif called_index is not None and called_side == "right":
            entries = [entry for index, entry in enumerate(entries) if index != called_index] + [entries[called_index]]
        elif called_index is not None and called_side == "center":
            normal = [entry for index, entry in enumerate(entries) if index != called_index]
            midpoint = len(normal) // 2
            entries = normal[:midpoint] + [entries[called_index]] + normal[midpoint:]
        pieces = []
        for value, called in entries:
            classes = "ma-meld-tile"
            if called:
                classes += f" ma-meld-called ma-called-{called_side or 'unknown'}"
            pieces.append(_img(value, asset_root, classes))
    label = {"chi": "チー", "pon": "ポン", "ankan": "暗槓", "kakan": "加槓", "daiminkan": "大明槓"}.get(kind, "副露")
    source = {"left": "左", "center": "対面", "right": "右"}.get(_called_side(meld))
    title = f"{label} / 鳴き元: {source}" if source else label
    return f'<span class="ma-meld" title="{_text(title)}">{"".join(pieces)}</span>'


def _melds(items: list[dict[str, Any]], asset_root: Path, position: str) -> str:
    if not items:
        return ""
    return f'<div data-testid="melds-{position}" class="ma-melds ma-meld-area ma-melds-{position}" aria-label="{position}の副露">{"".join(_meld(item, asset_root) for item in items)}</div>'


def _score_text(data: dict[str, Any], seat: int) -> str:
    scores = data.get("scores")
    if not isinstance(scores, list) or len(scores) != 4 or not isinstance(scores[seat], int):
        return f"{data['seat_labels'].get(seat, '不明')} 不明"
    return f"{data['seat_labels'].get(seat, '不明')} {scores[seat]:,}"


def render_table_html(scene: dict[str, Any], asset_root: Path) -> str:
    data = compact_table_data(scene)
    seats = data["seats"]
    mortal = data["mortal"]
    actual = _highlight_ids(mortal.get("selected_action"))
    expected = _highlight_ids(mortal.get("mortal_first_action"))
    hand = data["hand"].get("tiles") or []
    hand = sorted((value for value in hand if isinstance(value, str)), key=_tile_sort_key)
    hand_parts = []
    for tile_id in hand:
        hand_parts.append(_img(tile_id, asset_root, _highlight_class(tile_id, actual, expected)))
    tsumo = data["hand"].get("tsumo_tile")
    if isinstance(tsumo, str):
        hand_parts.append(_img(tsumo, asset_root, f"ma-tsumo {_highlight_class(tsumo, actual, expected)}", f"ツモ牌 {tsumo}"))
    riichi = [data["seat_labels"].get(seat, f"{seat}家") for seat in data["riichi_accepted_seats"]]
    pending = [data["seat_labels"].get(seat, f"{seat}家") for seat in data.get("riichi_pending_seats", [])]
    riichi_text = ", ".join(riichi) if riichi else "なし"
    if pending:
        riichi_text += f"（宣言中: {', '.join(pending)}）"
    round_data = data["round"]
    tiles_left = _text(round_data.get("tiles_left"), "未取得")
    kyotaku = _text(round_data.get("kyotaku"), "不明")
    dora = "".join(_img(value, asset_root, "ma-dora-tile", "ドラ表示牌") for value in data["dora_markers"])
    return f'''<div data-testid="review-table-shell" class="ma-table-shell"><div data-testid="review-table" class="ma-table">
      <div data-testid="score-top" class="ma-seat ma-player-area ma-seat-top">{_text(data['seat_labels'][seats.top])}　{_score_text(data, seats.top).split(' ', 1)[-1]}</div>
      <div data-testid="score-left" class="ma-seat ma-player-area ma-seat-left">{_text(data['seat_labels'][seats.left])}　{_score_text(data, seats.left).split(' ', 1)[-1]}</div>
      <div data-testid="score-right" class="ma-seat ma-player-area ma-seat-right">{_text(data['seat_labels'][seats.right])}　{_score_text(data, seats.right).split(' ', 1)[-1]}</div>
      <div data-testid="score-bottom" class="ma-seat ma-player-area ma-seat-bottom">自分　{_score_text(data, seats.self_seat).split(' ', 1)[-1]}</div>
      {_river(data['rivers']['top'], asset_root, 'top')}{_river(data['rivers']['left'], asset_root, 'left')}
      {_river(data['rivers']['right'], asset_root, 'right')}{_river(data['rivers']['self'], asset_root, 'bottom')}
      {_melds(data['melds']['top'], asset_root, 'top')}{_melds(data['melds']['left'], asset_root, 'left')}
      {_melds(data['melds']['right'], asset_root, 'right')}{_melds(data['melds']['self'], asset_root, 'bottom')}
      <div data-testid="center-info" class="ma-center"><div><div class="ma-round-stat">{_text(round_data.get('bakaze'))}場 / {_text(round_data.get('kyoku'))}局 / {_text(round_data.get('honba'))}本場 / 供託 {kyotaku}</div>
        <h2>局面情報</h2><p>{_text(round_data.get('turn_number'))}巡目 / 残りツモ {tiles_left} / {_text(data['hand'].get('shanten'))}向聴</p>
        <div class="ma-dora">ドラ {dora or '<span class="ma-muted">未取得</span>'}</div><p>リーチ: {_text(riichi_text)}</p></div></div>
      <div data-testid="hand-self" class="ma-hand ma-hand-area" aria-label="本人の手牌">{"".join(hand_parts)}</div>
    </div><div data-testid="table-legend" class="ma-legend">赤枠：本人の選択　紫枠：Mortal第一候補　黄＋紫：一致　／　赤点：ツモ切り</div></div>'''


def _tile_sort_key(tile_id: str) -> tuple[int, int, str]:
    if len(tile_id) == 2 and tile_id[0].isdigit():
        return ("mps".index(tile_id[1]), int(tile_id[0]), tile_id)
    return (3, "ESWNPFC".find(tile_id), tile_id)


def render_evaluation_html(scene: dict[str, Any], asset_root: Path) -> str:
    mortal = scene["mortal"]
    actual_action = mortal.get("selected_action")
    expected_action = mortal.get("mortal_first_action")
    candidates = [item for item in mortal.get("candidates", []) if isinstance(item, dict)]
    candidates.sort(key=lambda item: float(item.get("prob")) if isinstance(item.get("prob"), (int, float)) else -1, reverse=True)
    def render_bars(items: list[dict[str, Any]]) -> str:
        bars = []
        for item in items:
            prob = item.get("prob")
            if not isinstance(prob, (int, float)):
                continue
            value = max(0.0, min(1.0, float(prob)))
            action = _action_text(item.get("action"))
            cls = "actual" if item.get("action") == actual_action else ""
            bars.append(f'<div class="ma-prob"><div class="ma-prob-row"><span>{_text(action)}</span><b>{_percent(prob)}</b></div><div class="ma-bar {cls}"><span style="width:{value * 100:.6f}%"></span></div><span class="ma-raw">raw={value:.8f}</span></div>')
        return "".join(bars) if bars else '<span class="ma-muted">候補確率は未取得</span>'

    visible_bars = render_bars(candidates[:3])
    hidden_bars = render_bars(candidates[3:])
    more = ""
    if len(candidates) > 3:
        more = f'<details class="ma-more"><summary>もっとみる（{len(candidates) - 3}件）</summary>{hidden_bars}</details>'
    actual_probability = mortal.get("actual_probability")
    first_probability = candidates[0].get("prob") if candidates else None
    if isinstance(actual_probability, (int, float)) and isinstance(first_probability, (int, float)):
        difference = f"第一候補との差 {_percent(float(first_probability) - float(actual_probability))}"
    else:
        difference = "第一候補との差 不明"
    conditions = f"{mortal.get('model_tag') or 'モデル不明'} / reviewer {mortal.get('reviewer_version') or '不明'} / 温度 {_text(mortal.get('temperature'))}"
    return f'''<div class="ma-panel">
      <div class="ma-card"><h3>局面情報</h3><div>{_text(scene['round'].get('bakaze'))}場 / {_text(scene['round'].get('kyoku'))}局 / {_text(scene['round'].get('turn_number'))}巡目 / {_text(scene['hand'].get('shanten'))}向聴</div><div class="ma-muted">他家リーチ {len(scene['public'].get('riichi_accepted_seats', []))}人 / 評価条件: {_text(conditions)}</div></div>
      <div class="ma-card"><h3>本人の選択</h3><div class="ma-action-line"><strong class="ma-actual-text">{_text(_action_text(actual_action))}</strong><span class="ma-actual-text">本人</span></div><div class="ma-metric ma-actual-text">{_percent(mortal.get('actual_probability'))}</div><div class="ma-muted">行動選択確率 / {difference} <span class="ma-raw">raw={_raw_probability(mortal.get('actual_probability'))}</span></div></div>
      <div class="ma-card"><h3>Mortal第一候補</h3><div class="ma-action-line"><strong class="ma-mortal-text">{_text(_action_text(expected_action))}</strong><span class="ma-mortal-text">第一候補</span></div><div class="ma-muted">Q値や確率は期待得点・放銃率ではありません。</div></div>
      <div class="ma-card"><h3>候補行動（上位3件）</h3>{visible_bars}{more}</div>
    </div>'''


def table_css() -> str:
    return (Path(__file__).with_name("table.css")).read_text(encoding="utf-8")
