"""Prove: which translated lines render the same Japanese slot with sentence
components missing, compared against what the rest of the library writes there.

The same Japanese line recurs across dozens of TKSC blocks (date pools, narrator
pools).  Group every translated line by its (runs text, span) in blockN_work.tsv
and two members of a group are guaranteed to cost *identical bytes* for identical
text: same macro fold path, same step span.  So when a group has a dominant
rendering and a lone member that is >=2 hanzi shorter, that member probably lost
sentence components to byte-squeezing.

Caveat batch BM measured: **the guarantee is per step, not per box.**  Box budget
is the sum of its steps' spans, so copying the dominant line in CAN break the grid
when the box has no slack (b2#73, b36#503).  Re-measure the whole box before
landing, and expect the build to name the tight ones (AGENTS §三.7).  When the
dominant line *is* that slot's own macro body, copying it folds to a 2-byte call
and is free or cheaper than the thin rendering.

Second blind spot, same batch: this only sees **shorter** members.  A slot that renders
the same Japanese with a *different word of the same length* is invisible here -- and it
can be silently wrong at the fold level too: b79#417 (JP あぁ、いいよ。) wrote 「啊，没事。」,
which folds into a *different* macro (eac9, JP あっ、いいの。) at the identical 3 bytes, so
neither this tool nor `segtext --dict` nor the per-box byte ledger moved.  After editing any
glossary body, re-list that macro code's call sites across the library and compare word by
word (AGENTS §四).

usage: python3 tools/poolsync.py [--all]   # default lists candidates, --all also
                                     # lists the shorter-than-mainstream ones
"""
import sys, os, re, glob, collections

RG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', 'research')


def groups():
    """{(runs, span): [(block, seg, zh line)]} over every translated line."""
    out = collections.defaultdict(list)
    for f in glob.glob(os.path.join(RG, 'block*_work.tsv')):
        n = int(re.search(r'block(\d+)_', f).group(1))
        zf = os.path.join(RG, 'block%d_zh.txt' % n)
        if not os.path.exists(zf):
            continue
        zh = open(zf, encoding='utf-8').read().split('\n')
        for l in open(f, encoding='utf-8').read().splitlines()[1:]:
            c = l.split('\t')
            if len(c) < 8:
                continue
            try:
                i = int(c[0])
            except ValueError:
                continue
            runs = c[7].strip()
            if runs and i < len(zh):
                out[(runs, int(c[2]))].append((n, i, zh[i]))
    return out


def hanzi(t):
    return len(re.findall(r'[一-鿿]', t))


def main():
    min_gap = 0 if '--all' in sys.argv else 2
    hits = []
    for (runs, span), mem in groups().items():
        if len(mem) < 4 or len({m[0] for m in mem}) < 3:
            continue
        cnt = collections.Counter(m[2] for m in mem)
        dom, nd = cnt.most_common(1)[0]
        if nd < max(3, 0.6 * len(mem)):
            continue
        for (n, i, line) in mem:
            if cnt[line] == 1 and line != dom and hanzi(dom) - hanzi(line) >= min_gap:
                hits.append((n, i, span, runs, line, dom, nd, len(mem)))
    hits.sort()
    print('%d lines rendered by a unique minority while a mainstream exists at the '
          'identical (runs, span)' % len(hits))
    for (n, i, span, runs, line, dom, nd, tot) in hits:
        print('%3d/%-5d sp=%-4d %2dx/%-3d cur=%-24r dom=%r' % (n, i, span, nd, tot, line, dom))
        print('     JP=%s' % runs[:88])


if __name__ == '__main__':
    main()
