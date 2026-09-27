"""Iron Vigil — generate the sound effects.

Run:
    python tools/audio/gen_sfx.py                 # everything
    python tools/audio/gen_sfx.py foot_stone door

Design notes that matter more than the code
-------------------------------------------
**Every effect is mono.** They all play through AudioStreamPlayer3D, and a stereo source
fighting the positional panner destroys the one thing this game's audio is for: knowing where
a sound came from. The ambience beds are the only stereo assets.

**Loudness is set here, in dB, per sound.** The generator normalises by RMS, so the relative
balance between a footstep and a door slam is a decision made in this file and nowhere else.
Once a level is written here, do not "fix" it in the engine: an engine-side volume change
silently breaks the mix every time a file is regenerated.

**A sound has to say what it is, from where.** That is the whole brief. A door slam is not
"a loud noise": it is a specific object failing loudly, and it must be recognisable from
across the map, because the player's job is to decide whether that noise was theirs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "sfx"
SR = 48000

# The room the effects are rendered into. The engine adds per-room reverb on top (a bus
# effect driven by the room the listener stands in); this is only the "space" baked into each
# one-shot so it does not sound like it was recorded in a vacuum.
ROOM_WET = 0.14
ROOM_SIZE = 0.7


def space(x: np.ndarray, wet: float = ROOM_WET, room: float = ROOM_SIZE) -> np.ndarray:
    return dsp.reverb(x, wet=wet, room=room)


def mix(*parts: np.ndarray) -> np.ndarray:
    """Sum signals of different lengths, padding to the longest.

    `dsp.env(sec, ...)` builds an envelope of `sec` samples, which is NOT the same as the
    length of the signal it is shaping: a 0.3 s thud inside a 1.1 s slam has a 0.3 s envelope.
    Adding those two numpy arrays directly raises, and it raised on seven sounds the first time
    this file ran. Padding is the honest fix — the shorter sound simply does not extend that
    far — and it removes the whole class of mistake rather than seven instances of it.
    """
    if not parts:
        return np.zeros(1)
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


def save(name: str, x: np.ndarray, db: float = -20.0) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    x = dsp.fades(dsp.level(x, db), ms=3.0)
    dsp.write_wav(str(OUT / f"{name}.wav"), x, SR)
    print(f"  {name:22s} {len(x) / SR:5.2f}s  {db:6.1f} dB")


# =======================================================================================
# movement
# =======================================================================================

def foot(seed: int, weight: float, surface: str = "stone") -> np.ndarray:
    """A boot on a floor. `weight` 0..1 scales the low end, which is how a walk and a run
    end up sounding like the same person moving at different speeds rather than two
    different creatures."""
    n = 0.16
    body = dsp.noise(n, seed=seed) * dsp.env(n, 0.002, 0.06, 0.0, 0.09)
    if surface == "stone":
        body = dsp.bandpass(body, 180, 2600, stages=2)
        grit = dsp.bandpass(dsp.noise(n, seed=seed + 7), 1800, 5000, stages=1) \
            * dsp.env(n, 0.001, 0.02, 0.0, 0.03)
        body = body + grit * 0.5
    elif surface == "wood":
        body = dsp.bandpass(body, 120, 1800, stages=2)
        body = body + dsp.modal(body, [180, 340, 620], decay=0.05, seed=seed) * 0.35
    else:  # cloth / carpet
        body = dsp.bandpass(body, 90, 900, stages=2)
        body = body * 0.8
    thump = dsp.osc(58.0, n) * dsp.env(n, 0.001, 0.05, 0.0, 0.05) * (0.25 + 0.5 * weight)
    return space(body * (0.55 + 0.45 * weight) + thump, wet=0.08)


def stone_throw(seed: int) -> np.ndarray:
    """A thrown stone leaving the hand. Short and directional: the player needs to hear that
    it left, not where it lands (the landing is a separate, louder sound)."""
    n = 0.14
    whoosh = dsp.bandpass(dsp.noise(n, seed=seed), 600, 4200, stages=1)
    whoosh = whoosh * dsp.swell(n, peak_at=0.25) * 0.6
    return space(whoosh, wet=0.05)


def stone_impact(seed: int) -> np.ndarray:
    """A stone hitting stone. This is the noise the player MAKES, so it has to be loud, sharp
    and unmistakably somewhere else: it is the only tool they have for lying about where they
    are."""
    n = 0.42
    crack = dsp.bandpass(dsp.noise(n, seed=seed), 900, 6500, stages=1) * dsp.env(n, 0.0008, 0.03, 0.0, 0.12)
    ring = dsp.modal(crack, [420, 880, 1520, 2600], decay=0.28, seed=seed) * 0.5
    body = dsp.osc(120.0, n) * dsp.env(n, 0.001, 0.10, 0.0, 0.2) * 0.3
    return space(crack + ring + body, wet=0.3, room=0.85)


# =======================================================================================
# doors: the load-bearing sound of the whole game
# =======================================================================================

def door_open(seed: int, force: float = 0.5) -> np.ndarray:
    """A door being pushed open. `force` 0..1 is how hard.

    The design intent: a slow push is almost silent and a hard push announces you to the whole
    floor. That gradient has to be audible, or "open it quietly" is not a decision.
    """
    n = 0.9
    t = dsp.t(n)
    # Hinge creak: a wandering resonance, and the part that carries when the push is gentle.
    f0 = 320.0 + 140.0 * force
    wobble = 1.0 + 0.06 * np.sin(2 * np.pi * 3.1 * t + seed)
    creak = np.sin(2 * np.pi * np.cumsum(f0 * wobble) / SR)
    creak = dsp.bandpass(creak, 400, 3000, stages=2) * dsp.swell(n, peak_at=0.45)
    creak = creak * (0.5 + 0.5 * force)

    # The wooden thud as it comes off the frame, only when it is pushed hard.
    thud_n = 0.3
    thud = dsp.bandpass(dsp.noise(thud_n, seed=seed + 3), 90, 700, stages=2)
    thud = thud * dsp.env(thud_n, 0.002, 0.10, 0.0, 0.16)
    thud = thud + dsp.modal(thud, [96, 180, 300], decay=0.18, seed=seed) * 0.4
    thud = thud * force * 0.9

    return space(mix(creak, thud), wet=0.2 + 0.15 * force, room=0.8)


def door_slam(seed: int) -> np.ndarray:
    """Shouldered open at a run: instant, violent, and the loudest thing a player can cause
    on purpose without a weapon."""
    n = 1.1
    hit = dsp.bandpass(dsp.noise(n, seed=seed), 70, 1400, stages=2) * dsp.env(n, 0.0006, 0.05, 0.0, 0.5)
    body = dsp.modal(hit, [58, 92, 150, 260], decay=0.55, seed=seed) * 0.9
    crack_n = 0.25
    crack = dsp.bandpass(dsp.noise(crack_n, seed=seed + 5), 1500, 7000, stages=1) \
        * dsp.env(crack_n, 0.0005, 0.02, 0.0, 0.1)
    wood_n = 0.4
    wood = dsp.modal(dsp.noise(wood_n, seed=seed + 9), [180, 300, 520, 880], decay=0.25, seed=seed) * 0.5
    return space(mix(body, crack * 0.7, wood), wet=0.42, room=0.95)


# =======================================================================================
# the house
# =======================================================================================

def chest_open(seed: int) -> np.ndarray:
    n = 0.55
    latch_n = 0.12
    latch = dsp.bandpass(dsp.noise(latch_n, seed=seed), 1200, 5200, stages=1) \
        * dsp.env(latch_n, 0.0006, 0.02, 0.0, 0.05)
    hinge = np.sin(2 * np.pi * np.cumsum((260 + 90 * np.sin(dsp.t(n) * 4)) / SR))
    hinge = dsp.bandpass(hinge, 300, 2200, stages=2) * dsp.swell(n, peak_at=0.5) * 0.6
    thud_n = 0.3
    thud = dsp.modal(dsp.noise(thud_n, seed=seed + 2), [110, 200, 340], decay=0.16, seed=seed) * 0.5
    return space(mix(latch, hinge, thud), wet=0.18)


def pickup(seed: int) -> np.ndarray:
    """Something small and metal takes from a chest. Bright, short, and pleasant: this is the
    loop's reward, and it should feel like one."""
    n = 0.4
    chime = dsp.modal(np.ones(int(n * SR)), [880, 1320, 1760, 2640], decay=0.22, seed=seed)
    chime = dsp.bandpass(chime, 700, 6000, stages=1) * dsp.env(n, 0.001, 0.12, 0.0, 0.22)
    return space(chime * 0.8, wet=0.25, room=0.6)


def relic_pickup(seed: int) -> np.ndarray:
    """The quest item. Deliberately a different size of sound from ordinary loot: low, slow,
    resonant, and it keeps going after the player has stopped moving. The player must be able
    to tell they picked up the thing that matters without reading a line of text."""
    n = 2.2
    low = dsp.modal(np.ones(int(n * SR)), [110, 165, 220, 330, 440], decay=1.6, seed=seed)
    low = dsp.lowpass(low, 2400, stages=1) * dsp.env(n, 0.02, 0.4, 0.35, 1.1)
    air = dsp.bandpass(dsp.noise(n, seed=seed + 4), 3000, 9000, stages=1) * dsp.swell(n, peak_at=0.15)
    return space(low * 0.9 + air * 0.25, wet=0.5, room=1.0)


def altar_lit(seed: int) -> np.ndarray:
    """The rite lands. The run's resolution: warm, rising, and final."""
    n = 3.0
    root = 146.83  # D3
    tones = [root, root * 1.5, root * 2.0, root * 3.0]
    voice = np.zeros(int(n * SR))
    for i, f in enumerate(tones):
        voice += np.sin(2 * np.pi * f * dsp.t(n)) * (0.5 ** i)
    voice = dsp.lowpass(voice, 3600, stages=1) * dsp.env(n, 0.35, 0.6, 0.5, 1.4)
    flame = dsp.bandpass(dsp.noise(n, seed=seed + 3), 500, 5000, stages=1) * dsp.swell(n, peak_at=0.2)
    return space(voice * 0.7 + flame * 0.3, wet=0.55, room=1.0)


def altar_refuse(seed: int) -> np.ndarray:
    """Not yet. A dull, closed thud — no resonance, no reward. The player should feel the
    refusal rather than read it."""
    n = 0.7
    dull = dsp.lowpass(dsp.noise(n, seed=seed), 260, stages=2) * dsp.env(n, 0.003, 0.08, 0.0, 0.4)
    tone = dsp.osc(72.0, n) * dsp.env(n, 0.004, 0.2, 0.0, 0.35) * 0.5
    return space(dull + tone, wet=0.1, room=0.5)


# =======================================================================================
# violence
# =======================================================================================

def swing(seed: int) -> np.ndarray:
    n = 0.28
    air = dsp.bandpass(dsp.noise(n, seed=seed), 400, 3800, stages=1)
    air = air * dsp.swell(n, peak_at=0.35) * 0.7
    return space(air, wet=0.08)


def hit_flesh(seed: int) -> np.ndarray:
    n = 0.35
    thud = dsp.lowpass(dsp.noise(n, seed=seed), 700, stages=2) * dsp.env(n, 0.001, 0.05, 0.0, 0.2)
    crack_n = 0.15
    crack = dsp.bandpass(dsp.noise(crack_n, seed=seed + 1), 900, 4000, stages=1) \
        * dsp.env(crack_n, 0.0006, 0.02, 0.0, 0.06)
    return space(mix(thud, crack * 0.5), wet=0.12)


def enemy_die(seed: int) -> np.ndarray:
    n = 1.3
    rattle = dsp.bandpass(dsp.noise(n, seed=seed), 200, 3000, stages=2)
    rattle = rattle * dsp.env(n, 0.01, 0.15, 0.2, 0.7)
    fall_n = 0.5
    fall = dsp.lowpass(dsp.noise(fall_n, seed=seed + 2), 300, stages=2) \
        * dsp.env(fall_n, 0.002, 0.1, 0.0, 0.35)
    groan = dsp.modal(np.ones(int(n * SR)), [90, 140, 210], decay=0.9, seed=seed) * 0.5
    return space(mix(rattle * 0.7, fall, groan), wet=0.35)


def player_hurt(seed: int) -> np.ndarray:
    n = 0.6
    thud = dsp.lowpass(dsp.noise(n, seed=seed), 420, stages=2) * dsp.env(n, 0.001, 0.06, 0.0, 0.4)
    ring = dsp.modal(thud, [180, 300, 470], decay=0.35, seed=seed) * 0.4
    return space(thud + ring, wet=0.2)


# =======================================================================================
# the opposition
# =======================================================================================

def cultist_chant(seed: int) -> np.ndarray:
    """Heard before seen. Low, breathy, human — the point is that it is a PERSON, so the
    player's first reaction is to listen rather than to fight."""
    n = 2.4
    f = 128.0
    t = dsp.t(n)
    breath = dsp.bandpass(dsp.noise(n, seed=seed), 300, 2200, stages=2)
    breath = breath * (0.5 + 0.5 * np.sin(2 * np.pi * 1.3 * t)) * dsp.env(n, 0.3, 0.3, 0.5, 0.8)
    tone = np.sin(2 * np.pi * f * t + 0.4 * np.sin(2 * np.pi * 4.5 * t))
    tone = dsp.lowpass(tone, 900, stages=1) * dsp.env(n, 0.25, 0.3, 0.5, 0.9) * 0.6
    return space(breath * 0.6 + tone, wet=0.45, room=0.9)


def cultist_alert(seed: int) -> np.ndarray:
    """It heard you. Short, sharp intake of breath: the cue that a plan has just changed."""
    n = 0.5
    gasp = dsp.bandpass(dsp.noise(n, seed=seed), 500, 3600, stages=1)
    gasp = gasp * dsp.env(n, 0.01, 0.06, 0.1, 0.2)
    return space(gasp * 0.9, wet=0.25)


def cultist_die(seed: int) -> np.ndarray:
    return enemy_die(seed)


def stone_land(seed: int) -> np.ndarray:
    return stone_impact(seed)


# =======================================================================================
# the house itself
# =======================================================================================

def house_groan(seed: int) -> np.ndarray:
    """Timber settling somewhere the player cannot see. Pure unease, and it doubles as the
    game teaching the player that the house makes noises of its own — which is what makes a
    thrown stone believable later."""
    n = 3.6
    body = dsp.modal(np.ones(int(n * SR)), [48, 71, 96, 143], decay=2.4, seed=seed)
    body = dsp.lowpass(body, 600, stages=2) * dsp.env(n, 0.6, 0.8, 0.4, 1.6)
    creak = np.sin(2 * np.pi * np.cumsum((90 + 40 * np.sin(dsp.t(n) * 0.7)) / SR))
    creak = dsp.bandpass(creak, 80, 900, stages=2) * dsp.swell(n, peak_at=0.5) * 0.4
    return space(body + creak, wet=0.6, room=1.0)


def drip(seed: int) -> np.ndarray:
    n = 0.6
    drop = dsp.modal(np.ones(int(n * SR)), [1400, 2600, 3900], decay=0.25, seed=seed)
    drop = drop * dsp.env(n, 0.0005, 0.05, 0.0, 0.3)
    return space(drop * 0.7, wet=0.5, room=0.9)


def heartbeat(seed: int) -> np.ndarray:
    """Low health. Plays on the listener, not in the world: it is the player's own body."""
    n = 1.1
    b1 = dsp.osc(52.0, n) * dsp.env(n, 0.004, 0.10, 0.0, 0.16)
    b2 = dsp.osc(46.0, n) * dsp.env(n, 0.004, 0.08, 0.0, 0.14)
    off = int(0.32 * SR)
    x = mix(b1, np.concatenate([np.zeros(off), b2 * 0.7]))
    return dsp.lowpass(x, 200, stages=2)


# =======================================================================================
# ambience: the bed the rest of the mix sits on
# =======================================================================================

def amb_house(seed: int) -> np.ndarray:
    """A seamless 24 s loop of an empty stone building. Stereo, because it is the room rather
    than a thing in it."""
    n = 24.0
    parts = []
    for i in range(4):
        c = dsp.bandpass(dsp.noise(n, seed=seed + i * 11), 60 * (2 ** i), 400 * (2 ** i), stages=1)
        c = c * (0.5 + 0.5 * np.sin(2 * np.pi * (0.05 + 0.03 * i) * dsp.t(n) + i))
        parts.append(c / (i + 2))
    air = dsp.bandpass(dsp.noise(n, seed=seed + 99), 3000, 9000, stages=1) * 0.12
    x = sum(parts) + air
    x = dsp.loop_crossfade(x, fade=3.0)
    return dsp.widen(x, width=0.7)


def amb_tension(seed: int) -> np.ndarray:
    """20 s loop. A slow swell that never resolves, plus a sub pulse. Switches on when the
    house knows about you."""
    n = 20.0
    t = dsp.t(n)
    sub = np.sin(2 * np.pi * 41.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.12 * t))
    body = dsp.lowpass(dsp.noise(n, seed=seed), 220, stages=2) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.08 * t))
    high = dsp.bandpass(dsp.noise(n, seed=seed + 5), 2000, 6000, stages=1) * 0.08
    x = sub * 0.5 + body * 0.6 + high
    x = dsp.loop_crossfade(x, fade=2.5)
    return dsp.widen(x, width=0.55)


SOUNDS = [
    # movement — three surfaces so the mix changes with the room
    ("foot_stone", lambda s: foot(s, 0.55, "stone"), -21.0),
    ("foot_wood", lambda s: foot(s, 0.55, "wood"), -21.0),
    ("foot_cloth", lambda s: foot(s, 0.55, "cloth"), -23.0),
    ("foot_run", lambda s: foot(s, 0.95, "stone"), -17.0),
    # the player's one active tool
    ("stone_throw", stone_throw, -19.0),
    ("stone_impact", stone_impact, -13.0),
    # doors
    ("door_open_soft", lambda s: door_open(s, 0.25), -24.0),
    ("door_open_hard", lambda s: door_open(s, 0.85), -15.0),
    ("door_slam", door_slam, -10.0),
    # the house
    ("chest_open", chest_open, -17.0),
    ("pickup", pickup, -17.0),
    ("relic_pickup", relic_pickup, -14.0),
    ("altar_lit", altar_lit, -12.0),
    ("altar_refuse", altar_refuse, -19.0),
    # violence
    ("swing", swing, -18.0),
    ("hit_flesh", hit_flesh, -16.0),
    ("enemy_die", enemy_die, -15.0),
    ("player_hurt", player_hurt, -14.0),
    # the opposition
    ("cultist_chant", cultist_chant, -22.0),
    ("cultist_alert", cultist_alert, -16.0),
    ("cultist_die", cultist_die, -15.0),
    # atmosphere
    ("house_groan", house_groan, -26.0),
    ("drip", drip, -27.0),
    ("heartbeat", heartbeat, -17.0),
    ("amb_house", amb_house, -27.0),
    ("amb_tension", amb_tension, -25.0),
]


def main(argv: list[str]) -> int:
    wanted = set(argv) if argv else None
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"{len(SOUNDS)} sounds -> {OUT}")
    made = 0
    for i, (name, fn, db) in enumerate(SOUNDS):
        if wanted and name not in wanted:
            continue
        try:
            save(name, fn(1000 + i * 37), db)
            made += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:22s} FAILED: {exc}")
    print(f"\n{made} written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
