"""DEAD END -- kept so its numbers can be traced, but do not quote them.

`hi = next sorted pointer` is not a block end.  Block 133's base is followed by 1.7 MB
of non-text before the next pointer, so this script counts that as prose and reports
2.5M "text bytes" and 2,115 "macro codes" -- i.e. roughly the whole address space.  Use
`tools/corpus_from_dump.py`, which censuses the decoded script instead of guessing spans.

Three things decide whether the goal is reachable, and none of them is the glyph
budget the last round kept hitting:

* how many bytes of text exist in all 160 blocks, and how many are already shipped;
* how many *distinct* characters a Chinese rendering would need, split into the ones
  the stock kanji band already holds (which can be ridden in place at zero slot cost,
  once we accept that the Japanese form of that slot is being replaced anyway) and the
  simplified-only ones that still need a real slot;
* how much Japanese lives OUTSIDE the block stream -- the `$A0-$EF` / `$E8xx-$EFxx`
  word and macro codes, whose bodies sit in their own table and are not covered by any
  block translation.

usage: python3 tools/corpusmap.py [--json out.json]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import block_boxes as BB
import prologue_boxes as PB

BLOCKS = 160
HANZI = lambda c: '一' <= c <= '鿿'
KANA = lambda c: '぀' <= c <= 'ヿ'


def main():
    rom = T.Rom('rom_original_japanese.sfc')
    ptrs = {}
    for i in range(BLOCKS):
        p = rom.text_ptr(i)
        if p is not None:
            ptrs[i] = p
    order = sorted(ptrs.values())
    nxt = {order[k]: order[k + 1] for k in range(len(order) - 1)}
    band = {T.idx_to_char(i) for i in range(T.JIS_KANJI, T.MAX_INDEX)} - {None}
    rows, kind_ct = [], collections.Counter()
    hz, kn, macros = set(), set(), collections.Counter()
    for i, lo in sorted(ptrs.items(), key=lambda kv: kv[1]):
        hi = nxt.get(lo, lo + 0x200)
        kb = hi - lo
        n_hanzi = n_kana = n_word = 0
        # A block span can end inside a 2-byte glyph pair, which trips the atom walk's
        # byte-conservation assert (same boundary quirk tools/blocktails.py works around),
        # so widen until it walks and charge the few extra bytes to this block.
        for extra in (0, 2, 4, 6, 12):
            try:
                walked = BB.atoms(rom, lo, hi + extra)
                kb += extra
                break
            except AssertionError:
                continue
        else:
            rows.append((i, lo, kb, -1, -1, -1))
            continue
        for p, raw, k, txt in walked:
            kind_ct[k] += 1
            if k == 'glyph' and len(txt) == 1:
                if HANZI(txt):
                    hz.add(txt); n_hanzi += 1
                elif KANA(txt):
                    kn.add(txt); n_kana += 1
            elif k in ('word', 'macro'):
                n_word += 1
                code = raw[0] if len(raw) == 1 else (raw[0] << 8) | raw[1]
                macros[code] += 1
        rows.append((i, lo, kb, n_hanzi, n_kana, n_word))
    out = {'blocks': [{'blk': i, 'base': b, 'bytes': nb, 'hanzi': h, 'kana': k, 'words': w}
                      for i, b, nb, h, k, w in rows],
           'distinct_hanzi': ''.join(sorted(hz)),
           'distinct_kana': ''.join(sorted(kn)),
           'macro_codes': {hex(c): n for c, n in sorted(macros.items())}}
    if '--json' in sys.argv:
        json.dump(out, open(sys.argv[sys.argv.index('--json') + 1], 'w'), ensure_ascii=False)
    tot = sum(r[2] for r in rows)
    ok = [r for r in rows if r[3] >= 0]
    if len(ok) < len(rows):
        print('unwalked blocks (span ends mid-pair even widened): %s'
              % ', '.join(str(r[0]) for r in rows if r[3] < 0))
    print('blocks %d, text bytes %d (%.1f%% of the 4 MB image)' % (len(rows), tot, 100.0*tot/0x400000))
    print('glyph positions: hanzi %d, kana %d  -> kana is %.0f%% of all text positions'
          % (sum(r[3] for r in ok), sum(r[4] for r in ok),
             100.0*sum(r[4] for r in ok)/max(sum(r[3]+r[4] for r in ok), 1)))
    print('distinct: %d hanzi (%d already in the stock band), %d kana'
          % (len(hz), len(hz & band), len(kn)))
    print('word/macro atoms %d, in %d distinct codes  <- Japanese bodies living outside the block stream'
          % (sum(r[5] for r in ok), len(macros)))
    big = sorted(rows, key=lambda r: -r[2])[:8]
    print('largest blocks: ' + ', '.join('%d:%dB' % (b, nb) for b, _, nb, _, _, _ in big))


if __name__ == '__main__':
    main()
