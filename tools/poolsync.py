"""Prove: which translated lines are *shorter than a rendering that provably fits*
the same slot -- the byte-safe way to find sentences gutted to save budget.

The same Japanese line recurs across dozens of TKSC blocks (date pools, narrator
pools).  Group every translated line by its (runs text, span) in blockN_work.tsv
and two members of a group are guaranteed to cost *identical bytes*: same macro
fold path, same box capacity.  So when a group has a dominant rendering and a
lone member that is >=2 hanzi shorter, that member lost sentence components to
byte-squeezing, and copying the dominant line in cannot break the grid
(AGENTS §四 8: no per-box budgeting needed -- the group already proves fit).

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
