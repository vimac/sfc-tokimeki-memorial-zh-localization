"""Which glyph indices does the Japanese game actually reference?

There are no blank glyph records in this font - all 3509 slots hold live JIS
kanji - so "free slot" has to mean "slot no text in the game points at".
Walks every text block, name entry, phrase-macro body and sub-text body and
collects the indices they draw.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

rom = T.Rom()
used = set()

def walk(addr, depth=0, seen=()):
    if addr is None or addr in seen or depth > 4:
        return
    toks = T.decode(rom, addr, 0x2000, depth, 4)
    for t in toks:
        k = t[0]
        if k == 'sb':
            used.add(t[2])
        elif k == 'kanji':
            used.add(t[3])
        elif k == 'phrase':
            walk(rom.phrase_addr(t[1]), depth + 1, seen + (addr,))
        elif k == 'sub':
            walk(rom.sub_addr(t[1], t[2]), depth + 1, seen + (addr,))
        elif k in ('end', 'limit'):
            return

for i in range(T.PTR_COUNT):
    a, e = T.block_bytes(rom, i)
    if a is not None:
        walk(a)
for i in range(400):
    a = rom.name_ptr(i)
    if a is not None:
        walk(a, 1)
for c in range(0xA0, 0xE8):
    walk(rom.phrase_addr(c), 1)
for idx in range(0x800):
    walk(rom.sub_addr(0xE8 | (idx >> 8), idx & 0xFF), 1)
for c in range(0x40, 0xA0):
    used.add(rom.sb_entry(c))

free = [i for i in range(1, T.MAX_INDEX) if i not in used]
print('referenced indices: %d / %d' % (len(used), T.MAX_INDEX - 1))
print('free indices      : %d' % len(free))
print('free ranges:', [(hex(a), hex(b)) for a, b in
      __import__('itertools').groupby(())] or '')
runs = []
for i in free:
    if runs and i == runs[-1][1] + 1:
        runs[-1][1] = i
    else:
        runs.append([i, i])
print('free runs (top 12):', [(hex(a), hex(b)) for a, b in runs[:12]])
print('free above 0x49B  :', len([i for i in free if i > 0x49B]))
json.dump({'used': sorted(used), 'free': free},
          open('docs/research/idx_census.json', 'w'))
