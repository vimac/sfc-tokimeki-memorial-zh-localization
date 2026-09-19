"""Flag every on-screen cell whose font record we did NOT rewrite.

Such a cell is drawn with the stock JIS bitmap.  Inside translated dialog that
violates the standing rule, so this is the gate that proves the patch draws its
Chinese from WenQuanYi.  Three groups, reported separately because each has its
own answer:

  plate   -- the speaker nameplate (x <= 95 on the first dialog row).  It is drawn
             from name tables no text pointer reaches, the same way the `$E806`
             date glyphs are, so a block patch cannot touch it.
  inline  -- the player's own name substituted into a line.  That text is typed on
             the in-game kanji keyboard, so it is whatever the player picked.
  symbol  -- everything below the kanji band: the window's ┐/＿ rules, the 「 box
             bracket, and the full-width digits the `$E806` birthday splice draws.
             Script-neutral, so the Japanese bitmap is not standing in for a
             Chinese character.  Kana here would *not* be neutral, which is the
             real reason this group is scanned: an untranslated さん splice from
             the `$E803` name table would show up here.

usage: python3 tools/jisaudit.py [sheets-dir] [rom] [--json nameplate-out.json]
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T, ui_refs as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = [a for a in sys.argv[1:]]
json_out = None
if '--json' in argv:
    json_out = argv.pop(argv.index('--json') + 1)
DIR = argv[0] if argv else os.path.join(ROOT, 'docs', 'prologue_zh')
rom = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'rom_prologue_zh.sfc')
a = json.load(open(os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')))
ours = {int(v, 16) for g in ('fresh', 'inplace', 'at_stock') for v in a[g].values()}
table, words = U.record_map(rom)
sheets = sorted(x for x in os.listdir(DIR) if x.endswith('.png'))
foreign = collections.defaultdict(lambda: collections.Counter())
for n in sheets:
    for (x, y), idxs in U.cells(os.path.join(DIR, n), table, words).items():
        for i in idxs:
            if i in ours:
                continue
            group = 'symbol' if i < T.JIS_KANJI else ('plate' if x <= 95 else 'inline')
            foreign[group][i] += 1
print('%d sheets, %d foreign slots' % (
    len(sheets), sum(len(v) for v in foreign.values())))
for group in ('plate', 'inline', 'symbol'):
    if not foreign[group]:
        continue
    print('%s: %s' % (group, ' '.join('%03X(%s)x%d' % (i, T.idx_to_char(i), n)
                                      for i, n in sorted(foreign[group].items()))))
if json_out:
    json.dump({'note': 'kanji slots the speaker nameplate draws from the stock font, '
                       'measured by %s over %s' % (os.path.basename(__file__), DIR),
               'plate': {'%03X' % i: T.idx_to_char(i)
                         for i in sorted(foreign['plate'])}},
              open(json_out, 'w'), ensure_ascii=False, indent=1)
    print('-> %s' % json_out)
