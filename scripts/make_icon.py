"""Generates the brand icon: a location pin containing a house (Home Assistant -> Reitti),
with a dotted route leading to it. Needs Pillow. Usage: make_icon.py <output-dir>"""
import math
import sys

from PIL import Image, ImageDraw

BLUE = (3, 169, 244)       # Home Assistant blue
DARK = (13, 71, 161)
WHITE = (255, 255, 255)
SS = 4                     # supersampling factor


def make(size, path):
    n = size * SS
    u = n / 256
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # dotted route (evenly spaced) leading toward the pin tip
    K = 9
    for i in range(K):
        t = i / (K - 1)
        x = 24 + 96 * t
        y = 222 + 14 * math.sin(t * math.pi * 1.5) - 8 * t
        r = (4 + 3.5 * t) * u
        d.ellipse([x * u - r, y * u - r, x * u + r, y * u + r], fill=DARK)

    # pin body (triangle tangent to the circle, so no notch at the shoulders)
    cx, cy, R = 150 * u, 100 * u, 78 * u
    tip = (150 * u, 232 * u)
    th = math.acos(R / (tip[1] - cy))
    d.polygon([
        (cx - R * math.sin(th), cy + R * math.cos(th)),
        (cx + R * math.sin(th), cy + R * math.cos(th)),
        tip,
    ], fill=BLUE)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=BLUE)

    # white inner disc with house
    r2 = 56 * u
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=WHITE)
    hx, hy = cx, cy + 4 * u
    d.polygon([(hx - 38 * u, hy - 2 * u), (hx, hy - 38 * u), (hx + 38 * u, hy - 2 * u)], fill=BLUE)
    d.rectangle([hx - 26 * u, hy - 4 * u, hx + 26 * u, hy + 30 * u], fill=BLUE)
    d.rectangle([hx - 8 * u, hy + 10 * u, hx + 8 * u, hy + 30 * u], fill=WHITE)

    im.resize((size, size), Image.LANCZOS).save(path)


out = sys.argv[1]
make(256, f"{out}/icon.png")
make(512, f"{out}/icon@2x.png")
