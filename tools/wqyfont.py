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


def bitmap(ch, dx=0, dy=0):
    """14x14 list of rows of 0/1. dx/dy shift the glyph right/down."""
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
