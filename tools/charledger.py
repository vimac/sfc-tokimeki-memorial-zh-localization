"""How many glyph records the whole Chinese vocabulary really costs, and in what order to pay.

Censuses every hanzi our translated sources use (per source, re-runnable), then classifies
each distinct character as *owned* (the build already holds a record), *inplace* (the stock band
has an index whose character is exactly this one, so rewriting that record in place is free
and cannot mis-render surviving Japanese text), or *new* (needs a fresh slot or a B-tier
takeover).  Because the census is frequency-ordered, the same table is the trimming list: if
the pool is short, drop the tail first.

usage: python3 tools/charledger.py init | ingest | report | tail [N]

The database is derived, never authoritative: out/charledger.sqlite is rebuilt from the
sources listed in SOURCES (plus the builder's own UI_TEXT_ROWS), and the ROM is not touched.
"""
import os
import re
import sys
import sqlite3
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
DB = os.path.join(ROOT, 'out', 'charledger.sqlite')
ALLOC = os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')

MACRO = re.compile(r'⟦[^⟧]*⟧')
HANZI = lambda c: '一' <= c <= '鿿'

SOURCES = (
    ('block144', 'docs/research/prologue_zh.txt'),
    ('block8', 'docs/research/block8_zh.txt'),
    # Block 0's file grows one box-run at a time from segment 0, so the lines that
    # are not shipped yet simply are not in it -- nothing here may assume it is whole.
    ('block0', 'docs/research/block0_zh.txt'),
    ('block2', 'docs/research/block2_zh.txt'),
    ('block32', 'docs/research/block32_zh.txt'),
    ('block35', 'docs/research/block35_zh.txt'),
    ('block38', 'docs/research/block38_zh.txt'),
    ('block18', 'docs/research/block18_zh.txt'),
    ('block44', 'docs/research/block44_zh.txt'),
    ('block95', 'docs/research/block95_zh.txt'),
    ('block107', 'docs/research/block107_zh.txt'),
    ('block126', 'docs/research/block126_zh.txt'),
    ('block131', 'docs/research/block131_zh.txt'),
    ('block132', 'docs/research/block132_zh.txt'),
    ('block96', 'docs/research/block96_zh.txt'),
    ('block97', 'docs/research/block97_zh.txt'),
    ('block99', 'docs/research/block99_zh.txt'),
    ('block108', 'docs/research/block108_zh.txt'),
    ('block68', 'docs/research/block68_zh.txt'),
    ('block21', 'docs/research/block21_zh.txt'),
)

# Draft translations that are *not* in the ROM yet -- pricing them is the whole point of
# the ledger, so they get censused under their own src name and stay out of the build.
DRAFTS = (
    ('draft:TKSC2_zh', 'translations/TKSC2_zh.tsv'),
    ('draft:TKSC3_zh', 'translations/TKSC3_zh.tsv'),
)


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS usage(
            ch   TEXT   NOT NULL,
            src  TEXT   NOT NULL,
            n    INTEGER NOT NULL,
            PRIMARY KEY(ch, src));
        CREATE VIEW IF NOT EXISTS census AS
            SELECT ch, SUM(n) AS n FROM usage GROUP BY ch ORDER BY n DESC;
    """)
    return db


def owned_chars():
    import json
    g = json.load(open(ALLOC, encoding='utf-8'))
    return set(g['fresh']) | set(g['inplace']) | set(g['at_stock'])


def claimed_indices():
    """Indices our own build already points at, so they cannot also be rewritten in place.

    ``at_stock``/``inplace`` are bound to their own character -- `allocate`'s
    `stock_binding` only binds on an exact codepoint match, and `char_to_idx` is
    injective, so an index in them can never be the one some other character needs.
    ``fresh`` is the range allocate() handed out, and an index in it already draws a
    *different* hanzi; rewriting it would silently corrupt that character.
    """
    import json
    g = json.load(open(ALLOC, encoding='utf-8'))
    return {int(v, 16) for v in g['fresh'].values()}


def text_counts(text):
    out = collections.Counter()
    for ch in MACRO.sub('', text):
        if HANZI(ch):
            out[ch] += 1
    return out


def row_counts():
    import build_prologue as B
    out = collections.Counter()
    for row in B.UI_TEXT_ROWS:
        for ch in row[3]:
            if HANZI(ch):
                out[ch] += 1
    return out


def store(db, src, counter):
    db.execute('DELETE FROM usage WHERE src = ?', (src,))
    db.executemany('INSERT INTO usage VALUES(?,?,?)',
                   [(ch, src, n) for ch, n in counter.items()])


def tsv_counts(path):
    out = collections.Counter()
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        header = f.readline()
        col = max(header.rstrip('\n').split('\t').index('chinese'), 0)
        for line in f:
            fields = line.rstrip('\n').split('\t')
            if len(fields) > col:
                out.update(c for c in fields[col] if HANZI(c))
    return out


def ingest(db):
    for src, rel in SOURCES:
        store(db, src, text_counts(open(os.path.join(ROOT, rel), encoding='utf-8').read()))
    store(db, 'bank-ui', row_counts())
    for src, rel in DRAFTS:
        store(db, src, tsv_counts(rel))
    db.commit()


def tiered(db, where='', args=()):
    have = owned_chars()
    claimed = claimed_indices()
    sql = 'SELECT ch, SUM(n) FROM usage %s GROUP BY ch ORDER BY 2 DESC' % where
    rows = []
    for ch, n in db.execute(sql, args):
        idx = T.char_to_idx(ch)
        if ch in have:
            tier = 'owned'
        elif idx is not None and idx not in claimed:
            tier = 'inplace'
        else:
            tier = 'new'
        rows.append((ch, n, tier))
    return rows


def show(rows, label):
    by = collections.defaultdict(lambda: [0, 0])
    for ch, n, tier in rows:
        by[tier][0] += 1
        by[tier][1] += n
    total = sum(n for _, n, _ in rows)
    print('%s: %d distinct hanzi, %d positions' % (label, len(rows), total))
    for tier in ('owned', 'inplace', 'new'):
        c, p = by[tier]
        print('  %-5s %4d chars  %7d positions  (%.1f%%)'
              % (tier, c, p, 100.0 * p / max(total, 1)))
    return by


def report(db):
    show(tiered(db), 'census (in-build + draft)')
    show(tiered(db, 'WHERE src NOT LIKE ?', ('draft:%',)), 'shipped text only')
    show(tiered(db, "WHERE src LIKE 'draft:%' AND ch NOT IN "
                    '(SELECT ch FROM usage WHERE src NOT LIKE ?)',
                ('draft:%',)), 'draft lines, characters the build does not have yet')
    print('  "inplace" is the free tier -- those chars already have a stock index of their own, '
          'so a whole-font backfill rewrites the record in place at zero slot cost, and '
          'surviving Japanese text still reads correctly.')
    print('  "new" has to be placed: the fresh pool is what build_prologue.py prints on its '
          '`glyphs:` line every build -- read it there, never here, because this file is a '
          'snapshot and that one is the ledger.  The rest waits for the end-of-game B-tier '
          'takeover, one stock index at a time, as its last Japanese reference gets translated.')
    print('  trimming order = frequency tail: tools/charledger.py tail 60')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'report'
    db = connect()
    if cmd == 'init':
        print('schema ready at %s' % os.path.relpath(DB, ROOT))
    elif cmd == 'ingest':
        ingest(db)
        print('ingested %d distinct hanzi from %d sources'
              % (db.execute('SELECT COUNT(*) FROM census').fetchone()[0], len(SOURCES) + 1))
    elif cmd == 'tail':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        rows = tiered(db)
        tail = sorted(rows, key=lambda r: (-r[1], r[0]))[-n:]
        print(''.join('%s(%d)' % (ch, cnt) for ch, cnt, tier in tail))
        print('rarest tier counts: %s' % collections.Counter(t for _, _, t in tail))
    else:
        report(db)


if __name__ == '__main__':
    main()
