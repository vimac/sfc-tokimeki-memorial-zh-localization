"""Render a patched TEXT_PTRS block straight from the ROM's font data.

Reads one block of a patched ROM, resolves every glyph code to the 28-byte
14x14 record the emulator would fetch, and composes one image per dialog box.
$14 breaks a line, $0C/$0A close a box, so the picture shows both the injected
WenQuanYi glyphs and whether the control stream still lays text out sanely.

This is the gate for a text batch that the prologue never shows (block 0's phone
pools answer calls that only exist mid-game), so a batch of translated boxes can
be looked at without booting an emulator: pass the block and the box range the
batch covers, and the labels come out with kana counted per box.

usage: python3 tools/render_prologue.py [rom] [block] [first:last]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import tmtext as T
import build_prologue as B

ROM = sys.argv[1] if len(sys.argv) > 1 else B.OUT_ROM
BLK = int(sys.argv[2]) if len(sys.argv) > 2 else B.BLOCK
# Which boxes to render: a whole block is 725 boxes for block 0, and everything past
# the translated prefix is still Japanese, so the range defaults to the leading boxes.
RANGE = sys.argv[3] if len(sys.argv) > 3 else ''
OUT = 'docs/research/render_%s%s' % (
    os.path.splitext(os.path.basename(ROM))[0],
    '' if BLK == B.BLOCK and not RANGE else '_b%d%s' % (BLK, RANGE.replace(':', '-')))
CELL, PITCH, MARGIN = 16, 16, 6
BOX_CTRL, LINE_CTRL_B = (0x0C, 0x0A), 0x14
NAME_CTRL = (0x12, 0x13)


def glyph_stream(code, start, end):
    """encoded bytes -> stream of ('g', slot) | ('c', ctrl) | ('n', marker).

    Macro folds are expanded through the body's own token list, so the control
    bytes a macro emits ($14 inside $A8-$AD, $0C inside $A0-$A7) land where the
    engine will act on them.  The body's trailing $0A return is not content.

    Returns the stream plus the number of call sites left unexpanded: those are
    the runtime-variable bodies ($00/$0E/$0F parameters, a body that calls another
    macro), which no static reader can draw -- they are reported, not hidden.
    """
    out, ndrop = [], 0
    for a in code.walk(start, end):
        k = a['k']
        if k == 'c':
            out.append(('c', a['raw'][0]))
        elif k == 'g':
            r = a['raw']
            out.append(('g', code.sb[r[0]] if len(r) == 1
                        else ((r[0] << 8) | r[1]) & 0x0FFF))
        elif k == 'n':
            out.append(('n', a['raw'][0]))
        elif k == 'm':
            out += a['toks']
        elif k == 'v':
            ndrop += 1
    return out, ndrop


def boxes(stream):
    """control stream -> [[line[slot,...], ...], ...] per dialog box."""
    out, lines, cur = [], [], []
    for tag, v in stream:
        if tag == 'n':
            continue                     # surname/given-name insertion marker
        if tag != 'c':
            cur.append(v)
            continue
        if v == LINE_CTRL_B:
            lines.append(cur)
            cur = []
        elif v in BOX_CTRL:
            if cur:
                lines.append(cur)
                cur = []
            if lines:
                out.append(lines)
            lines = []
    if cur:
        lines.append(cur)
    if lines:
        out.append(lines)
    return out


def rows(rom, idx):
    o = T.glyph_offset(idx)
    grid = []
    for y in range(14):
        w = rom.data[o + y * 2] | (rom.data[o + y * 2 + 1] << 8)
        grid.append([(w >> (15 - x)) & 1 for x in range(14)])
    return grid


def draw(box, rom, path):
    w = MARGIN * 2 + CELL * max(len(l) for l in box)
    h = MARGIN * 2 + PITCH * len(box)
    im = Image.new('L', (w, h), 216)
    px = im.load()
    for ln, line in enumerate(box):
        for cn, idx in enumerate(line):
            for y, row in enumerate(rows(rom, idx)):
                for x, v in enumerate(row):
                    if v:
                        px[MARGIN + cn * CELL + x, MARGIN + ln * PITCH + y] = 20
    im.save(path)


def montage(items, path, cols=3):
    if not items:
        return
    imgs = [im for _, im in items]
    wide = max(im.width for im in imgs)
    tall = max(im.height for im in imgs)
    rowsn = (len(items) + cols - 1) // cols
    sheet = Image.new('L', (cols * (wide + 8) + 8, rowsn * (tall + 22) + 8), 255)
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for n, (tag, im) in enumerate(items):
        cx, cy = (n % cols) * (wide + 8) + 8, (n // cols) * (tall + 22) + 8
        sheet.paste(im, (cx, cy))
        dr.text((cx, cy + im.height + 4), tag, fill=0)
    sheet.save(path)


def main():
    rom = T.Rom(ROM)
    code = B.Codec(rom)
    # The span tables come from the source ROM: name-pool records sit in the
    # sub-text table's dead zone, and their patched glyph pairs re-parse as
    # body offsets there (see patched_codec in build_prologue).
    ref = B.Codec(B.T.Rom(B.SRC_ROM))
    code.ph_off, code.ph_next = ref.ph_off, ref.ph_next
    code.sub_off, code.sub_next = ref.sub_off, ref.sub_next
    enc = json.load(open('docs/research/block%d_enc.json' % BLK,
                         encoding='utf-8'))
    total, cov = enc['total'], enc['cov']
    if BLK != B.BLOCK and not RANGE:
        # Which boxes a batch *claims* is the whole question, so say it out loud:
        # past the translated prefix every box is still Japanese, and rendering
        # those would only bury the ones that matter.
        raise SystemExit('block %d: pass the box range the batch covers, '
                         'e.g. 0:277 (%d segments translated)' % (BLK, cov))
    lo, hi = (int(x) for x in (RANGE.split(':') + [None])[:2]) if RANGE else (0, None)
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    slot2ch = {}
    alloc = json.load(open('docs/research/glyph_alloc.json', encoding='utf-8'))
    for kind in ('fresh', 'inplace'):
        for ch, idx in alloc[kind].items():
            slot2ch[int(idx, 16)] = ch
    # A dictionary body reads a glyph slot, and half the slots in this disc are
    # characters the JIS band never had.  Without the patch's own names every
    # Chinese body parses as "not plain text" and its call site is dropped, so the
    # box under-reads (批次 AH: 3,123 of 59,703 call sites).
    code.names = slot2ch

    start = rom.text_ptr(BLK)
    stream, ndrop = glyph_stream(code, start, start + total)
    bs = boxes(stream)
    print('%s block %d: %d bytes, %d segments translated -> %d boxes, %d lines, '
          '%d runtime-only call site(s)'
          % (os.path.basename(ROM), BLK, total, cov, len(bs),
             sum(len(b) for b in bs), ndrop))
    dist = {}
    for b in bs:
        dist[len(b)] = dist.get(len(b), 0) + 1
    print('lines per box:', dist)
    print('line widths (cells):', sorted({len(l) for b in bs for l in b}))

    items, labels, kana = [], [], 0
    for k, box in enumerate(bs[lo:hi + 1 if hi is not None else None], lo):
        tag = '%02d' % k
        draw(box, rom, '%s/box_%s.png' % (OUT, tag))
        # Ours first: a slot we redrawn is Chinese whatever the stock band called it.
        # The fallback decodes the untouched JIS bands, which is what makes an
        # untranslated box legible enough to count as Japanese rather than as '?'.
        text = ''.join(slot2ch.get(s) or T.idx_to_char(s) or '?'
                       for line in box for s in line)
        n = sum(0x3041 <= ord(c) <= 0x3096 or 0x30A1 <= ord(c) <= 0x30FA
                for c in text)
        kana += n
        labels.append('%s  %s%s' % (tag, text, '  [%d kana]' % n if n else ''))
        items.append((tag, Image.open('%s/box_%s.png' % (OUT, tag))))
    open('%s/labels.txt' % OUT, 'w', encoding='utf-8').write(
        '\n'.join(labels) + '\n')
    for n in range(0, len(items), 12):
        montage(items[n:n + 12], '%s/sheet_%02d.png' % (OUT, n // 12))
    print('boxes %s: %d rendered, %d kana cells, %d "?" cells'
          % (RANGE or 'all', len(items), kana,
             sum(l.count('?') for l in labels)))
    print('-> %s/box_*.png + %d sheets' % (OUT, (len(items) + 11) // 12))


if __name__ == '__main__':
    main()
