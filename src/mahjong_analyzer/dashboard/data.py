from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote
from typing import Any

from ..analytics import ContextFilters, aggregate_contexts
from ..report import summary
from ..review import get_review_scene
from ..review_candidates import CandidateResult, list_review_candidates


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without allowing file creation or writes."""
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def home_data(connection: sqlite3.Connection, threshold: float = 0.05) -> dict[str, Any]:
    counts = connection.execute(
        "SELECT (SELECT COUNT(*) FROM games) games, "
        "(SELECT COUNT(*) FROM decisions) decisions, "
        "(SELECT COUNT(*) FROM reviews) reviews"
    ).fetchone()
    summaries = summary(connection, threshold)
    return {
        "games": counts["games"], "decisions": counts["decisions"],
        "reviews": counts["reviews"], "summaries": summaries,
        "recent_games": [dict(row) for row in connection.execute(
            "SELECT id, played_at, game_type FROM games "
            "ORDER BY played_at IS NULL, played_at DESC, id DESC LIMIT 10"
        )],
    }


def context_data(
    connection: sqlite3.Connection,
    *,
    dimension: str,
    filters: ContextFilters,
    score_target: str | None = None,
    score_bins: tuple[int, ...] = (0, 4000, 8000, 12000),
    early_end: int = 6,
    mid_end: int = 12,
) -> list[dict[str, Any]]:
    return aggregate_contexts(
        connection, dimension=dimension, filters=filters,
        score_target=score_target, score_bins=score_bins,
        early_end=early_end, mid_end=mid_end,
    )


def candidate_data(
    connection: sqlite3.Connection,
    *,
    sort: str,
    filters: ContextFilters,
    disagreement_only: bool,
    offset: int,
    limit: int,
    early_end: int = 6,
    mid_end: int = 12,
) -> CandidateResult:
    return list_review_candidates(
        connection, sort=sort, filters=filters,
        disagreement_only=disagreement_only, offset=offset, limit=limit,
        early_end=early_end, mid_end=mid_end,
    )


def scene_data(
    connection: sqlite3.Connection,
    decision_id: int,
    *,
    review_root: Path,
    source_root: Path,
) -> dict[str, Any]:
    return get_review_scene(
        connection, decision_id, review_root=review_root, source_root=source_root,
    )
