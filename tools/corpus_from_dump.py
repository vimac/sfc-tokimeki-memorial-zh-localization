"""Census the whole game's text from the decoded script dump, not from ROM bytes.

The J2E material in `reference/` already contains the game's complete decoded Japanese
script -- `translations/pending.json` is one extracted line list per TKSC file, and
`reference/.../Japanese/` holds the same text as raw EUC -- so the corpus size, the kana
load and the distinct-kanji count can be read off those directly, without having to
recover block ends from the ROM's pointer table.

What this output means today: coverage, not debt.  Every text block is translated, and TKSC
file numbers do not map one-to-one onto ROM block numbers, so a per-file line count here is
never a claim about a single block.

usage: python3 tools/corpus_from_dump.py [--json out.json]
"""
import sys, os, json, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

REF = 'REPO_ROOT/reference/j2e_full/scripts_x/Scripts/Japanese'
PENDING = 'REPO_ROOT/translations/pending.json'

HANZI = lambda c: '一' <= c <= '鿿'
KANA = lambda c: '぀' <= c <= 'ヿ'
# <$2E>, <END>, <N>, ● are the dump's own markup, not game text
MARKUP = re.compile(r'<[A-Z0-9$]{1,6}>|●')


def dump_lines():
    """{file: [line, ...]} from the extracted master work list."""
    return {k: [t for _, t in v] for k, v in json.load(open(PENDING)).items()}


def raw_files():
    """Every .EUC in the reference dump, decoded, as a cross-check on pending.json."""
    out = {}
    for root, _, names in os.walk(REF):
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, REF)] = MARKUP.sub('',
                open(p, 'rb').read().decode('euc_jp', 'replace')).replace('\r', '').split('\n')
    return out


def main():
    rom = T.Rom('rom_original_japanese.sfc')
    band = {T.idx_to_char(i) for i in range(T.JIS_KANJI, T.MAX_INDEX)} - {None}
    lines = dump_lines()
    text = {f: [MARKUP.sub('', l) for l in ls] for f, ls in lines.items()}
    allc = collections.Counter(''.join(''.join(v) for v in text.values()))
    hz = {c for c in allc if HANZI(c)}
    kn = {c for c in allc if KANA(c)}
    other = {c: n for c, n in allc.items() if not HANZI(c) and not KANA(c)}
    glyphpos = sum(allc.values())

    # the same census straight off the raw EUC files, as an independent count
    raw = raw_files()
    rawc = collections.Counter(''.join(''.join(v) for v in raw.values()))
    rhz = {c for c in rawc if HANZI(c)}

    npend = sum(len(v) for v in text.values())
    nraw = sum(len(v) for v in raw.values())
    print('pending.json: %d files, %d lines, %d glyph positions' % (len(text), npend, glyphpos))
    print('raw EUC dump: %d files, %d lines, %d glyph positions' % (len(raw), nraw, sum(rawc.values())))
    print('distinct kanji  %d in pending, %d in raw, %d in both' % (len(hz), len(rhz), len(hz & rhz)))
    print('distinct kana   %d ; positions %.1f%% of the corpus'
          % (len(kn), 100.0 * sum(allc[c] for c in kn) / glyphpos))
    print('kanji already in the stock font band: %d of %d (%.0f%%)' % (len(hz & band), len(hz),
          100.0 * len(hz & band) / len(hz)))
    miss = ''.join(sorted(hz - band))
    print('kanji with NO stock record (%d): %s' % (len(miss), miss or '-'))
    top = collections.Counter(other).most_common(12)
    print('non-kanji, non-kana characters: %d distinct -> %s'
          % (len(other), ', '.join('%r x%d' % t for t in top)))
    per = sorted(((len(''.join(v)), f) for f, v in text.items()), reverse=True)
    print('largest files: ' + ', '.join('%s:%d' % (f.split('.')[0], n) for n, f in per[:8]))
    print('smallest: ' + ', '.join('%s:%d' % (f.split('.')[0], n) for n, f in per[-4:]))
    if '--json' in sys.argv:
        json.dump({'files': {f: len(''.join(v)) for f, v in text.items()},
                   'distinct_kanji': ''.join(sorted(hz)),
                   'band_kanji': ''.join(sorted(hz & band)),
                   'distinct_kana': ''.join(sorted(kn)),
                   'other': other},
                  open(sys.argv[sys.argv.index('--json') + 1], 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main()
