from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from .context import DEFAULT_EXTRACTOR_VERSION


DIMENSIONS = (
    "all", "turn_phase", "shanten_group", "riichi_group", "rank",
    "score_diff", "action_category", "bakaze", "dealer", "kyoku", "honba",
)
SCORE_TARGETS = ("top", "last", "above", "below")


@dataclass(frozen=True)
class ContextFilters:
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION
    turn_min: int | None = None
    turn_max: int | None = None
    turn_phase: str | None = None
    shanten: int | None = None
    shanten_group: str | None = None
    riichi_count: int | None = None
    riichi_min: int | None = None
    riichi_max: int | None = None
    rank: int | None = None
    rank_unknown: bool = False
    score_target: str | None = None
    score_min: int | None = None
    score_max: int | None = None
    action_category: str | None = None
    bakaze: str | None = None
    kyoku: int | None = None
    honba: int | None = None
    is_dealer: bool | None = None
    model_tag: str | None = None
    reviewer_version: str | None = None
    temperature: float | None = None
    is_equal: bool | None = None
    probability_min: float | None = None
    probability_max: float | None = None


@dataclass(frozen=True)
class SearchResult:
    total: int
    offset: int
    limit: int
    items: tuple[dict[str, Any], ...]


def _validate_filters(filters: ContextFilters) -> None:
    if filters.turn_min is not None and filters.turn_min < 0:
        raise ValueError("turn_min must be non-negative")
    if filters.turn_max is not None and filters.turn_max < 0:
        raise ValueError("turn_max must be non-negative")
    if filters.turn_min is not None and filters.turn_max is not None and filters.turn_min > filters.turn_max:
        raise ValueError("turn_min cannot exceed turn_max")
    if filters.shanten_group not in {None, "tenpai", "one", "two", "three_plus", "negative", "unknown"}:
        raise ValueError("unsupported shanten_group")
    if filters.turn_phase not in {None, "early", "mid", "late", "unknown"}:
        raise ValueError("unsupported turn_phase")
    if filters.score_target not in {None, *SCORE_TARGETS}:
        raise ValueError("unsupported score_target")
    if filters.score_min is not None and filters.score_max is not None and filters.score_min > filters.score_max:
        raise ValueError("score_min cannot exceed score_max")
    if filters.probability_min is not None and filters.probability_max is not None and filters.probability_min > filters.probability_max:
        raise ValueError("probability_min cannot exceed probability_max")
    if filters.riichi_min is not None and filters.riichi_min < 0:
        raise ValueError("riichi_min must be non-negative")
    if filters.riichi_max is not None and filters.riichi_max < 0:
        raise ValueError("riichi_max must be non-negative")


def _score_value(row: sqlite3.Row | dict[str, Any], target: str | None) -> int | None:
    if target is None:
        return None
    column = "gap_to_first" if target == "top" else f"gap_to_{target}"
    return row[column]


def _has_tied_score(row: sqlite3.Row | dict[str, Any]) -> bool:
    raw = row["scores_before_json"]
    if not raw:
        return True
    try:
        scores = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return True
    return not isinstance(scores, list) or len(scores) != 4 or len(set(scores)) != 4


def _turn_phase(value: int | None, early_end: int, mid_end: int) -> str:
    if value is None or value <= 0:
        return "unknown"
    if value <= early_end:
        return "early"
    if value <= mid_end:
        return "mid"
    return "late"


def _shanten_group(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value < 0:
        return "negative"
    if value == 0:
        return "tenpai"
    if value == 1:
        return "one"
    if value == 2:
        return "two"
    return "three_plus"


def _riichi_group(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value == 0:
        return "none"
    if value == 1:
        return "one"
    return "two_plus"


def _score_bucket(value: int | None, boundaries: tuple[int, ...]) -> str:
    if value is None:
        return "unknown"
    if not boundaries or boundaries[0] != 0 or any(a >= b for a, b in zip(boundaries, boundaries[1:])):
        raise ValueError("score bins must be strictly increasing and start at 0")
    if value == 0:
        return "0"
    sign = "behind" if value < 0 else "ahead"
    magnitude = abs(value)
    for lower, upper in zip(boundaries[1:], boundaries[2:]):
        if magnitude < upper:
            return f"{sign}:{lower}-{upper - 1}"
    if magnitude < boundaries[1]:
        return f"{sign}:1-{boundaries[1] - 1}"
    return f"{sign}:{boundaries[-1]}+"


def _dimension_value(
    row: sqlite3.Row,
    dimension: str,
    *,
    early_end: int,
    mid_end: int,
    score_target: str | None,
    score_bins: tuple[int, ...],
) -> str:
    if dimension == "all":
        return "all"
    if dimension == "turn_phase":
        return _turn_phase(row["turn_number"], early_end, mid_end)
    if dimension == "shanten_group":
        return _shanten_group(row["shanten_before"])
    if dimension == "riichi_group":
        return _riichi_group(row["opponent_riichi_count"])
    if dimension == "rank":
        return "unknown" if _has_tied_score(row) else str(row["rank_before"] or "unknown")
    if dimension == "score_diff":
        if score_target is None:
            raise ValueError("score_target is required for score_diff dimension")
        return _score_bucket(_score_value(row, score_target), score_bins)
    if dimension == "action_category":
        return row["action_category"] or "unknown"
    if dimension == "bakaze":
        return row["bakaze"] or "unknown"
    if dimension == "dealer":
        return "dealer" if row["is_dealer"] == 1 else "non_dealer" if row["is_dealer"] == 0 else "unknown"
    if dimension == "kyoku":
        return str(row["kyoku"] or "unknown")
    if dimension == "honba":
        return str(row["honba"] if row["honba"] is not None else "unknown")
    raise ValueError(f"unsupported dimension: {dimension}")


def _where(filters: ContextFilters) -> tuple[list[str], list[Any]]:
    _validate_filters(filters)
    clauses = ["c.extractor_version = ?"]
    params: list[Any] = [filters.extractor_version]
    for column, value, operator in (
        ("c.turn_number", filters.turn_min, ">="),
        ("c.turn_number", filters.turn_max, "<="),
        ("c.shanten_before", filters.shanten, "="),
        ("c.opponent_riichi_count", filters.riichi_count, "="),
        ("c.opponent_riichi_count", filters.riichi_min, ">="),
        ("c.opponent_riichi_count", filters.riichi_max, "<="),
        ("c.kyoku", filters.kyoku, "="),
        ("c.honba", filters.honba, "="),
        ("c.action_category", filters.action_category, "="),
        ("c.bakaze", filters.bakaze, "="),
        ("r.model_tag", filters.model_tag, "="),
        ("r.reviewer_version", filters.reviewer_version, "="),
        ("r.temperature", filters.temperature, "="),
        ("d.actual_probability", filters.probability_min, ">="),
        ("d.actual_probability", filters.probability_max, "<="),
    ):
        if value is not None:
            clauses.append(f"{column} {operator} ?")
            params.append(value)
    if filters.is_dealer is not None:
        clauses.append("c.is_dealer = ?")
        params.append(int(filters.is_dealer))
    if filters.is_equal is not None:
        clauses.append("d.is_equal = ?")
        params.append(int(filters.is_equal))
    if filters.score_target is not None:
        score_column = {
            "top": "c.gap_to_first", "last": "c.gap_to_last",
            "above": "c.gap_to_above", "below": "c.gap_to_below",
        }[filters.score_target]
        if filters.score_min is not None:
            clauses.append(f"{score_column} >= ?")
            params.append(filters.score_min)
        if filters.score_max is not None:
            clauses.append(f"{score_column} <= ?")
            params.append(filters.score_max)
    if filters.turn_phase is not None or filters.shanten_group is not None or filters.rank is not None or filters.rank_unknown:
        # These classifications depend on configurable boundaries or tie policy and are applied after loading.
        pass
    return clauses, params


def _load_rows(connection: sqlite3.Connection, filters: ContextFilters) -> list[sqlite3.Row]:
    clauses, params = _where(filters)
    query = f"""
        SELECT
            d.id AS decision_id, d.review_id, d.decision_index, d.junme, d.shanten,
            d.actual_action, d.expected_action, d.is_equal, d.actual_probability,
            d.is_comparable, r.game_id, r.player_id, r.engine, r.reviewer_version,
            r.model_tag, r.model_identity, r.grp_identity, r.temperature, r.rating,
            g.source_game_id, g.rule_context, c.extractor_version, c.context_status, c.mapping_kind,
            c.source_event_index, c.source_round_event_index, c.round_index,
            c.bakaze, c.kyoku, c.honba, c.turn_number, c.hand_json, c.fuuros_json,
            c.shanten_before, c.opponent_riichi_count, c.riichi_seats_json,
            c.self_riichi, c.is_dealer, c.scores_before_json, c.rank_before,
            c.gap_to_first, c.gap_to_last, c.gap_to_above, c.gap_to_below,
            c.action_category, c.source_sha256, c.mjai_log_sha256
        FROM decisions d
        JOIN decision_contexts c ON c.decision_id = d.id
        JOIN reviews r ON r.id = d.review_id
        JOIN games g ON g.id = r.game_id
        WHERE {' AND '.join(clauses)}
        ORDER BY d.id
    """
    return list(connection.execute(query, params).fetchall())


def _post_filter(
    rows: Iterable[sqlite3.Row],
    filters: ContextFilters,
    *,
    early_end: int,
    mid_end: int,
) -> list[sqlite3.Row]:
    result = []
    for row in rows:
        if filters.turn_phase and _turn_phase(row["turn_number"], early_end, mid_end) != filters.turn_phase:
            continue
        if filters.shanten_group and _shanten_group(row["shanten_before"]) != filters.shanten_group:
            continue
        tied = _has_tied_score(row)
        if filters.rank_unknown and not tied:
            continue
        if filters.rank is not None and (tied or row["rank_before"] != filters.rank):
            continue
        result.append(row)
    return result


def _metric(rows: list[sqlite3.Row], key: str) -> dict[str, Any]:
    total = len(rows)
    matches = sum(row["is_equal"] == 1 for row in rows if row["is_equal"] is not None)
    agreement_denominator = sum(row["is_equal"] is not None for row in rows)
    comparable = [row for row in rows if row["is_comparable"] and row["actual_probability"] is not None]
    low = sum(row["actual_probability"] < 0.05 for row in comparable)
    review_ids = sorted({row["review_id"] for row in rows})
    ratings = [
        {"review_id": review_id, "rating": next(row["rating"] for row in rows if row["review_id"] == review_id)}
        for review_id in review_ids
        if next(row["rating"] for row in rows if row["review_id"] == review_id) is not None
    ]
    return {
        "group": key,
        "decision_count": total,
        "game_count": len({row["game_id"] for row in rows}),
        "review_count": len(review_ids),
        "agreement_numerator": matches,
        "agreement_denominator": agreement_denominator,
        "ai_agreement_rate": matches / agreement_denominator if agreement_denominator else None,
        "low_probability_numerator": low,
        "low_probability_denominator": len(comparable),
        "low_recommendation_rate": low / len(comparable) if comparable else None,
        "ratings_by_review": ratings,
    }


def aggregate_contexts(
    connection: sqlite3.Connection,
    *,
    dimension: str = "all",
    filters: ContextFilters = ContextFilters(),
    early_end: int = 6,
    mid_end: int = 12,
    score_target: str | None = None,
    score_bins: tuple[int, ...] = (0, 4000, 8000, 12000),
) -> list[dict[str, Any]]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"unsupported dimension: {dimension}")
    if early_end < 1 or mid_end < early_end:
        raise ValueError("turn boundaries are invalid")
    if score_target not in {None, *SCORE_TARGETS}:
        raise ValueError("unsupported score_target")
    if dimension == "score_diff" and score_target is None:
        raise ValueError("score_target is required for score_diff dimension")
    rows = _post_filter(_load_rows(connection, filters), filters, early_end=early_end, mid_end=mid_end)
    effective_score_target = score_target or filters.score_target
    groups: dict[tuple[Any, ...], list[sqlite3.Row]] = {}
    for row in rows:
        condition = (row["engine"], row["reviewer_version"], row["model_tag"],
                     row["model_identity"], row["grp_identity"], row["temperature"],
                     row["rule_context"])
        group = _dimension_value(row, dimension, early_end=early_end, mid_end=mid_end,
                                 score_target=effective_score_target, score_bins=score_bins)
        groups.setdefault((condition, group), []).append(row)
    result = []
    for (condition, group), group_rows in sorted(groups.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        item = _metric(group_rows, group)
        item["condition"] = {
            "engine": condition[0], "reviewer_version": condition[1], "model_tag": condition[2],
            "model_identity": condition[3], "grp_identity": condition[4], "temperature": condition[5],
            "rule_context": condition[6],
        }
        if dimension == "score_diff":
            item["score_target"] = effective_score_target
            item["score_bins"] = list(score_bins)
        result.append(item)
    return result


def search_decisions(
    connection: sqlite3.Connection,
    filters: ContextFilters = ContextFilters(),
    *,
    offset: int = 0,
    limit: int = 100,
    early_end: int = 6,
    mid_end: int = 12,
) -> SearchResult:
    if offset < 0 or limit <= 0:
        raise ValueError("offset must be non-negative and limit must be positive")
    rows = _post_filter(_load_rows(connection, filters), filters, early_end=early_end, mid_end=mid_end)
    items = []
    for row in rows[offset:offset + limit]:
        items.append({
            "decision_id": row["decision_id"], "game_id": row["game_id"],
            "source_game_id": row["source_game_id"], "review_id": row["review_id"],
            "decision_index": row["decision_index"], "round_index": row["round_index"],
            "source_event_index": row["source_event_index"],
            "source_round_event_index": row["source_round_event_index"],
            "turn_number": row["turn_number"], "shanten": row["shanten_before"],
            "opponent_riichi_count": row["opponent_riichi_count"],
            "rank": None if _has_tied_score(row) else row["rank_before"],
            "gap_to_first": row["gap_to_first"], "gap_to_last": row["gap_to_last"],
            "gap_to_above": row["gap_to_above"], "gap_to_below": row["gap_to_below"],
            "action_category": row["action_category"], "actual_action": row["actual_action"],
            "selected_action": row["actual_action"], "expected_action": row["expected_action"],
            "mortal_first_action": row["expected_action"],
            "actual_probability": row["actual_probability"], "is_equal": row["is_equal"],
            "model_tag": row["model_tag"], "reviewer_version": row["reviewer_version"],
            "temperature": row["temperature"], "rule_context": row["rule_context"],
            "context_status": row["context_status"],
            "mapping_kind": row["mapping_kind"],
        })
    return SearchResult(total=len(rows), offset=offset, limit=limit, items=tuple(items))


def parse_score_bins(value: str) -> tuple[int, ...]:
    try:
        bins = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise ValueError("score bins must be comma-separated integers") from exc
    if not bins or bins[0] != 0 or any(a >= b for a, b in zip(bins, bins[1:])):
        raise ValueError("score bins must start at 0 and be strictly increasing")
    return bins
