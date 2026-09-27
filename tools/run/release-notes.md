# Iron Vigil — first playable build

A co-op knight-cult run through a chapter house. Godot 4.7.1, HD-2D pixel art, Windows x86_64.

**Download `IronVigil-windows-x86_64.zip`, unzip it, run `IronVigil.exe`.** No installer, no
runtime to install — the zip holds the executable and its data pack.

## How to play

| Key | |
|---|---|
| **WASD** | move |
| **Shift** | run — nearly twice the speed, **more than four times the noise** |
| **Mouse** | turn and aim |
| **E** | interact: open a door, search a chest, perform the rite |
| **Left mouse** | swing |
| **G** | throw a stone |
| **F4** | toggle an inspection ambient light (for seeing, not for playing) |
| **R** | restart the run |

## The run

Eight rooms. Two relics are hidden in them — the **ritual dagger** and the **tallow of the
vigil**. Find both, carry them to the **altar**, and complete the rite. Cultists wander the
house and will interrupt you.

## What this build is testing

The design claim is one sentence: **a noise you make is information everyone shares.** You hear a
cultist before you see it, and it hears you. So making a noise is a decision with a cost, and the
HUD's noise meter is there to make that cost visible rather than something you have to be told
about.

The only way to lie about where you are is to make a noise somewhere else. That is what the
stones are for, and you have three.

## What it is not

A vertical slice, not a game. Deliberately missing: networking, an inventory, sanity, sound as a
full resource, and any second scenario. It exists to prove that the loop closes and that the
camera solves, and both of those are measured rather than assumed — see `tools/design/`.

Known rough edges: wood and cloth floor materials are declared but not drawn, so every room is
stone; rooms connect with no threshold between them; the cultists have no hearing memory beyond
seven seconds.

## Verified before this build was published

1. `--selftest` headless: **SELFTEST OK**, 13 checks (generator invariants over 200 seeds, asset
   and sound presence, camera constants).
2. The full run, end to end, **twice on different seeds**: **VERTICAL SLICE OK**, 46 assertions,
   0 failures.
3. The same 46 assertions run against an **exported binary** rather than the editor, to prove the
   export itself loses nothing. It is a real risk: a `.pck` can drop resources in ways the editor
   never sees.
4. The shipped exe smoke-tested: boots, renders, exits 0.
