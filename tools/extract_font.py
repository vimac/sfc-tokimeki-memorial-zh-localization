"""Final font extraction for the main 1BPP font.

Layout confirmed empirically:
  file offset 0x3E8000..0x400000 = 0x18000 bytes = 3072 glyphs
  glyph: 16x16 px, 1bpp, 2 bytes per row (MSB = leftmost pixel), 32 bytes
  glyph 0 at 0x3E8002 is all-zero (space); the +2 grid is anchored at 0x3E8000.

Outputs:
  out/font/font.png          full contact sheet (16 cols, labeled per row)
  out/font/font_zoom_*.png   zoomed slices for reading
  out/font/glyphs/<i>.png    individual glyphs (only on demand)
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import romlib

FONT_BASE = 0x3E8000
FONT_SIZE = 0x18000
N_GLYPHS = FONT_SIZE // 32
OUT = os.path.join(os.path.dirname(__file__), "..", "out", "font")


def glyph_at(data, idx):
    off = FONT_BASE + 2 + idx * 32
    g = data[off:off + 32]
    rows = [int.from_bytes(g[r * 2:r * 2 + 2], "big") for r in range(16)]
    return rows


def glyph_png(rows, scale=4):
    img = Image.new("L", (16, 16), 255)
    px = img.load()
    for r, v in enumerate(rows):
        for x in range(16):
            if v & (0x8000 >> x):
                px[x, r] = 0
    return img.resize((16 * scale, 16 * scale), Image.NEAREST)


def contact_sheet(data, first, count, cols=16, scale=2):
    rows_n = (count + cols - 1) // cols
    cell_h = 16 * scale + 10
    img = Image.new("L", (cols * (16 * scale + 2), rows_n * cell_h), 255)
    d = ImageDraw.Draw(img)
    for i in range(count):
        idx = first + i
        if idx >= N_GLYPHS:
            break
        g = glyph_png(glyph_at(data, idx), scale)
        gx = (i % cols) * (16 * scale + 2)
        gy = (i // cols) * cell_h
        img.paste(g, (gx, gy + 8))
        d.text((gx + 1, gy - 1), f"{idx:03X}", fill=120)
    return img


def glyph_width(rows):
    """Variable-width value: rightmost set pixel + 1 (0 for empty)."""
    w = 0
    for v in rows:
        for x in range(16):
            if v & (0x8000 >> x):
                w = max(w, x + 1)
    return w


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    data = romlib.load()
    print(f"font: 0x{FONT_BASE:X}+2, {N_GLYPHS} glyphs of 32B (last 2B of region: "
          f"{data[0x3FFFE0+30:0x400000].hex()})")

    full = contact_sheet(data, 0, N_GLYPHS, cols=16, scale=2)
    full.save(os.path.join(OUT, "font.png"))
    print("font.png:", full.size)

    # readable zoom slices
    for lo in range(0, N_GLYPHS, 256):
        contact_sheet(data, lo, 256, cols=16, scale=3).save(
            os.path.join(OUT, f"font_zoom_{lo:04X}.png"))

    # width table dump (for VWF analysis) + nonzero census
    widths = [glyph_width(glyph_at(data, i)) for i in range(N_GLYPHS)]
    with open(os.path.join(OUT, "widths.txt"), "w") as f:
        for i, w in enumerate(widths):
            f.write(f"{i:04X} {w}\n")
    nonempty = sum(1 for i in range(N_GLYPHS) if any(glyph_at(data, i)))
    print(f"non-empty glyphs: {nonempty}/{N_GLYPHS}; widths written to widths.txt")
