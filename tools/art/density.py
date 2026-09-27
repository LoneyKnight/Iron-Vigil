"""Pixel-density study for Iron Vigil.

The question this answers
------------------------
How many screen pixels should one floor tile get, and how tall should a knight be on
screen? That decides:

  * how much art detail is even visible (a 16 px tile cannot hold a carving),
  * how much of the level fits on screen (and therefore how the game plays),
  * how expensive every future asset is.

It cannot be answered from a concept painting: a 1024x1024 illustration looks identical
at every density. So this script takes the SAME scene and repaints it at several real
densities, at 1:1 with no scaling, and writes them side by side.

How
---
One high-resolution source per asset (tools/art_raw/*.png, 1024 px). Every asset is
downscaled with NEAREST to the exact pixel size it would be authored at, then drawn at
1:1 — so what you see is literally the pixels the game would show. Tiles are generated
procedurally because a diffusion model will not draw a quiet repeating surface.

Run:
    python tools/art/density.py                 # default set
    python tools/art/density.py --tile 32 48    # pick densities
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "tools" / "art_raw"
OUT = ROOT / "tools" / "design" / "concepts"

VIEW_W, VIEW_H = 1920, 1080
MAGENTA = (255, 0, 255)

# Densities to compare: screen pixels per floor tile. 16/24/32/48 covers "Black Room
# shipped this" through "HD-2D territory". Anything above ~48 cannot show more than two
# rooms and stops being a co-op view.
DEFAULT_TILES = [16, 24, 32, 40, 48]

# One floor tile is one world unit, so a knight's height is expressed in tiles. Keeping
# this ratio fixed across densities is the point: only the density changes.
KNIGHT_TILES = 1.85

# Framing: draw ONE room and centre it. The room is the fixed unit of level design, so
# holding it constant makes the density the only variable. Packing the viewport with
# whatever fits would instead vary the framing per density and rig the comparison:
# at 14 px/tile nine rooms fit, at 48 px/tile two do, and neither number is a result —
# they are both consequences of the same screen size.
ROOM_TILES = 13                        # a room is 13x13 tiles, the unit the map is built from


# ---------------------------------------------------------------------------------------
# procedural tiles: a diffusion model paints dioramas, not quiet repeating surfaces
# ---------------------------------------------------------------------------------------

def stone_tile(size: int, seed: int = 7) -> Image.Image:
    """Worn limestone slabs. Deliberately almost flat: a tile repeats hundreds of times
    and any strong motif turns into visible noise (Black Room's spec learned this the
    hard way)."""
    img = Image.new("RGBA", (size, size), (104, 100, 92, 255))
    px = img.load()
    # Deterministic value noise, cells of 1/4 tile.
    rng = seed * 2654435761 & 0xFFFFFFFF
    cells = max(2, size // 4)
    field = [[0] * cells for _ in range(cells)]
    for y in range(cells):
        for x in range(cells):
            rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
            field[y][x] = ((rng >> 16) % 21) - 10
    step = size / cells
    for y in range(size):
        for x in range(size):
            fx, fy = int(x / step), int(y / step)
            n = field[min(fy, cells - 1)][min(fx, cells - 1)]
            base = 100 + n
            px[x, y] = (base + 4, base, base - 8, 255)
    d = ImageDraw.Draw(img)
    # Mortar joints on the tile border: this is what makes slabs read as slabs.
    d.line([(0, 0), (size - 1, 0)], fill=(74, 71, 65, 255))
    d.line([(0, 0), (0, size - 1)], fill=(74, 71, 65, 255))
    if size >= 24:
        d.line([(0, size - 1), (size - 1, size - 1)], fill=(86, 83, 76, 255))
        d.line([(size - 1, 0), (size - 1, size - 1)], fill=(86, 83, 76, 255))
    # A hint of a crack, one pixel wide, only where there is room for it.
    if size >= 24:
        for i in range(size // 3, size // 3 + max(2, size // 4)):
            if i < size:
                px[i, (i * 3) % size] = (80, 77, 71, 255)
    return img


def wall_tile(size: int) -> Image.Image:
    """Cut limestone block face, running bond. Sits above the floor and is a step darker
    so the room silhouette reads without an outline."""
    img = Image.new("RGBA", (size, size), (78, 74, 68, 255))
    px = img.load()
    for y in range(size):
        for x in range(size):
            row_shade = -6 if (y // max(1, size // 2)) % 2 else 0
            v = 76 + row_shade + ((x * 7 + y * 13) % 7) - 3
            px[x, y] = (v + 3, v, v - 5, 255)
    d = ImageDraw.Draw(img)
    half = size // 2
    d.line([(0, half), (size - 1, half)], fill=(55, 52, 48, 255))
    # Vertical joint, offset every other course (running bond).
    d.line([(size // 3, 0), (size // 3, max(0, half - 1))], fill=(55, 52, 48, 255))
    d.line([(2 * size // 3, half), (2 * size // 3, size - 1)], fill=(55, 52, 48, 255))
    d.line([(0, 0), (size - 1, 0)], fill=(52, 50, 46, 255))
    return img


# ---------------------------------------------------------------------------------------
# source sprites
# ---------------------------------------------------------------------------------------

def load_frame(name: str, cell: int = 256, index: int = 0) -> Image.Image | None:
    """Cut one cell out of a generated 4x4 sheet and trim its magenta key."""
    path = RAW / f"{name}.png"
    if not path.is_file():
        return None
    sheet = Image.open(path).convert("RGBA")
    cols, rows = 4, 4
    cw, ch = sheet.width // cols, sheet.height // rows
    r, c = divmod(index, cols)
    cell_img = sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
    return trim_key(cell_img)


def trim_key(img: Image.Image, tolerance: int = 60) -> Image.Image:
    """Drop the magenta background and crop to the remaining silhouette."""
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 255 - tolerance and g < tolerance and b > 255 - tolerance:
                px[x, y] = (0, 0, 0, 0)
    box = img.getbbox()
    return img.crop(box) if box else img


def to_size(img: Image.Image, target_h: int) -> Image.Image:
    """Nearest-neighbour downscale to an exact height. NEAREST is the whole point: it is
    what the game will do, so the study shows real pixels, not a smooth preview."""
    if img.height == target_h:
        return img
    ratio = target_h / img.height
    target_w = max(1, round(img.width * ratio))
    return img.resize((target_w, target_h), Image.NEAREST)


# ---------------------------------------------------------------------------------------
# the composite
# ---------------------------------------------------------------------------------------

def compose(tile: int, knight_src: Image.Image | None, ambient_alpha: int = 150,
            lamp: bool = True) -> Image.Image:
    scene = Image.new("RGBA", (VIEW_W, VIEW_H), (10, 10, 12, 255))
    floor = stone_tile(tile)
    wall = wall_tile(tile)

    room_px = tile * ROOM_TILES
    cols = rows = 1
    margin_x = (VIEW_W - room_px) // 2
    margin_y = (VIEW_H - room_px) // 2

    # Room floors, then a wall band along each room's top edge and left edge, so the
    # 13x13 room grid is visible the way the map draws it.
    for iy in range(rows):
        for ix in range(cols):
            x0 = margin_x + ix * room_px
            y0 = margin_y + iy * room_px
            for yy in range(0, room_px, tile):
                for xx in range(0, room_px, tile):
                    scene.paste(floor, (x0 + xx, y0 + yy))
            for xx in range(0, room_px, tile):
                scene.paste(wall, (x0 + xx, y0))
            for yy in range(0, room_px, tile):
                scene.paste(wall, (x0, y0 + yy))

    # A few props so the room is not an empty plane: two braziers opposite the knight and
    # a reliquary chest. Drawn as flat pixel glyphs; they only need to carry scale.
    def glyph(w: int, h: int, body: tuple, top: tuple) -> Image.Image:
        g = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        d.rectangle([0, 0, w - 1, h - 1], fill=body)
        d.rectangle([0, 0, w - 1, max(0, h // 3)], fill=top)
        return g

    for (gx, gy, gw, gh, body, top) in [
        (0.62, 0.30, 0.55, 0.85, (96, 92, 84), (120, 116, 106)),
        (0.30, 0.62, 0.55, 0.85, (96, 92, 84), (120, 116, 106)),
        (0.72, 0.72, 1.00, 0.55, (108, 78, 44), (172, 138, 72)),
    ]:
        g = glyph(max(2, int(tile * gw)), max(2, int(tile * gh)), body, top)
        scene.alpha_composite(g, (margin_x + int(room_px * gx), margin_y + int(room_px * gy)))

    if knight_src is not None:
        knight = to_size(knight_src, max(6, round(tile * KNIGHT_TILES)))
        # Stand the knight on the room's lower half so both his size and the room read.
        kx = margin_x + room_px // 2 - knight.width // 2
        ky = margin_y + room_px - knight.height - tile
        scene.alpha_composite(knight, (kx, ky))
        # The lantern pool: the only light. Drawn as concentric alpha rings so it stays
        # chunky and shows how much of the room the player actually sees.
        halo = Image.new("RGBA", (VIEW_W, VIEW_H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        cx, cy = margin_x + room_px // 2, margin_y + room_px - tile
        for i in range(14, 0, -1):
            r = int(tile * 0.55 * i)
            hd.ellipse([cx - r, cy - r, cx + r, cy + r],
                       fill=(255, 196, 110, max(3, 30 - i * 2)))
        scene.alpha_composite(halo)

    # Ambient darkening, then the lamp pool punched back on a coarse grid. Doing it as
    # one alpha layer keeps the light chunky and on the tile grid instead of a smooth
    # gradient no pixel-art frame would ever produce.
    #
    # `ambient_alpha` is a STUDY parameter, not a game setting, and the study runs it
    # twice. A study that is only as dark as the shipping game is useless: the whole
    # question is how much tile detail survives at each density, and detail you cannot
    # see cannot be judged. "bright" answers "is the art any good"; "game" answers "can
    # the player read the room".
    if ambient_alpha <= 0 and not lamp:
        return scene.convert("RGB")
    lantern = Image.new("L", (VIEW_W, VIEW_H), ambient_alpha)
    ld = ImageDraw.Draw(lantern)
    if lamp and knight_src is not None:
        # The pool hangs on the knight, wherever he stands.
        cx = margin_x + room_px // 2
        cy = margin_y + room_px - tile
        reach = tile * 4.5
        step = max(8, tile)
        rings = max(3, int(reach / step))
        for i in range(rings, 0, -1):
            r = step * i
            # Inside the pool the room is nearly undarkened; the falloff is steep, which
            # is what makes a lantern feel like a lantern rather than a mood filter.
            level = int(ambient_alpha * (i / rings) ** 1.8)
            ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=level)
        # The knight's own soft glow, so he is not lost at the edge of the pool.
        ld.ellipse([cx - tile, cy - tile, cx + tile, cy + tile], fill=0)
    shade = Image.new("RGBA", (VIEW_W, VIEW_H), (4, 4, 10, 0))
    shade.putalpha(lantern)
    scene.alpha_composite(shade)
    return scene.convert("RGB")


def label(img: Image.Image, text: str, xy: tuple[int, int]) -> None:
    d = ImageDraw.Draw(img)
    x, y = xy
    d.rectangle([x - 6, y - 4, x + 8 * len(text) + 6, y + 16], fill=(0, 0, 0))
    d.text((x, y), text, fill=(255, 230, 170))


def build(tiles: list[int], knight_src: Image.Image | None) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Half-size panels, 2 per row: left = art at full light, right = the same scene at
    # game darkness. Reading the two together is the actual decision.
    pw, ph = VIEW_W // 2, VIEW_H // 2
    sheet = Image.new("RGB", (2 * pw, len(tiles) * ph), (16, 16, 18))
    for row, tile in enumerate(tiles):
        knight_h = max(6, round(tile * KNIGHT_TILES))
        room_px = tile * ROOM_TILES
        for col, (label_txt, alpha) in enumerate([("full light", 0), ("game light", 216)]):
            scene = compose(tile, knight_src, ambient_alpha=alpha)
            panel = scene.resize((pw, ph), Image.LANCZOS)
            head = (f"{tile}px/tile  knight {knight_h}px  room {room_px}px "
                    f"= {room_px / VIEW_W * 100:.0f}% of screen width  |  {label_txt}")
            label(panel, head, (10, 10))
            sheet.paste(panel, (col * pw, row * ph))
        # The 1:1 study is the thing to actually judge pixels from: the sheet is
        # downscaled, so it lies about edges. Save both.
        bright = compose(tile, knight_src, ambient_alpha=0)
        p1 = OUT / f"density_tile{tile:02d}_bright.png"
        bright.save(p1)
        written.append(p1)
        p2 = OUT / f"density_tile{tile:02d}_game.png"
        compose(tile, knight_src, ambient_alpha=216).save(p2)
        written.append(p2)
        print(f"tile {tile:3d}px  knight {knight_h:3d}px  "
              f"room {room_px:4d}px wide = {room_px / VIEW_W * 100:4.1f}% of screen  "
              f"({VIEW_W / room_px:.1f} rooms across)")
    overview = OUT / "density_overview.png"
    sheet.save(overview)
    written.append(overview)
    print(f"\noverview (downscaled, use 1:1 files to judge pixels) -> {overview}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tile", type=int, nargs="*", default=DEFAULT_TILES,
                    help=f"screen pixels per floor tile (default: {DEFAULT_TILES})")
    ap.add_argument("--sprite", default="knight_idle", help="raw sheet to cut the figure from")
    args = ap.parse_args()

    knight = load_frame(args.sprite, index=5)
    if knight is None:
        print(f"WARNING: no {RAW / (args.sprite + '.png')} — tiles only. "
              f"Run: python tools/art/samples.py gen {args.sprite}")
    else:
        print(f"figure source: {args.sprite}  {knight.width}x{knight.height} px after trim\n")

    build(sorted(set(args.tile)), knight)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
