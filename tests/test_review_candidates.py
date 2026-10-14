from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mahjong_analyzer.context import extract_review_context
from mahjong_analyzer.importer import ImportMetadata, import_review, normalize_review
from mahjong_analyzer.review_candidates import list_review_candidates
from mahjong_analyzer.schema import connect, initialize

from test_context import _payload


def _import_payload(connection: sqlite3.Connection, path: Path, payload: dict,
                    *, game_id: str | None = None, played_at: str | None = None) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode()
    path.write_bytes(raw)
    import_review(connection, normalize_review(
        raw, ImportMetadata(game_id=game_id, played_at=played_at)
    ))
    extract_review_context(connection, path)


def _prepared(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    payload = _payload()
    payload["review"]["kyokus"][0]["entries"][0]["details"][0]["prob"] = 0.02
    payload["review"]["kyokus"][0]["entries"][0]["is_equal"] = False
    payload["review"]["kyokus"][0]["entries"][1]["details"][0]["prob"] = None
    payload["review"]["total_matches"] = 1
    _import_payload(connection, tmp_path / "one.review.json", payload,
                    game_id="context-game", played_at="2026-10-14T10:00:00+00:00")
    second = _payload()
    second["mjai_log"][0]["ref"] = "context-game-2"
    second["review"]["model_tag"] = "other-model"
    _import_payload(connection, tmp_path / "two.review.json", second,
                    game_id="context-game-2", played_at="2026-10-15T10:00:00+00:00")
    return connection


def test_candidate_sorting_and_paging(tmp_path: Path) -> None:
    connection = _prepared(tmp_path)
    low = list_review_candidates(connection, sort="low-probability", limit=4)
    assert low.total == 4
    assert [item["decision_id"] for item in low.items] == [1, 3, 4, 2]
    assert low.items[0]["actual_probability"] == 0.02
    assert low.items[-1]["actual_probability"] is None
    page = list_review_candidates(connection, sort="low-probability", offset=1, limit=2)
    assert [item["decision_id"] for item in page.items] == [3, 4]
    assert len({item["decision_id"] for item in low.items}) == len(low.items)
    connection.close()


def test_disagreement_and_recent_modes(tmp_path: Path) -> None:
    connection = _prepared(tmp_path)
    disagreement = list_review_candidates(connection, sort="disagreement")
    assert disagreement.items[0]["is_equal"] is False
    assert list_review_candidates(connection, sort="disagreement", disagreement_only=True).total == 1
    recent = list_review_candidates(connection, sort="recent", limit=2)
    assert [item["game_id"] for item in recent.items] == [2, 2]
    connection.close()


def test_candidate_filters_and_json_shape(tmp_path: Path) -> None:
    connection = _prepared(tmp_path)
    from mahjong_analyzer.analytics import ContextFilters

    result = list_review_candidates(
        connection, filters=ContextFilters(action_category="none"), limit=10
    )
    assert result.total == 2
    assert all(item["action_category"] == "none" for item in result.items)
    json.dumps({"items": list(result.items)}, ensure_ascii=False)
    injection = list_review_candidates(
        connection, filters=ContextFilters(action_category="none' OR 1=1 --")
    )
    assert injection.total == 0
    connection.close()
