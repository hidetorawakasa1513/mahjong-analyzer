from __future__ import annotations

import pytest

from mahjong_analyzer.table_view import compact_table_data, relative_seats, seat_label


def test_relative_seats_keep_reviewed_player_at_bottom() -> None:
    assert relative_seats(0).left == 1
    assert relative_seats(0).top == 2
    assert relative_seats(0).right == 3
    assert relative_seats(3).left == 0
    assert seat_label(3, 3) == "自分"
    assert seat_label(0, 3) == "下家"


def test_relative_seats_reject_invalid_player() -> None:
    with pytest.raises(ValueError):
        relative_seats(4)


def test_compact_table_data_does_not_include_private_hands() -> None:
    scene = {
        "identity": {"player_id": 0},
        "public": {"rivers": [[], [], [], []], "melds": [[], [], [], []],
                   "dora_markers": [], "riichi_accepted_seats": []},
        "hand": {"tiles": ["1m"], "tsumo_tile": None, "fuuros": [], "shanten": 1},
        "score": {"scores_before": [25000] * 4},
        "round": {"bakaze": "E", "kyoku": 1, "honba": 0, "tiles_left": 50},
        "mortal": {},
    }
    compact = compact_table_data(scene)
    assert "tehais" not in compact
    assert compact["hand"]["tiles"] == ["1m"]
