from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any


def _condition_key(row: sqlite3.Row) -> tuple[Any, ...]:
    return (row["engine"], row["reviewer_version"], row["model_tag"], row["model_identity"],
            row["grp_identity"], row["temperature"], row["rule_context"])


def _condition_dict(key: tuple[Any, ...]) -> dict[str, Any]:
    names = ("engine", "reviewer_version", "model_tag", "model_identity", "grp_identity",
             "temperature", "rule_context")
    return dict(zip(names, key, strict=True))


def summary(connection: sqlite3.Connection, threshold: float = 0.05) -> list[dict[str, Any]]:
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    rows = connection.execute(
        """
        SELECT r.*, g.rule_context, d.actual_probability, d.is_comparable
        FROM reviews r
        JOIN games g ON g.id = r.game_id
        LEFT JOIN decisions d ON d.review_id = r.id
        ORDER BY r.id, d.decision_index
        """
    ).fetchall()
    grouped: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(
        lambda: {"total_reviewed": 0, "total_matches": 0, "comparable": 0, "low": 0,
                 "ratings": [], "review_ids": set()}
    )
    for row in rows:
        key = _condition_key(row)
        item = grouped[key]
        if row["id"] not in item["review_ids"]:
            item["review_ids"].add(row["id"])
            item["total_reviewed"] += row["total_reviewed"]
            item["total_matches"] += row["total_matches"]
            if row["rating"] is not None:
                item["ratings"].append(row["rating"])
        if row["is_comparable"]:
            item["comparable"] += 1
            if row["actual_probability"] < threshold:
                item["low"] += 1
    result = []
    for key, item in grouped.items():
        reviewed = item["total_reviewed"]
        comparable = item["comparable"]
        result.append({
            "condition": _condition_dict(key),
            "review_count": len(item["review_ids"]),
            "total_reviewed": reviewed,
            "total_matches": item["total_matches"],
            "ai_agreement_rate": item["total_matches"] / reviewed if reviewed else None,
            "comparable_decisions": comparable,
            "low_probability_decisions": item["low"],
            "low_recommendation_rate": item["low"] / comparable if comparable else None,
            "ratings": item["ratings"],
            "mortal_rating": "not aggregated",
            "threshold": threshold,
        })
    return result


def list_games(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT id, source, source_game_id, game_type, played_at, created_at FROM games ORDER BY id"
    ).fetchall()


def show_game(connection: sqlite3.Connection, game_id: int) -> dict[str, Any] | None:
    game = connection.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return None
    reviews = connection.execute(
        "SELECT * FROM reviews WHERE game_id = ? ORDER BY id", (game_id,)
    ).fetchall()
    return {"game": dict(game), "reviews": [dict(review) for review in reviews]}


def format_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No reviews imported."
    return json.dumps(items, ensure_ascii=False, indent=2)
