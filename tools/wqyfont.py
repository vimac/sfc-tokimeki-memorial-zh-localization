"""WenQuanYi 13px -> Tokimeki Memorial 14x14 1bpp glyph records.

Record format (proven by rendering the stock ROM font at 0x3E8000):
  28 bytes = 14 little-endian 16-bit row words, top row first.
  bit15 = leftmost pixel of the row, bits 15..2 are the 14 pixel columns;
  the low 2 bits of every word are unused.
  slot idx -> file offset 0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28
"""
import sys, os
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = '/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf'
W = H = 14
_font = None


def font():
    global _font
    if _font is None:
        # size 14 is the only size PIL accepts from this PCF's single strike
        _font = ImageFont.truetype(FONT_PATH, 14)
    return _font


def ink(ch):
    """Ink bbox (x0, x1, y0, y1) relative to the pen origin, or None if blank.

    WenQuanYi 13px is a bitmap strike, so this measures it rather than assuming: full
    kanji are 13 columns x 13 rows with 0-1 columns of left bearing, and a few are wider
    or taller (装 is 14 across, （ reaches row 14).
    """
    im = Image.new('L', (48, 48), 0)
    ImageDraw.Draw(im).text((0, 0), ch, font=font(), fill=255)
    px = im.load()
    pts = [(x, y) for y in range(48) for x in range(48) if px[x, y] >= 128]
    if not pts:
        return None
    return (min(p[0] for p in pts), max(p[0] for p in pts),
            min(p[1] for p in pts), max(p[1] for p in pts))


def fit(ch, dx, dy):
    """Largest offset <= (dx, dy) that keeps every ink dot inside the drawn 14x14.

    A record draws columns 0..13 and rows 0..13 only, so an over-size glyph must slide
    back instead of losing its last column: at dx=2 the crop silently cut the right
    stroke of 1,019 of the 1,154 characters this build ships.
    """
    b = ink(ch)
    if not b:
        return dx, dy
    return (max(-b[0], min(dx, 13 - b[1])), max(-b[2], min(dy, 13 - b[3])))


def bitmap(ch, dx=0, dy=0):
    """14x14 list of rows of 0/1. dx/dy shift the glyph right/down."""
    dx, dy = fit(ch, dx, dy)
    im = Image.new('L', (32, 32), 0)
    ImageDraw.Draw(im).text((9 + dx, 9 + dy), ch, font=font(), fill=255)
    px = im.crop((9, 9, 9 + W, 9 + H)).load()
    return [[1 if px[x, y] >= 128 else 0 for x in range(W)] for y in range(H)]


def record(ch, dx=0, dy=0):
    rows = bitmap(ch, dx, dy)
    out = bytearray()
    for row in rows:
        w = 0
        for x, v in enumerate(row):
            if v:
                w |= 1 << (15 - x)
        out += bytes((w & 0xFF, w >> 8))
    return bytes(out)


def art(ch, dx=0, dy=0):
    return [''.join('#' if v else '.' for v in r)
            for r in bitmap(ch, dx, dy)]


if __name__ == '__main__':
    asc, desc = font().getmetrics()
    print('metrics ascent=%d descent=%d' % (asc, desc))
    dx, dy = int(os.environ.get('DX', 0)), int(os.environ.get('DY', 0))
    for ch in sys.argv[1:] or '中国。、':
        print('%s dx=%+d dy=%+d' % (ch, dx, dy))
        for r in art(ch, dx, dy):
            print('   ' + r)
