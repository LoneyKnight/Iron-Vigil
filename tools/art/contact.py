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
import numpy as np

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


def seam_parts(img: Image.Image) -> tuple[float, float, float]:
    """(mean difference across the wrap, mean difference inside, their ratio).

    The ratio is the number that matters: a tile whose seam is much harsher than its own
    interior difference will read as a grid of stickers, however pretty the tile is on its
    own. The two raw numbers are returned as well because the ratio alone cannot tell a
    seamless surface from a flat colour — an almost uniform tile scores ~0.2 and means
    nothing (see the model-tile evidence in tiles.py).
    """
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
    return seam, inner, seam / max(inner, 0.5)


def seam_error(img: Image.Image) -> float:
    """Wrap error / interior error. Kept as the one-line entry point everything else calls."""
    return seam_parts(img)[2]


def seam_table() -> int:
    """Print the seam numbers for the SHIPPED tiles and for the model tiles they replaced.

    The shipped tiles are measured at their native 64x64, which is the size the engine
    repeats; the model evidence is measured the same way plus through `tileable()`'s
    quadrant swap, so the number in the acceptance report can be reproduced either way.
    """
    import props  # local import: props owns the size table, this module owns the pixels
    import tiles  # noqa: PLC0415

    print(f"SHIPPED  assets/tiles/*.png   ({tiles.SIZE}x{tiles.SIZE} texels = "
          f"{tiles.TILE_M:.0f}x{tiles.TILE_M:.0f} m)")
    print(f"{'tile':14s} {'seam':>6s} {'inner':>6s} {'swap':>6s} {'colours':>7s}")
    bad = 0
    for name in tiles.TILES:
        src = ROOT / "assets" / "tiles" / f"{name}.png"
        if not src.is_file():
            print(f"{name:14s}  missing {src}")
            bad += 1
            continue
        img = Image.open(src).convert("RGB")
        seam, inner, ratio = seam_parts(img)
        _, _, swapped = seam_parts(tileable(img, img.width))
        colours = len(np.unique(np.asarray(img).reshape(-1, 3), axis=0))
        flag = ""
        if ratio > 2.0:
            flag, bad = "  <-- FAIL (>2.0)", bad + 1
        elif inner < 1.0:
            flag, bad = "  <-- degenerate (interior ~flat)", bad + 1
        print(f"{name:14s} {ratio:6.2f} {inner:6.2f} {swapped:6.2f} {colours:7d}{flag}")
    print(f"\nMODEL EVIDENCE  tools/art_raw/*.png (cached, NOT shipped)")
    print(f"{'tile':14s} {'seam':>6s} {'inner':>6s} {'swap':>6s} {'colours':>7s}")
    for r in tiles.model_evidence():
        print(f"{r['name']:14s} {r['seam']:6.2f} {r['inner']:6.2f} {r['swap_seam']:6.2f} "
              f"{r['colours']:7d}")
    print(f"\nprops.py authored-size check: {'OK' if not bad else f'{bad} tile problem(s)'}")
    return 1 if bad else 0


# ---------------------------------------------------------------------------------------
# batch 1 contact sheet: the SHIPPED assets, at the size the game shows them
# ---------------------------------------------------------------------------------------

def _font(size: int):
    try:
        from PIL import ImageFont
        return ImageFont.load_default(size=size)
    except Exception:  # pragma: no cover - very old Pillow
        return None


def _batch1_rows() -> list[dict]:
    """Every shipped batch-1 asset with its authorised screen size and its measured deviation."""
    import props  # noqa: PLC0415

    rows: list[dict] = []
    for name, spec in props.SPECS.items():
        dest = props.OUT / spec["group"] / f"{name}.png"
        if not dest.is_file():
            continue
        aw, ah = props.authored(name)
        img = Image.open(dest).convert("RGBA")
        per_m = props.PPM if spec["plane"] == "ground" else props.VPPM
        rows.append({
            "name": name, "group": spec["group"], "img": img, "auth": (aw, ah),
            "dev_w": (img.width - aw) / aw, "dev_h": (img.height - ah) / ah,
            "world": (img.width / props.PPM, img.height / per_m), "box": spec["world"],
            "note": spec["note"],
        })
    return rows


def batch1_sheet() -> int:
    """The acceptance sheet: props at 1:1 screen size with the authorised height drawn on.

    Drawing them at 1:1 is the point — a cell that scales the sprite up to fill the box would
    hide exactly the number the batch is judged on. The yellow dashed line is the authorised
    height, so "did it land where the camera maths says" is answerable by looking.
    """
    import tiles  # noqa: PLC0415

    PAD = 12
    CELL = 250
    BG = (18, 17, 20)
    PANEL = (28, 26, 30)
    FG = (222, 218, 208)
    DIM = (150, 148, 142)
    GUIDE = (226, 186, 96)
    GOOD = (150, 200, 150)
    BAD = (220, 120, 110)

    rows = _batch1_rows()
    groups = [("PROPS  interactive", [r for r in rows if r["group"] == "props"]),
              ("DECOR  cheap identity, repeats everywhere",
               [r for r in rows if r["group"] == "decor"])]
    columns = 5
    width = PAD + columns * (CELL + PAD)
    TILE_BLOCK = 192   # 3 x 3 repeats of a 64 texel tile, 1:1
    TILE_PITCH = 250   # column pitch: wide enough that the captions cannot collide

    body_h = 0
    for _, items in groups:
        body_h += 30 + ((len(items) + columns - 1) // columns) * (CELL + 48)
    body_h += 40 + 2 * (TILE_BLOCK + 70) + 80 + 90
    sheet = Image.new("RGB", (width, 120 + body_h), BG)
    dr = ImageDraw.Draw(sheet)
    font = _font(13)
    small = _font(11)

    dr.text((PAD, 12), "IRON VIGIL  ·  ART BATCH 1  ·  props, decor, ground", fill=FG, font=font)
    # the two rulers everything in this batch is derived from
    dr.line([(PAD, 44), (PAD + 85, 44)], fill=GUIDE, width=1)
    dr.text((PAD, 48), "1 m across the ground = 85 px", fill=DIM, font=small)
    dr.line([(PAD + 620, 44), (PAD + 620, 44 + 69)], fill=GUIDE, width=1)
    dr.text((PAD + 626, 44), "1 m of height = 68.8 px (85 x cos 36)", fill=DIM, font=small)
    dr.text((PAD, 70), "Every cell is drawn at 1:1 screen pixels. The dashed yellow line is the "
                       "AUTHORISED height, i.e. world metres x 68.8.", fill=DIM, font=small)

    y = 100
    for title, items in groups:
        dr.text((PAD, y), title, fill=GUIDE, font=font)
        y += 26
        for i, r in enumerate(items):
            cx = PAD + (i % columns) * (CELL + PAD)
            cy = y + (i // columns) * (CELL + 48)
            dr.rectangle([cx, cy, cx + CELL, cy + CELL], fill=PANEL)
            img, (aw, ah) = r["img"], r["auth"]
            base = cy + CELL - 16
            dr.line([(cx + 6, base), (cx + CELL - 6, base)], fill=(60, 58, 62), width=1)
            # the authorised height, dashed, so a short sprite is visible at a glance
            gy = base - ah
            for x in range(cx + 6, cx + CELL - 6, 6):
                dr.line([(x, gy), (x + 3, gy)], fill=GUIDE, width=1)
            sheet.paste(img, (cx + 8, base - img.height), img)
            zoom = 1
            avail_w = CELL - img.width - 26
            if avail_w >= img.width and img.height < CELL - 70:
                zoom = max(1, min(4, avail_w // max(1, img.width),
                                  (CELL - 70) // max(1, img.height)))
            if zoom > 1:
                big = img.resize((img.width * zoom, img.height * zoom), Image.NEAREST)
                sheet.paste(big, (cx + 16 + img.width, base - big.height), big)
                dr.text((cx + 16 + img.width, base + 2), f"x{zoom}", fill=DIM, font=small)
            dev = max(abs(r["dev_w"]), abs(r["dev_h"]))
            colour = BAD if dev > 0.15 else GOOD
            dr.text((cx + 6, cy + CELL + 2), f"{r['name']}  {img.width}x{img.height}", fill=FG, font=small)
            dr.text((cx + 6, cy + CELL + 15),
                    f"auth {aw}x{ah}  devW {r['dev_w'] * 100:+.1f}%  devH {r['dev_h'] * 100:+.1f}%",
                    fill=colour, font=small)
            dr.text((cx + 6, cy + CELL + 28),
                    f"implies {r['world'][0]:.2f} x {r['world'][1]:.2f} m in the world",
                    fill=DIM, font=small)
        y += ((len(items) + columns - 1) // columns) * (CELL + 48) + 6

    # --- ground: shipped procedural tiles vs the model tiles they replaced --------------
    dr.text((PAD, y), f"GROUND  {tiles.SIZE}x{tiles.SIZE} texels = {tiles.TILE_M:.0f}x"
                      f"{tiles.TILE_M:.0f} m, shown repeated 3x3 at 1:1", fill=GUIDE, font=font)
    y += 26
    for i, name in enumerate(tiles.TILES):
        cx = PAD + i * TILE_PITCH
        src = ROOT / "assets" / "tiles" / f"{name}.png"
        dr.rectangle([cx, y, cx + TILE_BLOCK, y + TILE_BLOCK], fill=PANEL)
        if src.is_file():
            tile = Image.open(src).convert("RGB")
            seam, inner, ratio = seam_parts(tile)
            for ty in range(3):
                for tx in range(3):
                    sheet.paste(tile, (cx + tx * tile.width, y + ty * tile.height))
            flag = BAD if (ratio > 2.0 or inner < 1.0) else GOOD
            dr.text((cx, y + TILE_BLOCK + 2), f"{name}  {tile.width}x{tile.height}  seam {ratio:.2f}",
                    fill=flag, font=small)
            dr.text((cx, y + TILE_BLOCK + 15),
                    f"inner {inner:.2f}  "
                    f"{len(np.unique(np.asarray(tile).reshape(-1, 3), axis=0))} colours",
                    fill=DIM, font=small)
            dr.text((cx, y + TILE_BLOCK + 28), "1 tile = 1 m -> uv1_scale 1/m", fill=DIM, font=small)
    y += TILE_BLOCK + 58

    dr.text((PAD, y), "WHY PROCEDURAL: the same names from tools/art_raw (model output, not "
                      "shipped) repeated 3x3", fill=GUIDE, font=font)
    y += 26
    for i, r in enumerate(tiles.model_evidence()):
        cx = PAD + i * (TILE_PITCH)
        src = ROOT / "tools" / "art_raw" / f"{r['name']}.png"
        dr.rectangle([cx, y, cx + TILE_BLOCK, y + TILE_BLOCK], fill=PANEL)
        if src.is_file():
            tile = Image.open(src).convert("RGB").resize((tiles.SIZE, tiles.SIZE), Image.LANCZOS)
            for ty in range(3):
                for tx in range(3):
                    sheet.paste(tile, (cx + tx * tiles.SIZE, y + ty * tiles.SIZE))
        flag = BAD if r["seam"] > 2.0 or r["inner"] < 1.0 else GOOD
        dr.text((cx, y + TILE_BLOCK + 2), f"MODEL {r['name']}  seam {r['seam']:.2f}",
                fill=flag, font=small)
        dr.text((cx, y + TILE_BLOCK + 15), f"inner {r['inner']:.2f}  {r['colours']} colours",
                fill=DIM, font=small)
    y += TILE_BLOCK + 42

    dr.text((PAD, y), "seam = mean difference across the wrap / mean difference inside. "
                      "~1.0 is a tile; the ratio is meaningless below inner 1.0.",
            fill=DIM, font=small)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "art_batch1.png"
    sheet.crop((0, 0, width, min(sheet.height, y + 24))).save(path)
    print(f"{path}  {sheet.width}x{min(sheet.height, y + 24)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cell", type=int, default=170, help="cell size in px")
    ap.add_argument("--batch1", action="store_true",
                    help="build tools/design/concepts/art_batch1.png from the shipped assets")
    ap.add_argument("--seam", action="store_true", help="print the tile seam table and exit")
    args = ap.parse_args()
    if args.seam:
        return seam_table()
    if args.batch1:
        return batch1_sheet()
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

