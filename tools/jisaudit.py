"""Flag every on-screen cell whose font record we did NOT rewrite.

Such a cell is drawn with the stock JIS bitmap.  Inside translated dialog that
violates the standing rule, so this is the gate that proves the patch draws its
Chinese from WenQuanYi.  Each group below is reported twice, prefixed `on` or `off`
depending on whether the match landed on the real text grid (see the note before the
loop); only `on` can indict the patch.  The groups have their own answer:

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
rom = argv[1] if len(argv) > 1 else T.ROM_ZH
a = json.load(open(os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')))
ours = {int(v, 16) for g in ('fresh', 'inplace', 'at_stock') for v in a[g].values()}
table, words = U.record_map(rom)
sheets = sorted(x for x in os.listdir(DIR) if x.endswith('.png'))
foreign = collections.defaultdict(lambda: collections.Counter())
# A text cell always starts at x % 16 == 15, y % 16 == 1 (cell 0 at x=63, rows 161/177/193).
# `cells` slides its 14x14 window over every pixel, so it also reports off-grid matches:
# box rules and highlights, and -- since the glyphs sit 1 dot left of the Japanese ones --
# a neighbour-stock record read 1 px up-and-left of the real cell.  Only on-grid cells can
# prove the patch drew Japanese, so the verdict is split by that axis.
for n in sheets:
    for (x, y), idxs in U.cells(os.path.join(DIR, n), table, words).items():
        for i in idxs:
            if i in ours:
                continue
            on = 'on ' if x % 16 == 15 and y % 16 == 1 else 'off '
            group = on + ('symbol' if i < T.JIS_KANJI
                          else 'plate' if x <= 95 else 'inline')
            foreign[group][i] += 1
print('%d sheets, %d foreign slots' % (
    len(sheets), sum(len(v) for v in foreign.values())))
for group in ('on plate', 'on inline', 'on symbol', 'off plate', 'off inline', 'off symbol'):
    if not foreign[group]:
        continue
    print('%s: %s' % (group, ' '.join('%03X(%s)x%d' % (i, T.idx_to_char(i), n)
                                      for i, n in sorted(foreign[group].items()))))
if json_out:
    json.dump({'note': 'kanji slots the speaker nameplate draws from the stock font, '
                       'measured by %s over %s' % (os.path.basename(__file__), DIR),
               'plate': {'%03X' % i: T.idx_to_char(i)
                         for i in sorted(foreign['on plate'])}},
              open(json_out, 'w'), ensure_ascii=False, indent=1)
    print('-> %s' % json_out)
