"""Which control codes does a block *execute*, and are any of them wide?

The dispatcher's control path ($80:CAEB) looks up a handler per byte and the
handler tail decides the advance: `JMP $CAA2` = 1 byte, `JMP $CAA0` = 2,
`JMP $CA9E` = 3.  The codes that are *not* 1 byte are $00/$01/$02/$04/$07/$08/$28
and the pen family $30-$37 (2), $09 (3), $03 (4) and $0F (5); everything else in
$00-$2E, including $25/$26/$2F, eats just itself.  Copying a wide code as a lone
byte while the engine eats its operand shifts every later atom -- which is what
garbles a length-changed (Chinese) stream.

usage: python3 tools/ctrl_widths.py [rom] [block]
"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_zh as B

# advance width per control code: measured by tools/ctrl_advance.py, and the one
# copy of that table is build_zh.CTRL_WIDTH (everything not listed is 1).
WIDE = {c: w for c, w in B.CTRL_WIDTH.items() if w > 1}

ROM = sys.argv[1] if len(sys.argv) > 1 else T.ROM_JP
BLK = int(sys.argv[2]) if len(sys.argv) > 2 else 144

rom = T.Rom(ROM)
code = B.Codec(rom)
s, e = B.block_extent(rom, BLK)
atoms = code.walk(s, e)
cnt = collections.Counter(c for a in atoms for c in a['ctrl'])
print('block %d: %d bytes, %d atoms, %d executed control bytes, %d distinct'
      % (BLK, e - s, len(atoms), sum(cnt.values()), len(cnt)))
print('executed:', ' '.join('%02X:%d' % (k, v) for k, v in sorted(cnt.items())))
hits = [(k, cnt[k]) for k in WIDE if k in cnt]
print('operand-taking codes present:', hits or 'none')
raw = collections.Counter(b for b in rom.data[s:e] if b < 0x40)
print('codes that only ever appear inside a 2-byte glyph pair:',
      ' '.join('%02X:%d' % (k, raw[k] - cnt.get(k, 0))
               for k in sorted(raw) if raw[k] - cnt.get(k, 0)))
seen, pos = {}, s
for a in atoms:
    for c in a['ctrl']:
        if WIDE.get(c, 1) > 1 and c not in seen:
            seen[c] = '  $%02X width %d at file %#x' % (c, WIDE[c], pos)
    pos += len(a['raw'])
print('first execution of each operand-taking code (move these together with '
      'their operand):')
for c in sorted(seen):
    print(seen[c])
