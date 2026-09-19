"""Which control codes does a block *execute*, and are any of them wide?

The dispatcher's control path ($80:CAEB) looks up a handler per byte and the
handler tail decides the advance: `JMP $CAA2` = 1 byte, `JMP $CAA0` = 2,
`JMP $CA9E` = 3.  $00, $01 and $28 jump through a 16-bit operand read with
`LDA [$B4],Y` (Y=1), so they are 2-byte instructions; $09 does the same with a
16-bit operand and advances 3.  Copying such a code as a lone byte while the
engine eats its operand shifts every later atom -- which is what garbles a
length-changed (Chinese) stream.

usage: python3 tools/ctrl_widths.py [rom] [block]
"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

# advance width per control code, read off the handler tails (tools/ctrl_advance.py)
WIDE = {0x00: 2, 0x01: 2, 0x09: 3, 0x28: 2}
UNKNOWN = {0x2F, 0x25, 0x26}          # 0x25/0x26 fall into the 1-byte delay tail

ROM = sys.argv[1] if len(sys.argv) > 1 else 'rom_original_japanese.sfc'
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
for a in atoms:
    for c in a['ctrl']:
        if c in WIDE or c in UNKNOWN:
            i = s + sum(len(x['raw']) for x in atoms[:atoms.index(a)])
            print('  !! %02X (width %d) at file %#x' % (c, WIDE.get(c, 0), i))
