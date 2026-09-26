#!/usr/bin/env python3
"""证明这条事实：全库还有多少框是「同一句日文在别处写得更满、这里被写薄了」，而不是装不下。

批次 AH 的仪表（批次 AG 那条路的铺量版）。五条判据同时成立才算命中，缺任何一条都会大面积误配：
①同一句日文（剥句尾助词和 もう/どうも 类前缀后一致）**且两处日文长度差 <=2 字**——否则会把
  「さよなら、古式さん」（再见，古式同学。）当成「古式さん」（古式同学。）的更满写法；
②薄的那条是满的那条的**子序列**（＝同一措辞被删短，不是两种译法）；
③补进去的片段每段 <=4 字；④补的字在本框别处没出现过（否则改完整框重复）；
⑤框余量 >=2 B/补字——不满足的另报成「字节墙」，那是排版账不是文案账。
用法：python3 tools/thin_sweep.py [--md docs/research/batchAH_thin_forms.md]
"""
import sys, csv, json, pathlib, collections, argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tmtext as T
import build_zh as B

ROOT = pathlib.Path(__file__).resolve().parent.parent / 'docs/research'
JP_FUN = set('かよねねなよネヨもわぞざぜっんンぁぃぅぇぉゃゅょッ々ー')
CN_PUNCT = '，。、…！？「」『』（）：；ー・“”’'
import re
LEAD = re.compile(r'^(もう|どうも|やっぱり|そういえば|では|それでは|じゃ|それじゃ|じゃあ|それじゃあ|実は|ほんとうに)+、?')
PUNCT = re.compile(r'[、。「」『』（）：；…？！〜～\-·]')
HEX = re.compile(r'^[0-9a-f]{2}$')
BRACKET = re.compile(r'\[[0-9a-fA-F]{2}\]')
FORBID = re.compile('沧桑|桑田|采桑')      # 口径禁用，见 AGENTS.md §四


def jp_display(runs):
    """runs 列 → 日文显示串：吃掉尾部裸十六进制操作数和 [xx] 控制标记。"""
    toks = runs.split(' ')
    i = len(toks)
    while i > 0 and HEX.fullmatch(toks[i - 1]):
        i -= 1
    return BRACKET.sub('', ' '.join(toks[:i])).strip()


def cn_core(text):
    return re.sub('[' + re.escape(CN_PUNCT) + ']', '', text.replace('|', ''))


def stem(j):
    j = PUNCT.sub('', LEAD.sub('', jp_display(j)))
    while j and j[-1] in JP_FUN:
        j = j[:-1]
    for suf in ('です', 'ます', 'である', 'だ'):
        if j.endswith(suf):
            return j[:-len(suf)]
    return j


def insertions(a, b):
    """把 a 撑成 b 需要插入的片段；a 不是 b 的子序列则 None。"""
    pos, k = [], 0
    for ch in a:
        while k < len(b) and b[k] != ch:
            k += 1
        if k >= len(b):
            return None
        pos.append(k)
        k += 1
    segs, prev = [], -1
    for p in pos + [len(b)]:
        if p > prev + 1:
            segs.append(b[prev + 1:p])
        prev = p
    return segs


def steps():
    """整个镜像逐步：日文显示串、中文、实义字数、所在框的字节余量。"""
    pl = B.plan(verbose=False)
    out = []
    for p in sorted(ROOT.glob('block*_work.tsv')):
        blk = int(re.match(r'block(\d+)_work', p.name).group(1))
        zh = ROOT / ('block%d_zh.txt' % blk)
        if not zh.exists():
            continue
        lines = zh.read_text(encoding='utf-8').splitlines()
        budget, boxes = {}, collections.defaultdict(list)
        for r in csv.reader(open(p, encoding='utf-8'), delimiter='\t'):
            if len(r) < 9 or r[0].startswith('#'):
                continue
            try:
                n, cap, box = int(r[0]), int(r[4]), int(r[5])
            except ValueError:
                continue
            if 0 <= n < len(lines):
                boxes[box].append((n, cap, r[7], lines[n]))
        if blk in pl['by_blk']:
            ctx = pl['by_blk'][blk]
            for i, (lo, hi) in enumerate(ctx['spans']):
                if hi <= ctx['cov']:
                    budget[min(range(lo, hi))] = (
                        ctx['boxes'][i + 1]['bytes'],
                        sum(len(b) for b in ctx['seg_bytes'][lo:hi]))
        for box, ns in boxes.items():
            ns.sort()
            bud = budget.get(ns[0][0])
            slack = (bud[0] - bud[1]) if bud else None
            for n, cap, runs, cn in ns:
                j = jp_display(runs)
                out.append({'blk': blk, 'box': box, 'n': n, 'jp': j, 'cn': cn,
                            'J': len(PUNCT.sub('', j)), 'C': len(cn_core(cn)),
                            'stem': stem(runs), 'slack': slack})
    return out


def sweep(rows):
    """返回（命中列表, 字节墙处数）。"""
    boxes = collections.defaultdict(list)
    for s in rows:
        boxes[(s['blk'], s['box'])].append(s)
    grp = collections.defaultdict(list)
    for s in rows:
        if s['J'] >= 4:
            grp[s['stem']].append(s)
    hits, wall = [], 0
    for k, v in grp.items():
        if len(v) < 2 or len(k) < 3:
            continue
        best = max(v, key=lambda s: s['C'])
        for s in v:
            if best['C'] - s['C'] < 2 or s['C'] < 2 or best['J'] - s['J'] > 2 or FORBID.search(best['cn']):
                continue
            ins = insertions(cn_core(s['cn']), cn_core(best['cn']))
            if ins is None or any(len(x) > 4 for x in ins):
                continue
            sib = ''.join(cn_core(x['cn']) for x in boxes[(s['blk'], s['box'])] if x is not s)
            if any(x in sib for x in ins):
                continue
            need = 2 * sum(len(x) for x in ins)
            if s['slack'] is None:
                continue
            if s['slack'] < need:
                wall += 1
                continue
            hits.append({'stem': k, 'now': s['cn'], 'best': best['cn'], 'ins': ins,
                         'gap': sum(len(x) for x in ins), 'slack': s['slack'],
                         'jp': s['jp'], 'blk': s['blk'], 'box': s['box'], 'n': s['n']})
    return hits, wall


def report(hits, wall, path):
    groups = collections.defaultdict(list)
    for o in hits:
        groups[(o['stem'], o['now'], o['best'])].append(o)
    rows = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0]))
    multi = [(k, v) for k, v in rows if len(v) >= 2]
    single = [(k, v) for k, v in rows if len(v) == 1]
    L = ['# 批次 AH 清单：同一句日文在别处写得更满、这一框被写薄了',
         '',
         '这是批次 AG 那条路（「同一句日文在别处本来译得很好、这一框却写成残句」）按全库铺开后的清单。',
         '复现：`python3 tools/thin_sweep.py`（约 3 分钟，读原镜像算每框字节账）。',
         '',
         '## 一、判据（五条同时成立才算命中）', '',
         '1. **同一句日文**：剥掉句尾助词和 `もう/どうも/やっぱり/実は/ほんとうに` 这类前缀后一致，'
         '并且**两处日文长度差 <=2 字**。后半个条件是关键：不加它就会把「さよなら、古式さん」'
         '（再见，古式同学。）当成「古式さん」（古式同学。）的更满写法——那是跨句误配，不是落差。',
         '2. **薄的是满的子序列**：＝同一措辞只是被删短，不是两种译法。',
         '3. **补进去的片段每段 <=4 字**：更长说明满的那条多译了整句内容。',
         '4. **补的字在本框别处没出现过**：否则改完整框就重复。',
         '5. **框有余量 >=2 B/补字**：够把字落下去。所以这批不是字节墙，是当初写薄了。',
         '',
         '另外剔掉 `沧桑/桑田/采桑` 一族（口径禁用）。',
         '',
         '## 二、命中 %d 处 / %d 种形态' % (len(hits), len(rows)), '',
         '出现 >=2 次的 **%d 种覆盖 %d 处**（下表）；余下 %d 种各 1 处（§三）。' % (
             len(multi), sum(len(v) for _, v in multi), len(single)), '',
         '「补什么」全部取自本镜像别处已经上过屏的写法：不新增措辞、不新增字模。',
         '代价只是每个补字 1~2 字节，判据 5 按 2 B/字的最坏情况留量；落库前还要逐框实测一遍。', '',
         '| 处数 | 日文（词干） | 现在屏幕上 | 建议写法（别处的写法） | 补的字 | 最紧的框余量 |',
         '|---|---|---|---|---|---|']
    for (k, now, best), v in multi:
        L.append('| %d | %s | %s | %s | %s | %d B |' % (
            len(v), k, now.replace('|', ''), best.replace('|', ''),
            ' / '.join(''.join(x) for x in v[0]['ins']), min(x['slack'] for x in v)))
    L += ['', '## 三、只出现 1 处的 %d 种' % len(single), '',
          '同一判据，只是这种日文全库独此一处——没有多数写法可并齐，是**这一处自己写薄了**。',
          '',
          '| 块/框 | 日文（词干） | 现在屏幕上 | 别处更满的写法 | 补的字 | 余量 |',
          '|---|---|---|---|---|---|']
    for (k, now, best), v in single:
        o = v[0]
        L.append('| b%d/%d | %s | %s | %s | %s | %d B |' % (
            o['blk'], o['box'], k, now.replace('|', ''), best.replace('|', ''),
            ' / '.join(''.join(x) for x in o['ins']), o['slack']))
    L += ['', '## 四、查过但不成立的判据（别再重开）', '',
          '* **「残句步」**（按步筛中文只剩 1 个实义字符、日文却有完整谓语）：命中 37 处，逐条按整框回读后 '
          '37 处全是跨步分句的正常写法——例 `片桐さんの奴 ‖ 気持ちよさそうに ‖ 寝てるよ` → '
          '「片桐同学她呀、 ‖ 睡得正香 ‖ 呢。」。这一判据实际命中 **0 处**。',
          '* **词典体「写薄」**：249 条宏体的中文正文短于日文一半，抽查显示绝大多数只是中文信息密度高'
          '（`ありがとうございました`→「多谢款待」、`ジェットコースターに乗ろう`→「去坐过山车吧」），'
          '不是缺陷；这一类没有「别处的更满写法」作依据，只能人工通读。',
          '',
          '## 五、同类但改不了的量', '',
          '把判据 5 反过来（同样偏薄、**框余量装不下**）测得 **%d 处**。这些是字节墙，'
          '要么等码表/字库腾余量，要么就地换更短的说法，不属于「照别处并齐」这一类。' % wall, '']
    pathlib.Path(path).write_text('\n'.join(L), encoding='utf-8')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--md', default=str(ROOT / 'batchAH_thin_forms.md'))
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    rows = steps()
    print('步 %d / 框 %d' % (len(rows), len({(r['blk'], r['box']) for r in rows})))
    hits, wall = sweep(rows)
    if a.json:
        json.dump(hits, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    report(hits, wall, a.md)
    print('命中 %d 处 / 字节墙 %d 处 -> %s' % (len(hits), wall, a.md))
