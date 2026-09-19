"""Pick the WQY draw offset that best matches the stock ROM glyph placement.

Compares the ink bounding box of each shared kanji/kana in the ROM font
against WenQuanYi rendered at a candidate (dx,dy), and minimises the total
bbox error. A single global offset keeps characters' relative positions
intact (punctuation stays bottom-left, kanji stay centred).

(dx,dy) is a *ceiling*, not a shift: `wqyfont.fit()` slides an over-wide glyph back so no
dot lands on a column the hardware cannot draw, so every candidate >= that ceiling scores
identically. A candidate that would have needed the slide back is counted as `clip=` here
and excluded from BEST -- scoring one used to look optimal, because a glyph with its right
stroke cropped matches the stock box exactly. That is how dx=2 was originally chosen.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
from wqyfont import bitmap, fit

rom = T.Rom()


def rom_rows(idx):
    o = T.glyph_offset(idx)
    rows = []
    for r in range(14):
        w = rom.data[o + r * 2] | (rom.data[o + r * 2 + 1] << 8)
        rows.append([(w >> (15 - c)) & 1 for c in range(14)])
    return rows


def bbox(rows):
    pts = [(x, y) for y, r in enumerate(rows) for x, v in enumerate(r) if v]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


SAMPLE = '日月水火木金土学校生活部友情努力練習達成伝説樹君名前血液型趣味何今明日言思願気持強優真実恋心'


def main():
    glyphs = []
    for ch in SAMPLE:
        idx = T.char_to_idx(ch)
        if idx is None:
            continue
        glyphs.append((ch, idx, bbox(rom_rows(idx))))
    print('matched %d sample glyphs' % len(glyphs))
    best = None
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            err = n = clip = 0
            for ch, idx, rb in glyphs:
                if fit(ch, dx, dy) != (dx, dy):
                    clip += 1
                wb = bbox(bitmap(ch, dx, dy))
                if wb is None or rb is None:
                    continue
                err += sum(abs(a - b) for a, b in zip(wb, rb))
                n += 1
            avg = err / n
            if clip == 0 and (best is None or avg < best[0]):
                best = (avg, dx, dy)
            print('dx=%+d dy=%+d  mean bbox err=%.2f  clip=%d' % (dx, dy, avg, clip))
    print('\nBEST (no clip): dx=%+d dy=%+d (err %.2f)' % (best[1], best[2], best[0]))
    dx, dy = best[1], best[2]
    for ch, idx, rb in glyphs[:8]:
        wb = bbox(bitmap(ch, dx, dy))
        print('%s  rom=%s  wqy=%s' % (ch, rb, wb))


if __name__ == '__main__':
    main()
