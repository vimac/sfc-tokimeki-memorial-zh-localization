"""Price every remaining uncovered bank run in NEW glyph records, not total characters.

The song looked unaffordable for two rounds because it was costed at its full character
count; the font already holds 1146 records, so what a batch really pays for is the set
difference.  This lists each run still in Japanese with the characters a plain rendering
would add, so the last 20 free slots go to whatever is both visible and cheap.
"""
import sys, os, json, re
sys.path.insert(0, 'REPO_ROOT/tools')
import tmtext as T
import build_prologue as B

K = B.UI_KEEP
stock = T.Rom(B.SRC_ROM).data
g = json.load(open('REPO_ROOT/docs/research/glyph_alloc.json'))
owned = set(g['fresh']) | set(g['inplace']) | set(g['at_stock'])
covered = {r[0] for r in B.UI_TEXT_ROWS}

# every remaining run, with the rendering a Chinese player should see
CANDIDATES = [
    (0x19A54, 4, '体感マシ',   '体感机器'),
    (0x19A7C, 3, '嵐ヶ原',     '岚之原'),
    (0x19AC8, 6, 'エメラルドム', '翡翠海湾'),
    (0x19B74, 3, '力設定',     '心力设定'),
    (0x1FB50, 5, '噴奮文塀賓',  '喷奋文屏宾'),
    (0x1F3DA, 10, 'だぢづでどたちつてと', '的拟字得读他次自特土'),
    (0x1F482, 10, 'ダヂヅデドタチツテト', '的拟字得读他次自特土'),
    (0x1F558, 10, 'さしすせそたちつてと', '沙西苏塞索他七呰特刀'),
]
BANNED_HINT = re.compile(r'^\s*$')
rows = []
for addr, n, jp, zh in CANDIDATES:
    if addr in covered:
        print('ALREADY SHIPPED %#x' % addr)
        continue
    try:
        run = B.ui_run(stock, addr, n)
    except AssertionError as e:
        print('RUN %05X n=%d %r: %s' % (addr, n, jp, e))
        continue
    got = ''.join(T.idx_to_char(i) or K for i in run)
    ok = got.strip(' ') == jp
    new = {c for c in zh if c not in owned and c != ' '}
    print('%05X n=%-2d %-11s -> %-11s len %d  new %d %-6s %s'
          % (addr, n, jp, zh, len(zh), len(new), 'OK' if ok else 'MISMATCH',
             ''.join(sorted(new))))
    if ok and len(zh) <= n:
        rows.append((addr, n, jp, zh))
allnew = {c for _, _, _, zh in rows for c in zh if c not in owned and c != ' '}
print('\nrows that fit %d, total NEW records %d (only 20 slots free)' % (len(rows), len(allnew)))
