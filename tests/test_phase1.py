from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from mahjong_analyzer.errors import ConflictError, ValidationError
from mahjong_analyzer.importer import ImportMetadata, import_review, normalize_review
from mahjong_analyzer.report import summary
from mahjong_analyzer.schema import connect, initialize


def payload(
    *,
    game_id: str = "game-1",
    player_id: int = 0,
    model_tag: str = "model-a",
    total_reviewed: int = 2,
    total_matches: int = 1,
    entries: list[dict] | None = None,
    rating: float = 0.8,
) -> dict:
    if entries is None:
        entries = [
            {"junme": 1, "shanten": 2, "expected": "5m", "actual": "5m",
             "is_equal": True, "actual_index": 0,
             "details": [{"action": "5m", "prob": 0.049}]},
            {"junme": 2, "shanten": 1, "expected": "6m", "actual": "7m",
             "is_equal": False, "actual_index": 1,
             "details": [{"action": "6m", "prob": 0.8}, {"action": "7m", "prob": 0.05}]},
        ]
    return {
        "engine": "mortal",
        "version": "1.5.10",
        "player_id": player_id,
        "game_length": "tonpuu",
        "mjai_log": [{"type": "start_game", "ref": game_id}],
        "review": {
            "total_reviewed": total_reviewed,
            "total_matches": total_matches,
            "rating": rating,
            "temperature": 0.1,
            "model_tag": model_tag,
            "kyokus": [{"entries": entries}],
        },
    }


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "test.sqlite3")
    initialize(connection)
    yield connection
    connection.close()


def test_sqlite_initialization_enables_foreign_keys(db: sqlite3.Connection) -> None:
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0] == "2"


def test_normal_import_and_metrics(db: sqlite3.Connection) -> None:
    result = import_review(db, normalize_review(json.dumps(payload()).encode()))
    assert result == "imported"
    item = summary(db)[0]
    assert item["total_reviewed"] == 2
    assert item["total_matches"] == 1
    assert item["ai_agreement_rate"] == 0.5
    assert item["comparable_decisions"] == 2
    assert item["low_probability_decisions"] == 1
    assert item["low_recommendation_rate"] == 0.5
    assert item["ratings"] == [0.8]
    assert item["mortal_rating"] == "not aggregated"


def test_invalid_json_and_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        normalize_review(b"not-json")
    missing = payload()
    del missing["review"]["total_matches"]
    with pytest.raises(ValidationError, match="total_reviewed"):
        normalize_review(json.dumps(missing).encode())


def test_same_json_is_idempotent(db: sqlite3.Connection) -> None:
    normalized = normalize_review(json.dumps(payload()).encode())
    assert import_review(db, normalized) == "imported"
    assert import_review(db, normalized) == "duplicate"
    assert db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2


def test_volatile_review_times_do_not_create_duplicate(db: sqlite3.Connection) -> None:
    first = payload()
    second = payload()
    first["loading_time"] = "1ms"
    first["review_time"] = "1s"
    second["loading_time"] = "2ms"
    second["review_time"] = "2s"
    assert import_review(db, normalize_review(json.dumps(first).encode())) == "imported"
    assert import_review(db, normalize_review(json.dumps(second).encode())) == "duplicate"


def test_same_game_can_have_different_reviews(db: sqlite3.Connection) -> None:
    first = normalize_review(json.dumps(payload(model_tag="model-a")).encode())
    second = normalize_review(json.dumps(payload(model_tag="model-b", rating=0.7)).encode())
    assert import_review(db, first) == "imported"
    assert import_review(db, second) == "imported"
    assert db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 2


def test_conflicting_game_content_is_rejected(db: sqlite3.Connection) -> None:
    first = normalize_review(json.dumps(payload()).encode())
    changed = payload()
    changed["mjai_log"].append({"type": "end_game", "marker": "different-log-content"})
    changed["review"]["model_tag"] = "model-b"
    second = normalize_review(json.dumps(changed).encode())
    import_review(db, first)
    with pytest.raises(ConflictError):
        import_review(db, second)
    assert db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1


def test_player_id_must_be_explicit_and_in_range() -> None:
    missing = payload()
    del missing["player_id"]
    with pytest.raises(ValidationError, match="player_id"):
        normalize_review(json.dumps(missing).encode())
    with pytest.raises(ValidationError, match="between 0 and 3"):
        normalize_review(json.dumps(payload(player_id=4)).encode())
    with pytest.raises(ValidationError, match="does not match"):
        normalize_review(json.dumps(payload(player_id=0)).encode(), ImportMetadata(player_id=1))


def test_explicit_game_id_must_match_json() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        normalize_review(json.dumps(payload(game_id="json-id")).encode(), ImportMetadata(game_id="cli-id"))


def test_zero_reviewed_is_supported() -> None:
    value = payload(total_reviewed=0, total_matches=0, entries=[], rating=None)
    normalized = normalize_review(json.dumps(value).encode())
    assert normalized.total_reviewed == 0
    connection = connect(Path(":memory:"))
    initialize(connection)
    import_review(connection, normalized)
    item = summary(connection)[0]
    assert item["ai_agreement_rate"] is None
    assert item["low_recommendation_rate"] is None


def test_missing_probability_is_excluded_and_threshold_is_strict(db: sqlite3.Connection) -> None:
    value = payload()
    value["review"]["kyokus"][0]["entries"][1]["details"][1]["prob"] = None
    normalized = normalize_review(json.dumps(value).encode())
    import_review(db, normalized)
    item = summary(db, threshold=0.05)[0]
    assert item["comparable_decisions"] == 1
    assert item["low_probability_decisions"] == 1
    assert summary(db, threshold=0.049)[0]["low_probability_decisions"] == 0


def test_weighted_aggregate_and_mixed_conditions_are_separate(db: sqlite3.Connection) -> None:
    first = normalize_review(json.dumps(payload(game_id="g1", model_tag="same")).encode())
    second_value = payload(game_id="g2", model_tag="same")
    second_value["review"]["total_reviewed"] = 1
    second_value["review"]["total_matches"] = 1
    second_value["review"]["kyokus"][0]["entries"] = [
        second_value["review"]["kyokus"][0]["entries"][0]
    ]
    second = normalize_review(json.dumps(second_value).encode())
    third = normalize_review(json.dumps(payload(game_id="g3", model_tag="different")).encode())
    for item in (first, second, third):
        import_review(db, item)
    result = summary(db)
    same = next(item for item in result if item["condition"]["model_tag"] == "same")
    assert same["total_reviewed"] == 3
    assert same["total_matches"] == 2
    assert same["ai_agreement_rate"] == pytest.approx(2 / 3)
    assert len(result) == 2


def test_rating_is_not_averaged(db: sqlite3.Connection) -> None:
    import_review(db, normalize_review(json.dumps(payload(game_id="g1", rating=0.2)).encode()))
    import_review(db, normalize_review(json.dumps(payload(game_id="g2", rating=0.9)).encode()))
    assert summary(db)[0]["ratings"] == [0.2, 0.9]
    assert "average" not in summary(db)[0]


def test_import_rolls_back_when_decision_insert_fails(db: sqlite3.Connection) -> None:
    normalized = normalize_review(json.dumps(payload()).encode())
    db.execute(
        """
        CREATE TRIGGER fail_decision_insert BEFORE INSERT ON decisions
        BEGIN SELECT RAISE(ABORT, 'test failure'); END;
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        import_review(db, normalized)
    assert db.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
