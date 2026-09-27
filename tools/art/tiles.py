"""Procedural, genuinely seamless ground and wall textures.

Why procedural, in one line: style_spec.md §6.1 — "the image model will not draw a quiet
repeating surface", and even when it does, nothing makes the pattern wrap. Measured on this
project's own cached model tiles (tools/art_raw/, zero API cost to re-measure, numbers in the
report):

    model floor_stone   native seam 0.21   <- "passes" only because the surface is almost flat
    model floor_blood   native seam 0.95
    model wall_stone    native seam 2.03   <- FAILS the > 2.0 gate

A procedural tile wraps BY CONSTRUCTION: every feature is placed with a coordinate that is
reduced modulo the tile, including the interpolation of the noise lattice, so the seam error
is ~1.0 for a reason instead of by luck.

Texel density — the choice the Lead asked to have stated explicitly
------------------------------------------------------------------
A tile is **64 x 64 texels and represents 1 x 1 METRE** (option (a) of the two offered).
The game shows one metre of ground as 85 screen pixels, so magnification is:

    option (a): 64 texels / 1 m -> 64 texels per metre -> 85/64 = 1.33x   <-- chosen
    option (b): 64 texels / 2 m -> 32 texels per metre -> 85/32 = 2.66x

Option (b) is the same magnification that 32x32 tiles were rejected for: "64 pixels spread
over 2 metres" is 32 texels per metre, not 1:1 — it re-creates the 2.66x stretch. Option (a)
is the only one of the two that holds 1.33x, and it keeps the slab at a monastery-like 0.5 m:
the floor tile is a 2 x 2 grid of slabs, 32 texels each.

    room_builder.gd: uv1_scale = repeated per metre = 3.5 for a 7 x 7 m room.

Finer paving is a one-number change on the .gd side (uv1_scale = 2 per metre = 0.25 m slabs);
the texture does not change. Ground rules from style_spec §3 are honoured here: 32-48 texels
of detail per metre at most, flat colour, no hatching, a handful of value steps.

Run:
    python tools/art/tiles.py             # write assets/tiles/ + sidecars
    python tools/art/tiles.py --check     # measure only (seam, colour count, determinism)
    python tools/art/build.py --batch1    # props + decor + tiles, one report
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contact  # noqa: E402  (the single seam implementation lives there)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets"
RAW = ROOT / "tools" / "art_raw"

SIZE = 64          # texels per tile
TILE_M = 1.0       # world metres covered by one repeat (option (a), see the module docstring)

# style_spec.md §4 tokens, kept as floats so the noise can move them.
STONE = np.array([106, 102, 92], np.float32)     # Stone    #6A665C
MORTAR = np.array([74, 71, 65], np.float32)      # Mortar   #4A4741
OXBLOOD = np.array([90, 30, 30], np.float32)     # Oxblood  #5A1E1E
WALL = np.array([78, 74, 68], np.float32)        # one step darker than the floor
WALL_JOINT = np.array([55, 52, 48], np.float32)
HIGHLIGHT_CEIL = 235
SHADOW_FLOOR = 8


def _mix(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return a * (1.0 - t) + b * t


# Explicit palettes instead of a rounding step. A ground tile may hold about four value
# steps (style_spec §3) and at most 10 colours (TILE_RULES); rounding each channel to a
# multiple of 6 produced 12 and 59 colours respectively, which is the budget being decided
# by arithmetic instead of by the artist. Each palette below is a deliberate list, and every
# entry is anchored on a §4 token.
FLOOR_PALETTE = [STONE + d for d in (-6.0, -2.0, 2.5, 5.0)] + [MORTAR + d for d in (-2.0, 2.0)]
BLOOD_PALETTE = FLOOR_PALETTE + [
    _mix(STONE, OXBLOOD, 0.30),     # a damp stain edge
    _mix(STONE, OXBLOOD, 0.55),     # old blood on stone
    _mix(MORTAR, OXBLOOD, 0.65),    # blood collected in the joint
]
WALL_PALETTE = ([WALL + d for d in (-4.0, -1.0, 3.0)]
                + [WALL_JOINT, WALL_JOINT + 3.0])


# ---------------------------------------------------------------------------------------
# deterministic periodic noise
# ---------------------------------------------------------------------------------------

def _hash01(x: int, y: int, seed: int) -> float:
    """Deterministic lattice value in [0,1). Hashed rather than drawn from numpy's RNG so
    the tiles are byte-identical on any numpy version."""
    h = (x * 374761393 + y * 668265263 + seed * 1442695040888963407) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _value_noise(cells: int, seed: int) -> np.ndarray:
    """Smooth value noise in [-1,1] that is PERIODIC over the tile.

    Periodic because the lattice indices wrap (`% cells`) and the smoothstep weights are
    continuous: the value at x = SIZE is the value at x = 0 by construction, which is what
    makes the wrap seam invisible rather than merely small.
    """
    lat = np.array([[_hash01(x, y, seed) for x in range(cells)] for y in range(cells)], np.float32)
    step = SIZE / cells
    xs = np.arange(SIZE) / step
    x0 = np.floor(xs).astype(int) % cells
    x1 = (x0 + 1) % cells
    fx = xs - np.floor(xs)
    fx = fx * fx * (3 - 2 * fx)
    out = np.zeros((SIZE, SIZE), np.float32)
    for j in range(SIZE):
        yv = j / step
        y0 = int(yv) % cells
        y1 = (y0 + 1) % cells
        fy = yv - int(yv)
        fy = fy * fy * (3 - 2 * fy)
        row0 = lat[y0][x0] * (1 - fx) + lat[y0][x1] * fx
        row1 = lat[y1][x0] * (1 - fx) + lat[y1][x1] * fx
        out[j] = row0 * (1 - fy) + row1 * fy
    return out * 2.0 - 1.0


def _snap(rgb: np.ndarray, palette: list[np.ndarray]) -> np.ndarray:
    """Snap every pixel to its nearest palette entry.

    Deterministic, keeps the §4 tokens exactly, and makes the colour count a property of the
    palette list rather than of the noise amplitude — which is the only way "at most 10
    colours" stays true when the noise is retuned.
    """
    pal = np.array(palette, np.float32)
    flat = np.clip(rgb, SHADOW_FLOOR, HIGHLIGHT_CEIL)
    dist = ((flat[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(axis=3)
    return pal[np.argmin(dist, axis=2)]


def _wrap_distance(axis: np.ndarray, centre: float) -> np.ndarray:
    """Distance along one axis on a ring of circumference SIZE — a stain can then cross the
    tile edge and come back on the other side, which a plain Euclidean blob cannot."""
    d = np.abs(axis - centre)
    return np.minimum(d, SIZE - d)


def _to_image(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------------------------------
# the tiles
# ---------------------------------------------------------------------------------------

def floor_stone() -> Image.Image:
    """Worn limestone paving: a 2 x 2 grid of 0.5 m slabs (32 texels each).

    The 2-texel mortar joint is centred ON the tile boundary — one texel at x = 0 and one at
    x = 31 — instead of being drawn inside it. A joint drawn inside the tile would put stone
    against mortar across the wrap and the repeat would read as a grid of stickers; centred,
    the joint continues across the seam and the pattern is continuous.
    """
    noise = _value_noise(8, seed=11)
    xs, ys = np.arange(SIZE), np.arange(SIZE)
    slab = 32
    bx = xs % slab
    by = ys % slab
    joint_x = (bx == 0) | (bx == slab - 1)
    joint_y = (by == 0) | (by == slab - 1)
    joint = joint_y[:, None] | joint_x[None, :]

    # four slabs, four value steps: the only "pattern" a 32 px slab may carry (§3)
    tone = np.array([[-6.0, 2.5], [5.0, -2.0]], np.float32)
    slab_tone = tone[(ys // slab) % 2][:, (xs // slab) % 2]
    body = STONE[None, None, :] + slab_tone[:, :, None] + noise[:, :, None] * 3.5

    grout = MORTAR[None, None, :] + noise[:, :, None] * 2.0
    rgb = np.where(joint[:, :, None], grout, body)

    # a few chips: 1-2 texel specks, placed from the hash so the tile stays reproducible
    for i in range(5):
        cx = int(_hash01(i, 1, 3) * SIZE) % SIZE
        cy = int(_hash01(i, 2, 3) * SIZE) % SIZE
        rgb[cy, cx] = MORTAR * 1.05
        if i % 2:
            rgb[(cy + 1) % SIZE, cx] = MORTAR * 1.02
    return _to_image(_snap(rgb, FLOOR_PALETTE))


def floor_blood() -> Image.Image:
    """The same paving with a dried stain creeping along the joints.

    The stain is built from ring-wrapped distances, so it crosses the tile edge and comes
    back without a seam — the difference between "a stain on a floor" and "a stain per tile".
    """
    base = np.asarray(floor_stone(), np.float32)
    xs, ys = np.arange(SIZE, dtype=np.float32), np.arange(SIZE, dtype=np.float32)
    stain = np.zeros((SIZE, SIZE), np.float32)
    for cx, cy, radius, weight in ((32.0, 8.0, 15.0, 1.0), (4.0, 46.0, 11.0, 0.8),
                                   (48.0, 52.0, 9.0, 0.6)):
        dx = _wrap_distance(xs, cx)[None, :]
        dy = _wrap_distance(ys, cy)[:, None]
        r = np.sqrt(dx ** 2 + dy ** 2)
        stain = np.maximum(stain, np.clip(1.0 - r / radius, 0.0, 1.0) ** 1.7 * weight)
    # creep into the mortar lines: the joints are where blood would actually collect.
    # The joints are the dark pixels — their channel sum sits near the mortar token.
    in_joint = base.sum(axis=2) <= MORTAR.sum() + 14
    stain = np.clip(stain + in_joint * stain * 0.5, 0.0, 1.0)
    blend = (stain * 0.7)[:, :, None]
    rgb = base * (1.0 - blend) + OXBLOOD[None, None, :] * blend
    rgb = rgb + _value_noise(6, seed=29)[:, :, None] * 2.0
    return _to_image(_snap(rgb, BLOOD_PALETTE))


def wall_stone() -> Image.Image:
    """Rough-cut ashlar in running bond: 0.5 m blocks (32 texels) in 0.25 m courses.

    32 and 16 both divide 64, and the 16-texel course offset keeps the bond periodic, so the
    wall tiles exactly as the floor does. A step darker than the floor so the room silhouette
    reads without an outline (style_spec §4).
    """
    noise = _value_noise(8, seed=7)
    xs, ys = np.arange(SIZE), np.arange(SIZE)
    course = 16
    blockw = 32
    row = ys // course
    offset = (row % 2) * (blockw // 2)
    bx = (xs[None, :] + offset[:, None]) % blockw
    by = ys % course
    joint = ((bx == 0) | (bx == blockw - 1)) | ((by == 0) | (by == course - 1))[:, None]
    block_id = ((xs[None, :] + offset[:, None]) // blockw) + row[:, None] * 2
    tone = ((block_id % 4).astype(np.float32) - 1.5) * 2.6
    body = WALL[None, None, :] + tone[:, :, None] + noise[:, :, None] * 2.2
    grout = WALL_JOINT[None, None, :] + noise[:, :, None] * 1.4
    rgb = np.where(joint[:, :, None], grout, body)
    # one chipped block corner, wrapped and reproducible
    chip = int(_hash01(5, 9, 4) * SIZE) % SIZE
    rgb[chip, chip] = WALL_JOINT * 1.1
    return _to_image(_snap(rgb, WALL_PALETTE))


TILES: dict[str, object] = {
    "floor_stone": floor_stone,
    "floor_blood": floor_blood,
    "wall_stone": wall_stone,
}


# ---------------------------------------------------------------------------------------
# build + measure
# ---------------------------------------------------------------------------------------

def model_evidence() -> list[dict]:
    """Measure the cached MODEL tiles as the reason procedural wins.

    Not shipped, not deleted: tools/art_raw/floor_stone.png and friends stay exactly where the
    earlier pipeline put them, and their seam number is reported next to the procedural one so
    the decision is auditable rather than asserted.
    """
    rows: list[dict] = []
    for name in TILES:
        src = RAW / f"{name}.png"
        if not src.is_file():
            continue
        img = Image.open(src).convert("RGB")
        native = img.resize((SIZE, SIZE), Image.LANCZOS)
        seam, inner, ratio = contact.seam_parts(native)
        swapped = contact.tileable(img, SIZE)
        seam_s, inner_s, ratio_s = contact.seam_parts(swapped)
        rows.append({
            "name": name, "kind": "model (evidence, not shipped)",
            "seam": ratio, "inner": inner, "swap_seam": ratio_s,
            "colours": len(np.unique(np.asarray(native).reshape(-1, 3), axis=0)),
            "size": f"{img.width}x{img.height} -> {SIZE}x{SIZE}",
        })
    return rows


def build_all(check_only: bool = False) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    problems: list[str] = []
    for name, builder in TILES.items():
        img: Image.Image = builder()  # type: ignore[operator]
        if img.size != (SIZE, SIZE):
            problems.append(f"{name}: built {img.size}, expected {(SIZE, SIZE)}")
        if img.mode != "RGB":
            problems.append(f"{name}: ground tiles must be opaque (mode {img.mode})")
        seam, inner, ratio = contact.seam_parts(img)
        arr = np.asarray(img)
        colours = int(len(np.unique(arr.reshape(-1, 3), axis=0)))
        row = {
            "name": name, "size": f"{SIZE}x{SIZE}", "metres": TILE_M,
            "texels_per_m": SIZE / TILE_M, "magnification": 85.0 / (SIZE / TILE_M),
            "seam": ratio, "seam_raw": seam, "inner": inner, "colours": colours,
            "min": int(arr.min()), "max": int(arr.max()),
            "sha256": hashlib.sha256(arr.tobytes()).hexdigest()[:16],
            "dest": OUT / "tiles" / f"{name}.png",
        }
        if ratio > 2.0:
            problems.append(f"{name}: seam {ratio:.2f} > 2.0 — the repeat will read as a grid")
        if inner < 1.0:
            problems.append(f"{name}: interior variation {inner:.2f} is degenerate — the "
                            "seam ratio means nothing on a flat colour")
        if colours > 10:
            problems.append(f"{name}: {colours} colours > the 10 allowed by TILE_RULES")
        if row["max"] > HIGHLIGHT_CEIL or row["min"] < SHADOW_FLOOR:
            problems.append(f"{name}: value range {row['min']}-{row['max']} leaves the §4 tokens")
        if not check_only:
            row["dest"].parent.mkdir(parents=True, exist_ok=True)
            img.save(row["dest"])
        rows.append(row)

    print_tiles(rows)
    for r in model_evidence():
        print(f"  {r['name']:12s} {r['kind']:26s} {r['size']:24s} seam {r['seam']:5.2f} "
              f"(quadrant-swap {r['swap_seam']:5.2f})  inner {r['inner']:5.2f}")
    return rows, problems


def print_tiles(rows: list[dict]) -> None:
    print(f"\nTILES   {SIZE}x{SIZE} texels = {TILE_M:.0f} x {TILE_M:.0f} m "
          f"({SIZE / TILE_M:.0f} texels/m, shown at {85.0 / (SIZE / TILE_M):.2f}x on screen)")
    print(f"{'tile':14s} {'size':>9s} {'seam':>6s} {'inner':>6s} {'colours':>7s} "
          f"{'value':>9s} {'sha256':>16s}")
    for r in rows:
        print(f"{r['name']:14s} {r['size']:>9s} {r['seam']:6.2f} {r['inner']:6.2f} "
              f"{r['colours']:7d} {str(r['min']) + '-' + str(r['max']):>9s} {r['sha256']:>16s}")


def print_model_evidence() -> None:
    for r in model_evidence():
        print(f"{r['name']:14s} {r['kind']:30s} {r['size']:26s} seam {r['seam']:5.2f} "
              f"(quadrant-swap {r['swap_seam']:5.2f}) inner {r['inner']:5.2f} colours {r['colours']}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="measure only, write nothing")
    args = ap.parse_args(argv)
    rows, problems = build_all(check_only=args.check)
    if not args.check:
        # Local import: props.py loads this file lazily, so there is no cycle at import time.
        import props  # noqa: PLC0415
        for r in rows:
            props.write_import(r["dest"])
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
