"""Pure layout helpers for the compact review table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RelativeSeats:
    self_seat: int
    left: int
    top: int
    right: int


def relative_seats(player_id: int) -> RelativeSeats:
    """Return the four seats relative to the reviewed player.

    River order remains the source event order; only the seat placement is
    rotated so the reviewed player is always at the bottom.
    """
    if player_id not in range(4):
        raise ValueError(f"player_id must be 0..3: {player_id}")
    return RelativeSeats(player_id, (player_id + 1) % 4, (player_id + 2) % 4, (player_id + 3) % 4)


def seat_label(seat: int, self_seat: int) -> str:
    if seat == self_seat:
        return "自分"
    relative = (seat - self_seat) % 4
    return {1: "下家", 2: "対面", 3: "上家"}[relative]


def tile_ids_from_action(action: Any) -> list[str]:
    if not isinstance(action, dict):
        return []
    result = [action["pai"]] if isinstance(action.get("pai"), str) else []
    consumed = action.get("consumed")
    if isinstance(consumed, list):
        result.extend(value for value in consumed if isinstance(value, str))
    return result


def compact_table_data(scene: dict[str, Any]) -> dict[str, Any]:
    """Build only public/decision-time data needed by the table renderer."""
    self_seat = scene["identity"]["player_id"]
    seats = relative_seats(self_seat)
    public = scene["public"]
    rivers = public["rivers"]
    melds = public["melds"]
    return {
        "seats": seats,
        "seat_labels": {seat: seat_label(seat, self_seat) for seat in range(4)},
        "rivers": {"left": rivers[seats.left], "top": rivers[seats.top], "right": rivers[seats.right], "self": rivers[seats.self_seat]},
        "melds": {"left": melds[seats.left], "top": melds[seats.top], "right": melds[seats.right], "self": scene["hand"]["fuuros"] or []},
        "dora_markers": public["dora_markers"],
        "riichi_accepted_seats": public["riichi_accepted_seats"],
        "scores": scene["score"].get("scores_before") or [],
        "hand": scene["hand"],
        "round": scene["round"],
        "mortal": scene["mortal"],
    }
