"""Cost check for the ending theme's 21 lyric rows.

The bank has 32 unused glyph records left, but a batch only costs the characters it
*adds*: the prologue's 1142 chars are already in the font, and this song is written in
ordinary vocabulary.  So budget against the increment, not the total -- that number is
what decides whether the ending can be translated at all.

usage: python3 /tmp/draft_song.py
"""
import sys, json
sys.path.insert(0, 'REPO_ROOT/tools')
import tmtext as T
import build_prologue as B

K = B.UI_KEEP
DRAFT = [
    (0x1E4FE, '约会踩点的 水族馆'),
    (0x1E518, '我代替她 和他约会'),
    (0x1E536, '约定的时间 就算迟到'),
    (0x1E554, '道歉的样子 一点没有'),
    (0x1E570, '头发 被摸到的时候'),
    (0x1E58A, '是在想着她吧'),
    (0x1E5A2, '就像鱼儿一样 没有言语'),
    (0x1E5BE, '懂得越多 越难受'),
    (0x1E5D8, '谁都看得出 我们是恋人'),
    (0x1E5F2, '明明是同伴…'),
    (0x1E61C, '与你倒是 很相配'),
    (0x1E650, '我知道'),
    (0x1E65E, '不觉得 她比我可爱'),
    (0x1E69E, '配不上啦'),
    (0x1E6CC, '一句温柔的话'),
    (0x1E702, '我被吓到'),
    (0x1E728, '渐渐 看习惯了'),
    (0x1E740, '慢慢 喜欢上你'),
    (0x1E772, '完全 不是理想型'),
    (0x1E78C, '早就 明白了'),
    (0x1E7BC, '季节里'),
    (0x1E7DA, '可是已经 很擅长了'),
    (0x1E808, '气球在 不知不觉'),
    (0x1E834, '破掉的冲击 也很大'),
    (0x1E868, '派不上用场 的圣经'),
    (0x1E8A0, '还挺 难的功课'),
]

stock = T.Rom(B.SRC_ROM).data
g = json.load(open('REPO_ROOT/docs/research/glyph_alloc.json'))
owned = set(g['fresh']) | set(g['inplace']) | set(g['at_stock'])
owned |= {c for _, _, _, c, _ in B.UI_TEXT_ROWS for c in c}
rows, bad = [], 0
for addr, zh in DRAFT:
    n = 0
    while stock[addr + 2 * n] >= 0xF0 and n < 40:
        n += 1
    try:
        run = B.ui_run(stock, addr, n)
    except AssertionError as e:
        print('RUN %05X n=%d: %s' % (addr, n, e)); bad += 1; continue
    jp = ''.join(T.idx_to_char(i) or K for i in run)
    if len(zh) > n:
        print('TOO LONG %#X cap %d %r is %d' % (addr, n, zh, len(zh))); bad += 1
    kana = [c for c in zh if 'ぁ' <= c <= 'ㇺ']
    if kana:
        print('KANA %#X %s' % (addr, ''.join(kana))); bad += 1
    rows.append((addr, n, jp, zh))

new = sorted({c for _, _, _, zh in rows for c in zh if c not in owned and c != ' '})
print('\nrows %d  problems %d  codes %d  NEW records %d: %s'
      % (len(rows), bad, sum(r[1] for r in rows), len(new), ''.join(new)))
for a, n, jp, zh in rows:
    print("    (0X%05X, %2d, '%s', '%s', 'R')," % (a, n, jp, zh))
