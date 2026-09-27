"""Talk to the image API and cache every raw generation.

Reads credentials from tools/.env (gitignored):

    IMAGE_API_KEY=...
    IMAGE_API_URL=https://api.gpt.ge/v1
    IMAGE_MODEL=gpt-image-2.5-flare

Raw results land in tools/art_raw/<name>.png, so re-running the pixel pipeline costs
nothing. Delete a raw file to force a regeneration.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / "tools" / ".env"
RAW_DIR = ROOT / "tools" / "art_raw"

# Appended to every prompt. The magenta screen is what lets us cut the sprite out
# with a flood fill later; the explicit size/AA instructions are what make the
# generator draw in blocks we can snap to.
PIXEL_SUFFIX = (
    " Strict pixel art, {size}x{size} pixel grid, chunky visible pixels, no anti-aliasing, "
    "no gradients, no blur, no soft shading, flat solid colours only, "
    "limited palette of at most 24 colours, "
    "plain solid magenta background (#FF00FF) filling all empty space, "
    "no text, no labels, no watermark, no border, no drop shadow."
)


# Detailed world sprites: each 1024 image is a 4x4 grid of 256x256 cells, and each
# sprite is drawn at about 128 *art* pixels (2 screen px per art px). That ratio is the
# whole point: props are shown 16-22 px across and figures ~30 px tall, so a 256 px
# sprite is an 8-16x reduction — detail that cannot survive, which reads as a smooth
# smear instead of drawn art. 128 keeps silhouettes crisp.
HD_SUFFIX = (
    " Pixel art with HARD edges: the 1024x1024 canvas is a 4 columns x 4 rows grid of 256x256 cells, and each "
    "sprite is drawn at about 128x128 art pixels (2 screen pixels per art pixel) so big shapes stay readable "
    "when the sprite is scaled down. Crisp hard pixel edges, flat solid colours, at most 12 colours on the "
    "sheet, bold 1px near-black outline, coarse carved hatching ONLY in the deepest shadow. "
    "No anti-aliasing, no gradients, no blur, no dithering, no texture noise, no fine internal detail, "
    "no painterly brush strokes, no photographic texture. "
    "Plain solid flat magenta background (#FF00FF) filling all empty space and the gaps between cells, "
    "no grid lines, no text, no labels, no watermark, no drop shadow."
)


class ImageAPIError(RuntimeError):
    pass


def load_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        raise SystemExit(f"missing {ENV_PATH} — create it with IMAGE_API_KEY=..., IMAGE_API_URL=..., IMAGE_MODEL=...")
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    for k in ("IMAGE_API_KEY", "IMAGE_API_URL"):
        if not env.get(k):
            raise SystemExit(f"{k} is not set in {ENV_PATH}")
    env.setdefault("IMAGE_MODEL", "gpt-image-2.5-flare")
    return env


def _post(url: str, key: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:800]
        raise ImageAPIError(f"HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        # includes http.client.RemoteDisconnected (the gateway dropping long requests)
        raise ImageAPIError(f"connection failed: {e}") from e


def generate(
    prompt: str,
    *,
    size: int = 32,
    out_size: str = "1024x1024",
    model: str | None = None,
    timeout: int = 300,
    retries: int = 4,
    hd: bool = False,
    suffix: str | None = None,
) -> Image.Image:
    """One 1024x1024 generation, returned as an RGBA image.

    ``suffix`` replaces the built-in PIXEL_SUFFIX / HD_SUFFIX, which is how a style
    experiment pins a layer's own resolution and rendering rules (see samples.py).
    """
    env = load_env()
    tail = suffix if suffix is not None else (HD_SUFFIX if hd else PIXEL_SUFFIX.format(size=size))
    body = {
        "model": model or env["IMAGE_MODEL"],
        "prompt": prompt + tail,
        "size": out_size,
        "n": 1,
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            data = _post(env["IMAGE_API_URL"].rstrip("/") + "/images/generations", env["IMAGE_API_KEY"], body, timeout)
            break
        except ImageAPIError as e:
            last = e
            if attempt == retries - 1:
                raise
            time.sleep(3.0 * (attempt + 1))
    else:  # pragma: no cover
        raise ImageAPIError(str(last))

    items = data.get("data") or []
    if not items:
        raise ImageAPIError(f"no image in response: {json.dumps(data)[:400]}")
    item = items[0]
    if item.get("b64_json"):
        import io
        raw = base64.b64decode(item["b64_json"])
        return Image.open(io.BytesIO(raw)).convert("RGBA")
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=timeout) as r:
            import io
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    raise ImageAPIError(f"unusable image entry: {list(item)}")


def cached(name: str, prompt: str, *, size: int = 32, model: str | None = None,
           out_size: str = "1024x1024", force: bool = False, hd: bool = False,
           suffix: str | None = None) -> Image.Image:
    """generate(), but reused from tools/art_raw/<name>.png when it already exists."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{name}.png"
    if path.exists() and not force:
        return Image.open(path).convert("RGBA")
    img = generate(prompt, size=size, model=model, out_size=out_size, hd=hd, suffix=suffix)
    img.save(path)
    return img


def main() -> int:
    """Smoke test:  python tools/art/gen.py "some prompt" """
    prompt = " ".join(sys.argv[1:]) or "pixel art sprite of a single red apple"
    img = generate(prompt, size=32)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / "cli_latest.png"
    img.save(out)
    print(f"{out}  {img.size[0]}x{img.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
