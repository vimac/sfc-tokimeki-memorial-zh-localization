"""Prove the blast radius of one dictionary body: every box that folds it, and whether it survives a reword.

usage: python3 tools/dict_blast.py e979 ea0b
       python3 tools/dict_blast.py ea34 --want 摘一朵带回去
       python3 tools/dict_blast.py --from-doc docs/research/batchAM_dict_requests.md

改宏体正文＝同时改全部调用点（AGENTS §五）。这个仪表把调用点分成三种，因为「能不能改」完全取决于比例：

  bare   那一段只有宏体（+ 终止符）——新体只要还装得进自己的跨度，改完照样折叠。
  tail   体后面只挂着标点（「〔摘一朵带回〕？」）——看着像壳，其实重写代价≈0，照新体抄一遍就行。
  shell  体前后有实义字面（「我是〔时代剧迷〕来着」）——一改就不再折叠，框凭空多出整段字面字节。
         批次 AG 的 b47 就是这么炸的：先改体、后改壳行，少一边就破框。

跨度只信 `macro_span()`：`phrase_glossary.tsv` 第 2 列是人账，批次 AN 实测 1,016 条里有 383 行与真值
不符（三行写着 0，正文却住着 6~8 B），所有「span 未登记」的悬案都出在那一列。**装正文的上限是
`span - 1`**——体末尾还要落一个 `$0A`。字节按**本次 86 字码表**
（`block0_enc.json` 的 `codepage`）算：表内字 1 B、其余汉字 2 B、`SB_SHARE` 那批中日共用格
（「」（）、。？…‥）1 B、段末「，」2 B 而段末「。」1 B——
所以这个数是给裁决用的，落库仍以构建的每框账为准（AGENTS §三.7）。
"""
import sys, os, re, glob, json, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import build_prologue as B

# 段末那一个字符会被编码成框的终止码，所以它不算字面壳（AGENTS §五 终止符表）
TERMC = set(u'。？！、…」）’】「『（')
# 「」（）、。？…‥ 是中日共用的单字节 SB 码（`SB_SHARE`），照汉字计 2 B 会把体长估长一倍
P1 = B.SB_SHARE | set(u'、。？！…「」』【】')
PAGE = set(json.load(open('%s/docs/research/block0_enc.json' % ROOT, encoding='utf-8'))['codepage'])
GLOS = B.phrase_glossary()
_rom = B.T.Rom(B.SRC_ROM)
_code = B.Codec(_rom)

RAW = {}
for _p in glob.glob('%s/docs/research/block*_zh.txt' % ROOT) + ['%s/docs/research/prologue_zh.txt' % ROOT]:
    _b = os.path.basename(_p)
    _blk = 144 if _b == 'prologue_zh.txt' else int(re.match(r'block(\d+)_zh', _b).group(1))
    RAW[_blk] = open(_p, encoding='utf-8').read().split('\n')


def cost(s):
    """What a line costs its box, in bytes, on the code page the current disc carries."""
    n = 0
    for seg in s.split('|'):
        for i, c in enumerate(seg):
            last = i == len(seg) - 1
            if c == u'，':
                n += 2 if last else 1
            elif c in P1:
                n += 1
            else:
                n += 1 if c in PAGE else 2
    return n + s.count('|')


def classify(body):
    out = []
    for blk in sorted(RAW):
        for n, line in enumerate(RAW[blk]):
            if body not in line:
                continue
            for seg in line.split('|'):
                if body not in seg:
                    continue
                pre, post = seg.split(body, 1)
                kind = 'shell' if pre else ('bare' if not post else
                                            ('bare' if set(post) <= TERMC and len(post) == 1 else
                                             ('tail' if set(post) <= TERMC else 'shell')))
                out.append((blk, n, kind, seg))
    return out


def scan(key, want=None):
    body = GLOS.get(key)
    lo, hi = B.macro_span(_code, key)
    # 宏体后面还要落一个 `$0A` 终止符，它住在同一段里：体最长只能是 span-1 B
    # （`macro_bodies` 判的是 `len(body) + 1 > span`，批次 AO 就是拿这条把
    # 「拜托了，神大人」10 B 从「正好装得下」改成「装不下」的）。
    span = hi - lo - 1
    if not body:
        print('%-5s 体上限 %-4dB 无中文正文（A′ 新建类：%s）' %
              (key, span, '装得下 %d B' % span if want and cost(want) <= span
               else '装不下 %d B' % cost(want) if want else '要先写正文'))
        return
    hits = classify(body)
    c = collections.Counter(k for _, _, k, _ in hits)
    print('%-5s 正文=%r %dB / 体上限 %d 余 %d   调用 %d 段（裸 %d / 尾挂 %d / 真壳 %d）' %
          (key, body, cost(body), span, span - cost(body), len(hits),
           c['bare'], c['tail'], c['shell']))
    for blk, n, k, seg in [h for h in hits if h[2] == 'shell'][:8]:
        pre, post = seg.split(body, 1)
        print('        壳 b%-4s#%-5s %s〔%s〕%s' % (blk, n, pre, body, post))
    if c['shell'] > 8:
        print('        ... %d 处真壳未列' % (c['shell'] - 8))
    print('        分布 %s' % ' '.join('%s:%d' % kv for kv in
          list(collections.Counter('%d' % b for b, _, _, _ in hits).items())[:8]))
    if want:
        print('        期望正文 %r %dB → %s' % (want, cost(want),
              'FIT 余 %d' % (span - cost(want)) if cost(want) <= span else 'OVER +%d 字节墙' %
              (cost(want) - span)))


def main():
    a = sys.argv[1:]
    want = None
    if '--want' in a:
        i = a.index('--want'); want = a[i + 1]; a = a[:i] + a[i + 2:]
    if a and a[0] == '--from-doc':
        txt = open(os.path.join(ROOT, a[1]), encoding='utf-8').read()
        SKIP = {'a%d' % i for i in range(8)} | {'ac', 'ad'}
        keys, pat = [], re.compile(r'⟦([0-9A-Fa-f]{2,4})⟧|`([0-9a-fA-F ]{2,11})`')
        for m in pat.finditer(txt):
            toks = [t for t in re.split(r'[ ,/]+', (m.group(1) or m.group(2) or '').strip())
                    if re.fullmatch(r'[0-9a-fA-F]{1,4}', t)]
            i = 0
            while i < len(toks):
                t = toks[i].lower()
                if len(t) == 4:
                    k, i = t, i + 1
                elif len(t) == 2 and 'e8' <= t <= 'ef' and i + 1 < len(toks) and len(toks[i + 1]) == 2:
                    k, i = t + toks[i + 1].lower(), i + 2
                elif len(t) == 2 and t not in SKIP:
                    k, i = t, i + 1
                else:
                    i += 1
                if k not in SKIP and k not in keys:
                    keys.append(k)
        print('doc 里点名 %d 个宏码' % len(keys))
        a = keys
    for k in a:
        scan(k.lower(), want)


if __name__ == '__main__':
    main()
