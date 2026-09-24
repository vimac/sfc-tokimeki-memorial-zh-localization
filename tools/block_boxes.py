"""Split any TEXT_PTRS block into the byte spans the pointer grid freezes.

Two things make a block safe or unsafe to re-lay-out, and both are read off the
engine rather than guessed:

* a box start is `block base + 2 * script operand`, and the engine rewinds until the
  byte before the cursor is in TERM = {$0A, $A0..$A7}, so every offset that *follows*
  a TERM byte is a possible entry point.  A raw byte scan cannot find those: a
  2-byte glyph pair whose low byte is $A6 looks exactly like a terminator.  So TERM
  positions must come out of an atom walk.
* control codes are not all one byte.  $00/$01/$02/$04/$07/$08/$28 eat one operand,
  $09 two, $03 three, $0F four, $30-$37 one (tools/ctrl_advance.py reads each
  handler's `JMP $CAA2/$CAA0/$CA9E/$CA9C/$CA9A` tail = advance 1..5).  Walking them as
  one byte desynchronises everything after the first hit -- which is what injects
  phantom syllables into a block that uses them heavily (block 8 has 321 $01s).

usage: python3 tools/block_boxes.py <block> [--json out.json] [--end off] [--raw]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

BLOCKS = 160
# total bytes consumed by a control code, including the code byte itself -- one copy
# of the table, measured by tools/ctrl_advance.py and documented in
# docs/research/control-codes.md.
WIDTHS = B.CTRL_WIDTH
TERM = {0x0A} | set(range(0xA0, 0xA8))
BOX_END = set(range(0xA0, 0xA8))
LINE_END = set(range(0xA8, 0xAE))
# $A0-$A7 are "<punct> $0C" (the ● press-A box end) and $A8-$AD "<punct> $14"
# (sentence end plus a line break inside the same box).
PUNCT = {0xA0: '。', 0xA1: '？', 0xA2: '！', 0xA3: '。）', 0xA4: '。」',
         0xA5: '…」', 0xA6: '？」', 0xA7: '！」',
         0xA8: '。', 0xA9: '？', 0xAA: '！', 0xAB: '…', 0xAC: '、', 0xAD: '…'}
# Deliberately *not* listed here: $09, which an old note called a full-width space.
# Its handler $80:CC20 loads a 16-bit tile-cursor operand and the dispatcher eats 3
# bytes, so it belongs to the width table and prints as raw hex below.
CTRL_CH = {0x12: '〔姓〕', 0x13: '〔名〕', 0x14: '\n', 0x25: '†', 0x2E: '',
           0x00: '', 0x0A: '\x00'}

_CACHE = {}


def macro_text(rom, key, depth=0, seen=()):
    """Flat text of a dictionary entry: $AE-$E7 take one byte, $E8xx-$EFxx two."""
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if key in BOX_END or key in LINE_END:
        _CACHE[key] = PUNCT[key]
        return PUNCT[key]
    if key in seen or depth > 4:
        _CACHE[key] = ''
        return ''
    addr = (rom.phrase_addr(key) if key < 0xE8
            else rom.sub_addr(key >> 8, key & 0xFF))
    if addr is None:
        _CACHE[key] = ''
        return ''
    s = _flat(rom, addr, depth + 1, seen + (key,))
    _CACHE[key] = s
    return s


def _flat(rom, addr, depth, seen):
    """Entry body as one line, stepping by the same control widths as everywhere else."""
    d, out, i = rom.data, [], addr
    while i < addr + 0x60:
        b = d[i]
        if b == 0x00 or b == 0x0A:
            break
        if b < 0x40:
            w = WIDTHS.get(b, 1)
            out.append(CTRL_CH.get(b, '⟨%s⟩' % bytes(d[i:i + w]).hex()))
            i += w
        elif b < 0xA0:
            out.append(T.idx_to_char(rom.sb_entry(b)) or '?')
            i += 1
        elif b < 0xE8:
            out.append(macro_text(rom, b, depth, seen) if depth <= 4 else '')
            i += 1
        elif b < 0xF0:
            out.append(macro_text(rom, (b << 8) | d[i + 1], depth, seen))
            i += 2
        else:
            out.append(T.idx_to_char(((b << 8) | d[i + 1]) & 0x0FFF) or '?')
            i += 2
    return ''.join(out).split('\n')[0]


def width(code):
    return WIDTHS.get(code, 1)


def atoms(rom, lo, hi, sb=None):
    """Byte range -> [(offset, raw bytes, kind, text)] honouring control widths."""
    d, sb, i, out = rom.data, (sb or rom.sb_entry), lo, []
    while i < hi:
        b, p = d[i], i
        if b < 0x40:
            w = min(width(b), hi - i)
            raw = bytes(d[i:i + w])
            txt = CTRL_CH.get(b)
            kind = 'nl' if b == 0x14 else ('end' if b == 0x0A else 'ctrl')
            out.append((p, raw, kind, txt if txt is not None else '⟨%s⟩' % raw.hex()))
            i += w
        elif b < 0xA0:
            out.append((p, bytes([b]), 'glyph', T.idx_to_char(sb(b)) or '?'))
            i += 1
        elif b < 0xE8:
            out.append((p, bytes([b]), 'macro' if b in TERM else 'word',
                        PUNCT[b] if b in TERM else macro_text(rom, b)))
            i += 1
        elif b < 0xF0:
            k = (b << 8) | (d[i + 1] if i + 1 < hi else 0)
            out.append((p, bytes(d[i:i + 2]), 'word', macro_text(rom, k)))
            i += 2
        else:
            idx = (((b << 8) | (d[i + 1] if i + 1 < hi else 0)) & 0x0FFF)
            out.append((p, bytes(d[i:i + 2]), 'glyph', T.idx_to_char(idx) or '?'))
            i += 2
    got = b''.join(a[1] for a in out)
    assert got == bytes(d[lo:hi]), 'atom walk lost bytes: %d vs %d' % (len(got), hi - lo)
    return out


def segments(rom, lo, hi):
    """[(kind, offset, nbytes, [lines])], split at TERM atoms only."""
    out, cur, lines, off = [], [], [], lo
    for p, raw, kind, txt in atoms(rom, lo, hi):
        code = raw[0]
        cur.append(txt)
        if code in TERM and len(raw) == 1:
            lines.append(''.join(cur) + (PUNCT[code] if code in PUNCT else ''))
            out.append(('BOX' if code in BOX_END else 'STEP', off, p + 1 - off,
                        [x for x in lines if x]))
            cur, lines, off = [], [], p + 1
    if cur or lines:
        lines.append(''.join(cur))
        out.append(('TAIL', off, hi - off, [x for x in lines if x]))
    return out


def main():
    blk = int(sys.argv[1])
    rom = T.Rom('rom_original_japanese.sfc')
    lo = rom.text_ptr(blk)
    after = sorted({p for p in (rom.text_ptr(i) for i in range(BLOCKS))
                    if p is not None and p > lo})
    hi = int(sys.argv[sys.argv.index('--end') + 1], 16) if '--end' in sys.argv \
        else (after[0] if after else lo + 0x200)
    if '--raw' in sys.argv:
        for p, raw, kind, txt in atoms(rom, lo, hi):
            print('%06X %-14s %-5s %s' % (p, raw.hex(), kind, txt))
        return
    segs = segments(rom, lo, hi)
    if '--json' in sys.argv:
        json.dump([{'n': n, 'kind': k, 'off': o, 'bytes': nb, 'lines': ls}
                   for n, (k, o, nb, ls) in enumerate(segs)],
                  open(sys.argv[sys.argv.index('--json') + 1], 'w'),
                  ensure_ascii=False, indent=0)
    for n, (k, o, nb, ls) in enumerate(segs):
        print('%3d %-4s @%06X %4dB | %s' % (n, k, o, nb, ' / '.join(ls)))
    print('block %d: base %06X span %dB, %d segments, %dB accounted'
          % (blk, lo, hi - lo, len(segs), sum(s[2] for s in segs)), file=sys.stderr)


if __name__ == '__main__':
    main()
