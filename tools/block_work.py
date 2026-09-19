"""Emit the translation budget sheet for one TEXT_PTRS block, in the exact line
format `build_prologue.py` eats (one line per segment, `|` between runs).

The Japanese stream decides the geometry: a box starts where the engine's grid
probe says, so a Chinese line has to fit the box it replaces.  This prints, per
segment, the run texts (what the translator replaces), the control bytes each run
carries, the opaque variable codes that must survive, and the byte budget left for
the Chinese glyphs.

usage: python3 tools/block_work.py <block> [prefix]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
blk = int(sys.argv[1])
out = sys.argv[2] if len(sys.argv) > 2 else 'block%d' % blk

rom = T.Rom(os.path.join(root, 'rom_original_japanese.sfc'))
code = B.Codec(rom)
lo, hi = B.block_extent(rom, blk)
# 0x1E5E90 starts the $01 branch-table region: those bytes are partly runtime
# distance tables, so a linear walk must stop before them and the patch must
# not reach past them.
hi = min(hi, {8: 0x1E5E90}.get(blk, hi))
atoms = code.walk(lo, hi)
# A 1-byte control walk is only valid while it keeps the engine's widths.  Of the
# operand-taking codes (docs/research/control-codes.md) these blocks use only
# `$00 xx`, which draws a blank cell and *ignores* its operand -- so the walk stays
# aligned exactly when the operand is itself a $00, i.e. when the code appears in
# runs of even length.  Assert that instead of trusting it.
WIDE = {0x01, 0x02, 0x03, 0x04, 0x07, 0x08, 0x09, 0x0F, 0x28}
wide, off, run = [], lo, 0
for a in atoms:
    c = a['ctrl'][0] if a['k'] == 'c' and len(a['ctrl']) == 1 else None
    if c == 0x00:
        run += 1
    else:
        if run % 2:
            wide.append(('00-run %d' % run, '%06X' % (off - run)))
        run = 0
        if c in WIDE or (c is not None and 0x30 <= c <= 0x37):
            wide.append(('%02X' % c, '%06X' % off))
    off += len(a['raw'])
if run % 2:
    wide.append(('00-run %d' % run, '%06X' % (off - run)))
assert not wide, 'operand-taking codes in range: %s' % wide
segs = B.segmentize(atoms)
head, segs = segs[0], segs[1:]
boxes = B.group(atoms)
assert boxes[-1]['term'] != 'TAIL', 'block does not end on a terminator'
spans = B.box_spans(boxes)
assert sum(len(b['segs']) for b in boxes) == len(segs) + 1

rows, lines = [], []
for si, seg in enumerate(segs):
    runs = B.seg_runs(seg)
    ctrl = sum(len(a['ctrl']) for a in seg if a['k'] == 'c')
    raw = sum(len(a['raw']) for a in seg)
    jp = '|'.join(r[0] for r in runs)
    rows.append({'n': si, 'bytes': raw, 'ctrl': ctrl, 'cap': raw - ctrl,
                 'runs': [[r[0], ''.join('%02X' % c for c in r[1]),
                           [m[1].hex(' ') for m in r[2]]] for r in runs],
                 'jp': jp, 'zh': ''})
# offsets: recompute from the atom raw lengths so they stay byte-exact.  The head
# segment (the block's leading `$0A`) was dropped from `segs`, so start after it.
off, starts = lo + sum(len(a['raw']) for a in head), []
for seg in segs:
    starts.append(off)
    off += sum(len(a['raw']) for a in seg)
assert off == hi, 'segments cover %d of %d bytes' % (off - lo, hi - lo)
for r, s in zip(rows, starts):
    r['off'] = '%06X' % s
# which box is each segment in, and does the box end on $0A or a $0C macro
boxof, k = [], 0
for bi, bx in enumerate(boxes[1:]):
    for _ in range(len(bx['segs'])):
        boxof.append((bi, bx['term']))
    k += len(bx['segs'])
for r, (bi, term) in zip(rows, boxof):
    r['box'], r['term'] = bi, term

json.dump(rows, open(os.path.join(root, 'docs/research', out + '_work.json'), 'w'),
          ensure_ascii=False, indent=1)
with open(os.path.join(root, 'docs/research', out + '_work.tsv'), 'w',
          encoding='utf-8') as f:
    f.write('# n\toff\tspan\tctrl\tcap\tbox\tterm\truns(jp|ctrl|var)\ttranslation\n')
    for r in rows:
        runs = ' ; '.join('%s[%s]%s' % (j, t, (' ' + ' '.join(m)) if m else '')
                          for j, t, m in r['runs'])
        f.write('%3d\t%s\t%4d\t%3d\t%4d\t%3s\t%-4s\t%s\t\n' % (
            r['n'], r['off'], r['bytes'], r['ctrl'], r['cap'], r['box'], r['term'],
            runs.replace('\t', ' ')))
# the translator's reference: Japanese line, commented, one pair per segment.
# `_zh.txt` is the file build_prologue reads and must hold only the translation.
with open(os.path.join(root, 'docs/research', out + '_jp.txt'), 'w',
          encoding='utf-8') as f:
    for r in rows:
        f.write('# %d %s %dB cap %d box %d %s\n%s\n' % (
            r['n'], r['off'], r['bytes'], r['cap'], r['box'], r['term'], r['jp']))
print('block %d: %d bytes at %#x, %d segments, %d boxes, cap total %d B'
      % (blk, hi - lo, lo, len(segs), len(boxes) - 1, sum(r['cap'] for r in rows)))
print('wrote docs/research/%s_work.tsv, _work.json, _jp.txt' % out)
