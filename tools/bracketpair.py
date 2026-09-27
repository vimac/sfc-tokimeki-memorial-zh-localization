"""Prove: which boxes show a bracket whose partner is nowhere in the same box.

The unit is the **frame the reader sees** -- all steps of one box concatenated, with
dictionary macro bodies expanded (an opener can live in a macro body while the closer
is written in the box).  Counting per stored line would invent defects that the engine's
own frame already pairs up, and counting raw bytes would miss the half that hides in a
shared dictionary entry.

The same ruler is run against the **original image** too.  A box whose Japanese frame
itself draws one 「 with no 」 (speaker-quote lines in the bank pools do this constantly)
is faithfully mirrored and is not a defect -- only a box where Japanese is balanced and
ours is not gets named.  That control is the whole point: without it the report is noise.

usage: python3 tools/bracketpair.py [--json /tmp/out.json] [--verbose N]
"""
import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_zh as B
import segtext as S

GRP = {'（）': ('（', '）'), '()': ('(', ')'), '「」': ('「', '」'), '『』': ('『', '』'),
       '【】': ('【', '】'), '《》': ('《', '》')}


def boxes_of(blk):
    """step index -> frame index, straight from the block's own work table."""
    rows = [l.rstrip('\n').split('\t')
            for l in open(os.path.join(B.ROOT, 'docs/research',
                                       'block%d_work.tsv' % blk), encoding='utf-8')][1:]
    return {int(r[0]): r[5].strip() for r in rows if r[0].strip().isdigit()}


def tally(text):
    """[(group, open_count, close_count)] for groups that appear at all."""
    c = collections.Counter(text)
    return [(g, c[o], c[cl]) for g, (o, cl) in GRP.items() if c[o] or c[cl]]


def sweep(path):
    """{blk: {frame: (joined_text, unbalanced_groups)}} for one image."""
    rom, code = S.codec(path)
    painted = S.slot_chars(code, path)
    res = {}
    for blk, _zf, _hi in B.BLOCKS:
        p = os.path.join(B.ROOT, 'docs/research', 'block%d_enc.json' % blk)
        if not os.path.exists(p):
            continue
        cov = json.load(open(p, encoding='utf-8'))['cov']
        boxmap = boxes_of(blk)
        joined, order, frames_with_nul = {}, [], set()
        for n, _off, _span, text, _kept, _at in S.steps(rom, code, painted, blk, cov):
            bx = boxmap.get(n)
            if '\x00' in text:
                frames_with_nul.add(bx)
            if bx not in joined:
                joined[bx] = []
                order.append(bx)
            joined[bx].append(text)
        per = {}
        for bx in order:
            t = ''.join(joined[bx]).replace('\n', '').replace('\x00', '')
            bad = [(g, o, c) for g, o, c in tally(t) if o != c]
            if bad:
                per[bx] = (t, bad)
        res[blk] = (per, frames_with_nul)
    return res


def main():
    jp = sweep(B.SRC_ROM)
    cn = sweep(B.OUT_ROM)
    named, mirrored = [], []
    for blk, (per, nul_boxes) in sorted(cn.items()):
        for bx, (t, bad) in sorted(per.items(), key=lambda kv: int(kv[0])):
            jpb = jp[blk][0].get(bx)
            if jpb:
                mirrored.append((blk, bx, jpb[1], jpb[0]))
            else:
                named.append((blk, bx, bad, t))
    total = sum(len(v[0]) for v in cn.values())
    print('%s: %d frames hold an unbalanced pair (%d of them share a box number '
          'with a second frame, so a few may be already paired on screen)'
          % (os.path.basename(B.OUT_ROM), total,
             sum(len(v[1]) for v in cn.values())))
    print('  of those %d also do on the ORIGINAL image (faithful mirror, not ours)'
          % len(mirrored))
    print('  named as ours: %d' % len(named))
    n = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv)
                  if a == '--verbose'), 40))
    for blk, bx, bad, t in named[:n]:
        print('   b%d#%s %-14s | %s' % (blk, bx, ','.join('%s%d/%d' % (g, o, c)
                                                           for g, o, c in bad), t[:60]))
    if '--json' in sys.argv:
        out = sys.argv[sys.argv.index('--json') + 1]
        json.dump([{'block': b, 'box': int(x), 'text': t,
                    'bad': [[g, o, c] for g, o, c in bad]} for b, x, bad, t in named],
                  open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return named, mirrored


if __name__ == '__main__':
    main()
