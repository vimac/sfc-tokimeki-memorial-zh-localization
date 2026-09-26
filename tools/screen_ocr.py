"""Read what the engine actually drew, by matching screen cells to font records.

Eyeballing bitmaps in a screenshot is how the previous session misread its own
success, so this decodes the dialog box mechanically: every 16px cell is reduced
to the row-word pattern the drawer copies (rows 1..14, bit15 = leftmost pixel)
and looked up in the ROM's own font.  A cell that matches no record is reported
as '?', which is the garbling symptom.

usage: python3 tools/screen_ocr.py <rom> <frame.png> [...]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import tmtext as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def font_map(rom_path, alloc_path=None):
    """bitmap -> index, plus the label to print for an index.

    A slot that the patch took over must be labelled with its *new* Chinese
    character; T.idx_to_char() would report the JIS glyph that used to live
    there, which makes a correct screen read as Japanese garbage.
    """
    d = open(rom_path, 'rb').read()
    m = {}
    for i in range(T.MAX_INDEX):
        o = T.glyph_offset(i)
        key = bytes(d[o:o + 28])
        if key != b'\x00\x00' * 14:
            m.setdefault(key, []).append(i)
    labels = {}
    if alloc_path and os.path.exists(alloc_path):
        a = json.load(open(alloc_path))
        for group in ('fresh', 'inplace'):
            for ch, hx in a.get(group, {}).items():
                labels[int(hx, 16)] = ch
    return m, labels


def cells(img, x0, y0, w=16, x1=None):
    """row-word patterns for the grid whose first cell starts at (x0, y0).

    The record is 14 row *words*, so a glyph is 16 columns wide, not 14: the
    14px window used here made every wide kanji miss the lookup and come back
    as '?'.
    """
    ink = (np.asarray(img.convert('L')).astype(int) > 128)
    out = []
    h, w_ = ink.shape
    for y in range(y0, h - 14, 16):
        row = []
        for x in range(x0, w_ - w, 16):
            if x1 is not None and x >= x1:
                break
            blk = ink[y:y + 14, x:x + w]
            if not blk.any():
                row.append(None)
                continue
            words = bytearray()
            for r in range(14):
                v = 0
                for c in range(w):
                    if blk[r, c]:
                        v |= 1 << (15 - c)
                words += bytes((v & 0xFF, v >> 8))
            row.append(bytes(words))
        out.append(row)
    return out


def ocr(path, fm, labels, x0=127, y0=161, rows=3):
    """OCR the dialog box.  No 256px crop: the engine draws in 512px hi-res.

    x0=127 because cells 63..111 belong to the name plate and to the 「 the
    engine draws itself; pass 63 to see those too.

    Columns stop at x=400 because past that the box's own border/shadow art
    starts, and one of those tiles happens to be bit-identical to a font record
    (0x0DAD), which OCR'd as a stray kanji on every row.
    """
    im = Image.open(path)
    grid = cells(im, x0, y0, x1=400)
    lines = []
    for row in grid[:rows]:
        s = []
        for pat in row:
            if pat is None:
                continue
            hits = fm.get(pat)
            if not hits:
                s.append('?')
                continue
            i = hits[0]
            s.append(labels.get(i) or T.idx_to_char(i) or '{%04X}' % i)
        lines.append(''.join(s))
    return lines


if __name__ == '__main__':
    rom = sys.argv[1] if sys.argv[1].endswith('.sfc') else os.path.join(ROOT, sys.argv[1])
    frames = sys.argv[2:] or ['/tmp/play/pp_' + T.rom_tag(rom) + '/f011.png']
    fm, labels = font_map(rom, os.path.join(ROOT, 'docs/research/glyph_alloc.json'))
    for p in frames:
        print('%-12s %s' % (os.path.basename(p), ' / '.join(ocr(p, fm, labels))))
