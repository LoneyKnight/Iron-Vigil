"""Camera sweep for Iron Vigil: render the same room at several pitches and densities.

Choosing a camera angle from numbers does not work — the pitch decides how much floor
versus architecture is on screen, and that is a judgement you make with your eyes. So this
runs the real prototype once per setting, collects the screenshots and stacks them into one
contact sheet with the measured numbers printed on each panel.

Run:
    python tools/art/sweep.py                     # default sweep
    python tools/art/sweep.py --pitch 32 38 45    # pick your own
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "tests" / "shots"
OUT = ROOT / "tools" / "design" / "concepts"
GODOT = Path(r"E:\Godot\Godot_v4.7.1-stable_win64_console.exe")

DEFAULT_PITCH = [30.0, 36.0, 42.0, 48.0]


def run_one(pitch: float, ppm: float, timeout: int = 120) -> tuple[Path, str]:
    name = f"sweep_p{int(pitch):02d}_ppm{int(ppm):02d}"
    log = ROOT / "tests" / "_sweep.log"
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        subprocess.run(
            [str(GODOT), "--path", str(ROOT), "--", "--shot",
             f"--pitch={pitch}", f"--ppm={ppm}", f"--name={name}"],
            stdout=fh, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    shot = SHOTS / f"{name}.png"
    notes = ""
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if "knight on screen" in line or "wall face" in line or "one tile" in line:
                notes += line.strip() + "\n"
    return shot, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pitch", type=float, nargs="*", default=DEFAULT_PITCH)
    ap.add_argument("--ppm", type=float, default=42.43)
    args = ap.parse_args()

    if not GODOT.is_file():
        raise SystemExit(f"Godot not found at {GODOT}")
    OUT.mkdir(parents=True, exist_ok=True)

    panels: list[tuple[Image.Image, str]] = []
    for pitch in args.pitch:
        shot, notes = run_one(pitch, args.ppm)
        if not shot.is_file():
            print(f"pitch {pitch}: no screenshot produced")
            continue
        img = Image.open(shot).convert("RGB")
        panels.append((img, f"pitch {pitch:.0f} deg   ppm {args.ppm:.0f}\n{notes.strip()}"))
        print(f"pitch {pitch:5.1f} -> {shot.name}")

    if not panels:
        raise SystemExit("nothing rendered")

    # Stack vertically at half size: enough to judge composition, and the measured numbers
    # are printed on each panel so the picture and the spec cannot drift apart.
    w = 960
    h = int(panels[0][0].height * w / panels[0][0].width)
    sheet = Image.new("RGB", (w, h * len(panels)), (10, 10, 12))
    d = ImageDraw.Draw(sheet)
    for i, (img, caption) in enumerate(panels):
        sheet.paste(img.resize((w, h), Image.LANCZOS), (0, i * h))
        d.rectangle([8, i * h + 8, 8 + 8 * 62, i * h + 8 + 16 * (caption.count("\n") + 2)],
                    fill=(0, 0, 0))
        d.multiline_text((14, i * h + 12), caption, fill=(255, 226, 160))
    out = OUT / "camera_sweep.png"
    sheet.save(out)
    print(f"\n{out}  {sheet.width}x{sheet.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
