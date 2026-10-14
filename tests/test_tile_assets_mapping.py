from __future__ import annotations

from pathlib import Path

import pytest

from mahjong_analyzer.tile_assets import TILE_IDS, UNSUPPORTED_TILE_IDS, tile_asset


ASSET_DIR = Path(__file__).parents[1] / "assets" / "third_party" / "mj_king" / "tiles"


def test_mj_ai_ids_map_to_34_official_gifs_and_three_explicit_placeholders() -> None:
    assets = [tile_asset(tile_id, asset_root=ASSET_DIR) for tile_id in TILE_IDS]
    assert len(assets) == 37
    assert sum(asset.supported for asset in assets) == 34
    assert {asset.tile_id for asset in assets if not asset.supported} == UNSUPPORTED_TILE_IDS
    assert all(asset.path.is_file() for asset in assets)
    assert all(asset.path.suffix == ".gif" for asset in assets if asset.supported)


def test_official_gifs_are_47_by_63() -> None:
    for tile_id in TILE_IDS:
        asset = tile_asset(tile_id, asset_root=ASSET_DIR)
        if asset.supported:
            header = asset.path.read_bytes()
            assert header[:6] in {b"GIF87a", b"GIF89a"}
            assert int.from_bytes(header[6:8], "little") == 47
            assert int.from_bytes(header[8:10], "little") == 63


def test_tile_mapping_rejects_arbitrary_paths() -> None:
    with pytest.raises(ValueError):
        tile_asset("../../secret", asset_root=ASSET_DIR)
