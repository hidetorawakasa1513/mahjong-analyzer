from pathlib import Path

from mahjong_analyzer.dashboard.table_renderer import render_evaluation_html, render_table_html


ASSETS = Path(__file__).parents[1] / "assets/third_party/mj_king/tiles"


def _scene(player_id: int = 0) -> dict:
    return {
        "identity": {"player_id": player_id},
        "round": {"bakaze": "E", "kyoku": 1, "honba": 0, "kyotaku": 1,
                   "turn_number": 4, "tiles_left": 60},
        "hand": {"tiles": ["1m", "5mr", "7p"], "tsumo_tile": "5pr", "fuuros": [], "shanten": 1},
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
