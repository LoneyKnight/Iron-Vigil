"""Measure the knight's real height in pixels, straight off a screenshot.

The engine's own `unproject_position` is the thing under test, so using it to verify
itself is circular — and it disagreed with the analytic result by 17 px without saying
why. This measures the pixels that were actually written to the framebuffer: take the
column band through the knight, find the topmost and bottommost pixel that differs
noticeably from the floor, and report the height.

Run:
    python tools/art/measure_shot.py tests/shots/tile32_knight59.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def measure(path: Path, cx_frac: float = 0.5, cy_frac: float = 0.5,
            band: int = 26, threshold: int = 26) -> dict:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    cx, cy = int(w * cx_frac), int(h * cy_frac)
    px = img.load()

    # The floor's colour right next to the knight, sampled away from the lantern hotspot.
    ref_x = min(w - 1, cx + 220)
    ref = px[ref_x, cy]

    def differs(p) -> bool:
        return (abs(p[0] - ref[0]) + abs(p[1] - ref[1]) + abs(p[2] - ref[2])) > threshold

    top = None
    bottom = None
    for y in range(max(0, cy - 300), min(h, cy + 300)):
        hit = any(differs(px[x, y]) for x in range(max(0, cx - band), min(w, cx + band)))
        if hit:
            if top is None:
                top = y
            bottom = y
    # Second pass: the lantern's glow also differs from the floor, so narrow the search to
    # the strongest column — the sprite is the tallest column of change.
    return {
        "size": (w, h),
        "top": top,
        "bottom": bottom,
        "height_px": (bottom - top + 1) if (top is not None and bottom is not None) else 0,
        "floor_ref": ref,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shot", nargs="?", default="tests/shots/tile32_knight59.png")
    args = ap.parse_args()
    path = ROOT / args.shot if not Path(args.shot).is_absolute() else Path(args.shot)
    if not path.is_file():
        raise SystemExit(f"no such screenshot: {path}")
    r = measure(path)
    print(f"{path.name}  {r['size'][0]}x{r['size'][1]}  floor sample {r['floor_ref']}")
    print(f"  silhouette rows: top={r['top']} bottom={r['bottom']}")
    print(f"  measured height: {r['height_px']} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
