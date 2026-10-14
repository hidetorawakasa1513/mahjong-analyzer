from __future__ import annotations

import pytest

from mahjong_analyzer.compat import TenhouCompatibilityError, normalize_tenhou6_payload


def _payload() -> dict:
    return {
        "ver": "2.3",
        "name": ["A", "B", "C", "D"],
        "log": [[
            [0, 0, 0], [25000, 25000, 25000, 25000], [11], [],
            [11] * 13, ["c121314", "p121212", "12p1212", "m12121212", "12m121212", "k12121212", "1212k1212", "a12121212"],
            ["r12"],
            [21] * 13, ["12p1212"], [12],
            [31] * 13, ["121212a12"], [12],
            [41] * 13, ["1212k1212"], [12],
            ["流局", [0, 0, 0, 0]],
        ]],
    }


def test_normalizes_converter_ankan_and_preserves_other_forms() -> None:
    normalized = normalize_tenhou6_payload(_payload(), game_id="game-1")
    assert normalized["ref"] == "game-1"
    assert normalized["log"][0][5] == [
        "c121314", "p121212", "12p1212", "m12121212", "12m121212", "k12121212", "1212k1212", "121212a12"
    ]
    assert normalized["log"][0][11] == ["121212a12"]
    assert normalized["log"][0][14] == ["1212k1212"]
    assert normalized["log"][0][6] == ["r12"]


def test_rejects_unknown_or_ambiguous_meld_syntax() -> None:
    value = _payload()
    value["log"][0][5][0] = "1212x1212"
    with pytest.raises(TenhouCompatibilityError):
        normalize_tenhou6_payload(value)

    value = _payload()
    value["log"][0][5][0] = "12a121212"
    with pytest.raises(TenhouCompatibilityError):
        normalize_tenhou6_payload(value)
