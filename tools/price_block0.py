"""Price block 0 (the in-game hint / system pool) in NEW glyph records, not bytes.

Block 0's 726 boxes tile their 14778 B exactly, so it looked like a byte-capacity
problem.  It is not: the binding constraint is the font, and the font only charges for
characters it does not already hold.  If the pool's Japanese happens to be built from
kanji the prologue already injected, translating it is nearly free; if not, block 0 is
out of reach for good.  This measures which.

usage: python3 tools/price_block0.py [block ...]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import block_boxes as BB
import build_prologue as B

BLOCKS = 160
g = json.load(open(os.path.join(os.path.dirname(__file__), os.pardir,
                               'docs/research/glyph_alloc.json')))
owned = set(g['fresh']) | set(g['inplace']) | set(g['at_stock'])
HANZI = lambda c: '一' <= c <= '鿿'
KANA = lambda c: '぀' <= c <= 'ヿ'


def main():
    rom = T.Rom('rom_original_japanese.sfc')
    ptrs = sorted({p for p in (rom.text_ptr(i) for i in range(BLOCKS)) if p is not None})
    for blk in [int(a) for a in sys.argv[1:] if a.isdigit()] or [0]:
        lo = rom.text_ptr(blk)
        after = [p for p in ptrs if p > lo]
        hi = after[0] if after else lo + 0x2000
        seen, kana, bytes_ = collections.Counter(), collections.Counter(), 0
        boxes = 0
        for kind, off, nb, lines in BB.segments(rom, lo, hi):
            bytes_ += nb
            boxes += 1
            for p, raw, k, txt in BB.atoms(rom, off, off + nb):
                if k != 'glyph' or len(txt) != 1:
                    continue
                if HANZI(txt):
                    seen.update(txt)
                elif KANA(txt):
                    kana.update(txt)
        need = sorted(c for c in seen if c not in owned)
        print('block %d: base %06X span %dB, %d segments' % (blk, lo, hi - lo, boxes))
        print('  hanzi used %d distinct, %d already owned, %d NEW records needed'
              % (len(seen), len(seen) - len(need), len(need)))
        print('  kana used %d distinct (stay kana: drawn from the stock syllabary)'
              % len(kana))
        top = ''.join(c for c, n in seen.most_common() if c not in owned)
        print('  unowned, most-frequent-first: %s' % top[:80])
        cov = sum(n for c, n in seen.items() if c in owned)
        tot = sum(seen.values())
        print('  token coverage: %d/%d = %.1f%% of hanzi positions need no new glyph'
              % (cov, tot, 100.0 * cov / max(tot, 1)))
        if '--boxes' not in sys.argv:
            return
        # Per-box cost, then a greedy cheapest-first pick: how much of the pool is free
        # to translate inside the 20 records that are left.  A box's characters become
        # owned once bought, so costs are evaluated against a growing set.
        has = set(owned)
        per = []
        for kind, off, nb, lines in BB.segments(rom, lo, hi):
            txt = ''.join(lines)
            hz = {c for c in txt if HANZI(c)}
            per.append((off, nb, hz, len(hz - has), txt))
        order = sorted(range(len(per)), key=lambda i: (len(per[i][2] - owned), -per[i][1]))
        bought, picked, budget = 0, set(), 20
        for i in order:
            off, nb, hz, _, txt = per[i]
            new = hz - has
            if len(new) > budget:
                continue
            budget -= len(new)
            bought += len(new)
            has |= hz
            picked.add(i)
        print('  per-box cost: %d of %d boxes need 0 new records, %d need 1, %d need 2+'
              % (sum(1 for p in per if not (p[2] - owned)), len(per),
                 sum(1 for p in per if len(p[2] - owned) == 1),
                 sum(1 for p in per if len(p[2] - owned) > 1)))
        print('  greedy cheapest-first inside the last 20 records: %d boxes, %d records'
              ' spent, %d of %d pool bytes'
              % (len(picked), bought, sum(per[i][1] for i in picked), hi - lo))


if __name__ == '__main__':
    main()
