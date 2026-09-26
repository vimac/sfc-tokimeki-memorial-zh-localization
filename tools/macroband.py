"""Which $E8-$EF sub-macro indexes, and which bank-$C3 bytes, are dead.

The sub table (file 0x2196A8, 2048 x LE16 offsets in bank $C3) is a phrase dictionary
the game itself uses.  This scan measures it; it does NOT license moving dictionary
bodies somewhere else, and that route was tried and closed: an index that no TEXT_PTRS
block references statically can still be taken dynamically by a variable code such as
⟦E806⟧/⟦ECA5⟧, and the 1,883 recorded spans铺满整个 32 KB 段, so the "dead runs" below
are unread *text* inside a live table, not free space to lay bodies in.  中文词典体因此
只能在原地改写（改一条覆盖几十处调用），细节见 AGENTS.md §四 与 §五。

`census()` answers two questions, and caches the answer in
docs/research/macroband.json (derived, not tracked) because the transitive scan takes ~40s:

  available  sub indexes no text block reaches (null *or* orphan)
  dead_runs  byte runs inside the spans of those orphan indexes -- unread text, and by the
             paragraph above still not a place to put anything
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'docs', 'research', 'macroband.json')
PH_BASE = (0xB9 - 0x80) * 0x8000 - 0x8000
SUB_BANK = (0xC3 - 0x80) * 0x8000
SUB_BASE = SUB_BANK - 0x8000


def spans_of(table, offs, nxt, base, count, mask=0xFFFF):
    out = {}
    for k in range(count):
        o = offs[k]
        if 0x8000 <= o <= 0xFFFE:
            out[k & mask] = (base + o, base + nxt.get(o, 0xFFFF))
    return out


def census(rom, code, use_cache=True):
    if use_cache and os.path.exists(CACHE):
        j = json.load(open(CACHE))
        if j.get('version') == 3:
            return {k: (v if not isinstance(v, list) else tuple(v))
                    for k, v in j.items() if k != 'version'} | {
                        'available': set(j['available']),
                        'dead_runs': [tuple(r) for r in j['dead_runs']],
                        'spans': {int(k): tuple(v) for k, v in j['spans'].items()}}
    d = rom.data
    spans = spans_of(T.SUB_TABLE, code.sub_off, code.sub_next, SUB_BASE, 2048)
    ph = spans_of(T.PHRASE_TABLE, code.ph_off, code.ph_next, PH_BASE, 0x48)
    refs = collections.defaultdict(set)

    def walk(start, stop, blk, depth, seen):
        i = start
        while i < stop:
            b = d[i]
            if b < 0xA0:
                i += 1
            elif b < 0xE8:
                s = ph.get(b)
                if s and b not in seen and depth < 4:
                    walk(s[0], s[1], blk, depth + 1, seen | {b})
                i += 1
            elif b < 0xF0:
                k = (((b << 8) | d[i + 1]) & 0x7FF)
                refs[k].add(blk)
                s = spans.get(k)
                if s and k not in seen and depth < 4:
                    walk(s[0], s[1], blk, depth + 1, seen | {k})
                i += 2
            else:
                i += 2

    for blk in range(T.PTR_COUNT):
        a = rom.text_ptr(blk)
        if not a:
            continue
        nxt = rom.text_ptr(blk + 1) if blk + 1 < T.PTR_COUNT else None
        stop = min(len(d), (nxt if nxt and nxt > a else a + 0x2000))
        walk(a, max(a, min(stop, a + 0x2000)), blk, 0, frozenset())

    # The name table holds command lists, not text, but a false positive here
    # only costs us candidates -- it can never make the patch less safe.
    nstarts = sorted(a for a in (rom.name_ptr(i) for i in range(T.PTR_COUNT)) if a)
    for a in nstarts:
        n = next((s for s in nstarts if s > a), a + 0x100)
        walk(a, min(n, a + 0x100), -1, 0, frozenset())

    touched = set(refs)
    # dead = span of an index no text reaches, minus any span a live index shares
    occ = collections.Counter()
    for k in touched:
        s = spans.get(k)
        if s:
            for pos in range(s[0], s[1]):
                occ[pos] += 1
    for pos in range(T.SUB_TABLE, T.SUB_TABLE + 4096):
        occ[pos] += 1
    free = []
    for k in set(spans) - touched:
        s, e = spans[k]
        free += [p for p in range(s, e) if not occ[p]]
    runs, cur = [], None
    for p in sorted(set(free)):
        if cur and p == cur[1]:
            cur[1] = p + 1
        else:
            cur = [p, p + 1]
            runs.append(cur)
    runs = [(a, b - a) for a, b in runs if b - a >= 8]
    available = sorted(k for k in range(2048) if k not in touched)
    j = {'version': 3,
         'available': available,
         'dead_runs': [[a, n] for a, n in sorted(runs, key=lambda r: -r[1])],
         'spans': {str(k): list(spans[k]) for k in set(spans) - touched},
         'touched': sorted(touched)}
    json.dump(j, open(CACHE, 'w'))
    return {'available': set(available), 'dead_runs': [(a, n) for a, n in j['dead_runs']],
            'spans': {k: tuple(v) for k, v in j['spans'].items()},
            'touched': touched}


if __name__ == '__main__':
    import build_zh as B
    rom = T.Rom()
    c = census(rom, B.Codec(rom), use_cache='--refresh' not in sys.argv)
    print('available sub indexes: %d' % len(c['available']))
    print('dead runs >=8B: %d, total %d bytes' % (len(c['dead_runs']), sum(n for _, n in c['dead_runs'])))
    for a, n in c['dead_runs'][:8]:
        print('   file %#07x len=%4d  $C3:%04X' % (a, n, a - SUB_BANK + 0x8000))
