"""Build the batch-1 props and decor at their AUTHORISED screen size, and say so in numbers.

The one number that governs every size here
-------------------------------------------
Iron Vigil draws the world with a real perspective `Camera3D` at -36 deg pitch, so a metre of
world does not map to a constant number of screen pixels (style_spec.md §0/§1.2):

    across the ground (X) .......... 85.0 px per metre          (PPM)
    height (Y) and depth (Z) ....... 85 * cos(36) = 68.8 px/m   (VPPM)

A prop's authored size is therefore DERIVED, never chosen:

    authored_w = world_w_m * 85.0          # a wall-plane object seen from the camera
    authored_h = world_h_m * 68.8

Two planes need two rules, and mixing them is the classic way to ship a 1.5x-too-tall door:

  * `wall`  — a vertical object (door, banner, pillar, wall decor). Width uses PPM, height
              uses VPPM: the sprite is authored in SCREEN space, pre-squashed for the camera.
  * `ground`— a flat decal lying on the floor (the sigil). Both axes use PPM, because the
              camera supplies the vertical squash itself: a 2 m circle is authored 170x170.

Why the deviation table is not a formality
------------------------------------------
The trimmed silhouette is contain-fitted inside the authorised box with its aspect ratio
preserved, and the fit is NOT forced to the height. So when the model hands back an object
whose proportions disagree with the world, the binding axis shows up as a real deviation and
the build fails instead of quietly shipping a squat door. That is the whole check:

    contain-fit -> if the drawing is too wide, width binds and the height lands short

Gates per asset (all reported, all measured, none of them "looks fine"):
    deviation on either axis <= 15%      the task's tolerance
    magenta residue 0                    two definitions, see residue()
    ink pixels > 0                       no empty frames
    raw silhouette not touching the canvas edge   the object is whole, so feet anchoring works
    unique colours <= COLOURS            style_spec §3: props hold a small palette

Numpy is used only as the pixel kernel (the repo's tools already depend on Pillow); nothing
here touches the network. Raw model output is read from tools/art_raw/ and cached, so a
re-run of this file costs zero API calls.

Run:
    python tools/art/props.py                 # build assets/props + assets/decor (+ tiles)
    python tools/art/props.py --check         # measure and report, write nothing
    python tools/art/props.py --only door_closed altar
    python tools/art/build.py --batch1        # same thing, from the pipeline entry point
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "tools" / "art_raw"
OUT = ROOT / "assets"
CONCEPTS = ROOT / "tools" / "design" / "concepts"
REPORT = CONCEPTS / "art_batch1_report.txt"

# --- locked camera maths: change these together with the camera, never alone ---------------
PPM = 85.0                                    # screen px per metre across the ground
PITCH_DEG = 36.0
VPPM = PPM * math.cos(math.radians(PITCH_DEG))  # 68.77 px per metre of height

# --- keying / colour budget -----------------------------------------------------------------
KEY = np.array([255, 0, 255], dtype=np.int16)
KEY_TOL = 110.0        # RGB distance from the key that counts as background
HALO_RG = 45           # tier 2: dark magenta halo (r and b clearly above g) ...
HALO_BG = 40
HALO_G = 90            # ... with almost no green in it, however far from the key it is
FRINGE_PASSES = 3      # anti-aliased key fringe: pinkish pixels touching background
RESIDUE_TOL = 60.0     # "visually magenta" for the residue gate
COLOURS = 16           # <= 14 promised in the prompt + headroom for the 1 px outline
HIGHLIGHT_CEIL = 235   # style_spec §4: never blow to 255
SHADOW_FLOOR = 8       # style_spec §4: the darkest value in the room
MIN_SPECKS = 4         # connected components smaller than this are keying noise
TOLERANCE = 0.15       # the task's deviation tolerance
EDGE_MARGIN = 2        # raw silhouette this close to the canvas edge = possibly cropped

# name -> group, plane, world metres (width, height), note.
# The order is the order of the contact sheet. `wall` and `ground` are defined above.
#
# Where the task table gives a world size (door, chest, altar, pillar height, banner height,
# candle rack height) that number is used verbatim. Where it gives only a HEIGHT, the width
# is an art-side estimate of the object's widest part, and it is stated as such in the note:
# the first pass of this batch measured those widths against the drawings and corrected two
# of them to the value the object's real geometry supports (a 1.5 m floor stand on a 0.5 m
# tripod, a 1.2 m chain on a 0.25 m ring) rather than keeping a guess that made the sprite
# disagree with its own box. Anything listed as "task table" is not adjustable here.
SPECS: dict[str, dict] = {
    "door_closed": {"group": "props", "plane": "wall", "world": (1.6, 2.6),
                    "note": "door, closed - width is door.gd's 1.6 m collision box"},
    "door_open": {"group": "props", "plane": "wall", "world": (1.6, 2.6),
                  "note": "door, open leaf - same 1.6 m box"},
    "chest_closed": {"group": "props", "plane": "wall", "world": (1.0, 0.7),
                     "note": "chest, closed (task table)"},
    "chest_open": {"group": "props", "plane": "wall", "world": (1.0, 0.93),
                   "note": "chest, open (0.7 body + 0.23 raised lid)"},
    "altar": {"group": "props", "plane": "wall", "world": (2.0, 1.1),
              "note": "altar, unlit (task table)"},
    "altar_lit": {"group": "props", "plane": "wall", "world": (2.0, 1.1),
                  "note": "altar, candles lit (task table)"},
    "candle_rack": {"group": "props", "plane": "wall", "world": (0.5, 1.5),
                    "note": "iron floor stand; 1.5 m from the task, 0.5 m = the tripod base"},
    "pillar": {"group": "props", "plane": "wall", "world": (0.9, 3.1),
               "note": "Romanesque pillar; 3.1 m from the task, 0.9 m = capital + footing"},
    "banner": {"group": "props", "plane": "wall", "world": (1.1, 2.2),
               "note": "torn war banner; 2.2 m from the task, 1.1 m = the crossbar"},
    "sigil": {"group": "props", "plane": "ground", "world": (2.0, 2.0),
              "note": "floor decal, authored square 2 x 2 m"},
    "wall_sconce": {"group": "decor", "plane": "wall", "world": (0.28, 0.55),
                    "note": "iron wall sconce; 0.55 m with its candle, 0.28 m back plate + arm"},
    "wall_arch": {"group": "decor", "plane": "wall", "world": (2.0, 2.6),
                  "note": "limestone arch surround, opening keyed out"},
    "rubble": {"group": "decor", "plane": "wall", "world": (0.7, 0.4),
               "note": "broken stone heap"},
    "chain": {"group": "decor", "plane": "wall", "world": (0.25, 1.2),
              "note": "hanging iron chain, widest = the ring at the top"},
    "cobweb": {"group": "decor", "plane": "wall", "world": (0.62, 0.65),
               "note": "corner cobweb, near square on the wall, wider than tall on screen"},
}


def authored(name: str) -> tuple[int, int]:
    """(width, height) in screen px that the world size is authorised to occupy."""
    spec = SPECS[name]
    w_m, h_m = spec["world"]
    h_ppm = PPM if spec["plane"] == "ground" else VPPM
    return round(w_m * PPM), round(h_m * h_ppm)


# ---------------------------------------------------------------------------------------
# pixel kernel
# ---------------------------------------------------------------------------------------

def _dilate(mask: np.ndarray) -> np.ndarray:
    """4-neighbour dilation without wrapping (np.roll would leak across the frame edge)."""
    out = np.zeros_like(mask)
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def key_out(img: Image.Image) -> tuple[Image.Image, np.ndarray]:
    """Replace the magenta key with alpha EVERYWHERE in the frame.

    Not a flood fill from the border, on purpose: the see-through parts of a prop (the arch
    opening, the gap inside a chain link, the spaces between cobweb threads) are enclosed by
    the drawing, and a border fill leaves them magenta. The palette has no magenta in it, so
    keying every matching pixel removes background and nothing else.
    """
    a = np.asarray(img.convert("RGBA"), dtype=np.int16)
    rgb = a[:, :, :3]
    dist = np.sqrt(((rgb.astype(np.float32) - KEY.astype(np.float32)) ** 2).sum(axis=2))
    keyed = dist <= KEY_TOL
    # Tier 2: the model pads the object with a dark magenta halo (measured: rgb 168,11,120
    # sits 161 away from the key, so a distance test alone misses it) and that halo is
    # invisible in the prompt but very visible on screen once the sprite is 48 px tall.
    # Any pixel with a strong red-over-green and blue-over-green split and no green in it is
    # key bleed: the palette is limestone, iron, oxblood, tallow and moss, none of which can
    # produce a shadow with no green in it.
    halo = ((rgb[:, :, 0] - rgb[:, :, 1] > HALO_RG)
            & (rgb[:, :, 2] - rgb[:, :, 1] > HALO_BG)
            & (rgb[:, :, 1] < HALO_G))
    keyed |= halo
    # Tier 3: anti-aliased edge pixels are a mixture of the key and the object; they key out
    # only if they are still recognisably pink AND touch background.
    pink = (rgb[:, :, 0] - rgb[:, :, 1] > 40) & (rgb[:, :, 2] - rgb[:, :, 1] > 40)
    for _ in range(FRINGE_PASSES):
        add = pink & _dilate(keyed) & ~keyed
        if not add.any():
            break
        keyed |= add

    out = a.astype(np.uint8).copy()
    out[:, :, 3] = np.where(keyed, 0, 255)
    return Image.fromarray(out, "RGBA"), keyed


def residue(img: Image.Image) -> tuple[int, int]:
    """(visually magenta, pink-family) visible pixel counts. Both must be 0.

    Two definitions because one is nearly tautological — anything within RESIDUE_TOL of the
    key was already keyed at a wider tolerance. The pink-family count is the honest one: it
    fires on any pixel red-and-blue-dominant pixel, key or not, and the palette has none.
    """
    a = np.asarray(img.convert("RGBA"), dtype=np.int16)
    visible = a[:, :, 3] > 0
    rgb = a[:, :, :3]
    exact = np.sqrt(((rgb.astype(np.float32) - KEY.astype(np.float32)) ** 2).sum(axis=2)) <= RESIDUE_TOL
    pink = (rgb[:, :, 0] - rgb[:, :, 1] > 40) & (rgb[:, :, 2] - rgb[:, :, 1] > 40)
    return int((exact & visible).sum()), int((pink & visible).sum())


def trim(img: Image.Image) -> Image.Image | None:
    a = np.asarray(img.convert("RGBA"))
    ys, xs = np.nonzero(a[:, :, 3] > 0)
    if len(xs) == 0:
        return None
    return img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _resize_premultiplied(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize RGBA without dragging key-coloured RGB into the edge pixels.

    A plain RGBA resize interpolates the colour of fully transparent pixels, so every edge
    picks up a magenta halo that no later keying pass can see (it is a legitimate colour by
    then). Premultiplying first keeps the edge the object's own colour.
    """
    a = np.asarray(img.convert("RGBA"), dtype=np.float32)
    alpha = a[:, :, 3:4] / 255.0
    pm = a.copy()
    pm[:, :, :3] *= alpha
    small = np.asarray(
        Image.fromarray(pm.clip(0, 255).astype(np.uint8), "RGBA").resize(size, Image.LANCZOS),
        dtype=np.float32,
    )
    al = small[:, :, 3:4] / 255.0
    rgb = np.divide(small[:, :, :3], np.maximum(al, 1e-3))
    out = np.zeros_like(small)
    out[:, :, :3] = np.clip(rgb, 0, 255)
    out[:, :, 3:4] = small[:, :, 3:4]
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def harden_alpha(img: Image.Image) -> Image.Image:
    """Pixel art has no semi-transparent pixels: one alpha bit, no soft edges."""
    a = np.asarray(img.convert("RGBA")).copy()
    a[:, :, 3] = np.where(a[:, :, 3] >= 128, 255, 0)
    return Image.fromarray(a, "RGBA")


def drop_specks(img: Image.Image, min_px: int = MIN_SPECKS) -> Image.Image:
    """Delete connected ink islands smaller than min_px.

    Deliberately NOT a morphological opening: these sprites are made of 1 px lines (cobweb
    threads, chain links) and an erode-then-dilate pass erases the whole object.
    """
    a = np.asarray(img.convert("RGBA"))
    alpha = a[:, :, 3] > 0
    h, w = alpha.shape
    seen = np.zeros_like(alpha)
    keep = alpha.copy()
    for y0 in range(h):
        for x0 in range(w):
            if not alpha[y0, x0] or seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            comp: list[tuple[int, int]] = []
            while stack:
                y, x = stack.pop()
                comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(comp) < min_px:
                for y, x in comp:
                    keep[y, x] = False
    if keep.all():
        return img
    out = a.copy()
    out[:, :, 3] = np.where(keep, out[:, :, 3], 0)
    return Image.fromarray(out, "RGBA")


def quantise(img: Image.Image, colours: int = COLOURS) -> Image.Image:
    """Hard palette reduction. §7: quantisation is the LAST colour operation on an asset."""
    a = np.asarray(img.convert("RGBA"))
    visible = a[:, :, 3] > 0
    if not visible.any():
        return img
    flat = img.convert("RGB").quantize(colors=colours, method=Image.MEDIANCUT, dither=Image.NONE)
    out = np.asarray(flat.convert("RGB"), dtype=np.uint8)
    rgba = np.dstack([out, a[:, :, 3]])
    return Image.fromarray(rgba, "RGBA")


def clamp_tokens(img: Image.Image) -> Image.Image:
    """Hold the §4 value tokens: highlights never reach 255, shadow never below 8.

    The dark end is a lift, not a clip: anything below the floor is scaled up so it keeps its
    hue. Pure black has no hue to scale, and the first version of this left it black (measured
    on disk: darkest luma 0 in 11 of 15 sprites) — so a luma-0 pixel is set to the floor
    directly, and the target is the floor + 1 so uint8 rounding cannot land below it.
    """
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    visible = a[:, :, 3] > 0
    rgb = np.minimum(a[:, :, :3], HIGHLIGHT_CEIL)
    luma = rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114
    lift = visible & (luma < SHADOW_FLOOR)
    if lift.any():
        target = SHADOW_FLOOR + 1
        scale = np.where(luma > 1e-3, target / np.maximum(luma, 1e-3), 1.0)
        rgb[lift] = np.clip(rgb[lift] * scale[lift][:, None], 0, HIGHLIGHT_CEIL)
        black = lift & (luma <= 1e-3)
        if black.any():
            rgb[black] = target
    a[:, :, :3] = rgb
    return Image.fromarray(a.astype(np.uint8), "RGBA")


# ---------------------------------------------------------------------------------------
# import files
# ---------------------------------------------------------------------------------------

IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://{uid}"
path="res://.godot/imported/{file}-{md5}.ctex"
metadata={{
"vram_texture": false
}}

[deps]

source_file="res://{rel}"
dest_files=["res://.godot/imported/{file}-{md5}.ctex"]

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/uastc_level=0
compress/rdo_quality_loss=0.0
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""

_UID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def _uid_for(rel: str) -> str:
    """Deterministic uid from the resource path: same asset -> same uid, run to run."""
    digest = hashlib.sha1(("iron-vigil/" + rel).encode()).digest()
    return "".join(_UID_ALPHABET[b % len(_UID_ALPHABET)] for b in digest[:12])


def write_import(path: Path, keep_uid: bool = True) -> None:
    """Write the .import sidecar Godot expects.

    The ctex path is md5(source resource path) — verified against the sidecars already in the
    repo, so the metadata is correct before the first import. Godot creates the .ctex itself
    on the next import run.

    `detect_3d/compress_to=0` is deliberate and differs from the older sidecars in this repo:
    these textures are used on quads inside a 3D scene, and the default (1) lets Godot swap
    them for a VRAM-compressed variant on first 3D use, which would visibly mangle pixel art.
    """
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    res = "res://" + rel
    md5 = hashlib.md5(res.encode()).hexdigest()
    uid = _uid_for(rel)
    imp = path.with_name(path.name + ".import")
    if keep_uid and imp.is_file():
        for line in imp.read_text(encoding="utf-8").splitlines():
            if line.startswith("uid="):
                uid = line.split("=", 1)[1].strip().strip('"').replace("uid://", "")
                break
    imp.write_text(
        IMPORT_TEMPLATE.format(uid=uid, file=path.name, md5=md5, rel=rel),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------
# state variants
#
# A prop with two states must not change SIZE when it changes state: the lit altar and the
# unlit altar are the same 2.0 x 1.1 m object, and if the two drawings disagree on the
# silhouette the altar visibly jumps the moment it is lit. The model does not know that, and
# its second drawing came back in a raking perspective (measured: 959x703, aspect 1.36,
# against the box's 2.24 -> -38.8% width) while the first is a flat elevation (2.01 -> -10%).
#
# So the lit state is DERIVED from the accepted unlit sprite instead of being drawn beside it:
# same silhouette by construction, plus candle flames placed on the slab's top surface. The
# flames are procedural on purpose -- at 76 px tall a candle is three pixels, which is below
# what the model can place reliably and well inside what a palette can say.
# ---------------------------------------------------------------------------------------

DERIVED: dict[str, dict] = {
    "altar_lit": {"base": "altar", "candles": 9},
}

CANDLE_WAX = (226, 214, 184)   # tallow, light
CANDLE_FLAME = (255, 200, 120)  # style_spec §4 Tallow, clamped to 235 on the way out
CANDLE_EMBER = (232, 150, 70)


def draw_candles(img: Image.Image, count: int) -> Image.Image:
    """Stand `count` burning candles on the top surface of a slab-shaped sprite.

    The top surface is found per column (the first ink row), and the candle is drawn INSIDE
    the existing silhouette: a two-pixel wax stub with a two-pixel flame above it. Drawing
    them above the top edge would grow the sprite and put the two states back out of step.
    """
    out = img.copy()
    px = out.load()
    a = np.asarray(out)
    ink = a[:, :, 3] > 0
    w, h = out.size
    span = np.nonzero(ink.any(axis=0))[0]
    if len(span) == 0:
        return out
    left, right = int(span[0]), int(span[-1])
    inner = left + max(2, (right - left) // 12)
    usable = max(1, right - inner - 2)
    for i in range(count):
        x = inner + round(usable * (i + 0.5) / count)
        column = np.nonzero(ink[:, x])[0]
        if len(column) == 0:
            continue
        top = int(column[0])
        # flame, then wax, both inside the silhouette
        if top + 2 < h:
            px[x, top] = CANDLE_FLAME
            px[min(x + 1, w - 1), top] = CANDLE_EMBER
            px[x, top + 1] = CANDLE_FLAME
            for dy in (2, 3, 4):
                if top + dy < h:
                    px[x, top + dy] = CANDLE_WAX
                    if x + 1 < w:
                        px[x + 1, top + dy] = CANDLE_WAX
            if x + 1 < w and top + 1 < h:
                px[x + 1, top + 1] = CANDLE_FLAME
    return out


def _from_raw(name: str) -> tuple[Image.Image | None, dict, list[str]]:
    """Key, check and contain-fit one raw generation. No palette work, no writing."""
    problems: list[str] = []
    aw, ah = authored(name)
    src = RAW / f"{name}.png"
    info: dict = {}
    if not src.is_file():
        return None, info, [f"{name}: missing raw {src} -- run: python tools/art/samples.py gen {name}"]

    raw = Image.open(src).convert("RGBA")
    info["raw"] = f"{raw.width}x{raw.height}"
    keyed, _ = key_out(raw)

    # "whole object in frame": a silhouette that touches the canvas edge was cropped by the
    # model, and a cropped prop cannot be anchored by its feet.
    box = keyed.getbbox()
    if box is None:
        return None, info, [f"{name}: nothing survived keying (raw is all magenta)"]
    x0, y0, x1, y1 = box
    info["raw_ink"] = f"{x1 - x0}x{y1 - y0}"
    info["clipped"] = (x0 <= EDGE_MARGIN or y0 <= EDGE_MARGIN
                       or x1 >= raw.width - EDGE_MARGIN or y1 >= raw.height - EDGE_MARGIN)
    if info["clipped"]:
        problems.append(
            f"{name}: raw silhouette touches the canvas edge -> object may be cropped; "
            "a cropped prop floats when it is anchored by its base"
        )

    ink = trim(keyed)
    assert ink is not None
    k = min(aw / ink.width, ah / ink.height)
    info["scale"] = k
    resized = harden_alpha(_resize_premultiplied(
        ink, (max(1, round(ink.width * k)), max(1, round(ink.height * k)))))
    resized = drop_specks(resized)
    built = trim(resized)
    if built is None:
        return None, info, [f"{name}: empty after downscale"]
    return built, info, problems


def build_one(name: str) -> tuple[dict, list[str]]:
    """Key, fit, quantise and measure one prop. Returns (row, problems)."""
    problems: list[str] = []
    aw, ah = authored(name)
    group = SPECS[name]["group"]
    row: dict = {"name": name, "group": group, "auth_w": aw, "auth_h": ah, "note": SPECS[name]["note"]}

    variant = DERIVED.get(name)
    if variant:
        base = variant["base"]
        if authored(base) != (aw, ah):
            problems.append(f"{name}: derived from {base}, whose box {authored(base)} differs")
        built, info, probs = _from_raw(base)
        problems += probs
        if built is None:
            row["error"] = f"base {base} failed"
            return row, problems
        built = draw_candles(built, variant["candles"])
        row["raw"] = f"derived from {base} {info.get('raw', '?')}"
        row["raw_ink"] = info.get("raw_ink", "?")
        row["scale"] = info.get("scale", 0.0)
        row["clipped"] = info.get("clipped", False)
        row["derived_from"] = base
    else:
        built, info, probs = _from_raw(name)
        problems += probs
        if built is None:
            row["error"] = "no raw" if "missing raw" in " ".join(probs) else "empty"
            return row, problems
        row.update(info)

    built = quantise(built, COLOURS)
    built = clamp_tokens(built)

    row["w"], row["h"] = built.width, built.height
    row["dev_w"] = (built.width - aw) / aw
    row["dev_h"] = (built.height - ah) / ah
    row["dev_max"] = max(abs(row["dev_w"]), abs(row["dev_h"]))
    row["ink_frac"] = float((np.asarray(built)[:, :, 3] > 0).mean())

    exact, pink = residue(built)
    row["residue"] = (exact, pink)
    a = np.asarray(built.convert("RGBA"))
    visible = a[:, :, 3] > 0
    row["colours"] = int(len(np.unique(a[:, :, :3][visible].reshape(-1, 3), axis=0))) if visible.any() else 0
    luma = a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114
    row["min"] = int(luma[visible].min()) if visible.any() else 0   # §4 shadow floor
    row["max"] = int(a[:, :, :3][visible].max()) if visible.any() else 0  # §4 highlight ceiling

    # Two different things, kept apart on purpose:
    #   HEIGHT is the acceptance number. It is what the locked camera maths fixes, and a
    #     drawing too wide to reach it is a failure of the asset.
    #   WIDTH is the art/world agreement number. A narrow drawing still lands at exactly the
    #     authorised height, but the sprite will not fill its collision box horizontally; that
    #     is a warning with a number attached, not a silent pass and not a build failure.
    row["warn"] = []
    if abs(row["dev_h"]) > TOLERANCE:
        problems.append(
            f"{name}: HEIGHT deviation {row['dev_h'] * 100:+.1f}% "
            f"(authored {aw}x{ah}, built {built.width}x{built.height}) -- the drawing is wider "
            "than its box, so width binds and the sprite cannot reach the authorised height"
        )
    if abs(row["dev_w"]) > TOLERANCE:
        dw, dh = drawn_world(row)
        row["warn"].append(
            f"{name}: width deviation {row['dev_w'] * 100:+.1f}% -- drawn {dw:.2f} m wide "
            f"against a {SPECS[name]['world'][0]:.2f} m box; the sprite will not fill its "
            "collision box horizontally (height is exact)"
        )
    if exact or pink:
        problems.append(f"{name}: magenta residue exact={exact} pink={pink}")
    if row["colours"] > COLOURS:
        problems.append(f"{name}: {row['colours']} colours > budget {COLOURS}")
    if row["colours"] == 0:
        problems.append(f"{name}: empty frame (no ink pixels)")

    dest = OUT / group / f"{name}.png"
    row["dest"] = dest
    row["_img"] = built
    return row, problems


def build_props(check_only: bool = False, only: list[str] | None = None) -> tuple[list[dict], list[str]]:
    names = [n for n in SPECS if not only or n in only]
    rows: list[dict] = []
    problems: list[str] = []
    for name in names:
        row, probs = build_one(name)
        rows.append(row)
        problems += probs
        if not check_only and row.get("_img") is not None and "error" not in row:
            dest: Path = row["dest"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            row["_img"].save(dest)
            write_import(dest)
    return rows, problems


def drawn_world(row: dict) -> tuple[float, float]:
    """The world size the DELIVERED sprite implies, in metres, on each axis.

    The height is the exact one the camera maths asked for. The width is whatever the drawing's
    own proportions produce, which is the number the Lead needs when placing the sprite: a
    sprite narrower than its collision box leaves a gap, and no amount of scaling fixes that
    without stretching the art.
    """
    spec = SPECS[row["name"]]
    return (row["w"] / PPM,
            row["h"] / (PPM if spec["plane"] == "ground" else VPPM))


def print_table(rows: list[dict]) -> None:
    print(f"\nAUTHORISED vs BUILT   (85 px/m across, {VPPM:.1f} px/m up, tolerance +-{TOLERANCE:.0%})")
    print(f"{'asset':14s} {'auth':>9s} {'built':>9s} {'devW':>7s} {'devH':>7s} "
          f"{'raw ink':>10s} {'scale':>6s} {'col':>4s} {'res':>4s} {'ink%':>5s}  note")
    for r in rows:
        if "error" in r:
            print(f"{r['name']:14s} {r['auth_w']:4d}x{r['auth_h']:<4d} {'--':>9s}   {r['error']}")
            continue
        exact, pink = r["residue"]
        flag = "  <-- FAIL" if r["dev_max"] > TOLERANCE else ""
        print(f"{r['name']:14s} {r['auth_w']:4d}x{r['auth_h']:<4d} {r['w']:4d}x{r['h']:<4d} "
              f"{r['dev_w'] * 100:+6.1f}% {r['dev_h'] * 100:+6.1f}% {r['raw_ink']:>10s} "
              f"{r['scale']:6.3f} {r['colours']:4d} {exact + pink:4d} {r['ink_frac'] * 100:4.0f}%"
              f"  {r['note']}{flag}")

    built = [r for r in rows if "error" not in r]
    height_bad = [r for r in built if abs(r["dev_h"]) > TOLERANCE]
    width_bad = [r for r in built if abs(r["dev_w"]) > TOLERANCE]
    print(f"\nheight gate (the acceptance table, world height x {VPPM:.1f}): "
          f"{len(built) - len(height_bad)}/{len(built)} within +-{TOLERANCE:.0%}")
    print(f"width  gate (does the drawing fill its box):                    "
          f"{len(built) - len(width_bad)}/{len(built)} within +-{TOLERANCE:.0%}")
    for r in width_bad:
        dw, dh = drawn_world(r)
        bw, bh = SPECS[r["name"]]["world"]
        print(f"  {r['name']:14s} drawn {dw:.2f} m wide vs a {bw:.2f} m box "
              f"({dw - bw:+.2f} m) - the sprite will not fill its collision box horizontally")


def write_report(rows: list[dict], problems: list[str], tile_rows: list[dict] | None = None,
                 warnings: list[str] | None = None) -> None:
    CONCEPTS.mkdir(parents=True, exist_ok=True)
    lines = [
        "Iron Vigil - art batch 1 - prop and decor size report",
        "=" * 72,
        "",
        "Derivation (style_spec.md §0/§1.2, camera pitch -36 deg):",
        f"  screen px per metre across the ground : {PPM:.1f}",
        f"  screen px per metre of height         : {PPM:.1f} * cos({PITCH_DEG:.0f} deg) = {VPPM:.2f}",
        "  wall-plane object : width = world_w * {:.1f}, height = world_h * {:.2f}".format(PPM, VPPM),
        "  ground decal      : both axes = world * {:.1f} (the camera squashes it)".format(PPM),
        "",
        "Fit: trimmed silhouette contain-fitted inside the authorised box, aspect preserved.",
        "The height is NOT forced, so a drawing with the wrong proportions shows up as a",
        "deviation on the axis that binds.",
        "",
        f"{'asset':14s} {'plane':>6s} {'world m':>11s} {'authored':>9s} {'built':>9s} "
        f"{'devW':>7s} {'devH':>7s} {'colours':>7s} {'residue':>7s}",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"{r['name']:14s} {'?':>6s} {'?':>11s} {r['auth_w']:4d}x{r['auth_h']:<4d} "
                         f"{'--':>9s}  {r['error']}")
            continue
        spec = SPECS[r["name"]]
        w_m, h_m = spec["world"]
        exact, pink = r["residue"]
        lines.append(
            f"{r['name']:14s} {spec['plane']:>6s} {w_m:5.2f}x{h_m:<5.2f} "
            f"{r['auth_w']:4d}x{r['auth_h']:<4d} {r['w']:4d}x{r['h']:<4d} "
            f"{r['dev_w'] * 100:+6.1f}% {r['dev_h'] * 100:+6.1f}% {r['colours']:7d} "
            f"{exact + pink:7d}"
        )
    lines += [
        "",
        "Per-asset detail",
        "-" * 72,
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"{r['name']}: {r['error']}")
            continue
        dw, dh = drawn_world(r)
        bw, bh = SPECS[r["name"]]["world"]
        lines.append(
            f"{r['name']}: raw {r['raw']} -> ink {r['raw_ink']} -> built {r['w']}x{r['h']} px "
            f"(scale {r['scale']:.3f}, ink {r['ink_frac'] * 100:.0f}% of the box, "
            f"darkest luma {r['min']} / brightest channel {r['max']}, clipped={r['clipped']})"
        )
        lines.append(
            f"    implies {dw:.2f} x {dh:.2f} m in the world, against a {bw:.2f} x {bh:.2f} m box"
            f"  ({dw - bw:+.2f} m wide, {dh - bh:+.2f} m tall)"
        )
    if tile_rows:
        tiles = _load_tiles()
        lines += [
            "",
            "GROUND TILES (procedural — style_spec §6.1)",
            "-" * 72,
            f"  {tiles.SIZE}x{tiles.SIZE} texels = {tiles.TILE_M:.0f}x{tiles.TILE_M:.0f} m  ->  "
            f"{tiles.SIZE / tiles.TILE_M:.0f} texels per metre, shown at "
            f"{85.0 / (tiles.SIZE / tiles.TILE_M):.2f}x on screen  (option (a), see tiles.py)",
            "  room_builder.gd: uv1_scale = repeats per metre = 3.5 for a 7 x 7 m room",
            "",
            f"{'tile':14s} {'size':>9s} {'seam':>6s} {'inner':>6s} {'colours':>7s} "
            f"{'value':>9s} {'sha256':>16s}",
        ]
        for r in tile_rows:
            lines.append(f"{r['name']:14s} {r['size']:>9s} {r['seam']:6.2f} {r['inner']:6.2f} "
                         f"{r['colours']:7d} {str(r['min']) + '-' + str(r['max']):>9s} "
                         f"{r['sha256']:>16s}")
        lines += ["", "  MODEL EVIDENCE (tools/art_raw, cached, NOT shipped):",
                  f"  {'tile':12s} {'seam':>6s} {'inner':>6s} {'swap':>6s} {'colours':>7s}"]
        for r in tiles.model_evidence():
            lines.append(f"  {r['name']:12s} {r['seam']:6.2f} {r['inner']:6.2f} "
                         f"{r['swap_seam']:6.2f} {r['colours']:7d}")
    lines += [
        "",
        f"Gate (HEIGHT, the acceptance table): deviation <= {TOLERANCE:.0%}, residue 0, "
        f"colours <= {COLOURS}, ink > 0, raw silhouette inside the frame.",
        "  The height is what the locked camera maths fixes (world_m * "
        f"{VPPM:.2f}), and a drawing too wide to reach it FAILS the build.",
        f"Gate (WIDTH): reported, not gated -- a drawing narrower than its box still lands at",
        "  exactly the authorised height, but leaves a horizontal gap in its collision box.",
        "Gate (tiles): seam <= 2.0 and interior variation >= 1.0; measured at native size.",
        "RESULT: " + ("PASS" if not problems else f"{len(problems)} PROBLEM(S)")
        + (f", {len(warnings)} width warning(s)" if warnings else ""),
    ]
    if warnings:
        lines += ["", "Width warnings"] + [f"  - {w}" for w in warnings]
    if problems:
        lines += [""] + [f"  - {p}" for p in problems]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport  {REPORT}")


def build_batch1(check_only: bool = False, only: list[str] | None = None) -> int:
    """Props + decor + procedural tiles, one table and one report."""
    tiles = _load_tiles()
    rows, problems = build_props(check_only=check_only, only=only)
    print_table(rows)
    tile_rows, tile_problems = tiles.build_all(check_only=check_only)
    if not check_only:
        for r in tile_rows:
            write_import(r["dest"])
    problems += tile_problems
    warnings = [w for r in rows for w in r.get("warn", [])]
    if warnings:
        print("\nWARNINGS (measured, not hidden: the sprite is narrower than its box)")
        for w in warnings:
            print(f"  - {w}")
    if problems:
        print("\nPROBLEMS (fix these; do not paper over them):")
        for p in problems:
            print(f"  - {p}")
    write_report(rows, problems, tile_rows, warnings)
    return 1 if problems else 0


def _load_tiles():
    spec = importlib.util.spec_from_file_location("tiles", Path(__file__).with_name("tiles.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_shipped(only: list[str] | None = None) -> int:
    """Re-measure the files in assets/ — the acceptance numbers, taken off disk.

    Deliberately separate from `--check`: that one measures the raws on their way through the
    pipeline, this one opens the shipped PNGs and its sidecars and re-derives every gate. If
    the two ever disagree, the written asset is not the asset that was measured.
    """
    problems: list[str] = []
    print(f"\nVERIFY (reading assets/, not raws)   tolerance +-{TOLERANCE:.0%}")
    print(f"{'asset':14s} {'auth':>9s} {'on disk':>9s} {'devW':>7s} {'devH':>7s} "
          f"{'colours':>7s} {'residue':>7s} {'ink':>9s} {'range':>9s}  sidecar")
    for name, spec in SPECS.items():
        if only and name not in only:
            continue
        dest = OUT / spec["group"] / f"{name}.png"
        aw, ah = authored(name)
        if not dest.is_file():
            problems.append(f"{name}: missing {dest}")
            continue
        img = Image.open(dest).convert("RGBA")
        sidecar = dest.with_name(dest.name + ".import")
        a = np.asarray(img)
        visible = a[:, :, 3] > 0
        exact, pink = residue(img)
        colours = int(len(np.unique(a[:, :, :3][visible].reshape(-1, 3), axis=0))) if visible.any() else 0
        # §4 tokens are about VALUE, not about a single channel: the shadow floor is the
        # darkest luma in the room and the highlight ceiling is the brightest channel.
        luma = (a[:, :, 0] * 0.299 + a[:, :, 1] * 0.587 + a[:, :, 2] * 0.114)
        lo = int(luma[visible].min()) if visible.any() else 0
        hi = int(a[:, :, :3][visible].max()) if visible.any() else 0
        dev_w = (img.width - aw) / aw
        dev_h = (img.height - ah) / ah
        ok = "ok" if sidecar.is_file() else "MISSING"
        print(f"{name:14s} {aw:4d}x{ah:<4d} {img.width:4d}x{img.height:<4d} "
              f"{dev_w * 100:+6.1f}% {dev_h * 100:+6.1f}% {colours:7d} {exact + pink:7d} "
              f"{int(visible.sum()):9d} {str(lo) + '-' + str(hi):>9s}  {ok}")
        if exact or pink:
            problems.append(f"{name}: magenta residue on disk exact={exact} pink={pink}")
        if not visible.any():
            problems.append(f"{name}: empty frame on disk")
        if colours > COLOURS:
            problems.append(f"{name}: {colours} colours on disk > {COLOURS}")
        if hi > HIGHLIGHT_CEIL or lo < SHADOW_FLOOR:
            problems.append(f"{name}: darkest luma {lo} / brightest channel {hi} leaves the "
                            f"§4 tokens (floor {SHADOW_FLOOR}, ceiling {HIGHLIGHT_CEIL})")
        if abs(dev_h) > TOLERANCE:
            problems.append(f"{name}: height deviation on disk {dev_h * 100:+.1f}%")
        if not sidecar.is_file():
            problems.append(f"{name}: missing .import sidecar")

    tiles = _load_tiles()
    print(f"\n{'tile':14s} {'size':>9s} {'seam':>6s} {'inner':>6s} {'colours':>7s} "
          f"{'mode':>6s}  sidecar")
    for name in tiles.TILES:
        dest = OUT / "tiles" / f"{name}.png"
        if not dest.is_file():
            problems.append(f"tile {name}: missing {dest}")
            continue
        img = Image.open(dest)
        seam, inner, ratio = tiles.contact.seam_parts(img.convert("RGB"))
        colours = int(len(np.unique(np.asarray(img.convert("RGB")).reshape(-1, 3), axis=0)))
        sidecar = dest.with_name(dest.name + ".import")
        print(f"{name:14s} {img.width:4d}x{img.height:<4d} {ratio:6.2f} {inner:6.2f} "
              f"{colours:7d} {img.mode:>6s}  {'ok' if sidecar.is_file() else 'MISSING'}")
        if (img.width, img.height) != (tiles.SIZE, tiles.SIZE):
            problems.append(f"tile {name}: {img.size} != {tiles.SIZE}")
        if ratio > 2.0 or inner < 1.0:
            problems.append(f"tile {name}: seam {ratio:.2f} / inner {inner:.2f} out of gate")
        if img.mode != "RGB":
            problems.append(f"tile {name}: mode {img.mode}, ground tiles must be opaque")
        if not sidecar.is_file():
            problems.append(f"tile {name}: missing .import sidecar")

    print("\nVERIFY " + ("PASS" if not problems else f"{len(problems)} PROBLEM(S)"))
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="measure and report, write nothing")
    ap.add_argument("--verify", action="store_true",
                    help="re-measure the shipped files in assets/ (independent of the build)")
    ap.add_argument("--only", nargs="*", default=None, help="subset of asset names")
    args = ap.parse_args(argv)
    if args.verify:
        return verify_shipped(only=args.only)
    return build_batch1(check_only=args.check, only=args.only)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
