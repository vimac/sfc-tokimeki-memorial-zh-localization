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
import prologue_boxes as PB

BLOCKS = 160
# total bytes consumed by a control code, including the code byte itself
WIDTHS = {0x00: 2, 0x01: 2, 0x02: 2, 0x03: 4, 0x04: 2, 0x07: 2, 0x08: 2, 0x09: 3,
          0x0F: 5, 0x28: 2}
TERM = {0x0A} | set(range(0xA0, 0xA8))


def width(code):
    if code in WIDTHS:
        return WIDTHS[code]
    if 0x30 <= code <= 0x37:
        return 2
    return 1


def atoms(rom, lo, hi, sb=None):
    """Byte range -> [(offset, raw bytes, kind, text)] honouring control widths."""
    d, sb, i, out = rom.data, (sb or rom.sb_entry), lo, []
    while i < hi:
        b, p = d[i], i
        if b < 0x40:
            w = min(width(b), hi - i)
            raw = bytes(d[i:i + w])
            txt = PB.CTRL_CH.get(b)
            kind = 'nl' if b == 0x14 else ('end' if b == 0x0A else 'ctrl')
            out.append((p, raw, kind, txt if txt is not None else '⟨%s⟩' % raw.hex()))
            i += w
        elif b < 0xA0:
            out.append((p, bytes([b]), 'glyph', T.idx_to_char(sb(b)) or '?'))
            i += 1
        elif b < 0xE8:
            out.append((p, bytes([b]), 'macro' if b in TERM else 'word',
                        PB.PUNCT[b] if b in TERM else PB.macro_text(rom, b)))
            i += 1
        elif b < 0xF0:
            k = (b << 8) | (d[i + 1] if i + 1 < hi else 0)
            out.append((p, bytes(d[i:i + 2]), 'word', PB.macro_text(rom, k)))
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
            lines.append(''.join(cur) + (PB.PUNCT[code] if code in PB.PUNCT else ''))
            out.append(('BOX' if code in PB.BOX_END else 'STEP', off, p + 1 - off,
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
