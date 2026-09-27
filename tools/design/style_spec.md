# Iron Vigil · Style Spec v1

> **Read this before touching art, camera or render settings.**
> Every number here is a decision, not a default. Black Room shipped five visual languages
> and a character that was never displayed 1:1 because these numbers were never fixed;
> this file exists so that cannot happen again.

## 0. The four locked numbers

| # | Quantity | Value | Why |
|---|---|---|---|
| 1 | Screen pixels per floor tile | **32 px** | player reads the room; 4.6 rooms across a 1920 view |
| 2 | Knight height on screen | **59 px** = 1.85 tiles | large enough to read armour, small enough to be a person in a room |
| 3 | Game pixel : screen pixel | **1 : 1** | the atlas is authored at exactly the size the game shows |
| 4 | Reference resolution | **1920 × 1080** | the screen the art is budgeted against |

**Corollary — and the whole point of choosing HD-2D:** the world is drawn by a real
`Camera3D`, so a sprite's apparent size comes from 3D perspective, not from a CanvasItem
`zoom`. There is no fractional-zoom shimmer to avoid, and `pixel_size` maps texels to
world metres directly. This removes an entire class of bugs that a 2D canvas camera has:
the character is always exactly the size the atlas was authored at.

## 1. Camera setup

| Parameter | Value | Note |
|---|---|---|
| Type | `Camera3D`, perspective | |
| Pitch | **−52°** | HD-2D read: enough height for a room, enough angle to see faces |
| FOV | **34°** | narrow on purpose: keeps the pixel scale uniform across the frame |
| Distance to subject | **7.5 m** | derived: at 34° FOV the vertical span is ≈ 4.6 m |
| Yaw | fixed (no rotation) | the level is authored for one angle; no "rotate the world" verb |
| Follow | lerp toward the player, ~9/s | same feel as Black Room's top-down camera |
| Far / near | 60 m / 0.05 m | |

**Verification (do this after any camera change).** Put the knight at world origin and
measure his on-screen height. It must be **59 px ± 2**. If it is not, fix the camera —
do not "fix" the art. A one-off script that reads the sprite's projected screen height is
the cheapest test in the project.

## 2. World scale

| Quantity | Value |
|---|---|
| 1 tile | 1.0 m |
| 1 game pixel | **1/32 m** = 0.03125 m |
| 1 room | 13 × 13 tiles = 13 m = 416 screen px |
| Wall height | 3.2 m |
| Knight (game px) | 59 × 59 px sprite; ≈ 1.84 m tall in world units |

## 3. Three layers, three rules

HD-2D is *not* one drawing style. Three layers with different rules, composited:

| Layer | Content | Authored at | Displayed at | Technique |
|---|---|---|---|---|
| **Ground** | floors, walls, ceilings | 32 × 32 px, tileable | 32 px, 1:1 | flat, low contrast, **no hatching** |
| **Props** | furniture, doors, altars, figures | ≤ 128 px | scaled into the 3D scene | hard 1 px ink outline, coarse hatching in deepest shadow only |
| **Paper** | UI, notes, cards, menus | 512–1024 px | ≈ 1:1 | dense cross-hatching, paper grain — this is where illustration lives |

The rule that governs all three: **a source image should not carry more than ~4× the
detail the screen shows.** Detail beyond that is destroyed by minification and reads as
smear, not as craft. At 32 px/tile a floor slab can hold about 4 value steps. That is the
budget; spend it.

## 4. Colour tokens

| Token | Value | Use |
|---|---|---|
| Ink | `#16130F` | outlines, deepest shadow. **Never pure black** — it reads as cheap |
| Stone | `#6A665C` | base limestone |
| Mortar | `#4A4741` | joints only |
| Iron | `#3A3A3E` | metal, chains, grilles |
| Oxblood | `#5A1E1E` | banners, blood, ritual — the only saturated hue allowed to repeat |
| Tallow | `#FFC46E` | candle and lantern light |
| Highlight ceiling | `235` | **never blow to 255**; blown highlights destroy the value structure |
| Shadow floor | `8–14` | the darkest room value, so shapes survive in the dark |

**Chroma gate:** the environment is desaturated. Only gameplay-significant pixels keep
saturation — enemies, interactables, doors, drops, sigils. That is how the player finds
things in a dark room without a UI marker.

## 5. Pixel-density evidence

`tools/art/density.py` draws one 13 × 13 room at 16 / 24 / 32 / 40 / 48 px per tile, in
both full light and game darkness, at 1:1. Sheet: `tools/design/concepts/density_overview.png`.

| px/tile | knight | room width | rooms on screen |
|---|---|---|---|
| 16 | 30 px | 208 px | 9.2 |
| 24 | 44 px | 312 px | 6.2 |
| **32** | **59 px** | **416 px** | **4.6** |
| 40 | 74 px | 520 px | 3.7 |
| 48 | 89 px | 624 px | 3.1 |

32 is the pick: the knight clears the readability threshold, and 4.6 rooms is enough
co-op information to see where your partner went.

## 6. Generation rules learned the hard way

1. **The image model will not draw a quiet repeating surface.** Ask for "floor slabs" and
   you get a 3D diorama on a magenta key, complete with candles. Ask for a "seamless
   repeating flat stone texture, viewed from directly overhead" and you get a tile.
   **Tiles are procedural in this project.** The model is used for figures and props only
   (`tools/art/contact.py` also measures tile seam error so a bad tile is caught).
2. **"Straight down" does not come back as straight down.** The model keeps a few degrees
   of pitch no matter how the prompt is worded. Camera angles are decided in code, not
   asked for in prompts.
3. **Name a material, not a place.** Any word that names somewhere pulls the model into
   drawing somewhere: it composes a scene instead of rendering an asset.
4. **Every prompt carries the same palette sentence.** Consistency between assets comes
   from the shared vocabulary, not from post-processing them into agreement.

## 7. Non-negotiables (each one is a Black Room scar)

- **Assets are in version control from the first commit.** Black Room's `assets/` was
  never tracked; the only copy was a manual backup.
- **2D pixel snapping is on in `project.godot`** (`rendering/2d/snap/*_to_pixel`). Do not
  turn it off to "fix" a jitter; find the real cause.
- **One definition per enum/constant.** Black Room kept three hand-written copies of its
  view-state enum; inserting one value silently turned the door close-up into the altar
  close-up with no error anywhere.
- **No view state may hide the player's feedback.** Prompt, hint and header were all
  hard-disabled in Black Room and the game never once told the player how to open a door.
- **Quantisation is the last colour operation on any asset**, and no asset group is
  exempt from it.
- **Screenshot baselines are compared, not just written.** A test that only saves an image
  passes on a black screen.
