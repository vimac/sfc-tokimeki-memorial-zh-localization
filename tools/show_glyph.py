"""Print ROM font glyphs as ASCII art in the terminal, optionally with
matched candidate characters from several reference fonts.

Usage:
  python3 tools/show_glyph.py 0A00 0B12 0102      # just game glyphs
  python3 tools/show_glyph.py --match 0A00-0A0F   # game glyph + per-font best match
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import romlib
import extract_font as ef

NOTO_DIR = "/usr/share/fonts/google-noto-sans-cjk-fonts"
WQY = "/usr/share/fonts/wqy-bitmap/wenquanyi_12pt.pcf"


def glyph_ascii(rows):
    lines = []
    for v in rows:
        lines.append("".join("#" if v & (0x8000 >> x) else "." for x in range(16)))
    return lines


def ref_ascii(ch, fontpath, size=16):
    f = ImageFont.truetype(fontpath, size)
    img = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(img)
    d.text((8, 8), ch, fill=255, font=f, anchor="mm")
    rows = []
    for r in range(16):
        v = 0
        for x in range(16):
            v |= (1 if img.getpixel((x, r)) >= 128 else 0) << (15 - x)
        rows.append(v)
    return glyph_ascii(rows), rows


def iou(a, b):
    ia = a.bit_count(); ib = b.bit_count()
    i = (a & b).bit_count()
    return i / (ia + ib - i) if i else 0.0


def rowints(rows):
    return sum(rows[r] << ((15 - r) * 16) for r in range(16))


def match_one(gi, refs):
    data = romlib.load()
    grows = ef.glyph_at(data, gi)
    g = rowints(grows)
    out = {}
    for name, path, size in refs:
        f = ImageFont.truetype(path, size)
        best = (None, -1)
        # try a broad slice of JIS kanji + kana via cp932 codes
        for hi in list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)):
            for lo in range(0x40, 0x100):
                if lo == 0x7F:
                    continue
                try:
                    ch = bytes([hi, lo]).decode("cp932")
                except UnicodeDecodeError:
                    continue
                img = Image.new("L", (16, 16), 0)
                d = ImageDraw.Draw(img)
                d.text((8, 8), ch, fill=255, font=f, anchor="mm")
                v = 0
                for r in range(16):
                    for x in range(16):
                        v |= (1 if img.getpixel((x, r)) >= 128 else 0) << (15 - x)
                s = iou(g, v)
                if s > best[1]:
                    best = (ch, s)
        lines, _ = ref_ascii(best[0], path, size)
        out[name] = (best[0], best[1], lines)
    return grows, out


if __name__ == "__main__":
    args = sys.argv[1:]
    do_match = "--match" in args
    args = [a for a in args if a != "--match"]
    refs = [
        ("NotoReg", os.path.join(NOTO_DIR, "NotoSansCJK-Regular.ttc"), 16),
        ("NotoBold", os.path.join(NOTO_DIR, "NotoSansCJK-Bold.ttc"), 16),
        ("WQY12", WQY, 16),
    ]
    idxs = []
    for a in args:
        if "-" in a:
            lo, hi = a.split("-")
            idxs.extend(range(int(lo, 16), int(hi, 16) + 1))
        else:
            idxs.append(int(a, 16))
    data = romlib.load()
    for gi in idxs[:40]:
        grows = ef.glyph_at(data, gi)
        cols = [glyph_ascii(grows)]
        heads = [f"glyph {gi:04X}"]
        if do_match:
            grows, m = match_one(gi, refs)
            cols = [glyph_ascii(grows)]
            heads = [f"glyph {gi:04X}"]
            for name, (ch, s, lines) in m.items():
                cols.append(lines)
                heads.append(f"{name} '{ch}' {s:.2f}")
        sep = "   "
        print(" | ".join(h.ljust(16) for h in heads))
        for r in range(16):
            print(sep.join(c[r] for c in cols))
        print()
