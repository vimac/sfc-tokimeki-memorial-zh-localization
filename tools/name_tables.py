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


def record(s, e):
    """Glyph-code pairs -> characters, with anything unaccounted for spelled out."""
    out = []
    for j in range(s, e, 2):
        i = ((d[j] << 8) | d[j + 1]) & 0x0FFF
        out.append(slot2ch.get(i) or '{%03X}' % i)
    return ''.join(out)


for hi in POOL_HEADS:
    offs = [d[hi + 3 + k] for k in range(N_OFFS)]
    names = [record(hi + o, d.index(0x0A, hi + o)) for o in offs]
    pool += names
    bad = [n for n in names if '{' in n]
    print('opcode %02X pool @%#x: %2d names, %d slots not ours%s'
          % (d[hi + 1], hi, len(names), len(bad), ': ' + ' '.join(bad) if bad else ''))
    print('   ', ' '.join(names))
    assert offs == sorted(offs) and all(d[hi + o - 1] == 0x0A or o == offs[0]
                                       for o in offs), 'offsets point mid-record'

off, surnames = SURNAME[0], []
while off < SURNAME[1]:
    e = d.index(0x0A, off)
    surnames.append(record(off, e))
    off = e + 1
bad = [n for n in surnames if '{' in n]
print('nameplate surnames @%#x: %d names, %d slots not ours%s'
      % (SURNAME[0], len(surnames), len(bad), ': ' + ' '.join(bad) if bad else ''))
print('   ', ' '.join(surnames))
names = pool + surnames
junk = [n for n in names
        if any('\u3040' <= c <= '\u30ff' or c in '{}' for c in n)]
print('%s: %d/%d name records still hold kana or an unknown slot'
      % ('PASS' if not junk else 'FAIL', len(junk), len(names)))
