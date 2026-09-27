"""Cut generated sheets into engine-ready assets.

Takes the 4x4 figure sheets and the single-object prop sheets out of tools/art_raw/
(cached model output) and writes trimmed, keyed PNGs into assets/.

Why the sizes are what they are
-------------------------------
The atlas is authored at the size the game shows (style_spec.md §0). A knight reserves a
128 px cell and is trimmed within it, so his trimmed height lands near the 59 px screen
target after the prop layer's own scaling. Nothing here resizes to a "nice" number: the
size is derived from the screen budget, and the pipeline reports the result so drift is
visible immediately.

Run:
    python tools/art/build.py            # write assets/
    python tools/art/build.py --check     # report only, write nothing
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "tools" / "art_raw"
OUT = ROOT / "assets"

MAGENTA_TOL = 60

# group -> (cell size for figures, output subdirectory)
FIGURES = {
    "knight_idle": ("characters/knight", 128),
    "knight_sheet": ("characters/knight_walk", 128),
    "cultist": ("enemies/cultist", 112),
    "penitent": ("enemies/penitent", 112),
}
PROPS = {
    "pillar": "props",
    "arch_door": "props",
    "altar": "props",
    "candle_rack": "props",
    "reliquary": "props",
    "banner": "props",
    "sigil": "props",
}


def key_out(img: Image.Image) -> Image.Image:
    """Replace the magenta generation key with alpha, then crop to the silhouette."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 255 - MAGENTA_TOL and g < MAGENTA_TOL and b > 255 - MAGENTA_TOL:
                px[x, y] = (0, 0, 0, 0)
    box = img.getbbox()
    return img.crop(box) if box else img


def frames_of(sheet: Image.Image, cols: int = 4, rows: int = 4) -> list[Image.Image]:
    cw, ch = sheet.width // cols, sheet.height // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    return out


def fit_height(img: Image.Image, target: int) -> Image.Image:
    if img.height == target:
        return img
    ratio = target / img.height
    return img.resize((max(1, round(img.width * ratio)), target), Image.LANCZOS)


def build(check_only: bool = False) -> int:
    written = 0
    problems: list[str] = []

    # --- figures: one trimmed sheet per character, 4 columns x 4 rows ----------------
    for name, (subdir, cell) in FIGURES.items():
        src = RAW / f"{name}.png"
        if not src.is_file():
            problems.append(f"missing raw sheet: {src.name}")
            continue
        sheet = Image.open(src).convert("RGBA")
        cells = [key_out(c) for c in frames_of(sheet)]
        empty = [i for i, c in enumerate(cells) if c.getbbox() is None]
        if empty:
            problems.append(f"{name}: {len(empty)} of 16 cells are empty after keying")
        # Uniform frame box so the walk cycle does not jitter: every frame gets the same
        # canvas and its own anchor preserved by centring horizontally, feet at bottom.
        fw = max(c.width for c in cells)
        fh = max(c.height for c in cells)
        fh = min(fh, cell)
        out = Image.new("RGBA", (fw * 4, fh * 4), (0, 0, 0, 0))
        for i, c in enumerate(cells):
            c = fit_height(c, fh)
            r, col = divmod(i, 4)
            out.alpha_composite(c, (col * fw + (fw - c.width) // 2, r * fh + (fh - c.height)))
        dest = OUT / subdir
        if not check_only:
            dest.mkdir(parents=True, exist_ok=True)
            out.save(dest / f"{Path(subdir).name}.png")
        written += 1
        print(f"{name:14s} -> {subdir:28s} {out.width}x{out.height}  cell {fw}x{fh}")

    # --- props: one trimmed image each ----------------------------------------------
    for name, subdir in PROPS.items():
        src = RAW / f"{name}.png"
        if not src.is_file():
            problems.append(f"missing raw prop: {src.name}")
            continue
        img = key_out(Image.open(src))
        if img.getbbox() is None:
            problems.append(f"{name}: nothing survived keying")
            continue
        img = fit_height(img, min(img.height, 128))
        dest = OUT / subdir
        if not check_only:
            dest.mkdir(parents=True, exist_ok=True)
            img.save(dest / f"{name}.png")
        written += 1
        print(f"{name:14s} -> {subdir:28s} {img.width}x{img.height}")

    print(f"\n{written} assets {'checked' if check_only else 'written'}")
    if problems:
        print("\nPROBLEMS (fix these; do not paper over them):")
        for p in problems:
            print(f"  - {p}")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()
    return build(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
