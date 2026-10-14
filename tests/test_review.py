from __future__ import annotations

import json
from pathlib import Path

import pytest

from mahjong_analyzer.context import extract_review_context
from mahjong_analyzer.errors import ValidationError
from mahjong_analyzer.importer import import_review, normalize_review
from mahjong_analyzer.review import adjacent_decisions, get_review_scene
from mahjong_analyzer.schema import connect, initialize

from test_context import _payload


def _prepared(tmp_path: Path):
    payload = _payload()
    raw = json.dumps(payload, ensure_ascii=False).encode()
    review_path = tmp_path / "sample.review.json"
    review_path.write_bytes(raw)
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    import_review(connection, normalize_review(raw))
    extract_review_context(connection, review_path)
    return connection, review_path


def test_review_scene_reconstructs_normal_action_and_public_state(tmp_path: Path) -> None:
    connection, review_path = _prepared(tmp_path)
    scene = get_review_scene(connection, 1, review_root=tmp_path)
    assert scene["status"] == "complete"
    assert scene["identity"]["source_event_index"] == 3
    assert scene["hand"]["tiles"] == ["1m"] * 14
    assert scene["public"]["decision_phase"] == "before_action_event"
    assert scene["public"]["rivers"][0] == []
    assert scene["score"]["score_consistent_with_replay"] is True
    assert scene["score"]["rank"] is None
    assert scene["mortal"]["candidates"]
    json.dumps(scene, ensure_ascii=False)
    connection.close()


def test_review_scene_exposes_reference_discard_for_none(tmp_path: Path) -> None:
    connection, _ = _prepared(tmp_path)
    scene = get_review_scene(connection, 2, review_root=tmp_path)
    assert scene["mortal"]["action_category"] == "none"
    assert scene["none_judgment"]["meaning"].startswith("unknown")
    assert scene["public"]["decision_phase"] == "after_reference_event"
    assert scene["public"]["rivers"][1] == [{"pai": "5m", "tsumogiri": False, "event_index": 4}]
    assert scene["none_judgment"]["reference_event_is_exposed"] is True
    connection.close()


def test_review_scene_rejects_missing_or_unregistered_review_json(tmp_path: Path) -> None:
    connection, review_path = _prepared(tmp_path)
    with pytest.raises(ValidationError, match="does not match"):
        get_review_scene(connection, 1, review_json=tmp_path / "missing.json")
    other = tmp_path / "other.review.json"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(ValidationError, match="does not match"):
        get_review_scene(connection, 1, review_json=other)
    assert review_path.exists()
    connection.close()


def test_adjacent_decisions_stay_inside_same_review(tmp_path: Path) -> None:
    connection, _ = _prepared(tmp_path)
    assert adjacent_decisions(connection, 1) == (None, 2)
    assert adjacent_decisions(connection, 2) == (1, None)
    assert adjacent_decisions(connection, 1, disagreement_only=True) == (None, None)
    connection.close()
