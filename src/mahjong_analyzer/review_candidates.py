from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from .analytics import ContextFilters, _has_tied_score, _load_rows, _post_filter


SortMode = Literal["low-probability", "disagreement", "recent"]


@dataclass(frozen=True)
class CandidateResult:
    total: int
    offset: int
    limit: int
    sort: SortMode
    disagreement_only: bool
    items: tuple[dict[str, Any], ...]


def _action(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def _sort_key(row: sqlite3.Row, mode: SortMode) -> tuple[Any, ...]:
    date = row["played_at"]
    stable = (row["source_game_id"] or "", row["decision_id"])
    if mode == "low-probability":
        probability = row["actual_probability"]
        return (probability is None, probability if probability is not None else 0.0, *stable)
    if mode == "disagreement":
        probability = row["actual_probability"]
        return (row["is_equal"] != 0, probability is None,
                probability if probability is not None else 0.0, *stable)
    raise ValueError(f"unsupported sort mode: {mode}")


def _candidate_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "decision_id": row["decision_id"],
        "review_id": row["review_id"],
        "game_id": row["game_id"],
        "played_at": row["played_at"],
        "source_game_id": row["source_game_id"],
        "bakaze": row["bakaze"],
        "kyoku": row["kyoku"],
        "honba": row["honba"],
        "turn_number": row["turn_number"],
        "shanten": row["shanten_before"],
        "opponent_riichi_count": row["opponent_riichi_count"],
        "rank": None if _has_tied_score(row) else row["rank_before"],
        "gap_to_first": row["gap_to_first"],
        "gap_to_above": row["gap_to_above"],
        "gap_to_last": row["gap_to_last"],
        "action_category": row["action_category"],
        "actual_action": _action(row["actual_action"]),
        "selected_action": _action(row["actual_action"]),
        "expected_action": _action(row["expected_action"]),
        "mortal_first_action": _action(row["expected_action"]),
        "is_equal": None if row["is_equal"] is None else bool(row["is_equal"]),
        "actual_probability": row["actual_probability"],
        "source_event_index": row["source_event_index"],
        "source_round_event_index": row["source_round_event_index"],
        "context_status": row["context_status"],
        "mapping_kind": row["mapping_kind"],
        "model_tag": row["model_tag"],
        "reviewer_version": row["reviewer_version"],
        "temperature": row["temperature"],
    }


def list_review_candidates(
    connection: sqlite3.Connection,
    *,
    sort: SortMode = "low-probability",
    filters: ContextFilters = ContextFilters(),
    disagreement_only: bool = False,
    offset: int = 0,
    limit: int = 100,
    early_end: int = 6,
    mid_end: int = 12,
) -> CandidateResult:
    if sort not in {"low-probability", "disagreement", "recent"}:
        raise ValueError(f"unsupported sort mode: {sort}")
    if offset < 0 or limit <= 0:
        raise ValueError("offset must be non-negative and limit must be positive")
    rows = _post_filter(_load_rows(connection, filters), filters,
                        early_end=early_end, mid_end=mid_end)
    if disagreement_only:
        rows = [row for row in rows if row["is_equal"] == 0]
    if sort == "recent":
        known = [row for row in rows if row["played_at"] is not None]
        unknown = [row for row in rows if row["played_at"] is None]
        known.sort(key=lambda row: row["decision_id"])
        known.sort(key=lambda row: (row["played_at"], row["source_game_id"] or ""), reverse=True)
        unknown.sort(key=lambda row: row["decision_id"])
        unknown.sort(key=lambda row: row["source_game_id"] or "", reverse=True)
        rows = known + unknown
    else:
        rows.sort(key=lambda row: _sort_key(row, sort))
    items = tuple(_candidate_item(row) for row in rows[offset:offset + limit])
    return CandidateResult(len(rows), offset, limit, sort, disagreement_only, items)
