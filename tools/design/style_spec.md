# Iron Vigil · Style Spec v1

> **Read this before touching art, camera or render settings.**
> Every number here is a decision, not a default. Black Room shipped five visual languages
> and a character that was never displayed 1:1 because these numbers were never fixed;
> this file exists so that cannot happen again.

## 0. The locked numbers

| # | Quantity | Value | Why |
|---|---|---|---|
| 1 | Screen px per metre of ground | **85** | measured: puts a 7 m room at 34% of the frame |
| 2 | Knight height on screen | **128 px** (1.80 m world) | armour and lantern read at this size |
| 3 | Wall height on screen | **316 px** (4.6 m world) | side walls must be surfaces, not edges |
| 4 | Reference resolution | **1920 × 1080** | the screen the art is budgeted against |
| 5 | Room | **7 × 7 m** | a chapter house, not a hall — see §2.1 |

**Corollary — and the whole point of choosing HD-2D:** the world is drawn by a real
`Camera3D`, so a sprite's apparent size comes from 3D perspective, not from a CanvasItem
`zoom`. There is no fractional-zoom shimmer to avoid, and `pixel_size` maps texels to
world metres directly. This removes an entire class of bugs that a 2D canvas camera has:
the character is always exactly the size the atlas was authored at.

## 1. Camera setup

| Parameter | Value | Note |
|---|---|---|
| Type | `Camera3D`, **perspective** | not a preference — see §1.1 |
| Pitch | **−36°** | **signed**: negative puts the camera above the room |
| FOV | **24°** | narrow, which compresses depth the way HD-2D does |
| Distance to focus | **50.6 m** | solved: `VH / (2 · PPM · tan(fov/2))` |
| Yaw | fixed (no rotation) | the level is authored for one angle |
| Follow | lerp toward the player, 9/s | |
| Near / far | 0.05 / 200 m | |

### 1.1 Why perspective, and what it costs

The first playable frame was **orthographic**, chosen to keep pixel density exactly constant.
It did not read as HD-2D at all: a parallel projection has no vanishing point, so the room
came out as a **flat floor plan with a light on it**. The look depends on convergence, fog
and a shallow focal plane. Perspective costs a few percent of density variation across the
frame — the test tolerance is 6% for that reason — and buys the depth.

### 1.2 The trigonometry, once

Measured on the live camera (the CALIB lines in `tests/shot.gd`), one metre of world along
each axis projects to:

| World axis | Screen px per metre | Factor |
|---|---|---|
| X — across the ground | **85.0** | `ppm` |
| Z — into the ground | **68.8** | `ppm · cos(pitch)` |
| Y — **height** | **68.8** | `ppm · cos(pitch)` |

A metre of **height** and a metre of **depth** foreshorten **together**: both lie in the
plane the camera looks along. A metre of width does not. Therefore

```
figure_px = height_m × ppm × cos(pitch)
wall_px   = wall_m   × ppm × cos(pitch)
```

An earlier version of this spec said `sin(pitch)`. That is wrong, and it produced a spec
claiming a 59 px knight while the engine rendered 36. The CALIB print caught it and is kept
as a standing diagnostic for exactly that reason.

### 1.3 Verify after any camera change

Put the knight at the focus point and measure. Do **not** fix the art to match a broken
camera.

| Quantity | Expected |
|---|---|
| pixels per metre of ground | 85.0 ± 0.5 |
| knight on screen | 128 px ± 6% |
| wall face | 316 px ± 5% |
| room coverage | ≥ 25% of the frame in both axes |

## 2. World scale

| Quantity | Value |
|---|---|
| 1 tile | 1.0 m |
| 1 room | **7 × 7 tiles** = 7 m = 595 px wide on screen |
| Wall height | **4.6 m** |
| Knight | 1.80 m world → 128 px on screen |
| Visible ground | 22.6 m wide ≈ 1.7 rooms |

### 2.1 Why the room is 7 tiles and not 13

It was 13, inherited from the previous project, and that one number is why the knight looked
like a speck: at 1.8 m tall he filled 14% of the room's width, so the camera had to pull back
to show the room and he shrank with it. Seven tiles reads as a real medieval chamber and
makes the figure a plausible occupant of it.

### 2.2 Three walls, not four

The camera sits outside the south wall, so a full-height south wall is the nearest object in
frame and hides the room behind it — the first 7 m frame was mostly a grey slab. This is the
cutaway HD-2D depends on, and it is why the reference images all show architecture receding
away from the viewer with nothing between camera and subject. The south edge keeps a 0.55 m
parapet so the room still reads as enclosed rather than as a floor floating in space.

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
