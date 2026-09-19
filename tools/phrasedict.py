"""How much of the game's text is not in the text blocks at all, but in the shared phrase dictionary.

Two bands of codes expand to whole sentences from elsewhere: `$A0-$EF` phrase macros (bank
`$B9`, table at `T.PHRASE_TABLE`) and `$E8xx-$EFxx` sub-text calls (bank `$C3`, table at
`T.SUB_TABLE`).  A tight 2-3 byte box is therefore *not* a dead end -- the sentence it shows
lives in a body we can rewrite once, and every box that calls that code follows.  This counts
the other side of that bargain: which dictionary entries the 160 text blocks actually call,
what each one says, how many bytes its body may hold before the next entry starts, and how
many blocks would change if we rewrote it.

usage: python3 tools/phrasedict.py [--block N] [--min-refs 1] [--json out.json]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import prologue_boxes as PB
import block_boxes as BB
import build_prologue as BP

SRC_ROM = 'rom_original_japanese.sfc'
BLOCKS = 160


def mapscan(path):
    """A builder work sheet (`docs/research/blockN_work.tsv`) -> [(off, span)] byte map.

    Needed because `T.block_bytes` stops at the first $00, and these pools use $00 as a
    control code with an operand: reading a block that way sees only its head.
    """
    rows = [l.rstrip('\n').split('\t') for l in open(path, encoding='utf-8')][1:]
    return [(int(r[1], 16), int(r[2])) for r in rows if r[0].strip().isdigit()]


def refscan(rom, code, spans):
    """key -> {'jp', 'raw', 'refs': set of boxes, 'n': calls} for every macro call."""
    out = collections.defaultdict(lambda: {'refs': set(), 'n': 0})
    for n, (lo, size) in enumerate(spans):
        for pos, raw, kind, txt in BB.atoms(rom, lo, lo + size):
            if kind != 'word':
                continue
            e = out[raw.hex()]
            e['refs'].add(n)
            e['n'] += 1
            e.setdefault('jp', txt)
    return out


def entries(code, keys):
    """key -> (expansion, body bytes, capacity) reading the ROM's own span tables."""
    out = {}
    for k in keys:
        codes = [int(x, 16) for x in (k[i:i + 2] for i in range(0, len(k), 2))]
        if len(codes) == 1:
            lo, hi = code.phrase_span(codes[0])
        else:
            lo, hi = code.sub_span(*codes)
        raw = bytes(code.rom.data[lo:hi])
        body = raw[:raw.index(0x0A) + 1] if 0x0A in raw else raw
        out[k] = (PB.macro_text(code.rom, codes[0] if len(codes) == 1
                                else (codes[0] << 8) | codes[1]),
                  body.hex(' '), hi - lo)
    return out


def main():
    argv = sys.argv[1:]
    rom = T.Rom(SRC_ROM)
    code = BP.Codec(rom)
    path = argv[argv.index('--map') + 1] if '--map' in argv else 'docs/research/block0_work.tsv'
    mins = int(argv[argv.index('--min-refs') + 1]) if '--min-refs' in argv else 1
    spans = mapscan(path)
    refs = refscan(rom, code, spans)
    det = entries(code, sorted(refs))
    rows = []
    for k, e in sorted(refs.items(), key=lambda kv: (-kv[1]['n'], kv[0])):
        jp, body, cap = det[k]
        if e['n'] >= mins and len(body.split()) >= 2:
            rows.append({'key': k, 'jp': jp, 'body': body, 'cap': cap,
                         'nrefs': e['n'], 'nboxes': len(e['refs'])})
    if '--json' in argv:
        json.dump(rows, open(argv[argv.index('--json') + 1], 'w'), ensure_ascii=False, indent=1)
    inline = sum(1 for lo, size in spans
                 for _, _, kind, _ in BB.atoms(rom, lo, lo + size) if kind == 'glyph')
    print('%s: %d segments, %d inline glyph atoms, %d dictionary entries over %d calls'
          % (path, len(spans), inline, len(rows), sum(r['nrefs'] for r in rows)))
    caps = sorted(r['cap'] for r in rows)
    if caps:
        print('body capacity: min %d, median %d, max %d B; %d entries have cap <= 8 B'
              % (caps[0], caps[len(caps) // 2], caps[-1], sum(1 for c in caps if c <= 8)))
    for r in rows[:25]:
        print('  %s cap%-4d x%-5d boxes%-4d %s'
              % (r['key'], r['cap'], r['nrefs'], r['nboxes'], r['jp']))


if __name__ == '__main__':
    main()
