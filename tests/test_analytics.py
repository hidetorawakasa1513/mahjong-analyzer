from __future__ import annotations

import json
from pathlib import Path

from mahjong_analyzer.analytics import (
    ContextFilters,
    _score_bucket,
    _turn_phase,
    aggregate_contexts,
    parse_score_bins,
    search_decisions,
)
from mahjong_analyzer.context import extract_review_context
from mahjong_analyzer.importer import import_review, normalize_review
from mahjong_analyzer.schema import connect, initialize

from test_context import _payload


def _database(tmp_path: Path, payload: dict | None = None):
    payload = payload or _payload()
    raw = json.dumps(payload, ensure_ascii=False).encode()
    review_path = tmp_path / "review.json"
    review_path.write_bytes(raw)
    connection = connect(tmp_path / "db.sqlite3")
    initialize(connection)
    import_review(connection, normalize_review(raw))
    extract_review_context(connection, review_path)
    return connection


def test_aggregate_metrics_and_none_are_consistent(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    result = aggregate_contexts(connection)
    assert len(result) == 1
    assert result[0]["decision_count"] == 2
    assert result[0]["agreement_numerator"] == 2
    assert result[0]["agreement_denominator"] == 2
    assert result[0]["low_probability_numerator"] == 0
    assert result[0]["low_probability_denominator"] == 2

    actions = aggregate_contexts(connection, dimension="action_category")
    assert {item["group"]: item["decision_count"] for item in actions} == {
        "discard": 1, "none": 1
    }
    connection.close()


def test_search_supports_and_filters_paging_and_parameter_binding(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    result = search_decisions(
        connection,
        ContextFilters(action_category="discard"),
        offset=0,
        limit=1,
    )
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0]["selected_action"] == result.items[0]["actual_action"]
    assert result.items[0]["mortal_first_action"] == result.items[0]["expected_action"]

    injected = search_decisions(
        connection,
        ContextFilters(action_category="discard' OR 1=1 --"),
    )
    assert injected.total == 0
    connection.close()


def test_rank_ties_are_unknown_and_score_bins_keep_signed_direction(tmp_path: Path) -> None:
    connection = _database(tmp_path)
    rank_groups = aggregate_contexts(connection, dimension="rank")
    assert rank_groups[0]["group"] == "unknown"
    assert rank_groups[0]["decision_count"] == 2
    assert search_decisions(connection, ContextFilters(rank=1)).total == 0
    assert search_decisions(connection, ContextFilters(rank_unknown=True)).total == 2
    assert _score_bucket(-8000, (0, 4000, 8000, 12000)) == "behind:8000-11999"
    assert _score_bucket(-12000, (0, 4000, 8000, 12000)) == "behind:12000+"
    assert _score_bucket(0, (0, 4000, 8000, 12000)) == "0"
    connection.close()


def test_boundaries_and_zero_denominator_are_explicit(tmp_path: Path) -> None:
    assert _turn_phase(6, 6, 12) == "early"
    assert _turn_phase(7, 6, 12) == "mid"
    assert _turn_phase(13, 6, 12) == "late"
    assert parse_score_bins("0, 5000, 10000") == (0, 5000, 10000)

    payload = _payload()
    for entry in payload["review"]["kyokus"][0]["entries"]:
        entry["is_equal"] = None
        entry["details"][0]["prob"] = None
    connection = _database(tmp_path, payload)
    result = aggregate_contexts(connection)[0]
    assert result["agreement_numerator"] == 0
    assert result["agreement_denominator"] == 0
    assert result["ai_agreement_rate"] is None
    assert result["low_probability_denominator"] == 0
    assert result["low_recommendation_rate"] is None
    connection.close()
