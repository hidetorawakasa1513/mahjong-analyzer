"""Create red-five derivatives from the preserved Mahjong Kingdom GIFs."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


SOURCE_IDS = ("5m", "5p", "5s")
TARGET_IDS = {"5m": "5mr", "5p": "5pr", "5s": "5sr"}


def _redraw(source: Image.Image) -> Image.Image:
    image = source.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            # Keep the outer border, shadow and white face intact.  Only dark
            # ink inside the face is recolored, including anti-aliased edges.
            if not (6 <= x < image.width - 5 and 5 <= y < image.height - 5):
                continue
            red, green, blue, alpha = pixels[x, y]
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            if luminance >= 205:
                continue
            intensity = max(0.0, min(1.0, (205 - luminance) / 205))
            pixels[x, y] = (
                164 + round(52 * intensity),
                34 + round(22 * (1 - intensity)),
                31 + round(18 * (1 - intensity)),
                alpha,
            )
    return image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)


def generate(asset_dir: Path) -> None:
    for source_id in SOURCE_IDS:
        source_path = asset_dir / f"{source_id}.gif"
        target_path = asset_dir / f"{TARGET_IDS[source_id]}.gif"
        with Image.open(source_path) as source:
            if source.size != (47, 63):
                raise ValueError(f"unexpected source size for {source_id}: {source.size}")
            _redraw(source).save(target_path, format="GIF")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, default=Path("assets/third_party/mj_king/tiles"))
    args = parser.parse_args()
    generate(args.asset_dir)
    print("generated 3 red-five GIFs")


if __name__ == "__main__":
    main()
