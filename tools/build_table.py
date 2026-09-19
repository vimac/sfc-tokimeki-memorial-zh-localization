"""Auto-build the glyph->character table by bitmap matching (v3).

References:
  - WenQuanYi Bitmap Song 12pt (= native 16 px PCF bitmap, binary)  [primary]
  - Noto Sans CJK JP Bold / Black at 16 px, threshold 100           [JIS coverage]
Per (glyph, char) the best IoU across references wins; +-1 px shifts are
tried in stage 2 on the top-15 candidates of a cheap stage-1 scan.

Output: out/table.txt, out/font/match_check_*.png
"""
import os
import sys
import time
import unicodedata

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import romlib
import extract_font as ef

OUT = os.path.join(os.path.dirname(__file__), "..", "out")
WQY = "/usr/share/fonts/wqy-bitmap/wenquanyi_12pt.pcf"
NOTO = "/usr/share/fonts/google-noto-sans-cjk-fonts"
REFS = [
    (WQY, 16, 128),
    (os.path.join(NOTO, "NotoSansCJK-Bold.ttc"), 16, 100),
    (os.path.join(NOTO, "NotoSansCJK-Black.ttc"), 16, 100),
    (os.path.join(NOTO, "NotoSansCJK-Regular.ttc"), 16, 95),
]


def candidates():
    seen = set()
    for c in range(0x20, 0x7F):
        seen.add(chr(c)); yield chr(c)
    for c in range(0xA1, 0xE0):
        ch = chr(c)
        if ch not in seen:
            seen.add(ch); yield ch
    for hi in list(range(0x81, 0xA0)) + list(range(0xE0, 0xF0)):
        for lo in range(0x40, 0x100):
            if lo == 0x7F:
                continue
            try:
                ch = bytes([hi, lo]).decode("cp932")
            except UnicodeDecodeError:
                continue
            if ch not in seen:
                seen.add(ch); yield ch


def to_int(img):
    v = 0
    for r in range(16):
        for x in range(16):
            v = (v << 1) | (1 if img.getpixel((x, r)) >= 128 else 0)
    return v


def shift_int(v, dx, dy):
    mask = (1 << 16) - 1
    rows = [(v >> ((15 - r) * 16)) & mask for r in range(16)]
    out = 0
    for r in range(16):
        sr = r - dy
        if 0 <= sr < 16:
            row = rows[sr]
            row = row >> dx if dx >= 0 else (row << -dx) & mask
            out |= row << ((15 - r) * 16)
    return out


def iou(a, b):
    i = (a & b).bit_count()
    if not i:
        return 0.0
    return i / (a.bit_count() + b.bit_count() - i)


def render_ref(fonts, ch):
    """Return list of 256-bit ints, one per reference font."""
    outs = []
    for font, thr in fonts:
        img = Image.new("L", (16, 16), 0)
        d = ImageDraw.Draw(img)
        d.text((8, 8), ch, fill=255, font=font, anchor="mm")
        v = 0
        for r in range(16):
            for x in range(16):
                v = (v << 1) | (1 if img.getpixel((x, r)) >= thr else 0)
        if v:
            outs.append(v)
    return outs


def ref_png(ch):
    img = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(img)
    d.text((8, 8), ch, fill=255, font=ImageFont.truetype(WQY, 16), anchor="mm")
    return img


def main():
    t0 = time.time()
    data = romlib.load()
    n = ef.N_GLYPHS
    glyphs = [ef.glyph_at(data, i) for i in range(n)]
    gint = [sum(rows[r] << ((15 - r) * 16) for r in range(16)) for rows in glyphs]
    gpop = [g.bit_count() for g in gint]

    fonts = [(ImageFont.truetype(p, s), thr) for p, s, thr in REFS]
    chars = list(candidates())
    print(f"{len(chars)} candidate chars, {n} glyphs")

    cands = []  # (ch, [ints])
    for ch in chars:
        vs = render_ref(fonts, ch)
        if vs:
            cands.append((ch, vs))
    print(f"{len(cands)} renderable candidates ({time.time()-t0:.0f}s)")

    flat = []
    for ch, vs in cands:
        for v in vs:
            flat.append((ch, v, v.bit_count()))
    print(f"{len(flat)} bitmaps total")

    results = []
    for gi in range(n):
        g = gint[gi]
        if g == 0:
            results.append((None, 0.0)); continue
        gp = gpop[gi]
        scored = []
        for ch, v, vp in flat:
            if abs(gp - vp) > 0.55 * max(gp, vp):
                continue
            s = iou(g, v)
            if s > 0.3:
                scored.append((s, ch, v))
        scored.sort(reverse=True)
        best_ch, best_s = None, -1.0
        for s0, ch, v in scored[:15]:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    s = iou(g, shift_int(v, dx, dy))
                    if s > best_s:
                        best_s, best_ch = s, ch
        results.append((best_ch, best_s))
        if gi % 384 == 0:
            print(f"  glyph {gi:04X} ({time.time()-t0:.0f}s)")

    good = sum(1 for ch, s in results if ch and s >= 0.45)
    print(f"matched IoU>=0.45: {good}/{n}")

    with open(os.path.join(OUT, "table.txt"), "w", encoding="utf-8") as f:
        f.write("# Tokimeki Memorial SFC main font glyph table\n")
        f.write("# GGGG U+XXXX <char> <IoU> <unicode name>\n")
        for i, (ch, s) in enumerate(results):
            if ch is None:
                f.write(f"{i:04X} U+0000  (empty)  0.000\n")
            else:
                f.write(f"{i:04X} U+{ord(ch):04X} {ch} {s:.3f}  # "
                        f"{unicodedata.name(ch, '?')[:36]}\n")

    # QA sheets: game glyph | WQY render side by side
    cols, per_sheet, sc, cell = 8, 256, 3, 20
    for base in range(0, n, per_sheet):
        rows_n = per_sheet // cols
        img = Image.new("L", (cols * cell * sc, rows_n * cell * sc), 255)
        d = ImageDraw.Draw(img)
        for k in range(per_sheet):
            gi = base + k
            if gi >= n:
                break
            gx = (k % cols) * cell * sc
            gy = (k // cols) * cell * sc
            img.paste(ef.glyph_png(glyphs[gi], sc), (gx, gy + 14))
            ch, s = results[gi]
            if ch:
                rpng = ref_png(ch).resize((16 * sc, 16 * sc), Image.NEAREST)
                rpng = rpng.point(lambda p: 255 - p)
                img.paste(rpng, (gx + 2 * sc, gy + 14))
            d.text((gx + 1, gy), f"{gi:04X}", fill=100)
            d.text((gx + 42, gy), f"{s:.2f}" if ch else "--", fill=150)
        img.save(os.path.join(OUT, "font", f"match_check_{base:04X}.png"))
    print("table.txt + QA sheets written")


if __name__ == "__main__":
    main()
