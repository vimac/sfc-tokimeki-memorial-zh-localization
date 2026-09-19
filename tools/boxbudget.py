"""Per-box byte budget: the constraint the pointer grid actually imposes.

$82:A1D6 computes each box's start as `per-object base + 2*script operand` and
looks at the text only to decide +/-1 (keep P when the byte at P-1 is $0A or
$A0..$A7, else rewind one).  The operands live in the object script, which a
text patch cannot touch, so the grid of starts is fixed: box i must end its
terminator on the *same file offset* the Japanese box i did, i.e. occupy exactly
the same byte span.  Fitting the whole block, as the old builder checked, is not
enough -- one over-long box shifts every later box, which is the drift the
prologue screenshots show.

Reports per box: the Japanese span, the Chinese encoded size and the slack, so
over-budget boxes can be shortened or given more code page slots.

usage: python3 tools/boxbudget.py [--over] [--json]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

NAME = os.path.join(B.ROOT, 'docs', 'research', 'prologue_zh.txt')


_PL = None


def pack(extra=(), blk=None):
    """The shipped build's own plan for one block, as
    (boxes, spans, zh, seg bytes, page, enc, char2idx, segs).

    This used to re-derive a code page from one block alone; the page is a single
    global resource shared by every translated block, so re-deriving it made this
    tool disagree with the ROM the build wrote.  `build_prologue.plan()` is now
    the only source of truth and every verifier reads it through here.
    """
    global _PL
    if _PL is None:
        _PL = B.plan(verbose=False)
    ctx = _PL['by_blk'][blk if blk is not None else B.BLOCK]
    return (ctx['boxes'], ctx['spans'], ctx['zh'],
            [len(b) for b in ctx['seg_bytes']], _PL['page'], ctx['enc'],
            _PL['char2idx'], ctx['segs'])


def main():
    boxes, spans, zh, seg_bytes, page, enc, char2idx, segs = pack()
    rows, over, n_over = [], 0, 0
    for bi, bx in enumerate(boxes[1:]):
        lo, hi = spans[bi]
        sb = seg_bytes[lo:hi]
        zb = sum(sb)
        d = zb - bx['bytes']
        if d > 0:
            over += d
            n_over += 1
        rows.append({'n': bi, 'term': bx['term'], 'jp': bx['bytes'], 'zh': zb,
                     'seg_bytes': sb, 'lines': zh[lo:hi],
                     'jp_seg_bytes': [sum(len(a['raw']) for a in s)
                                      for s in bx['segs']],
                     'jp_lines': ['|'.join(r[0] for r in B.seg_runs(s))
                                  for s in bx['segs']]})
        print('%3d %-4s jp %3d zh %3d %+3d%s' % (bi, bx['term'], bx['bytes'],
                                                 zb, d,
                                                 '   <== OVER' if d > 0 else ''))
        for l in zh[lo:hi]:
            print('        %s' % l.replace('|', ' / '))
    if '--over' in sys.argv:
        for r in rows:
            if r['zh'] <= r['jp']:
                continue
            print('\n%3d %-4s budget %d bytes (need -%d)'
                  % (r['n'], r['term'], r['jp'], r['zh'] - r['jp']))
            for j, z, jb, sb in zip(r['jp_lines'], r['lines'],
                                    r['jp_seg_bytes'], r['seg_bytes']):
                print('   jp %2dB %-24s zh %2dB  %s'
                      % (jb, j, sb, z.replace('|', ' / ')))
    print('\nboxes %d, jp %d B, zh %d B, %d over-budget by %d B, code page %d'
          % (len(boxes) - 1, sum(b['bytes'] for b in boxes[1:]),
             sum(seg_bytes), n_over, over, len(page)), file=sys.stderr)
    if '--json' in sys.argv:
        json.dump(rows, open('/tmp/play/boxbudget.json', 'w'),
                  ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
