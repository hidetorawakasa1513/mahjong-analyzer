"""Generate the 16 realistic-style SVG tile prototypes for design review.

The renderer intentionally uses only inline SVG primitives and text.  No
external images, fonts, scripts, or network resources are embedded.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape


VIEWBOX = "0 0 80 112"
PROTOTYPE_IDS = (
    "1m", "5m", "9m", "1p", "5p", "9p", "1s", "5s", "9s",
    "E", "P", "F", "C", "5mr", "5pr", "5sr",
)
HONORS = {"E": ("東", "#1f4d7a"), "P": ("", "#56616b"), "F": ("發", "#16734b"), "C": ("中", "#b6382e")}
SUIT_COLORS = {"m": "#9e3f2f", "p": "#23658e", "s": "#28734e"}
PIP_GRID = ((27, 35), (40, 35), (53, 35), (27, 53), (40, 53), (53, 53), (27, 71), (40, 71), (53, 71))


def _base(tile_id: str, description: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">{escape(tile_id)}</title>',
        f'  <desc id="desc">{escape(description)}</desc>',
        '  <rect x="3" y="3" width="76" height="108" rx="7" fill="#1c252b" fill-opacity="0.12"/>',
        '  <rect x="2" y="2" width="76" height="108" rx="7" fill="#fffdf8" stroke="#31383d" stroke-width="1.4"/>',
        '  <rect x="5" y="5" width="70" height="102" rx="5" fill="none" stroke="#d4d0c8" stroke-width="0.8"/>',
    ]


def _red_badge(out: list[str]) -> None:
    out.extend([
        '  <rect x="57" y="7" width="15" height="9" rx="3.5" fill="#c0392b"/>',
        '  <text x="64.5" y="13.7" text-anchor="middle" font-family="Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="5.2" font-weight="700" fill="#fff">赤</text>',
    ])


def _manzu(tile_id: str, number: int, red: bool) -> str:
    ink = "#c0392b" if red else SUIT_COLORS["m"]
    out = _base(tile_id, f"{number}萬" + (" 赤五" if red else ""))
    out.append(f'  <text x="40" y="47" text-anchor="middle" font-family="Hiragino Kaku Gothic ProN, Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="31" font-weight="700" fill="{ink}">{number}</text>')
    out.append(f'  <path d="M18 57 H62 M22 61 H58" stroke="{ink}" stroke-width="1.4" stroke-linecap="round"/>')
    out.append(f'  <text x="40" y="91" text-anchor="middle" font-family="Hiragino Kaku Gothic ProN, Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="24" font-weight="700" fill="{ink}">萬</text>')
    out.append('  <path d="M24 99 H56" stroke="#777d80" stroke-width="0.8"/>')
    if red:
        _red_badge(out)
    out.append('</svg>')
    return "\n".join(out) + "\n"


def _pinzu(tile_id: str, number: int, red: bool) -> str:
    ink = "#c0392b" if red else SUIT_COLORS["p"]
    out = _base(tile_id, f"{number}筒" + (" 赤五" if red else ""))
    positions = PIP_GRID[:number]
    for index, (x, y) in enumerate(positions):
        radius = 7.1 if number == 1 else 5.3
        out.append(f'  <circle cx="{x}" cy="{y + 12}" r="{radius}" fill="{ink}" fill-opacity="0.07" stroke="{ink}" stroke-width="1.8"/>')
        if number == 1:
            out.append(f'  <circle cx="{x}" cy="{y + 12}" r="2.2" fill="{ink}"/>')
        elif index % 3 == 0:
            out.append(f'  <circle cx="{x}" cy="{y + 12}" r="1.4" fill="{ink}"/>')
    out.append(f'  <text x="40" y="98" text-anchor="middle" font-family="Arial, sans-serif" font-size="8" font-weight="700" letter-spacing="1" fill="#626b70">{number}P</text>')
    if red:
        _red_badge(out)
    out.append('</svg>')
    return "\n".join(out) + "\n"


def _souzu(tile_id: str, number: int, red: bool) -> str:
    ink = "#c0392b" if red else SUIT_COLORS["s"]
    out = _base(tile_id, f"{number}索" + (" 赤五" if red else ""))
    if number == 1:
        out.extend([
            f'  <path d="M29 63 C29 53 37 47 46 51 C53 54 55 62 49 68 C43 73 34 72 29 63 Z" fill="{ink}" fill-opacity="0.13" stroke="{ink}" stroke-width="1.8"/>',
            f'  <path d="M48 53 L61 46 L53 61 M31 62 L20 70" fill="none" stroke="{ink}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
            f'  <circle cx="44" cy="57" r="1.8" fill="{ink}"/>',
        ])
    else:
        for index, (x, y) in enumerate(PIP_GRID[:number]):
            rotation = -18 if index % 2 == 0 else 18
            out.append(f'  <g transform="rotate({rotation} {x} {y + 12})"><rect x="{x - 3.2}" y="{y + 4}" width="6.4" height="17" rx="2.8" fill="{ink}"/><path d="M{x - 3} {y + 9} H{x + 3} M{x - 3} {y + 15} H{x + 3}" stroke="#fffdf8" stroke-width="1"/></g>')
    out.append(f'  <text x="40" y="98" text-anchor="middle" font-family="Arial, sans-serif" font-size="8" font-weight="700" letter-spacing="1" fill="#626b70">{number}S</text>')
    if red:
        _red_badge(out)
    out.append('</svg>')
    return "\n".join(out) + "\n"


def _honor(tile_id: str) -> str:
    label, color = HONORS[tile_id]
    out = _base(tile_id, f"字牌 {label or '白'}")
    if tile_id == "P":
        out.extend([
            '  <rect x="20" y="31" width="40" height="49" rx="2" fill="#fff" stroke="#8f9699" stroke-width="1.6"/>',
            '  <path d="M27 38 H53 M27 73 H53" stroke="#d7d9d7" stroke-width="1"/>',
            '  <text x="40" y="96" text-anchor="middle" font-family="Arial, sans-serif" font-size="7" letter-spacing="1" fill="#697277">HAKU</text>',
        ])
    else:
        out.append(f'  <text x="40" y="77" text-anchor="middle" font-family="Hiragino Kaku Gothic ProN, Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="42" font-weight="700" fill="{color}">{label}</text>')
        out.append(f'  <path d="M22 88 H58" stroke="{color}" stroke-width="1.2" stroke-linecap="round"/>')
    out.append(f'  <text x="40" y="101" text-anchor="middle" font-family="Arial, sans-serif" font-size="7" font-weight="700" letter-spacing="1" fill="#626b70">{tile_id}</text>')
    out.append('</svg>')
    return "\n".join(out) + "\n"


def render_tile(tile_id: str) -> str:
    if tile_id in HONORS:
        return _honor(tile_id)
    number = int(tile_id[0])
    suit = tile_id[1]
    red = len(tile_id) == 3
    if suit == "m":
        return _manzu(tile_id, number, red)
    if suit == "p":
        return _pinzu(tile_id, number, red)
    if suit == "s":
        return _souzu(tile_id, number, red)
    raise ValueError(f"unsupported prototype tile: {tile_id}")


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for tile_id in PROTOTYPE_IDS:
        (output_dir / f"{tile_id}.svg").write_text(render_tile(tile_id), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("assets/tiles"))
    args = parser.parse_args()
    generate(args.output)
    print(f"generated {len(PROTOTYPE_IDS)} prototype SVG tiles in {args.output}")


if __name__ == "__main__":
    main()
