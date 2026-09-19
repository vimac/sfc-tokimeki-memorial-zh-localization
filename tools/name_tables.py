"""Decode the name tables out of a built ROM, through the tables' OWN offsets.

`build_prologue.verify_name_tables` checks the records it wrote; this one is the
independent read -- it takes the three `$E803`/`$E804`/`$E805` offset tables and the
surname list as they now sit in the file and follows the distances the engine will,
so a record that no longer begins where its table says cannot hide.  Indices resolve
through `docs/research/glyph_alloc.json`, the build's own character report, which is
the only thing that knows what a freshly claimed slot is supposed to read as.

usage: python3 tools/name_tables.py [rom]

Run it against the Japanese ROM as the contrast case: every stock slot the tables
address reports as `not ours`, because that report only knows the slots this patch
allocated.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'rom_prologue_zh.sfc')
POOL_HEADS = (0x21A2A6, 0x21A2B7, 0x21A2C8)     # $E804 / $E805 / $E803
SURNAME = (0x180C0, 0x18107)                    # right after the 96-word SB table
N_OFFS = 14

a = json.load(open(os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')))
slot2ch = {int(v, 16): c for g in a for c, v in a[g].items()}
d = open(ROM, 'rb').read()
pool = []


def record(s):
    """(characters, offset just past the terminator) for the record at `s`.

    Read the way the engine reads it: a `$F0-$FF` lead takes the next byte as its
    operand, and only a `$0A` in a *lead* position ends the record.  Scanning for the
    byte would cut 诗织 in half, because 诗 is index $060A.
    """
    out, j = [], s
    while d[j] != 0x0A:
        i = ((d[j] << 8) | d[j + 1]) & 0x0FFF
        out.append(slot2ch.get(i) or '{%03X}' % i)
        j += 2
    return ''.join(out), j + 1


for hi in POOL_HEADS:
    offs = [d[hi + 3 + k] for k in range(N_OFFS)]
    names = [record(hi + o)[0] for o in offs]
    pool += names
    bad = [n for n in names if '{' in n]
    print('opcode %02X pool @%#x: %2d names, %d slots not ours%s'
          % (d[hi + 1], hi, len(names), len(bad), ': ' + ' '.join(bad) if bad else ''))
    print('   ', ' '.join(names))
    assert offs == sorted(offs) and all(d[hi + o - 1] == 0x0A or o == offs[0]
                                       for o in offs), 'offsets point mid-record'

off, surnames = SURNAME[0], []
while off < SURNAME[1]:
    name, off = record(off)
    surnames.append(name)
bad = [n for n in surnames if '{' in n]
print('nameplate surnames @%#x: %d names, %d slots not ours%s'
      % (SURNAME[0], len(surnames), len(bad), ': ' + ' '.join(bad) if bad else ''))
print('   ', ' '.join(surnames))
names = pool + surnames
junk = [n for n in names
        if any('\u3040' <= c <= '\u30ff' or c in '{}' for c in n)]
print('%s: %d/%d name records still hold kana or an unknown slot'
      % ('PASS' if not junk else 'FAIL', len(junk), len(names)))
