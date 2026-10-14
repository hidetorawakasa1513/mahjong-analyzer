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
    rotated so the reviewed player is always at the bottom.  In the
    reviewer-facing view, shimo is on the right and kamicha is on the left.
    """
    if player_id not in range(4):
        raise ValueError(f"player_id must be 0..3: {player_id}")
    return RelativeSeats(player_id, (player_id + 3) % 4, (player_id + 2) % 4, (player_id + 1) % 4)


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


def tile_sort_key(tile_id: str) -> tuple[int, int, int, str]:
    """Return the deterministic riichi-mahjong sorting key used by the view."""
    if len(tile_id) >= 2 and tile_id[0].isdigit() and tile_id[1] in "mps":
        return ("mps".index(tile_id[1]), int(tile_id[0]), int(tile_id.endswith("r")), tile_id)
    honors = {value: index for index, value in enumerate("ESWNPFC")}
    return (3, honors.get(tile_id, len(honors)), 0, tile_id)


def sort_hand_tiles(tiles: Any) -> list[str]:
    """Sort concealed tiles without losing red-five identifiers."""
    if not isinstance(tiles, list):
        return []
    return sorted((tile for tile in tiles if isinstance(tile, str)), key=tile_sort_key)


def split_hand_and_tsumo(tiles: Any, tsumo_tile: Any, *, show_tsumo: bool) -> tuple[list[str], str | None, bool]:
    """Separate one known draw from the sorted concealed hand.

    The event identifies the tile type, not a physical copy.  Removing one
    equal tile keeps the visible count correct; if the type is absent, the
    draw is reported as unknown instead of inventing a replacement.
    """
    sorted_tiles = sort_hand_tiles(tiles)
    if not show_tsumo or not isinstance(tsumo_tile, str):
        return sorted_tiles, None, False
    try:
        index = sorted_tiles.index(tsumo_tile)
    except ValueError:
        return sorted_tiles, None, False
    return sorted_tiles[:index] + sorted_tiles[index + 1:], tsumo_tile, True


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
        "judgment": scene.get("judgment", {}),
        "round": scene["round"],
        "mortal": scene["mortal"],
    }
