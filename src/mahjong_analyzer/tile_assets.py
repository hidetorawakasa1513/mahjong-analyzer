"""Safe MJAI tile-id to local image mapping for the review dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TILE_IDS = (
    *(f"{number}m" for number in range(1, 10)),
    *(f"{number}p" for number in range(1, 10)),
    *(f"{number}s" for number in range(1, 10)),
    "E", "S", "W", "N", "P", "F", "C",
    "5mr", "5pr", "5sr",
)
SUPPORTED_TILE_IDS = frozenset(tile_id for tile_id in TILE_IDS if len(tile_id) != 3)
UNSUPPORTED_TILE_IDS = frozenset({"5mr", "5pr", "5sr"})
_HONOR_FILES = {"E": "E.gif", "S": "S.gif", "W": "W.gif", "N": "N.gif",
                "P": "P.gif", "F": "F.gif", "C": "C.gif"}


@dataclass(frozen=True)
class TileAsset:
    tile_id: str
    path: Path
    supported: bool
    source_name: str | None


def _filename(tile_id: str) -> str:
    if tile_id in _HONOR_FILES:
        return _HONOR_FILES[tile_id]
    if len(tile_id) == 2 and tile_id[0] in "123456789" and tile_id[1] in "mps":
        return f"{tile_id}.gif"
    raise ValueError(f"unsupported MJAI tile id: {tile_id}")


def tile_asset(tile_id: str, *, asset_root: Path) -> TileAsset:
    """Resolve one allow-listed MJAI id without accepting arbitrary paths."""
    if tile_id not in TILE_IDS:
        raise ValueError(f"unsupported MJAI tile id: {tile_id}")
    if tile_id in UNSUPPORTED_TILE_IDS:
        return TileAsset(tile_id, asset_root / "unsupported-red.svg", False, None)
    filename = _filename(tile_id)
    return TileAsset(tile_id, asset_root / filename, True, filename)


def all_tile_assets(*, asset_root: Path) -> list[TileAsset]:
    return [tile_asset(tile_id, asset_root=asset_root) for tile_id in TILE_IDS]
