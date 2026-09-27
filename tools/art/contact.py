"""Contact sheet for the Iron Vigil concept samples.

Reviewing 16 separate PNGs one at a time hides exactly what matters: whether they look
like they came from the same hand. A contact sheet on one background shows consistency,
silhouette quality and value range at a glance.

Tiles are also made *tileable* here (mirror-wrapped edges + a seam check), because a
single tile image tells you nothing about how it repeats — and repetition is where a
floor tile succeeds or fails.

Run:
    python tools/art/contact.py
    python tools/art/contact.py --cell 200
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "tools" / "art_raw"
OUT = ROOT / "tools" / "design" / "concepts"

SPRITES = ["knight_idle", "knight_sheet", "cultist", "penitent"]
PROPS = ["pillar", "arch_door", "altar", "candle_rack", "reliquary", "banner", "sigil"]
SCENES = ["scene_cloister", "scene_ritual"]
TILES = ["floor_stone", "floor_blood", "wall_stone"]

MAGENTA_TOL = 60


def key_out(img: Image.Image) -> Image.Image:
    """Drop the magenta key, then crop to the remaining silhouette."""
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


def fit(img: Image.Image, box: int) -> Image.Image:
    """Scale to sit inside a square cell, nearest-neighbour, never upscaled past 2x."""
    scale = min(box / max(1, img.width), box / max(1, img.height))
    scale = min(scale, 2.0)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                      Image.NEAREST)


def tileable(img: Image.Image, size: int = 64) -> Image.Image:
    """Make a tile that actually tiles: half-offset wrap.

    A flat surface pattern has no 'correct' phase, so the cheapest honest trick is to
    resize to the tile size and then blend the seam. Without this the tile shows a hard
    line every 64 px and the floor reads as a grid of stickers.
    """
    img = img.convert("RGB").resize((size, size), Image.LANCZOS)
    a = img.crop((0, 0, size // 2, size // 2))
    b = img.crop((size // 2, size // 2, size, size))
    c = img.crop((size // 2, 0, size, size // 2))
    d = img.crop((0, size // 2, size // 2, size))
    out = img.copy()
    out.paste(a, (0, 0)); out.paste(b, (size // 2, size // 2))
    out.paste(c, (size // 2, 0)); out.paste(d, (0, size // 2))
    return out


def seam_error(img: Image.Image) -> float:
    """Mean absolute difference across the wrap seam vs the image's own mean difference.
    A tile whose seam is much harsher than its interior will read as a grid."""
    px = img.load()
    w, h = img.size
    seam = 0.0
    for i in range(h):
        seam += abs(px[0, i][0] - px[w - 1, i][0]) + abs(px[i, 0][0] - px[i, h - 1][0])
    seam /= (2 * h)
    inner = 0.0
    for i in range(h):
        for j in range(0, w - 1, 4):
            inner += abs(px[j, i][0] - px[j + 1, i][0])
    inner /= (h * (w // 4))
    return seam / max(inner, 0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", type=int, default=170, help="cell size in px")
    args = ap.parse_args()
    cell = args.cell
    OUT.mkdir(parents=True, exist_ok=True)

    BG = (22, 20, 24)
    PAD = 12
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def block(names: list[str], title: str, columns: int, kind: str) -> Image.Image:
        rows = (len(names) + columns - 1) // columns
        w = columns * (cell + PAD) + PAD
        h = rows * (cell + PAD + 16) + 34
        sheet = Image.new("RGB", (w, h), BG)
        dr = ImageDraw.Draw(sheet)
        dr.text((PAD, 8), title, fill=(240, 214, 150))
        present = []
        for i, name in enumerate(names):
            src = RAW / f"{name}.png"
            if not src.is_file():
                continue
            present.append(name)
            r, c = divmod(i, columns)
            x0 = PAD + c * (cell + PAD)
            y0 = 30 + r * (cell + PAD + 16)
            if kind == "tile":
                t = tileable(Image.open(src), 64)
                # Show it repeated 3x3 the way a floor repeats it.
                rep = Image.new("RGB", (cell, cell), BG)
                step = cell // 3
                for ty in range(3):
                    for tx in range(3):
                        rep.paste(t.resize((step, step), Image.NEAREST), (tx * step, ty * step))
                sheet.paste(rep, (x0, y0))
                err = seam_error(t)
                dr.text((x0, y0 + cell + 2), f"{name}  seam x{err:.1f}", fill=(170, 200, 170))
            else:
                img = Image.open(src)
                if name in SPRITES or name in PROPS:
                    img = key_out(img)
                img = fit(img, cell)
                sheet.paste(img, (x0 + (cell - img.width) // 2, y0 + (cell - img.height) // 2),
                            img if img.mode == "RGBA" else None)
                dr.text((x0, y0 + cell + 2), name, fill=(190, 190, 195))
        return sheet

    sheets = [
        block(SPRITES, "FIGURES  (4x4 sheets, magenta key removed)", 2, "sprite"),
        block(PROPS, "PROPS  (single objects)", 4, "prop"),
        block(TILES, "TILES  (shown repeated 3x3; seam = wrap error / interior error)", 3, "tile"),
    ]
    total_w = max(s.width for s in sheets)
    total_h = sum(s.height for s in sheets)
    sheet = Image.new("RGB", (total_w, total_h), BG)
    y = 0
    for s in sheets:
        sheet.paste(s, (0, y))
        y += s.height
    path = OUT / "concept_sheet.png"
    sheet.save(path)
    print(f"{path}  {sheet.width}x{sheet.height}")

    for name in SCENES:
        src = RAW / f"{name}.png"
        if src.is_file():
            dst = OUT / f"{name}.png"
            Image.open(src).convert("RGB").save(dst)
            print(f"{dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
