"""Row colours per contractor.

Every contractor has one fixed colour (contractors.color), used as the row background of
its wells on every sheet and month. New contractors get the first unused colour from a
calm palette automatically (see the before_flush hook in app.models); managers can change
it in Contractors. When the palette runs out, further pastel colours are generated, so a
new contractor never needs a code change.
"""
from __future__ import annotations

import colorsys
import re

# Soft, distinct backgrounds. Dark text (#15211f) on each has a contrast ratio above 12:1.
PALETTE = [
    "#DCEBFA",  # sky blue
    "#E2F3E4",  # mint
    "#FCE8D5",  # peach
    "#EDE3F7",  # lavender
    "#FFF3C9",  # butter
    "#DDF2F1",  # aqua
    "#FBE3E8",  # rose
    "#E4F0D3",  # pistachio
    "#E0E7F5",  # periwinkle
    "#F3E6DA",  # sand
    "#F6DFF0",  # orchid
    "#E8E6DF",  # stone
]
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _generated(i: int) -> str:
    """i-th extra pastel, spread around the colour wheel by the golden angle."""
    h = (i * 0.618033988749895 + 0.11) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.90, 0.55)
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def next_color(used: set[str]) -> str:
    used_u = {u.upper() for u in used if u}
    for c in PALETTE:
        if c.upper() not in used_u:
            return c
    i = 0
    while True:
        c = _generated(i)
        if c.upper() not in used_u:
            return c
        i += 1
