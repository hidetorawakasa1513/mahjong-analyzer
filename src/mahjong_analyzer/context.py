from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .importer import _canonical
from .schema import initialize


DEFAULT_EXTRACTOR_VERSION = "phase2-context-v1"


@dataclass(frozen=True)
class ContextExtractionResult:
    review_id: int
    total: int
    complete: int
    event_mapped: int
    non_action_mapped: int
    partial: int
    unmapped: int
    invalid: int
    inserted: int
    duplicate: bool
    shanten_success: int
    turn_success: int
    score_success: int


@dataclass(frozen=True)
class _EventMatch:
    event_index: int
    round_event_index: int
    kind: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return _canonical(value)


def _same_action(expected: dict[str, Any], event: dict[str, Any]) -> bool:
    if expected.get("type") != event.get("type"):
        return False
    for key in ("actor", "target", "pai", "tsumogiri", "consumed"):
        if key in expected and expected.get(key) != event.get(key):
            return False
    return True


def _rounds(events: list[dict[str, Any]]) -> list[tuple[int, int, list[dict[str, Any]]]]:
    starts = [index for index, event in enumerate(events) if event.get("type") == "start_kyoku"]
    if not starts:
        raise ValidationError("mjai_log does not contain start_kyoku events")
    result = []
    for round_index, start in enumerate(starts):
        end = starts[round_index + 1] if round_index + 1 < len(starts) else len(events)
        result.append((start, end, events[start:end]))
    return result


def _tiles_left_after(segment: list[dict[str, Any]]) -> list[int]:
    tiles_left = 70
    result: list[int] = []
    for event in segment:
        if event.get("type") == "tsumo":
            tiles_left -= 1
        result.append(tiles_left)
    return result


def _match_entries(
    entries: list[dict[str, Any]],
    events: list[dict[str, Any]],
    global_start: int,
) -> list[_EventMatch | None]:
    left = _tiles_left_after(events)
    cursor = 1  # position zero is start_kyoku
    matches: list[_EventMatch | None] = []
    for entry in entries:
        actual = entry.get("actual")
        if not isinstance(actual, dict) or not isinstance(entry.get("tiles_left"), int):
            matches.append(None)
            continue
        if actual.get("type") == "none":
            expected = {"type": "dahai", "actor": entry.get("last_actor"), "pai": entry.get("tile")}
            kind = "non_action_opportunity"
        else:
            expected = actual
            kind = "event"
        candidates = [
            index for index in range(cursor, len(events))
            if left[index] == entry["tiles_left"] and _same_action(expected, events[index])
        ]
        if len(candidates) != 1:
            matches.append(None)
            continue
        index = candidates[0]
        matches.append(_EventMatch(global_start + index, index, kind))
        cursor = index + 1
    return matches


def _action_category(entry: dict[str, Any]) -> str | None:
    action = entry.get("actual")
    if not isinstance(action, dict):
        return None
    action_type = action.get("type")
    if action_type == "dahai":
        return "discard"
    if action_type == "reach":
        return "riichi"
    if action_type in {"chi", "pon", "ankan", "kakan", "daiminkan"}:
        return action_type
    if action_type == "hora":
        return "hora"
    if action_type == "none":
        return "none"
    return str(action_type) if action_type is not None else None


def _rank_and_gaps(scores: list[int], player_id: int) -> tuple[int, int, int, int | None, int | None]:
    player_score = scores[player_id]
    rank = 1 + sum(score > player_score for score in scores)
    ordered = sorted(scores, reverse=True)
    gap_first = player_score - ordered[0]
    gap_last = player_score - ordered[-1]
    above = sorted({score for score in scores if score > player_score}, reverse=True)
    below = sorted({score for score in scores if score < player_score}, reverse=True)
    gap_above = player_score - above[-1] if above else None
    gap_below = player_score - below[0] if below else None
    return rank, gap_first, gap_last, gap_above, gap_below


def _event_snapshots(
    segment: list[dict[str, Any]],
    initial_scores: list[int],
) -> tuple[list[list[int]], list[set[int]], list[bool]]:
    scores = initial_scores[:]
    riichi: set[int] = set()
    snapshots: list[list[int]] = []
    riichi_snapshots: list[set[int]] = []
    self_pending: list[bool] = []
    pending: set[int] = set()
    for event in segment:
        snapshots.append(scores[:])
        riichi_snapshots.append(riichi.copy())
        self_pending.append(bool(pending))
        event_type = event.get("type")
        if event_type == "reach":
            pending.add(int(event["actor"]))
        elif event_type == "reach_accepted":
            actor = int(event["actor"])
            pending.discard(actor)
            riichi.add(actor)
            scores[actor] -= 1000
        elif event_type in {"hora", "ryukyoku"}:
            deltas = event.get("deltas")
            if isinstance(deltas, list) and len(deltas) == 4 and all(isinstance(v, int) for v in deltas):
                scores = [score + delta for score, delta in zip(scores, deltas, strict=True)]
    return snapshots, riichi_snapshots, self_pending


def _validate_state(entry: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    state = entry.get("state")
    if not isinstance(state, dict):
        return None, None, "missing_state"
    hand = state.get("tehai")
    fuuros = state.get("fuuros")
    if not isinstance(hand, list) or not all(isinstance(tile, str) for tile in hand):
        return None, None, "invalid_state_tehai"
    if not isinstance(fuuros, list):
        return None, None, "invalid_state_fuuros"
    return _json(hand), _json(fuuros), None


def _context_rows(
    connection: sqlite3.Connection,
    review_id: int,
    game: sqlite3.Row,
    payload: dict[str, Any],
    extractor_version: str,
) -> tuple[list[tuple[Any, ...]], dict[str, int]]:
    log = payload.get("mjai_log")
    review = payload.get("review")
    if not isinstance(log, list) or not all(isinstance(event, dict) for event in log):
        raise ValidationError("review JSON must contain an object mjai_log array")
    if not isinstance(review, dict) or not isinstance(review.get("kyokus"), list):
        raise ValidationError("review.kyokus is required")
    events = log
    rounds = _rounds(events)
    kyokus = review["kyokus"]
    if len(kyokus) != len(rounds):
        raise ValidationError("review.kyokus count does not match MJAI start_kyoku count")
    player_id = int(payload.get("player_id"))
    mjai_hash = hashlib.sha256(_canonical(log).encode()).hexdigest()
    rows: list[tuple[Any, ...]] = []
    counts = {"complete": 0, "event_mapped": 0, "non_action_mapped": 0,
              "partial": 0, "unmapped": 0, "invalid": 0, "shanten_success": 0,
              "turn_success": 0, "score_success": 0}
    previous_scores: list[int] | None = None
    for round_index, (global_start, global_end, segment) in enumerate(rounds):
        kyoku = kyokus[round_index]
        if not isinstance(kyoku, dict):
            raise ValidationError("each review kyoku must be an object")
        initial = segment[0].get("scores")
        if not isinstance(initial, list) or len(initial) != 4 or not all(isinstance(v, int) for v in initial):
            raise ValidationError("start_kyoku.scores must contain four integers")
        if previous_scores is not None and previous_scores != initial:
            raise ValidationError("MJAI score transitions do not match next start_kyoku")
        snapshots, riichi_snapshots, pending = _event_snapshots(segment, initial)
        entries = kyoku.get("entries")
        if not isinstance(entries, list):
            raise ValidationError("review kyoku entries must be an array")
        matches = _match_entries(entries, segment, global_start)
        for entry, match in zip(entries, matches, strict=True):
            hand_json, fuuros_json, state_error = _validate_state(entry)
            action_category = _action_category(entry)
            status = "complete"
            mapping_kind = match.kind if match else "unmapped"
            reason = state_error
            source_event_index = match.event_index if match else None
            source_round_event_index = match.round_event_index if match else None
            score_values = None
            riichi_seats: set[int] = set()
            self_riichi = None
            is_dealer = None
            rank = gap_first = gap_last = gap_above = gap_below = None
            if match is not None:
                index = match.round_event_index
                score_values = snapshots[index]
                riichi_seats = riichi_snapshots[index]
                self_riichi = int(player_id in riichi_seats)
                is_dealer = int(segment[0].get("oya") == player_id)
                rank, gap_first, gap_last, gap_above, gap_below = _rank_and_gaps(score_values, player_id)
            if state_error or match is None:
                status = "partial" if match is not None else "unmapped"
                reason = reason or ("event_not_uniquely_mapped" if match is None else None)
            if status == "complete":
                counts["complete"] += 1
            elif status == "partial":
                counts["partial"] += 1
            else:
                counts["unmapped"] += 1
            if match is not None:
                counts["event_mapped" if match.kind == "event" else "non_action_mapped"] += 1
                counts["score_success"] += 1
            else:
                mapping_kind = "unmapped"
            if isinstance(entry.get("shanten"), int):
                counts["shanten_success"] += 1
            if isinstance(entry.get("junme"), int):
                counts["turn_success"] += 1
            rows.append((
                entry["_decision_id"], extractor_version, status, mapping_kind, reason,
                source_event_index, source_round_event_index, round_index,
                segment[0].get("bakaze"), segment[0].get("kyoku"), segment[0].get("honba"),
                entry.get("junme"), hand_json, fuuros_json, entry.get("shanten"),
                len(riichi_seats) - int(player_id in riichi_seats), _json(sorted(riichi_seats)),
                self_riichi, is_dealer, _json(score_values) if score_values is not None else None,
                rank, gap_first, gap_last, gap_above, gap_below, action_category,
                game["source_sha256"], mjai_hash, reason, _now(),
            ))
        # Apply the end-of-round events to validate the next start score.
        scores = initial[:]
        for event in segment:
            if event.get("type") == "reach_accepted":
                scores[int(event["actor"])] -= 1000
            elif event.get("type") in {"hora", "ryukyoku"}:
                deltas = event.get("deltas")
                if isinstance(deltas, list) and len(deltas) == 4 and all(isinstance(v, int) for v in deltas):
                    scores = [score + delta for score, delta in zip(scores, deltas, strict=True)]
        previous_scores = scores
    return rows, counts


def extract_review_context(
    connection: sqlite3.Connection,
    review_path: Path,
    *,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
) -> ContextExtractionResult:
    initialize(connection)
    raw = review_path.read_bytes()
    try:
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("review JSON must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationError("review JSON root must be an object")
    review_hash = hashlib.sha256(raw).hexdigest()
    review = connection.execute("SELECT * FROM reviews WHERE review_sha256 = ?", (review_hash,)).fetchone()
    if review is None:
        review_data = payload.get("review")
        log = payload.get("mjai_log")
        player_id = payload.get("player_id")
        if isinstance(review_data, dict) and isinstance(log, list) and isinstance(player_id, int):
            log_hash = hashlib.sha256(_canonical(log).encode()).hexdigest()
            candidates = connection.execute(
                """
                SELECT r.*
                FROM reviews r JOIN games g ON g.id = r.game_id
                WHERE g.log_sha256 = ? AND r.player_id = ?
                  AND r.reviewer_version = ? AND r.model_tag = ?
                  AND r.temperature = ?
                """,
                (log_hash, player_id, str(payload.get("version")),
                 str(review_data.get("model_tag")), review_data.get("temperature")),
            ).fetchall()
            if len(candidates) == 1:
                review = candidates[0]
    if review is None:
        raise ValidationError("review JSON is not registered in this database")
    game = connection.execute("SELECT * FROM games WHERE id = ?", (review["game_id"],)).fetchone()
    assert game is not None
    entries = connection.execute(
        "SELECT id, decision_index FROM decisions WHERE review_id = ? ORDER BY decision_index", (review["id"],)
    ).fetchall()
    kyokus = payload.get("review", {}).get("kyokus", [])
    flattened = [entry for kyoku in kyokus for entry in kyoku.get("entries", [])]
    if len(entries) != len(flattened):
        raise ValidationError("database decisions do not match review entries")
    for row, entry in zip(entries, flattened, strict=True):
        entry["_decision_id"] = row["id"]
    rows, counts = _context_rows(connection, review["id"], game, payload, extractor_version)
    existing = connection.execute(
        "SELECT COUNT(*) FROM decision_contexts WHERE decision_id IN "
        "(SELECT id FROM decisions WHERE review_id = ?) AND extractor_version = ?",
        (review["id"], extractor_version),
    ).fetchone()[0]
    if existing:
        return ContextExtractionResult(review["id"], len(rows), counts["complete"], counts["event_mapped"],
                                       counts["non_action_mapped"], counts["partial"], counts["unmapped"],
                                       counts["invalid"], 0, True, counts["shanten_success"],
                                       counts["turn_success"], counts["score_success"])
    with connection:
        connection.executemany(
            """
            INSERT INTO decision_contexts(
                decision_id, extractor_version, context_status, mapping_kind, status_reason,
                source_event_index, source_round_event_index, round_index, bakaze, kyoku, honba,
                turn_number, hand_json, fuuros_json, shanten_before, opponent_riichi_count,
                riichi_seats_json, self_riichi, is_dealer, scores_before_json, rank_before,
                gap_to_first, gap_to_last, gap_to_above, gap_to_below, action_category,
                source_sha256, mjai_log_sha256, extraction_note, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows,
        )
    return ContextExtractionResult(review["id"], len(rows), counts["complete"], counts["event_mapped"],
                                   counts["non_action_mapped"], counts["partial"], counts["unmapped"],
                                   counts["invalid"], len(rows), False, counts["shanten_success"],
                                   counts["turn_success"], counts["score_success"])


def extract_contexts_path(
    connection: sqlite3.Connection,
    path: Path,
    *,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
) -> list[ContextExtractionResult]:
    paths = [path] if path.is_file() else sorted(path.glob("*.review.json")) if path.is_dir() else []
    if not paths:
        raise ValidationError(f"no review JSON files found: {path}")
    return [extract_review_context(connection, item, extractor_version=extractor_version) for item in paths]
