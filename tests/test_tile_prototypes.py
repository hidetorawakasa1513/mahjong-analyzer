from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.generate_tile_prototypes import PROTOTYPE_IDS, render_tile


ASSET_DIR = Path(__file__).parents[1] / "assets" / "tiles"


def test_prototype_set_has_expected_ids() -> None:
    assert len(PROTOTYPE_IDS) == 16
    assert len(set(PROTOTYPE_IDS)) == 16
    assert all((ASSET_DIR / f"{tile_id}.svg").is_file() for tile_id in PROTOTYPE_IDS)


def test_prototypes_are_self_contained_xml_with_uniform_size() -> None:
    for tile_id in PROTOTYPE_IDS:
        content = (ASSET_DIR / f"{tile_id}.svg").read_text(encoding="utf-8")
        root = ET.fromstring(content)
        assert root.attrib["viewBox"] == "0 0 80 112"
        assert "<script" not in content.lower()
        assert "href=" not in content.lower()
        assert "url(" not in content.lower()
        assert root.find("{http://www.w3.org/2000/svg}title").text == tile_id


def test_red_prototypes_are_visibly_distinct() -> None:
    for normal, red in (("5m", "5mr"), ("5p", "5pr"), ("5s", "5sr")):
        normal_svg = (ASSET_DIR / f"{normal}.svg").read_text(encoding="utf-8")
        red_svg = (ASSET_DIR / f"{red}.svg").read_text(encoding="utf-8")
        assert normal_svg != red_svg
        assert 'fill="#c0392b"' in red_svg
        assert ">赤</text>" in red_svg
        assert ">赤</text>" not in normal_svg


def test_prototype_preview_lists_all_ids_once_per_size() -> None:
    preview = (ASSET_DIR / "prototype-preview.html").read_text(encoding="utf-8")
    references = re.findall(r'<img src="([^"]+\.svg)"', preview)
    assert len(references) >= 16
    assert {Path(reference).stem for reference in references} == set(PROTOTYPE_IDS)


def test_prototype_renderer_is_parseable() -> None:
    for tile_id in PROTOTYPE_IDS:
        ET.fromstring(render_tile(tile_id))
