"""Generate the self-contained SVG tile assets used by the future review UI."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape


VIEWBOX = "0 0 80 112"
TILE_IDS = (
    *(f"{n}m" for n in range(1, 10)),
    *(f"{n}p" for n in range(1, 10)),
    *(f"{n}s" for n in range(1, 10)),
    "E", "S", "W", "N", "P", "F", "C",
    "5mr", "5pr", "5sr",
)
HONOR_LABELS = {"E": "東", "S": "南", "W": "西", "N": "北", "P": "白", "F": "發", "C": "中"}
HONOR_COLORS = {"E": "#1464a0", "S": "#1464a0", "W": "#1464a0", "N": "#1464a0",
                "P": "#555b66", "F": "#17804d", "C": "#c0392b"}
PIP_POSITIONS = ((26, 37), (40, 37), (54, 37), (26, 53), (40, 53), (54, 53),
                 (26, 69), (40, 69), (54, 69))


def _header(tile_id: str, label: str) -> str:
    safe_id = escape(tile_id, {'"': "&quot;"})
    safe_label = escape(label)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}" role="img" aria-labelledby="title desc">
  <title id="title">{safe_id}</title>
  <desc id="desc">{safe_label}</desc>
  <rect x="1" y="1" width="78" height="110" rx="8" fill="#fffdf8" stroke="#27313a" stroke-width="2"/>
  <rect x="5" y="5" width="70" height="102" rx="5" fill="none" stroke="#d6d0c5" stroke-width="1"/>
'''


def _footer(red: bool = False) -> str:
    if not red:
        return "</svg>\n"
    return '''  <rect x="55" y="7" width="18" height="10" rx="4" fill="#c0392b"/>
  <text x="64" y="14.5" text-anchor="middle" font-family="Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="6" font-weight="700" fill="#fff">赤</text>
</svg>
'''


def _number_tile(tile_id: str) -> str:
    number = int(tile_id[0])
    suit = tile_id[1]
    red = len(tile_id) == 3
    ink = "#c0392b" if red else {"m": "#b34b35", "p": "#1769aa", "s": "#16805a"}[suit]
    suit_label = {"m": "萬", "p": "筒", "s": "索"}[suit]
    out = [_header(tile_id, f"{number}{suit}牌")]
    out.append(f'  <text x="40" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="25" font-weight="700" fill="{ink}">{number}</text>')
    if suit == "m":
        out.append(f'  <text x="40" y="91" text-anchor="middle" font-family="Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="27" font-weight="700" fill="{ink}">{suit_label}</text>')
    elif suit == "p":
        for x, y in PIP_POSITIONS[:number]:
            out.append(f'  <circle cx="{x}" cy="{y + 16}" r="5.2" fill="none" stroke="{ink}" stroke-width="2.3"/>')
    else:
        for index, (x, y) in enumerate(PIP_POSITIONS[:number]):
            rotation = -28 if index % 2 == 0 else 28
            out.append(f'  <rect x="{x - 3}" y="{y + 13}" width="6" height="16" rx="2.5" fill="{ink}" transform="rotate({rotation} {x} {y + 21})"/>')
    out.append(f'  <text x="40" y="103" text-anchor="middle" font-family="Arial, sans-serif" font-size="7" letter-spacing="1" fill="#59636b">{suit.upper()}</text>')
    out.append(_footer(red))
    return "\n".join(out)


def _honor_tile(tile_id: str) -> str:
    color = HONOR_COLORS[tile_id]
    label = HONOR_LABELS[tile_id]
    out = [_header(tile_id, f"字牌 {label}")]
    out.append(f'  <text x="40" y="74" text-anchor="middle" font-family="Hiragino Sans, Yu Gothic, Noto Sans CJK JP, sans-serif" font-size="42" font-weight="700" fill="{color}">{label}</text>')
    out.append(f'  <path d="M18 91 H62" stroke="{color}" stroke-width="2" stroke-linecap="round"/>')
    out.append(f'  <text x="40" y="101" text-anchor="middle" font-family="Arial, sans-serif" font-size="7" letter-spacing="1" fill="#59636b">{tile_id}</text>')
    out.append(_footer())
    return "\n".join(out)


def render_tile(tile_id: str) -> str:
    if tile_id in HONOR_LABELS:
        return _honor_tile(tile_id)
    return _number_tile(tile_id)


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for tile_id in TILE_IDS:
        (output_dir / f"{tile_id}.svg").write_text(render_tile(tile_id), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("assets/tiles"))
    args = parser.parse_args()
    generate(args.output)
    print(f"generated {len(TILE_IDS)} SVG tiles in {args.output}")


if __name__ == "__main__":
    main()
