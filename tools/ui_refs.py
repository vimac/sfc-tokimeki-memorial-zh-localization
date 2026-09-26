"""Which glyph indices the *UI* draws, read off the screen instead of off a pointer.

`allocate()` protects the slots a TEXT_PTRS-reachable block can reach, plus the kana
redirect and the preset-name table.  That is not enough: the name-entry keyboard, the
file-select labels and the status screen's tabs copy records straight out of the shared
3510-record font array, so a slot none of those scans sees is still live font.  When one
was handed to 干 the keyboard's 漢字 tab silently became 干字.

So decode the captured screens and ask which records are actually on pixels.  Every
16x14 window is hashed with the same 64-bit rolling hash used for the ROM's records and
only exact matches are kept, which makes a hit unambiguous.  The result is the set of
slots the patch must never claim.

usage: python3 tools/ui_refs.py <capture_dir> [...] [--out FILE]
       python3 tools/ui_refs.py <capture_dir> [...] --dump ROM   # print the screens' text

tools/name_entry.py produces such a directory for the pre-prologue flow.
"""
import sys, os, json, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import tmtext as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHITE = 200                       # these labels are drawn white on a mid-tone paper
HASH_BITS = 64
MASK = (1 << HASH_BITS) - 1


def _weights():
    rng = np.random.default_rng(20260919)
    return [int(x) for x in rng.integers(1, 1 << 62, size=14)]


WEIGHTS = _weights()


def hash_words(words):
    """The hash of one 14-row-word record, matching `hash_plane`'s window hash."""
    h = 0
    for w, wt in zip(words, WEIGHTS):
        h = (h + w * wt) & MASK
    return h


def row_words(ink):
    """(H, W-15) uint64 of the 16-bit row word starting at each pixel.

    Bit15 is the leftmost pixel, exactly what the drawer copies into OBJ/tile RAM.
    """
    bits = (1 << np.arange(15, -1, -1)).astype(np.uint64)
    win = np.lib.stride_tricks.sliding_window_view(ink, 16, axis=1)
    return (win.astype(np.uint64) * bits).sum(2)


def hash_from(P):
    """Window hashes for every origin, given the row-word plane."""
    h = np.zeros((P.shape[0] - 13, P.shape[1]), dtype=np.uint64)
    for r, wt in enumerate(WEIGHTS):
        h = (h + P[r:r + h.shape[0]] * np.uint64(wt)) & np.uint64(MASK)
    return h


def cells(img_path, table, words_by_index, min_ink=12):
    """{(x, y): [index]} for every window that reproduces a font record exactly.

    `min_ink` matters: the array's tail holds records with a couple of lit pixels, and
    without it they match sparse sprite art and look like live UI glyphs.
    """
    g = np.asarray(Image.open(img_path).convert('RGB'), dtype=np.int16).mean(2)
    P = row_words((g > WHITE).astype(np.uint8))
    C = np.zeros_like(P)
    for r in range(P.shape[0]):
        C[r] = np.bitwise_count(P[r])
    dense = np.zeros((C.shape[0] - 13, C.shape[1]), dtype=np.uint64)
    for r in range(14):
        dense = dense + C[r:r + dense.shape[0]]
    hits = {}
    ys, xs = np.nonzero((hash_from(P) != 0) & (dense >= min_ink))
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        got = tuple(int(P[y0 + r, x0]) for r in range(14))
        for i in table.get(hash_words(got), ()):
            if words_by_index.get(i) == got:
                hits.setdefault((x0, y0), []).append(i)
    return hits


def record_map(rom_path):
    """hash -> [index] plus index -> row words for one ROM's font array.

    A record's row words are stored little-endian, so read them that way: the screen's
    leftmost pixel is bit15, and matching byte orders is what makes a hit mean anything.
    The fully-lit records are skipped -- they are the highlight block the fade uses, and
    every one of them matches a white patch of art.
    """
    d = open(rom_path, 'rb').read()
    hits, words = collections.defaultdict(list), {}
    for i in range(T.MAX_INDEX):
        o = T.glyph_offset(i)
        raw = bytes(d[o:o + 28])
        if raw == b'\x00' * 28 or raw == b'\xff' * 28:
            continue
        w = struct.unpack('<14H', raw)
        hits[hash_words(w)].append(i)
        words[i] = w
    return hits, words


def decode_lines(img_path, table, words, label=None):
    """The screen's text, one string per row of cells.

    `label` maps an index to the character to print for it; without it the JIS name of
    the slot is used, which is right for the Japanese ROM and wrong for a patched one
    (a slot we took over would print the kanji that used to live there).
    """
    rows = collections.defaultdict(list)
    for (x, y), idxs in cells(img_path, table, words).items():
        i = idxs[0]
        rows[y].append((x, (label or {}).get(i) or T.idx_to_char(i) or '?'))
    return [(y, ''.join(c for _, c in sorted(v))) for y, v in sorted(rows.items())]


def main(argv):
    dirs = [a for a in argv if not a.startswith('--')]
    out = os.path.join(ROOT, 'docs', 'research', 'ui_glyph_indices.json')
    if '--out' in argv:
        out = argv[argv.index('--out') + 1]
        dirs.remove(out)
    if '--dump' in argv:
        rom = argv[argv.index('--dump') + 1]
        dirs.remove(rom)
        table, words = record_map(rom)
        label = {}
        alloc = os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')
        if os.path.exists(alloc):
            a = json.load(open(alloc))
            for g in ('fresh', 'inplace', 'at_stock'):
                for ch, hx in a.get(g, {}).items():
                    label[int(hx, 16)] = ch
        for dirpath in dirs:
            for n in sorted(x for x in os.listdir(dirpath) if x.endswith('.png')):
                print('== %s' % n)
                for y, line in decode_lines(os.path.join(dirpath, n), table, words, label):
                    print('  y%3d %s' % (y, line))
        return
    table, words = record_map(T.ROM_JP)
    seen = collections.defaultdict(list)
    total = 0
    for dirpath in dirs:
        names = sorted(n for n in os.listdir(dirpath) if n.endswith('.png'))
        for n in names:
            hits = cells(os.path.join(dirpath, n), table, words)
            total += len(hits)
            for (x, y), idxs in hits.items():
                for i in idxs:
                    seen[i].append('%s:%d,%d' % (n.split('_')[0], x, y))
        print('%s: %d cells so far' % (dirpath, total))
    kanji = {i: v for i, v in seen.items() if i >= T.JIS_KANJI}
    json.dump({'note': 'font indices the pre-prologue UI draws on screen, from %d cells' % total,
               'drawn': {'%03X' % i: {'jp': T.idx_to_char(i), 'where': sorted(set(v))[:4]}
                         for i, v in sorted(kanji.items())}},
              open(out, 'w'), ensure_ascii=False, indent=1)
    print('%d kanji-band indices drawn by the UI -> %s' % (len(kanji), out))
    print(' '.join('%03X(%s)' % (i, T.idx_to_char(i)) for i in sorted(kanji)))


if __name__ == '__main__':
    main(sys.argv[1:])
