from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .importer import ImportMetadata, normalize_review


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"review JSON cannot be read: {path}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("review JSON root must be an object")
    return raw, payload


def _find_review_path(
    review: sqlite3.Row,
    *,
    review_json: Path | None,
    review_root: Path,
) -> tuple[Path, bytes, dict[str, Any]]:
    candidates = [review_json] if review_json is not None else sorted(review_root.rglob("*.review.json"))
    for path in candidates:
        if path is None or not path.is_file():
            continue
        raw, payload = _load_json(path)
        exact = hashlib.sha256(raw).hexdigest() == review["review_sha256"]
        try:
            stable = normalize_review(
                raw,
                ImportMetadata(game_id=review["source_game_id"], player_id=review["player_id"]),
            ).review_identity_sha256 == review["review_identity_sha256"]
        except ValidationError:
            stable = False
        if exact or stable:
            return path, raw, payload
    if review_json is not None:
        raise ValidationError("specified review JSON does not match the registered review")
    raise ValidationError(f"registered review JSON was not found below: {review_root}")


def _flatten_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    review = payload.get("review")
    if not isinstance(review, dict) or not isinstance(review.get("kyokus"), list):
        raise ValidationError("review.kyokus is required")
    flattened: list[dict[str, Any]] = []
    for kyoku in review["kyokus"]:
        if not isinstance(kyoku, dict) or not isinstance(kyoku.get("entries"), list):
            raise ValidationError("each review kyoku must contain entries")
        flattened.extend(entry for entry in kyoku["entries"] if isinstance(entry, dict))
    return flattened


def _round_start(events: list[dict[str, Any]], event_index: int) -> int:
    starts = [i for i, event in enumerate(events[: event_index + 1]) if event.get("type") == "start_kyoku"]
    if not starts:
        raise ValidationError("source event is not inside a start_kyoku segment")
    return starts[-1]


def _public_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    rivers: list[list[dict[str, Any]]] = [[], [], [], []]
    melds: list[list[dict[str, Any]]] = [[], [], [], []]
    riichi_pending: set[int] = set()
    riichi_accepted: set[int] = set()
    dora_markers: list[str] = []
    for event in events:
        event_type = event.get("type")
        if event_type == "start_kyoku":
            marker = event.get("dora_marker")
            if isinstance(marker, str):
                dora_markers = [marker]
        elif event_type == "dahai" and isinstance(event.get("actor"), int):
            actor = event["actor"]
            if 0 <= actor < 4:
                rivers[actor].append({
                    "pai": event.get("pai"),
                    "tsumogiri": event.get("tsumogiri"),
                })
        elif event_type in {"chi", "pon", "ankan", "kakan", "daiminkan"}:
            actor = event.get("actor")
            if isinstance(actor, int) and 0 <= actor < 4:
                melds[actor].append({
                    key: event[key] for key in ("type", "actor", "target", "pai", "consumed") if key in event
                })
        elif event_type == "reach" and isinstance(event.get("actor"), int):
            riichi_pending.add(event["actor"])
        elif event_type == "reach_accepted" and isinstance(event.get("actor"), int):
            riichi_pending.discard(event["actor"])
            riichi_accepted.add(event["actor"])
        elif event_type == "dora" and isinstance(event.get("dora_marker"), str):
            dora_markers.append(event["dora_marker"])
    return {
        "rivers": rivers,
        "melds": melds,
        "riichi_pending_seats": sorted(riichi_pending),
        "riichi_accepted_seats": sorted(riichi_accepted),
        "dora_markers": dora_markers,
        "event_count": len(events),
    }


def _scores_before(events: list[dict[str, Any]], round_start: int, event_index: int) -> list[int] | None:
    start = events[round_start].get("scores")
    if not isinstance(start, list) or len(start) != 4 or not all(isinstance(value, int) for value in start):
        return None
    scores = start[:]
    for event in events[round_start + 1 : event_index]:
        if event.get("type") == "reach_accepted" and isinstance(event.get("actor"), int):
            scores[event["actor"]] -= 1000
        elif event.get("type") in {"hora", "ryukyoku"}:
            deltas = event.get("deltas")
            if isinstance(deltas, list) and len(deltas) == 4 and all(isinstance(value, int) for value in deltas):
                scores = [score + delta for score, delta in zip(scores, deltas, strict=True)]
    return scores


def _parse_json_column(row: sqlite3.Row, name: str, default: Any) -> Any:
    value = row[name]
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _source_reference(game: sqlite3.Row, review_path: Path, review_root: Path) -> dict[str, Any]:
    source_sha256 = game["source_sha256"]
    matched: str | None = None
    if source_sha256:
        for path in review_root.rglob("*"):
            if path.is_file() and path.suffix not in {".json", ".mjai"}:
                try:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    continue
                if digest == source_sha256:
                    matched = str(path)
                    break
    return {
        "source_game_id": game["source_game_id"],
        "source_sha256": source_sha256,
        "original_file": matched,
        "original_file_available": matched is not None,
        "review_json": str(review_path),
        "reconstruction_source": "review_json.mjai_log",
        "event_index_basis": "review JSON mjai_log, zero-based; not original XML node index",
    }


def get_review_scene(
    connection: sqlite3.Connection,
    decision_id: int,
    *,
    review_root: Path = Path("local_data"),
    review_json: Path | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Return a decision-time, public-information-only review scene.

    The review JSON's MJAI log is replayed up to the decision reference event.
    A normal action is shown before its event; a ``none`` opportunity includes
    the referenced opponent discard so the exposed tile is visible.
    """
    row = connection.execute(
        """
        SELECT d.*, r.game_id, r.player_id, r.engine, r.reviewer_version,
               r.model_tag, r.model_identity, r.grp_identity, r.temperature, r.rating,
               r.review_sha256, r.review_identity_sha256,
               g.source_game_id, g.source_sha256, g.rule_context
        FROM decisions d
        JOIN reviews r ON r.id = d.review_id
        JOIN games g ON g.id = r.game_id
        WHERE d.id = ?
        """,
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ValidationError(f"decision not found: {decision_id}")
    context = connection.execute(
        """
        SELECT * FROM decision_contexts
        WHERE decision_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (decision_id,),
    ).fetchone()
    if context is None:
        raise ValidationError(f"decision context not found: {decision_id}")
    path, _, payload = _find_review_path(row, review_json=review_json, review_root=review_root)
    entries = _flatten_entries(payload)
    if row["decision_index"] >= len(entries):
        raise ValidationError("decision index is outside review entries")
    entry = entries[row["decision_index"]]
    events = payload.get("mjai_log")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValidationError("review JSON mjai_log is required")
    event_index = context["source_event_index"]
    if event_index is None or not 0 <= event_index < len(events):
        raise ValidationError("decision has no valid MJAI source event")
    round_start = _round_start(events, event_index)
    include_reference = context["mapping_kind"] == "non_action_opportunity"
    public_events = events[round_start : event_index + (1 if include_reference else 0)]
    public = _public_snapshot(public_events)
    state = entry.get("state") if isinstance(entry.get("state"), dict) else {}
    hand = state.get("tehai") if isinstance(state.get("tehai"), list) else None
    fuuros = state.get("fuuros") if isinstance(state.get("fuuros"), list) else None
    action = entry.get("actual") if isinstance(entry.get("actual"), dict) else None
    expected = entry.get("expected") if isinstance(entry.get("expected"), dict) else None
    details = entry.get("details") if isinstance(entry.get("details"), list) else []
    candidates = [item for item in details if isinstance(item, dict)]
    context_scores = _parse_json_column(context, "scores_before_json", None)
    start_event = events[round_start]
    reconstructed_scores = _scores_before(events, round_start, event_index)
    score_consistent = context_scores == reconstructed_scores
    if context_scores is not None and len(context_scores) == 4:
        score_consistent = context_scores == reconstructed_scores
    rank_is_tied = (
        not isinstance(context_scores, list) or len(context_scores) != 4
        or len(set(context_scores)) != 4
    )
    status = "complete"
    if hand is None or fuuros is None or not score_consistent:
        status = "inconsistent" if not score_consistent else "partial"
    player_id = row["player_id"]
    oya = start_event.get("oya")
    winds = ("E", "S", "W", "N")
    self_wind = winds[(player_id - oya) % 4] if isinstance(oya, int) and 0 <= oya < 4 else None
    return {
        "status": status,
        "status_reasons": [] if status == "complete" else [
            reason for reason, failed in (
                ("hand_state_unavailable", hand is None),
                ("fuuros_state_unavailable", fuuros is None),
                ("context_score_mismatch", not score_consistent),
            ) if failed
        ],
        "identity": {
            "decision_id": row["id"], "review_id": row["review_id"], "game_id": row["game_id"],
            "player_id": player_id, "round_index": context["round_index"],
            "source_event_index": event_index, "source_round_event_index": context["source_round_event_index"],
            "extractor_version": context["extractor_version"],
        },
        "source": _source_reference(row, path, source_root or review_root),
        "round": {
            "bakaze": context["bakaze"], "kyoku": context["kyoku"], "honba": context["honba"],
            "oya": oya, "self_wind": self_wind, "turn_number": context["turn_number"],
            "tiles_left": entry.get("tiles_left"),
        },
        "hand": {
            "tiles": hand, "tsumo_tile": entry.get("tile"), "fuuros": fuuros,
            "shanten": context["shanten_before"], "self_riichi": context["self_riichi"],
        },
        "public": {
            **public,
            "decision_phase": "after_reference_event" if include_reference else "before_action_event",
            "reference_event": events[event_index],
        },
        "score": {
            "scores_before": context_scores,
            "rank": None if rank_is_tied else context["rank_before"],
            "gap_to_first": context["gap_to_first"], "gap_to_last": context["gap_to_last"],
            "gap_to_above": context["gap_to_above"], "gap_to_below": context["gap_to_below"],
            "score_consistent_with_replay": score_consistent,
        },
        "mortal": {
            "engine": row["engine"], "reviewer_version": row["reviewer_version"],
            "model_tag": row["model_tag"], "model_identity": row["model_identity"],
            "grp_identity": row["grp_identity"], "temperature": row["temperature"],
            "rating": row["rating"], "actual_action": action, "expected_action": expected,
            "selected_action": action, "mortal_first_action": expected,
            "is_equal": None if row["is_equal"] is None else bool(row["is_equal"]),
            "actual_probability": row["actual_probability"], "candidates": candidates,
            "action_category": context["action_category"],
        },
        "none_judgment": {
            "is_none": context["action_category"] == "none",
            "meaning": "unknown; not assumed to be a meld pass",
            "reference_event_is_exposed": include_reference,
        },
    }


def adjacent_decisions(
    connection: sqlite3.Connection,
    decision_id: int,
    *,
    disagreement_only: bool = False,
) -> tuple[int | None, int | None]:
    """Return previous/next decisions within the same review condition."""
    current = connection.execute(
        "SELECT review_id, decision_index FROM decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    if current is None:
        raise ValidationError(f"decision not found: {decision_id}")
    predicate = " AND is_equal = 0" if disagreement_only else ""
    previous = connection.execute(
        f"SELECT id FROM decisions WHERE review_id = ? AND decision_index < ?{predicate} "
        "ORDER BY decision_index DESC, id DESC LIMIT 1",
        (current["review_id"], current["decision_index"]),
    ).fetchone()
    following = connection.execute(
        f"SELECT id FROM decisions WHERE review_id = ? AND decision_index > ?{predicate} "
        "ORDER BY decision_index ASC, id ASC LIMIT 1",
        (current["review_id"], current["decision_index"]),
    ).fetchone()
    return (previous["id"] if previous else None, following["id"] if following else None)
