"""Generates a simple placeholder brand icon (pin on a track). Needs Pillow."""
import sys
from PIL import Image, ImageDraw

def make(size, path):
    s = size / 256
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], 48 * s, fill=(30, 100, 200, 255))
    d.line([(40 * s, 200 * s), (100 * s, 170 * s), (160 * s, 205 * s), (216 * s, 170 * s)],
           fill=(255, 255, 255, 140), width=max(1, int(8 * s)), joint="curve")
    cx, cy, r = 128 * s, 100 * s, 44 * s
    d.polygon([(cx - r * 0.8, cy + r * 0.6), (cx + r * 0.8, cy + r * 0.6), (cx, 190 * s)], fill="white")
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
    d.ellipse([cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4], fill=(30, 100, 200, 255))
    im.save(path)

out = sys.argv[1]
make(256, f"{out}/icon.png")
make(512, f"{out}/icon@2x.png")
