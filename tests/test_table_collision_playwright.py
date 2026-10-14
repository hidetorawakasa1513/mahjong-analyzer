"""Optional real-browser collision checks for the table renderer.

These tests use only a synthetic scene and embedded tile data, so they do not
open the application, SQLite, or any private replay.  Install Playwright and
its local Chromium binary separately when running this optional test.
"""

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="optional Playwright dependency is not installed")
from playwright.sync_api import sync_playwright  # noqa: E402

from mahjong_analyzer.dashboard.table_renderer import render_table_html, table_css  # noqa: E402


ASSETS = Path(__file__).parents[1] / "assets/third_party/mj_king/tiles"


def _scene() -> dict:
    river = [{"pai": f"{(index % 9) + 1}m"} for index in range(18)]
    return {
        "identity": {"player_id": 0},
        "round": {"bakaze": "E", "kyoku": 3, "honba": 0, "kyotaku": 1,
                   "turn_number": 12, "tiles_left": 24},
        "hand": {"tiles": ["1m", "2m", "3m", "4m", "5m"], "tsumo_tile": "5p",
                 "fuuros": [{"type": "pon", "actor": 0, "target": 1, "pai": "E", "consumed": ["E", "E"]}],
                 "shanten": 1},
        "public": {
            "rivers": [river, river[:12], river[:15], river[:10]],
            "melds": [[{"type": "pon", "actor": 0, "target": 1, "pai": "E", "consumed": ["E", "E"]}], [], [], []],
            "dora_markers": ["5p"], "riichi_accepted_seats": [0], "riichi_pending_seats": [],
        },
        "score": {"scores_before": [25000, 24000, 26000, 25000]},
        "mortal": {"selected_action": {"type": "dahai", "pai": "5m"},
                   "mortal_first_action": {"type": "dahai", "pai": "4m"}, "candidates": []},
    }


def _overlap(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and a["x"] + a["width"] > b["x"]
            and a["y"] < b["y"] + b["height"] and a["y"] + a["height"] > b["y"])


def _page_content() -> str:
    return f"<!doctype html><style>{table_css()}</style>{render_table_html(_scene(), ASSETS)}"


def test_table_regions_do_not_overlap_at_desktop_viewports() -> None:
    viewports = ((1920, 1080), (1440, 900), (1366, 768))
    river_ids = ["river-top", "river-left", "river-right", "river-bottom"]
    score_ids = ["score-top", "score-left", "score-right", "score-bottom"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            for width, height in viewports:
                page.set_viewport_size({"width": width, "height": height})
                page.set_content(_page_content())
                boxes = {
                    testid: page.get_by_test_id(testid).bounding_box()
                    for testid in ["review-table", "center-info", "hand-self", "table-legend", *river_ids, *score_ids]
                }
                assert all(boxes.values()), f"missing table region at {width}x{height}"
                table = boxes["review-table"]
                for testid, box in boxes.items():
                    if testid not in {"review-table", "table-legend"}:
                        assert box["x"] >= table["x"] - 1 and box["x"] + box["width"] <= table["x"] + table["width"] + 1, testid
                        assert box["y"] >= table["y"] - 1 and box["y"] + box["height"] <= table["y"] + table["height"] + 1, testid
                for river_id in river_ids:
                    assert not _overlap(boxes["center-info"], boxes[river_id]), (width, height, "center", river_id)
                    for score_id in score_ids:
                        assert not _overlap(boxes[score_id], boxes[river_id]), (width, height, score_id, river_id)
                assert not _overlap(boxes["hand-self"], boxes["river-bottom"])
                for index, first in enumerate(river_ids):
                    for second in river_ids[index + 1:]:
                        assert not _overlap(boxes[first], boxes[second]), (width, height, first, second)
        finally:
            browser.close()


def test_collision_helper_detects_an_intentional_overlap() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<div data-testid="a" style="position:absolute;left:0;top:0;width:20px;height:20px"></div>'
                            '<div data-testid="b" style="position:absolute;left:10px;top:10px;width:20px;height:20px"></div>')
            assert _overlap(page.get_by_test_id("a").bounding_box(), page.get_by_test_id("b").bounding_box())
        finally:
            browser.close()
