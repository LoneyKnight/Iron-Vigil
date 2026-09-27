"""Iron Vigil - camera and pixel-density geometry.

Read this before changing any camera or art number.

The mistake this file exists to prevent
---------------------------------------
The first version of the study assumed a figure "1.85 tiles tall" lands on screen at
1.85 x (a tile's screen size). That is only true for a camera looking straight down. At any
real HD-2D pitch the ground plane and the vertical axis are foreshortened by DIFFERENT
factors, and the engine prototype measured it: at 52 deg pitch a 1.84 m knight projected to
36 px while the spec claimed 59. A spec can therefore not quote one density number for both
"a metre of floor" and "a metre of knight".

The geometry
------------
Let k = screen pixels per metre measured ON THE GROUND PLANE, p = camera pitch.

    a metre of floor, going away from the camera : k * cos(p) px on screen
    a metre of height (a standing figure)        : k * sin(p) px on screen

So a figure of height h metres appears as  h * k * sin(p)  pixels tall, and the visible
ground area is  (VW / k) x (VH / (k * cos p))  metres.

Two honest consequences
-----------------------
1. A human figure is naturally SMALL in this framing. A 1.8 m knight is only 1.8 tiles
   tall at a 1 m tile, so at k = 32 he is ~45 px on screen at 52 deg. You cannot have
   large figures AND many tiles visible at a human scale; you pick.
2. Straight down (p = 90) removes the problem entirely -- sin = 1, cos = 0 -- but then
   walls have no face and the scene is a floor plan. That is the trade the project has to
   make explicitly rather than discover later.

Run:
    python tools/art/camera.py
"""

from __future__ import annotations

import argparse
import math

VIEW = (1920, 1080)

FIGURE_M = 1.80          # a knight, metres, eye-to-floor of a real person scaled to game
TILE_M = 1.00            # one grid tile in metres
ROOM_TILES = 13          # a room is 13x13 tiles


def report(figure_px: float, pitch_deg: float) -> dict:
    p = math.radians(pitch_deg)
    k = figure_px / (FIGURE_M * math.sin(p))       # ground-plane density, px per metre
    tile_px = k * TILE_M
    return {
        "k": k,
        "tile_px": tile_px,
        "room_px": tile_px * ROOM_TILES,
        "tiles_wide": VIEW[0] / tile_px,
        "tiles_deep": VIEW[1] / (tile_px * math.cos(p)),
        "rooms_wide": VIEW[0] / (tile_px * ROOM_TILES),
        "fig_screen_pct": figure_px / VIEW[1] * 100.0,
        "ortho_size": VIEW[1] / (k * math.cos(p)),   # metres of ground, vertically
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pitches", type=float, nargs="*", default=[38.0, 45.0, 52.0])
    ap.add_argument("--figures", type=float, nargs="*", default=[36, 45, 54, 64, 76])
    args = ap.parse_args()

    print(f"viewport {VIEW[0]}x{VIEW[1]}   figure {FIGURE_M} m   tile {TILE_M} m   "
          f"room {ROOM_TILES}x{ROOM_TILES} tiles\n")

    for pitch in args.pitches:
        print(f"=== pitch {pitch:.0f} deg "
              f"(ground foreshortening cos={math.cos(math.radians(pitch)):.3f}, "
              f"height factor sin={math.sin(math.radians(pitch)):.3f}) ===")
        print(f"{'fig px':>7} {'% screen':>9} {'px/tile':>8} {'room px':>8} "
              f"{'tiles x':>8} {'tiles deep':>11} {'rooms x':>8} {'ortho size':>11}")
        for fig in args.figures:
            r = report(fig, pitch)
            print(f"{fig:7.0f} {r['fig_screen_pct']:8.1f}% {r['tile_px']:8.1f} "
                  f"{r['room_px']:8.0f} {r['tiles_wide']:8.1f} {r['tiles_deep']:11.1f} "
                  f"{r['rooms_wide']:8.1f} {r['ortho_size']:10.1f}m")
        print()

    print("How to read it")
    print("  fig px    a knight's height on screen. <36 he is a smear; 45-64 reads as a")
    print("            person; >80 he stops being a figure in a room and becomes the view.")
    print("  tiles x   level on screen horizontally. <20 is claustrophobic, >45 reads as")
    print("            a map instead of a place. 38-46 is the HD-2D band.")
    print("  rooms x   the co-op number: can you see where your partner went.")
    print()
    print("The uncomfortable conclusion, stated plainly:")
    print("  At a human figure scale (1.8 m) with 1 m tiles you CANNOT have both a large")
    print("  knight and a wide view. The levers are (a) accept a smaller figure, (b) make")
    print("  the tile smaller in world metres so rooms contain more tiles, or (c) raise the")
    print("  pitch toward straight-down, which costs the wall faces and the HD-2D look.")
    print()

    # The recommended solve, with the numbers an implementation needs.
    pitch = 45.0
    fig = 54.0
    r = report(fig, pitch)
    print(f"RECOMMENDED SOLVE: pitch {pitch:.0f} deg, knight {fig:.0f} px on screen")
    print(f"  ground-plane density k   : {r['k']:.2f} screen px per metre")
    print(f"  one tile on screen       : {r['tile_px']:.1f} px")
    print(f"  orthographic size        : {r['ortho_size']:.2f} m of ground, vertically")
    print(f"  visible                  : {r['tiles_wide']:.0f} x {r['tiles_deep']:.0f} tiles"
          f" = {r['rooms_wide']:.1f} rooms across")
    print(f"  knight                   : {FIGURE_M:.2f} m world, {fig:.0f} px screen"
          f" = {r['fig_screen_pct']:.1f}% of screen height")
    print(f"  AUTHORING SIZE           : the atlas is drawn for {fig:.0f} px on screen,"
          f" which is what tools/art/build.py must target.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
