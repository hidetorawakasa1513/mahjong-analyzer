from __future__ import annotations

import json
from pathlib import Path

from mahjong_analyzer.context import extract_review_context
from mahjong_analyzer.importer import import_review, normalize_review
from mahjong_analyzer.schema import connect, initialize


def _entry(actual: dict, *, junme: int, tiles_left: int, state: dict, **extra) -> dict:
    return {
        "junme": junme,
        "tiles_left": tiles_left,
        "last_actor": extra.pop("last_actor", 0),
        "tile": extra.pop("tile", "1m"),
        "state": state,
        "at_self_chi_pon": False,
        "at_self_riichi": False,
        "at_opponent_kakan": False,
        "at_furiten": False,
        "actual": actual,
        "expected": actual,
        "is_equal": True,
        "actual_index": 0,
        "details": [{"action": actual, "q_value": 0.0, "prob": 1.0}],
        "shanten": 2,
        **extra,
    }


def _payload() -> dict:
    start = {
        "type": "start_kyoku",
        "bakaze": "E",
        "kyoku": 1,
        "honba": 0,
        "kyotaku": 0,
        "oya": 0,
        "scores": [25000, 25000, 25000, 25000],
        "tehais": [[], [], [], []],
    }
    dahai_0 = {"type": "dahai", "actor": 0, "pai": "1m", "tsumogiri": False}
    dahai_1 = {"type": "dahai", "actor": 1, "pai": "5m", "tsumogiri": False}
    state = {"tehai": ["1m"] * 14, "fuuros": []}
    return {
        "engine": "mortal",
        "version": "1.5.10",
        "player_id": 0,
        "mjai_log": [
            {"type": "start_game", "ref": "context-game"},
            start,
            {"type": "tsumo", "actor": 0, "pai": "1m"},
            dahai_0,
            {"type": "tsumo", "actor": 1, "pai": "5m"},
            dahai_1,
            {"type": "end_kyoku"},
            {"type": "end_game"},
        ],
        "review": {
            "total_reviewed": 2,
            "total_matches": 2,
            "rating": 0.9,
            "temperature": 0.1,
            "model_tag": "test-model",
            "kyokus": [{
                "kyoku": 0,
                "honba": 0,
                "relative_scores": [25000, 25000, 25000, 25000],
                "end_status": [],
                "entries": [
                    _entry(dahai_0, junme=1, tiles_left=69, state=state),
                    _entry({"type": "none"}, junme=1, tiles_left=68, state=state,
                           last_actor=1, tile="5m",
                           details=[
                               {"action": {"type": "none"}, "q_value": 0.0, "prob": 1.0},
                               {"action": {"type": "pon", "actor": 0, "target": 1,
                                            "pai": "5m", "consumed": ["5m", "5m"]},
                                "q_value": -1.0, "prob": 0.0},
                           ]),
                ],
            }],
        },
    }


def test_context_extraction_maps_events_and_non_action_opportunity(tmp_path: Path) -> None:
    raw = json.dumps(_payload(), ensure_ascii=False).encode()
    review_path = tmp_path / "review.json"
    review_path.write_bytes(raw)
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    assert import_review(connection, normalize_review(raw)) == "imported"

    result = extract_review_context(connection, review_path)

    assert result.total == 2
    assert result.complete == 2
    assert result.event_mapped == 1
    assert result.non_action_mapped == 1
    assert result.unmapped == 0
    assert result.score_success == 2
    rows = connection.execute(
        "SELECT mapping_kind, source_event_index, scores_before_json, rank_before, "
        "gap_to_first, gap_to_last, action_category FROM decision_contexts ORDER BY decision_id"
    ).fetchall()
    assert [row[0] for row in rows] == ["event", "non_action_opportunity"]
    assert [row[1] for row in rows] == [3, 5]
    assert json.loads(rows[0][2]) == [25000, 25000, 25000, 25000]
    assert rows[0][3:] == (1, 0, 0, "discard")
    assert rows[1][6] == "none"
    connection.close()


def test_context_extraction_is_idempotent(tmp_path: Path) -> None:
    raw = json.dumps(_payload(), ensure_ascii=False).encode()
    review_path = tmp_path / "review.json"
    review_path.write_bytes(raw)
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    import_review(connection, normalize_review(raw))

    first = extract_review_context(connection, review_path)
    second = extract_review_context(connection, review_path)

    assert first.inserted == 2
    assert not first.duplicate
    assert second.inserted == 0
    assert second.duplicate
    assert connection.execute("SELECT COUNT(*) FROM decision_contexts").fetchone()[0] == 2
    connection.close()
