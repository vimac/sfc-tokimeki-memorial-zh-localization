"""Inventory every TEXT_PTRS block: size, box count, and which codes it uses.

The patch so far covers 3 of the ROM's 145 text blocks, and "translate all text,
then trim the font" needs the whole map to be planable: how much text there is,
how it is divided into boxes (the pointer grid that fixes each translation's byte
budget), and which phrase-macro codes ($A0-$E7) are actually referenced -- the
unused ones are the only place a 1-byte Chinese code can still come from, and the
per-box budget decides whether block 0-sized blocks are translatable at all.

usage: python3 tools/textmap.py [--json]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rom = T.Rom(os.path.join(ROOT, 'rom_original_japanese.sfc'))
code = B.Codec(rom)
starts = B.block_starts(rom)
rows, macro = [], collections.Counter()

for blk in range(T.PTR_COUNT):
    lo = rom.text_ptr(blk)
    nxt = next((s for s in starts if s > lo), None)
    hi = min(len(rom.data), nxt if nxt else lo + 0x2000)
    try:
        atoms = code.walk(lo, hi)
    except Exception as e:                              # data, not text
        rows.append({'blk': blk, 'off': '%06X' % lo, 'bytes': hi - lo, 'err': str(e)[:40]})
        continue
    boxes = B.group(atoms)
    segs = B.segmentize(atoms)[1:]
    glyphs = sum(1 for a in atoms if a['k'] in ('g', 'n'))
    two = sum(1 for a in atoms if a['k'] == 'g' and len(a['raw']) == 2)
    ms = {a['code'] for a in atoms if a['k'] == 'm' and len(a['code']) == 2}
    macro.update(ms)
    rows.append({'blk': blk, 'off': '%06X' % lo, 'bytes': hi - lo,
                 'boxes': len(boxes) - 1, 'segs': len(segs), 'glyphs': glyphs,
                 'wide_glyphs': two, 'macros': len(ms),
                 'term': boxes[-1]['term'],
                 'tail': ''.join(a['ch'] for a in atoms if a['k'] in ('g', 'm'))[:40]})

tot = sum(r['bytes'] for r in rows if 'bytes' in r and 'err' not in r)
gly = sum(r['glyphs'] for r in rows if 'glyphs' in r)
box = sum(r['boxes'] for r in rows if 'boxes' in r)
free = sorted({'%02X' % c for c in range(0xA0, 0xE8)} - set(macro))
print('%d blocks, %d B of walkable text, %d glyph atoms, %d boxes'
      % (len([r for r in rows if 'err' not in r]), tot, gly, box))
print('macro codes referenced: %d of %d in $A0-$E7, free: %s'
      % (len(macro), 0xE8 - 0xA0, ' '.join(free)))
print('top-referenced macros: %s' % macro.most_common(12))
for r in rows:
    if 'err' in r:
        print('%3d %s %6d B  unwalkable: %s' % (r['blk'], r['off'], r['bytes'], r['err']))
        continue
    print('%3d %s %6d B %4d boxes %4d segs %5d glyphs %4d wide  %s'
          % (r['blk'], r['off'], r['bytes'], r['boxes'], r['segs'], r['glyphs'],
             r['wide_glyphs'], r['tail'].replace('\n', ' ')))
if '--json' in sys.argv:
    json.dump(rows, open(os.path.join(ROOT, 'docs/research/textmap.json'), 'w'),
              ensure_ascii=False, indent=1)
