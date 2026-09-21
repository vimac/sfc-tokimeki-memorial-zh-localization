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
# the prefix is relative to docs/research/, unless it spells a path
if os.sep in out:
    jdir, out = os.path.split(out)
    jdir = os.path.join(root, jdir)
else:
    jdir = os.path.join(root, 'docs', 'research')

rom = T.Rom(os.path.join(root, 'rom_original_japanese.sfc'))
code = B.Codec(rom)
try:
    lo, hi = B.block_extent(rom, blk)
except StopIteration:
    # the highest TEXT_PTRS entry has no following pointer, so its end cannot be
    # derived from the table -- this is a pre-existing pipeline limitation.
    raise SystemExit('block %d: no extent (last TEXT_PTRS entry; end unknown)' % blk)
# 0x1E5E90 starts the $01 branch-table region: those bytes are partly runtime
# distance tables, so a linear walk must stop before them and the patch must
# not reach past them.
hi = min(hi, {8: 0x1E5E90}.get(blk, hi))

# ---------------------------------------------------------------- wide codes
# Engine-verified advance width per control code (tools/ctrl_widths.py reads the
# dispatcher's own advance chain: at $CA9A..$CAA2 five stacked `INC $B4`,
# entered at $CA9A/9C/9E/A0/A2 = advance 5/4/3/2/1; codes $00-$2E go through
# the handler table at $CB0B, $30-$37 through the handler at $CD8C and
# $38-$3F through $CD67).  Every width below is the first advance-chain jump of
# the handler, and it is unconditional (branches inside a handler, e.g. the $28
# wait loop `d0 f7`, only re-enter the same jump).  The walk has to group these
# with their operand bytes the way the engine consumes them -- Codec.walk walks
# one instruction per band and gives 1-byte atoms for every control byte, so
# its lone $09 is only the opcode: the operand bytes would otherwise be parsed
# as glyphs/macros/terminators that the engine never executes (block 16's
# "executed $01" hits are nothing but $09 operand bytes under this parser).
# Full per-code semantics: docs/research/control-codes.md.
WIDTHS = {0x00: 2,   # LDA #$0000; JSL $80:D23D; JMP $CAA0
          0x02: 2,   # call: pushes cursor+3, $B4 <- 1-byte operand address.
                     # Safe to copy: the target is a fixed bank address (the
                     # pointer grid keeps every file offset across a patch, and
                     # pack_boxes only ever re-flows inside those spans), and
                     # the subroutine's $0A return pops the pushed +3, which
                     # lands after the copied 2-byte call either way.
          0x04: 2,   # LDA ($B4),Y; STA $0A2C; JMP $CAA0
          0x07: 2,   # operand folded into $0A26; JMP $CAA0
          0x08: 2,   # operand folded into $0A26; JMP $CAA0
          0x28: 2}   # STZ $17DE; operand; JSL delay loop; JMP $CAA0
W3 = {0x09: 3}       # LDA ($B4),Y x2; STA $0A26/$0A28; JMP $CA9E
W4 = {0x03: 4}       # two operands + table byte; JSL $80:CFC5; JMP $CA9C
W5 = {0x0F: 5}       # JSL $80:CFC5; JMP $CA9A
W30 = (0x30, 0x37)   # $30-$37: WRAM-table op (handler $CD8C); JMP $CAA0 = 2.
                     # $38-$3F ($CD67) advance 1 -- block 8 ships $39/$3A/$3B
                     # as single bytes, so they need no grouping.
# $01 is not groupable text: `new cursor = c + byte_at(c + word@($0000+op) + 3)`
# reads its jump distance from an in-stream table whose bytes a translation
# *reflows* (same span, different content), so no sheet can promise the jump
# still lands in its subroutine (docs/research/control-codes.md, consequence 2;
# that is why block 8 was already capped at the table start 0x1E5E90).  It gets
# the same treatment generalized: the sheet stops there and says so -- covering
# a prefix is the pipeline's own semantics (`cov` only trusts the continuous
# prefix from segment 0 anyway).
CAP01 = 0x01
# $2F: the 47-entry handler table stops at $2E; $2F's slot aliases into the
# $00 handler's own bytes ($CB69 -> address $00A9) and dispatches through a
# runtime WRAM vector -- no static width exists, so a stream that executes it
# cannot be walked at all.
REJECT = {0x2F: 'handler table ends at $2E; $2F dispatches via runtime vector $00A9'}


def instr_w(b):
    """Engine width of a control byte needing grouping, or None if it is 1."""
    if b in WIDTHS:
        return WIDTHS[b]
    if b in W3:
        return 3
    if b in W4:
        return 4
    if b in W5:
        return 5
    if W30[0] <= b <= W30[1]:
        return 2
    return None


def engine_walk(lo, hi):
    """Engine-aligned atom list; trims an instruction that runs past `hi`.

    Codec.walk walks one instruction per byte-band and gives 1-byte atoms for
    every control byte, so its lone $09 is only the opcode -- walk position by
    position instead, grouping each wide code with its operand bytes.  Single
    narrow atoms are delegated to Codec.walk on [pos, pos+k), which returns
    exactly the one atom the big walk would produce here.  An atom starting
    inside the block whose bytes sit past its end -- the 1-byte 'atom walk lost
    bytes' overshoot was a 2-byte glyph pair straddling the next block's
    pointer -- is dropped with a note: the sheet may not budget bytes the block
    does not own.
    """
    atoms, pos, notes = [], lo, []
    while pos < hi:
        b = rom.data[pos]
        if b in REJECT:
            raise SystemExit('block %d: $%02X at %06X -- %s, cannot be linearly '
                             're-emitted' % (blk, b, pos, REJECT[b]))
        if b == CAP01:
            notes.append('$01@%06X: relative distance-table jump; sheet capped '
                         'here (%d B of the block left uncovered)'
                         % (pos, hi - pos))
            break
        w = instr_w(b)
        if w is None:
            a = code.walk(pos, pos + (2 if b >= 0xE8 else 1))[0]
        else:
            if pos + w > hi:
                notes.append('$%02X@%06X runs %d B past block end: trimmed'
                             % (b, pos, w - (hi - pos)))
                break
            raw = bytes(rom.data[pos:pos + w])
            a = {'k': 'c', 'ch': '', 'raw': raw, 'ctrl': list(raw)}
        if pos + len(a['raw']) > hi:
            notes.append('%02X@%06X runs %d B past block end: trimmed'
                         % (b, pos, len(a['raw']) - (hi - pos)))
            break
        atoms.append(a)
        pos += len(a['raw'])
    return atoms, pos, notes


atoms, hi, notes = engine_walk(lo, hi)

notes.append('%d wide-control atom(s) grouped with operands' %
             sum(1 for a in atoms if a['k'] == 'c' and len(a['ctrl']) > 1))


def last_split(a):
    """The byte that may end a line/segment/box -- never an operand byte."""
    if a['k'] == 'c' and len(a['ctrl']) > 1:
        return None
    return a['ctrl'][-1] if a['ctrl'] else None


def segmentize(atoms):
    segs, cur = [], []
    for a in atoms:
        cur.append(a)
        if last_split(a) in B.LINE_CTRL:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


def group(atoms):
    boxes, cur, n = [], [], 0
    for a in atoms:
        cur.append(a)
        n += len(a['raw'])
        if last_split(a) in (0x0C, 0x0A):
            boxes.append({'bytes': n, 'term': 'STEP' if last_split(a) == 0x0A
                          else 'BOX', 'raw': a['raw'], 'atoms': cur})
            cur, n = [], 0
    if cur:
        boxes.append({'bytes': n, 'term': 'TAIL', 'raw': b'', 'atoms': cur})
    for bx in boxes:
        bx['segs'] = segmentize(bx['atoms'])
    return boxes


# The sheet covers whole boxes only -- that is the pack_boxes rule (no box may
# cross its grid-fixed terminator) and `cov`'s prefix rule.  So anything the
# walk leaves past the last $0A/$0C -- unterminated padding, a half-open box at
# a $01 cap, a straddled tail atom -- is dropped back off `hi` with a note.
while True:
    segs = segmentize(atoms)
    boxes = group(atoms)
    if not boxes or boxes[-1]['term'] != 'TAIL':
        break
    drop = boxes[-1]
    junk = all(not a['ch'] and last_split(a) in (None, 0x2E) for a in drop['atoms'])
    hi -= drop['bytes']
    notes.append('%d B after the last terminator dropped (%s)' % (
        drop['bytes'], 'unterminated padding' if junk else 'half-open box at the walk cap'))
    atoms = atoms[:-len(drop['atoms'])]
    if not atoms:
        raise SystemExit('block %d: no terminated text in range (pure data/padding)'
                         % blk)
if len(boxes) < 2:
    raise SystemExit('block %d: no terminated text in range (pure data/padding)'
                     % blk)
head, segs = segs[0], segs[1:]
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

json.dump(rows, open(os.path.join(jdir, out + '_work.json'), 'w'),
          ensure_ascii=False, indent=1)
with open(os.path.join(jdir, out + '_work.tsv'), 'w',
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
with open(os.path.join(jdir, out + '_jp.txt'), 'w',
          encoding='utf-8') as f:
    for r in rows:
        f.write('# %d %s %dB cap %d box %d %s\n%s\n' % (
            r['n'], r['off'], r['bytes'], r['cap'], r['box'], r['term'], r['jp']))
print('block %d: %d bytes at %#x, %d segments, %d boxes, cap total %d B'
      % (blk, hi - lo, lo, len(segs), len(boxes) - 1, sum(r['cap'] for r in rows)))
for n in notes:
    print('  note:', n)
print('wrote docs/research/%s_work.tsv, _work.json, _jp.txt' % out)
