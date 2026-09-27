"""Iron Vigil — concept samples.

One place for every prompt. Nothing here writes to assets/: it saves raw model output
into tools/art_raw/ (cached, gitignored) and a review sheet into tools/design/concepts/.

Why the samples are built this way
---------------------------------
The open question for this project is *pixel density*: how many screen pixels does one
tile get, and how tall is a knight on screen. That is not answerable from a pretty
concept image, because a 1024x1024 painting looks the same at every density. So the
density test renders ONE high-resolution source sprite and then composites the same
scene at several densities, with the tiles scaled to match. The only variable is the
density, which is what makes the comparison worth looking at.

Usage:
    python tools/art/samples.py list
    python tools/art/samples.py gen <name> [<name> ...]
    python tools/art/samples.py gen --all
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------------------
# Style anchors. Every prompt carries these; the shared vocabulary is what stops a batch
# from looking like five different artists.
# --------------------------------------------------------------------------------------

PALETTE = (
    "a muted medieval palette of weathered limestone grey, cold iron, deep oxblood red, "
    "rusted bronze, tallow-yellow candlelight, and mossy green, "
    "never saturated, no neon, no pastel"
)

WORLD = (
    "Dark medieval knight-cult atmosphere, a ruined fortified abbey of a militant religious "
    "order, " + PALETTE + ". "
)

# Rendered as a game sprite sheet: hard edges, fixed cell grid, magenta key.
SPRITE_RULES = (
    " Pixel art sprite sheet: 4 columns x 4 rows of 256x256 cells. "
    "Each sprite is drawn at about 128x128 art pixels so the silhouette survives scaling down. "
    "HARD pixel edges, flat solid colours, at most 14 colours, "
    "bold 1px near-black outline, coarse carved hatching ONLY in the deepest shadow. "
    "No anti-aliasing, no gradients, no blur, no dithering, no texture noise, "
    "no fine internal detail, no painterly brush strokes. "
    "Plain solid flat magenta background (#FF00FF) filling every empty area and the gaps "
    "between cells, no grid lines, no text, no labels, no watermark, no drop shadow."
)

# A single object centered in its own cell, still on the magenta key.
PROP_RULES = (
    " Pixel art, ONE object centred on the canvas, hard pixel edges, flat solid colours, "
    "at most 14 colours, bold 1px near-black outline, coarse carved hatching only in the "
    "deepest shadow, no anti-aliasing, no gradients, no blur, no dithering, "
    "no painterly strokes. Plain solid flat magenta background (#FF00FF) filling all empty "
    "space, no text, no labels, no watermark, no drop shadow."
)

# Tiles are their own problem and need their own rules. Asking for a "tile" gets a
# model to paint a little isometric diorama of a floor with candles on it: models have
# seen far more decorative tilesets than seamless ground textures. Say PATTERN, say the
# camera is straight down, and forbid everything that makes it scenery.
TILE_RULES = (
    " A FLAT repeating SURFACE PATTERN, viewed from directly overhead, perfectly "
    "orthographic, camera pointing straight down. The pattern covers the ENTIRE canvas "
    "edge to edge and is COMPLETELY FLAT: no perspective, no horizon, no vanishing point, "
    "no isometric or three-quarter angle, no 3D depth, no objects sitting on the surface, "
    "no rugs, no candles, no debris piles, no single focal point. Low contrast and quiet, "
    "almost flat colour with only the faintest texture. Hard pixel edges, flat solid "
    "colours, at most 10 colours, no anti-aliasing, no gradients, no blur, no dithering, "
    "no painterly brush strokes, no text, no labels, no watermark, no border, "
    "no drop shadow, no magenta."
)

# A full illustration the model paints freely — used for look-dev, not for sprites.
SCENE_RULES = (
    " Painterly pixel-art scene in the style of a modern HD-2D RPG: chunky readable pixel "
    "shapes on a high-detail painted backdrop, strong single-source warm lighting, deep "
    "shadow, subtle depth of field, slight vignette. No text, no UI, no watermark."
)

# --------------------------------------------------------------------------------------
# Camera-angle probes. The angle is the single biggest style decision and the one a
# concept image can settle fastest, so the three candidates are generated as the SAME
# subject from three different cameras. Everything else — palette, subject, era, light —
# is held constant on purpose.
# --------------------------------------------------------------------------------------

CLOISTER_SUBJECT = (
    "A long stone cloister of a militant religious order at night: a row of round arches "
    "down the left, hanging torn banners bearing a faded cross, iron candle sconces on the "
    "pillars, worn flagstones, and a carved stone cross at the far end. Two knights in "
    "weathered plate armour with hooded mail coifs and cross tabards walk down the "
    "corridor side by side, one carrying a lantern; the other has a kite shield on his arm. "
    "A hooded cultist with a curved knife stands half-hidden in the shadow of the third "
    "arch."
)

ANGLE_TOPDOWN = (
    " Camera: looking STRAIGHT DOWN from directly above, absolutely no side view and no "
    "wall height visible; walls are read only as a one-tile-thick band of stone under the "
    "roof. Objects are seen from above. Even ambient light so every tile is legible."
)
ANGLE_ISO = (
    " Camera: an isometric three-quarter view of a cutaway fortress interior, the walls "
    "sliced away at the near side so the room can be seen from a fixed diagonal angle. "
    "Everything drawn on the diagonal."
)
ANGLE_HD2D = (
    " Camera: standing inside the cloister at a low angle, landscape composition, a real "
    "vaulted ceiling and a deep receding colonnade, warm lantern light falling off into "
    "blackness, distant fog."
)

# --------------------------------------------------------------------------------------
# Samples. `cell` is the intended size of one sprite inside the 256 px grid cell.
# --------------------------------------------------------------------------------------

SAMPLES: dict[str, dict] = {
    # --- the knight: the single most density-sensitive asset in the game ---------------
    "knight_idle": {
        "prompt": WORLD + (
            "A knight of a militant religious order standing at rest, seen from a slightly "
            "elevated three-quarter top-down angle, facing down-screen. Weathered plate armour "
            "over a hooded mail coif, a torn tabard bearing a faded cross, a tall kite shield "
            "held low, a broadsword sheathed at the left hip. A small iron lantern hangs from "
            "the belt and casts a warm pool of light on the ground at his feet."
        ) + SPRITE_RULES,
        "note": "hero silhouette; decides the screen height of a player",
    },
    "knight_sheet": {
        "prompt": WORLD + (
            "A knight of a militant religious order, four rows of walk-cycle animation: "
            "row 1 walking toward the camera, row 2 walking left, row 3 walking right, "
            "row 4 walking away from the camera. Seen from a slightly elevated three-quarter "
            "top-down angle. Weathered plate armour, hooded mail coif, torn cross tabard, "
            "kite shield, sword sheathed, iron belt lantern."
        ) + SPRITE_RULES,
        "note": "4x4 walk sheet in the real camera angle",
    },

    # --- tiles: the density question, and the 'tiles must be quiet' lesson -------------
    "floor_stone": {
        # NOTE: "floor slabs" makes the model paint a little room. It has seen far more
        # decorative isometric tilesets than seamless ground textures, so any word that
        # names a *place* pulls it into drawing a place. Describe a MATERIAL instead.
        "prompt": WORLD + (
            "A seamless repeating flat stone texture: worn grey limestone paving in a "
            "regular grid of square slabs about 64 by 64 pixels with thin darker mortar "
            "lines between them. Almost one flat colour, extremely low contrast, no "
            "staining, no pattern motif, no symbols, no lettering."
        ) + TILE_RULES,
        "note": "ground tile; must stay quiet when repeated hundreds of times",
    },
    "floor_blood": {
        "prompt": WORLD + (
            "A seamless repeating flat stone texture: worn grey limestone paving in a "
            "regular grid of square slabs about 64 by 64 pixels, with a thin dried dark "
            "bloodstain creeping along the mortar joints. Extremely low contrast, flat."
        ) + TILE_RULES,
        "note": "damaged/ritual variant",
    },

    # --- architecture: what makes a room read as a medieval abbey ---------------------
    "wall_stone": {
        "prompt": WORLD + (
            "A seamless repeating flat stone texture: rough-cut limestone ashlar blocks "
            "about 64 by 32 pixels, laid in a regular running bond with thin darker mortar "
            "joints. Flat, quiet, even lighting, no perspective."
        ) + TILE_RULES,
        "note": "wall face tile",
    },
    "pillar": {
        "prompt": WORLD + (
            "A single heavy Romanesque stone pillar with a carved capital, seen from a slightly "
            "elevated three-quarter top-down angle, standing on a small stone footing."
        ) + PROP_RULES,
        "note": "architecture prop, blocky silhouette",
    },
    "arch_door": {
        "prompt": WORLD + (
            "A single heavy medieval abbey door of iron-banded oak set in a rounded stone arch, "
            "seen from a slightly elevated three-quarter top-down angle, closed. A small "
            "wrought-iron ring handle and a keyhole plate."
        ) + PROP_RULES,
        "note": "the interaction verb; must read at the smallest size",
    },

    # --- cult furniture: the identity of the place ------------------------------------
    "altar": {
        "prompt": WORLD + (
            "A single stone altar of a militant religious order, seen from a slightly elevated "
            "three-quarter top-down angle: a heavy carved slab on two block supports, twelve "
            "tallow candles burning around a shallow blood channel cut into the top."
        ) + PROP_RULES,
        "note": "ritual centrepiece",
    },
    "candle_rack": {
        "prompt": WORLD + (
            "A single black iron floor rack holding five burning tallow candles, seen from a "
            "slightly elevated three-quarter top-down angle."
        ) + PROP_RULES,
        "note": "the only light source; gameplay-critical readability",
    },
    "reliquary": {
        "prompt": WORLD + (
            "A single gilded reliquary chest with an iron lock and a carved cross on the lid, "
            "seen from a slightly elevated three-quarter top-down angle, closed."
        ) + PROP_RULES,
        "note": "the loot container",
    },
    "banner": {
        "prompt": WORLD + (
            "A single torn heraldic war banner hanging from a crossbar, deep oxblood field with "
            "a weathered white cross, seen from a slightly elevated three-quarter top-down angle."
        ) + PROP_RULES,
        "note": "cheap identity: repeats everywhere, makes rooms feel owned",
    },

    # --- the cult itself --------------------------------------------------------------
    "sigil": {
        "prompt": WORLD + (
            "A single circular occult sigil carved into a stone slab: a ring, an inverted "
            "cross, radiating notches and a few crude runes. Seen from directly above."
        ) + PROP_RULES,
        "note": "floor marker for ritual rooms",
    },
    "cultist": {
        "prompt": WORLD + (
            "A hooded cultist of a militant religious order in a coarse dark robe with a "
            "bloodied hem, holding a curved knife low, face hidden in shadow except for a "
            "pale mask, seen from a slightly elevated three-quarter top-down angle."
        ) + SPRITE_RULES,
        "note": "common enemy; must be distinguishable from the knight in silhouette",
    },
    "penitent": {
        "prompt": WORLD + (
            "A gaunt bare-chested penitent enemy draped in chains and iron hooks, hunched "
            "forward, head wrapped in bloodstained linen, seen from a slightly elevated "
            "three-quarter top-down angle."
        ) + SPRITE_RULES,
        "note": "second enemy archetype: reads as wrong-shaped, not just recoloured",
    },

    # --- look-dev scenes: painted freely, no pixel-density constraint ------------------
    "scene_cloister": {
        "prompt": WORLD + (
            "A cloister corridor of the abbey seen from a slightly elevated three-quarter "
            "top-down angle: rows of round arches, one hooded knight walking away from the "
            "camera carrying a lantern, its warm cone lighting the flagstones ahead while the "
            "rest of the corridor falls into near-black. A carved stone cross stands at the "
            "far end."
        ) + SCENE_RULES,
        "note": "the pitch image: does this look like a game you want to play",
    },
    "scene_ritual": {
        "prompt": WORLD + (
            "A circular ritual chamber deep in the abbey seen from a slightly elevated "
            "three-quarter top-down angle: a carved sigil inlaid in the stone floor, a stone "
            "altar at the centre with twelve burning candles, hooded figures standing in a "
            "ring at the edge of the light, tall shadows thrown up the walls."
        ) + SCENE_RULES,
        "note": "the antagonist fantasy",
    },

    # --- camera-angle probes: same subject, three cameras -----------------------------
    "angle_topdown": {
        "prompt": WORLD + CLOISTER_SUBJECT + ANGLE_TOPDOWN + SCENE_RULES,
        "note": "OPTION A: straight top-down, walls are a band — cheapest, most readable",
    },
    "angle_iso": {
        "prompt": WORLD + CLOISTER_SUBJECT + ANGLE_ISO + SCENE_RULES,
        "note": "OPTION B: isometric three-quarter — most atmospheric, most art work",
    },
    "angle_hd2d": {
        "prompt": WORLD + CLOISTER_SUBJECT + ANGLE_HD2D + SCENE_RULES,
        "note": "OPTION C: HD-2D walk-in view — the Octopath fantasy, 3D scene required",
    },
}


def list_samples() -> None:
    for name, spec in SAMPLES.items():
        print(f"{name:16s} {spec.get('note', '')}")
    print(f"\n{len(SAMPLES)} samples")


def generate_one(name: str, force: bool = False) -> Path:
    spec = SAMPLES[name]
    img = gen.cached(name, spec["prompt"], out_size="1024x1024", force=force)
    path = gen.RAW_DIR / f"{name}.png"
    print(f"{name:16s} {img.size[0]}x{img.size[1]}  {path}")
    return path


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "list":
        list_samples()
        return 0
    if cmd == "gen":
        rest = argv[1:]
        force = "--force" in rest
        rest = [a for a in rest if a != "--force"]
        if not rest or rest == ["--all"]:
            names = list(SAMPLES)
        else:
            unknown = [n for n in rest if n not in SAMPLES]
            if unknown:
                raise SystemExit(f"unknown samples: {unknown}\nsee: python tools/art/samples.py list")
            names = rest
        for name in names:
            generate_one(name, force=force)
        return 0
    raise SystemExit(f"unknown command {cmd!r}\nsee --help")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
