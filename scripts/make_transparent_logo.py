"""Make a transparent-background PNG of the official HAYAH logo.

Only the plain background around the logo is removed: we flood-fill from the
image border through light, low-colour pixels. The drop, leaves, letters and
their white highlights are untouched (not recoloured, not resized).

    python3 scripts/make_transparent_logo.py branding/hayah-logo-original.jpeg branding/hayah-logo-transparent.png
"""
import sys
from collections import deque

import numpy as np
from PIL import Image


def main(src: str, dst: str):
    rgb = np.asarray(Image.open(src).convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat, val = mx - mn, mx
    bgish = (sat < 40) & (val > 175)          # light, nearly grey: background or soft shadow
    seen = np.zeros((h, w), bool)
    q = deque((y, x) for y in range(h) for x in (0, w - 1)) + deque((y, x) for x in range(w) for y in (0, h - 1))
    while q:
        y, x = q.popleft()
        if seen[y, x] or not bgish[y, x]:
            continue
        seen[y, x] = True
        if y > 0: q.append((y - 1, x))
        if y < h - 1: q.append((y + 1, x))
        if x > 0: q.append((y, x - 1))
        if x < w - 1: q.append((y, x + 1))
    alpha = np.full((h, w), 255, np.int16)
    alpha[seen] = 0
    # soft edge (3px): logo pixels next to the background fade by how pale they are,
    # so there is no white fringe on dark backgrounds
    near = seen.copy()
    for _ in range(3):
        near = near | np.roll(near, 1, 0) | np.roll(near, -1, 0) | np.roll(near, 1, 1) | np.roll(near, -1, 1)
    edge = near & ~seen
    soft = np.clip(sat * 3 + (255 - val) * 4, 0, 255)
    alpha[edge] = np.minimum(255, soft[edge])
    out = np.dstack([rgb, alpha]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst, optimize=True)
    print(f"wrote {dst}: {w}x{h}, transparent pixels {int((alpha == 0).sum() * 100 / alpha.size)}%")


if __name__ == "__main__":
    main(*sys.argv[1:3])
