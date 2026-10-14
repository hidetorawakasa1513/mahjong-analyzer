from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.generate_tile_assets import TILE_IDS, render_tile


ASSET_DIR = Path(__file__).parents[1] / "assets" / "tiles"


def test_all_mjai_tile_ids_have_unique_svg_assets() -> None:
    assert len(TILE_IDS) == 37
    assert len(set(TILE_IDS)) == 37
    assert {path.stem for path in ASSET_DIR.glob("*.svg")} == set(TILE_IDS)


def test_svg_assets_are_self_contained_and_have_uniform_viewbox() -> None:
    for tile_id in TILE_IDS:
        path = ASSET_DIR / f"{tile_id}.svg"
        content = path.read_text(encoding="utf-8")
        root = ET.fromstring(content)
        assert root.attrib["viewBox"] == "0 0 80 112"
        assert "<script" not in content.lower()
        assert "href=" not in content.lower()
        assert "url(" not in content.lower()
        assert root.find("{http://www.w3.org/2000/svg}title").text == tile_id


def test_red_fives_are_distinguishable_from_normal_fives() -> None:
    for normal, red in (("5m", "5mr"), ("5p", "5pr"), ("5s", "5sr")):
        normal_svg = (ASSET_DIR / f"{normal}.svg").read_text(encoding="utf-8")
        red_svg = (ASSET_DIR / f"{red}.svg").read_text(encoding="utf-8")
        assert normal_svg != red_svg
        assert 'fill="#c0392b"' in red_svg
        assert '>赤</text>' in red_svg
        assert '>赤</text>' not in normal_svg


def test_preview_references_each_asset_once() -> None:
    preview = (ASSET_DIR / "preview.html").read_text(encoding="utf-8")
    references = re.findall(r'<img src="([^"]+\.svg)"', preview)
    assert len(references) == 37
    assert {Path(reference).stem for reference in references} == set(TILE_IDS)


def test_generator_output_is_parseable() -> None:
    for tile_id in TILE_IDS:
        ET.fromstring(render_tile(tile_id))
