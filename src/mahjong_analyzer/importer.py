from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ConflictError, ValidationError
from .schema import initialize


@dataclass(frozen=True)
class ImportMetadata:
    source: str = "review-json"
    game_id: str | None = None
    player_id: int | None = None
    played_at: str | None = None
    game_type: str | None = None
    rule_context: str | None = None


@dataclass(frozen=True)
class NormalizedReview:
    metadata: ImportMetadata
    source_game_id: str
    log_sha256: str | None
    engine: str
    reviewer_version: str | None
    model_tag: str | None
    model_identity: str | None
    grp_identity: str | None
    temperature: float | None
    rating: float | None
    total_reviewed: int
    total_matches: int
    review_sha256: str
    game_type: str | None
    rule_context: str | None
    decisions: tuple[dict[str, Any], ...]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return _canonical(value)


def _finite_number(value: Any, label: str, *, minimum: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a number or null")
    number = float(value)
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValidationError(f"{label} is outside the supported range")
    return number


def _integer(value: Any, label: str, *, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{label} must be an integer or null")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} is below the supported minimum")
    return value


def _extract_game_id(payload: dict[str, Any], metadata: ImportMetadata) -> str | None:
    discovered: str | None = None
    for key in ("game_id", "replay_id", "ref"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            discovered = value.strip()
            break
    review = payload.get("review")
    if discovered is None and isinstance(review, dict):
        for key in ("game_id", "replay_id", "ref"):
            value = review.get(key)
            if isinstance(value, str) and value.strip():
                discovered = value.strip()
                break
    log = payload.get("mjai_log")
    if discovered is None and isinstance(log, list):
        for event in log:
            if isinstance(event, dict) and event.get("type") == "start_game":
                value = event.get("ref")
                if isinstance(value, str) and value.strip():
                    discovered = value.strip()
                    break
    explicit = metadata.game_id.strip() if metadata.game_id and metadata.game_id.strip() else None
    if discovered is not None and explicit is not None and discovered != explicit:
        raise ValidationError("--game-id does not match the review JSON game ID")
    return discovered or explicit


def _extract_player_id(payload: dict[str, Any], metadata: ImportMetadata) -> int | None:
    value = payload.get("player_id")
    if value is None and isinstance(payload.get("review"), dict):
        value = payload["review"].get("player_id")
    discovered = _integer(value, "player_id", minimum=0) if value is not None else None
    if discovered is not None and metadata.player_id is not None and discovered != metadata.player_id:
        raise ValidationError("--player-id does not match the review JSON player_id")
    return discovered if discovered is not None else metadata.player_id


def _extract_rule_context(payload: dict[str, Any], metadata: ImportMetadata) -> str | None:
    if metadata.rule_context is not None:
        return metadata.rule_context
    value = payload.get("rule_context", payload.get("rule"))
    if value is None:
        return None
    return _canonical(value) if isinstance(value, (dict, list)) else _text_value(value)


def _entries(review: dict[str, Any]) -> list[tuple[int | None, dict[str, Any]]]:
    kyokus = review.get("kyokus")
    if not isinstance(kyokus, list):
        raise ValidationError("review.kyokus must be an array")
    result: list[tuple[int | None, dict[str, Any]]] = []
    for kyoku_index, kyoku in enumerate(kyokus):
        if not isinstance(kyoku, dict):
            raise ValidationError("each review.kyokus item must be an object")
        entries = kyoku.get("entries")
        if not isinstance(entries, list):
            raise ValidationError("each review.kyokus item must contain entries")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError("each review entry must be an object")
            result.append((kyoku_index, entry))
    return result


def _normalize_decision(index: int, kyoku_index: int | None, entry: dict[str, Any]) -> dict[str, Any]:
    actual_index = entry.get("actual_index")
    details = entry.get("details")
    probability: float | None = None
    missing_reason: str | None = None
    if not isinstance(actual_index, int) or isinstance(actual_index, bool):
        missing_reason = "missing_actual_index"
    elif not isinstance(details, list):
        missing_reason = "missing_details"
    elif actual_index < 0 or actual_index >= len(details):
        missing_reason = "actual_index_out_of_range"
    elif not isinstance(details[actual_index], dict):
        missing_reason = "invalid_detail"
    else:
        probability = _finite_number(details[actual_index].get("prob"), "details[].prob")
        if probability is None:
            missing_reason = "missing_probability"
        elif not 0 <= probability <= 1:
            raise ValidationError("details[].prob must be between 0 and 1")

    is_equal = entry.get("is_equal")
    if is_equal is not None and not isinstance(is_equal, bool):
        raise ValidationError("entry.is_equal must be boolean or null")
    return {
        "decision_index": index,
        "kyoku_index": kyoku_index,
        "junme": _integer(entry.get("junme"), "entry.junme", minimum=0),
        "shanten": _integer(entry.get("shanten"), "entry.shanten"),
        "actual_action": _text_value(entry.get("actual")),
        "expected_action": _text_value(entry.get("expected")),
        "is_equal": None if is_equal is None else int(is_equal),
        "actual_probability": probability,
        "is_comparable": int(probability is not None),
        "missing_reason": missing_reason,
    }


def normalize_review(raw: bytes, metadata: ImportMetadata = ImportMetadata()) -> NormalizedReview:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("review file must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("review JSON root must be an object")
    review = payload.get("review")
    if not isinstance(review, dict):
        raise ValidationError("review object is required")
    source_game_id = _extract_game_id(payload, metadata)
    if not source_game_id:
        raise ValidationError("source game ID is missing; provide --game-id")
    player_id = _extract_player_id(payload, metadata)
    if player_id is None or player_id > 3:
        raise ValidationError("player_id is required and must be between 0 and 3")
    if "total_reviewed" not in review or "total_matches" not in review:
        raise ValidationError("review.total_reviewed and review.total_matches are required")
    total_reviewed = _integer(review["total_reviewed"], "review.total_reviewed", minimum=0)
    total_matches = _integer(review["total_matches"], "review.total_matches", minimum=0)
    assert total_reviewed is not None and total_matches is not None
    if total_matches > total_reviewed:
        raise ValidationError("review.total_matches cannot exceed total_reviewed")
    entries = _entries(review)
    if len(entries) != total_reviewed:
        raise ValidationError(
            f"review entry count ({len(entries)}) does not match total_reviewed ({total_reviewed})"
        )
    decisions = tuple(_normalize_decision(i, k, entry) for i, (k, entry) in enumerate(entries))
    known_matches = [decision["is_equal"] for decision in decisions if decision["is_equal"] is not None]
    if len(known_matches) == total_reviewed and sum(known_matches) != total_matches:
        raise ValidationError("review.total_matches does not match entry is_equal values")

    log = payload.get("mjai_log")
    log_sha256 = hashlib.sha256(_canonical(log).encode()).hexdigest() if log is not None else None
    engine = _text_value(payload.get("engine", "mortal")) or "mortal"
    reviewer_version = _text_value(payload.get("version"))
    temperature = _finite_number(review.get("temperature"), "review.temperature")
    rating = _finite_number(review.get("rating"), "review.rating")
    game_type = metadata.game_type or _text_value(payload.get("game_length"))
    rule_context = _extract_rule_context(payload, metadata)
    model_tag = _text_value(review.get("model_tag", payload.get("model_tag")))
    model_identity = _text_value(review.get("model_identity", payload.get("model_identity")))
    grp_identity = _text_value(review.get("grp_identity", payload.get("grp_identity")))
    return NormalizedReview(
        metadata=ImportMetadata(source=metadata.source, game_id=metadata.game_id, player_id=player_id,
                                played_at=metadata.played_at, game_type=game_type,
                                rule_context=rule_context),
        source_game_id=source_game_id,
        log_sha256=log_sha256,
        engine=engine,
        reviewer_version=reviewer_version,
        model_tag=model_tag,
        model_identity=model_identity,
        grp_identity=grp_identity,
        temperature=temperature,
        rating=rating,
        total_reviewed=total_reviewed,
        total_matches=total_matches,
        review_sha256=hashlib.sha256(raw).hexdigest(),
        game_type=game_type,
        rule_context=rule_context,
        decisions=decisions,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def import_review(connection: sqlite3.Connection, normalized: NormalizedReview) -> str:
    initialize(connection)
    with connection:
        existing_review = connection.execute(
            "SELECT id FROM reviews WHERE review_sha256 = ?", (normalized.review_sha256,)
        ).fetchone()
        if existing_review is not None:
            return "duplicate"
        game = connection.execute(
            "SELECT * FROM games WHERE source = ? AND source_game_id = ?",
            (normalized.metadata.source, normalized.source_game_id),
        ).fetchone()
        if game is None:
            cursor = connection.execute(
                """
                INSERT INTO games(source, source_game_id, log_sha256, played_at, game_type,
                                   rule_context, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (normalized.metadata.source, normalized.source_game_id, normalized.log_sha256,
                 normalized.metadata.played_at, normalized.game_type, normalized.rule_context, _now()),
            )
            game_id = int(cursor.lastrowid)
        else:
            if (game["log_sha256"] and normalized.log_sha256 and
                    game["log_sha256"] != normalized.log_sha256):
                raise ConflictError(
                    f"game ID {normalized.source_game_id} has conflicting log content"
                )
            game_id = int(game["id"])
        cursor = connection.execute(
            """
            INSERT INTO reviews(game_id, player_id, engine, reviewer_version, model_tag,
                                model_identity, grp_identity, temperature, rating,
                                total_reviewed, total_matches, review_sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (game_id, normalized.metadata.player_id, normalized.engine, normalized.reviewer_version,
             normalized.model_tag, normalized.model_identity, normalized.grp_identity,
             normalized.temperature, normalized.rating, normalized.total_reviewed,
             normalized.total_matches, normalized.review_sha256, _now()),
        )
        review_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO decisions(review_id, decision_index, kyoku_index, junme, shanten,
                                   actual_action, expected_action, is_equal, actual_probability,
                                   is_comparable, missing_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(review_id, decision["decision_index"], decision["kyoku_index"], decision["junme"],
              decision["shanten"], decision["actual_action"], decision["expected_action"],
              decision["is_equal"], decision["actual_probability"], decision["is_comparable"],
              decision["missing_reason"]) for decision in normalized.decisions],
        )
    return "imported"


def import_file(connection: sqlite3.Connection, path: Path, metadata: ImportMetadata) -> str:
    return import_review(connection, normalize_review(path.read_bytes(), metadata))
