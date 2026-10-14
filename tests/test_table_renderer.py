from pathlib import Path

from mahjong_analyzer.dashboard.table_renderer import render_evaluation_html, render_table_html, table_css


ASSETS = Path(__file__).parents[1] / "assets/third_party/mj_king/tiles"


def _scene(player_id: int = 0) -> dict:
    return {
        "identity": {"player_id": player_id},
        "round": {"bakaze": "E", "kyoku": 1, "honba": 0, "kyotaku": 1,
                   "turn_number": 4, "tiles_left": 60},
        "hand": {"tiles": ["1m", "5mr", "7p"], "tsumo_tile": "5pr", "fuuros": [{"type": "pon", "actor": 0, "target": 1, "pai": "E", "consumed": ["E", "E"]}], "shanten": 1},
        "public": {
            "rivers": [[{"pai": "1m", "tsumogiri": True, "riichi_declaration": True}], [], [], []],
            "melds": [[{"type": "pon", "actor": 0, "target": 1, "pai": "E", "consumed": ["E", "E"]}], [], [], []],
            "dora_markers": ["5p"], "riichi_accepted_seats": [0], "riichi_pending_seats": [],
        },
        "score": {"scores_before": [25000, 24000, 26000, 25000]},
        "mortal": {
            "selected_action": {"type": "dahai", "pai": "5mr"},
            "mortal_first_action": {"type": "dahai", "pai": "7p"},
            "actual_probability": 0.00000123,
            "candidates": [{"action": {"type": "dahai", "pai": "7p"}, "prob": 0.8},
                           {"action": {"type": "dahai", "pai": "5mr"}, "prob": 0.2}],
            "model_tag": "sample", "reviewer_version": "1.5.10", "temperature": 0.0,
        },
    }


def test_renderer_escapes_dynamic_text_and_keeps_external_urls_out() -> None:
    scene = _scene()
    scene["round"]["bakaze"] = '<script>alert(1)</script>'
    html = render_table_html(scene, ASSETS) + render_evaluation_html(scene, ASSETS)
    assert "<script>" not in html
    assert "http://" not in html and "https://" not in html
    assert "data:image/gif;base64," in html
    assert "raw=0.00000123" in html


def test_renderer_shows_riichi_claimed_and_relative_data() -> None:
    html = render_table_html(_scene(3), ASSETS)
    assert "ma-riichi" in html
    assert "ma-meld-called" in html
    assert "5mr" in html and "5pr" in html


def test_called_tile_position_follows_source_direction() -> None:
    for target, side in ((1, "right"), (2, "center"), (3, "left")):
        scene = _scene()
        scene["public"]["melds"][0][0]["target"] = target
        scene["hand"]["fuuros"][0]["target"] = target
        html = render_table_html(scene, ASSETS)
        assert f"ma-called-{side}" in html
        assert f"鳴き元: {'右' if side == 'right' else '対面' if side == 'center' else '左'}" in html


def test_non_discard_action_does_not_highlight_a_hand_tile() -> None:
    scene = _scene()
    scene["mortal"]["selected_action"] = {"type": "none"}
    html = render_table_html(scene, ASSETS)
    assert "ma-actual" not in html


def test_same_discard_is_marked_as_both_actual_and_recommended() -> None:
    scene = _scene()
    scene["mortal"]["mortal_first_action"] = {"type": "dahai", "pai": "5mr"}
    html = render_table_html(scene, ASSETS)
    assert "ma-both" in html


def test_evaluation_shows_three_candidates_and_collapses_the_rest() -> None:
    scene = _scene()
    scene["mortal"]["candidates"] = [
        {"action": {"type": "dahai", "pai": tile}, "prob": probability}
        for tile, probability in (("1m", 0.40), ("2m", 0.30), ("3m", 0.20), ("4m", 0.07), ("5m", 0.03))
    ]
    html = render_evaluation_html(scene, ASSETS)
    assert html.count('class="ma-prob"') == 5
    assert html.count("もっとみる") == 1
    assert "もっとみる（2件）" in html
    assert "40.00%" in html and "3.00%" in html


def test_table_layout_keeps_player_zones_and_hand_meld_gap_explicit() -> None:
    css = table_css()
    assert "--hand-meld-gap" in css
    assert "aspect-ratio:1 / 1" in css
    assert "ma-river-rows-4" in css
    assert ".ma-river-top" in css and ".ma-river-bottom" in css
    assert ".ma-melds-top" in css and ".ma-melds-bottom" in css
    assert ".ma-center" in css and ".ma-legend" in css
    html = render_table_html(_scene(), ASSETS)
    assert "ma-player-area" in html and "ma-hand-area" in html
    assert "ma-meld-area" in html and "ma-river-area" in html


def test_river_uses_rows_based_on_discard_count() -> None:
    scene = _scene()
    scene["public"]["rivers"][0] = [{"pai": "1m"}] * 13
    html = render_table_html(scene, ASSETS)
    assert "ma-river-rows-3" in html
