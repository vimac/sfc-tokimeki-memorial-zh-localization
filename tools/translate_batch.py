"""批量剧情翻译流水线 (TM 翻译记忆 + 人名占位符).

TM 命中: 段落规范化后查表输出中文
未命中: 记入待翻清单
产出: translations/tm_coverage.txt, translations/pending_*.txt
"""
import os, re, glob, json
from collections import Counter

JP = 'reference/j2e_full/scripts_x/Scripts/Japanese/Tksc'

# 人名表 (替换为占位符 <N>) —— 真值在 translations/name_glossary.tsv，
# 那里同时给出 wiki 的通行译名，所以不要再在本文件里手写人名：漏一个姓就会让
# 该角色的所有台词规范化不出同一个 <N>，TM 就白分了。
GLOSSARY_PATH = 'translations/name_glossary.tsv'


def _glossary(path=GLOSSARY_PATH):
    """{日文: 中文} for every row typed ``name`` in the glossary."""
    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            col = line.rstrip('\n').split('\t')
            if len(col) >= 3 and col[2] == 'name':
                out[col[0]] = col[1]
    return out


GLOSSARY = _glossary()
NAMES = list(GLOSSARY)

# 翻译记忆: 规范化日文(人名-><N>) => 中文
TM = {
    "「‥‥‥‥‥‥‥‥‥‥。": "「………………。",
    "<N>　「‥‥‥‥‥‥‥‥‥‥。": "「………………。",
    "<N>「おーい、<N>さーん。待ってくれー。": "「喂——<N>——等等我啊——!",
    "<N>「おーい、<N>…。待ってくれー。": "「<N>……等等我啊——!",
    "<N>「やっぱり、この身なりじゃ、逃げられるよなぁ。": "「果然,这身打扮还是被发现了呀。",
    "<N>「しょうがない、家に帰るか。": "「没办法,回家吧。",
    "<N>「<N>は、とうとう来なかったな。": "「<N>,终究还是没有来啊。",
    "<N>「どうしたんだろう?しょうがない、家に帰るか。": "「怎么回事呢?没办法,回家吧。",
    "<N>「<N>、ごめんね。ちょっとした手違いで、遅くなっちゃった。": "「<N>,抱歉啊。出了点小差错,来晚了。",
    "<N>「遅れなくてよかったよ。": "「还好没有迟到。",
    "<N>「遅れなくてよかった。": "「还好没有迟到。",
    "<N>「遅いわよ。もう、帰るところだったんだから。": "「太迟了啦。我都要回去了。",
    "<N>「ごめんよ。|もう二度としないから。": "「对不起,再也不这样了。",
    "<N>「待った?": "「等很久了吗?",
    "<N>「<N>さん、遅いな。": "「<N>,真慢啊。",
    "<N>「<N>の奴、遅いな‥‥。どうしたのかな?": "「<N>那家伙,真慢啊……怎么回事呢?",
    "<N>「本当にごめんね。": "「真的非常抱歉。",
    "<N>「ごめん。|悪かった。": "「抱歉。是我的不好。",
    "<N>「本当、寒いね。": "「真的,好冷啊。",
    "<N>「眠くなる季節の到来だね。": "「让人发困的季节到来了呢。",
    "<N>「そうだね。すごく暑いね。": "「是啊。非常热呢。",
    "<N>「本当、過ごし易くなったよ。": "「真的,变得舒服了哦。",
    "<N>「読んでくれたんだ。ありがとう。": "「你读了啊。谢谢。",
    "<N>「いや、そんな大した事じゃないから。": "「不,又不是什么了不起的事。",
    "<N>「気に入ってくれた?": "「你喜欢吗?",
    "<N>「気に入ってくれて、良かったよ。": "「你能喜欢,太好了。",
    "<N>「うん、読書の秋だもんね。": "「嗯,秋天就是读书的季节嘛。",
    "<N>「そ、そうだね。": "「是、是啊。",
}

def norm(jp):
    """规范化: 剥控制码/换行/空白/说话人, 人名-><N>"""
    s = re.sub(r'<\$[0-9A-Fa-f]{2}>', '', jp)
    s = s.replace('\r', '').replace('\n', '')   # 换行删除(排版)
    s = s.replace('　', '').replace(' ', '')
    # 人名替换 (长的优先)
    for nm in sorted(NAMES, key=len, reverse=True):
        s = s.replace(nm, '<N>')
    # 说话人行首剥离: <N>「 / Saro「 等
    s = re.sub(r'^(<N>|[A-Za-z]+)?「', '「', s)
    return s

def main():
    # TM key 也做同样的说话人规范化; 另读增量 tm.json
    TM2 = {}
    for k, v in TM.items():
        k2 = re.sub(r'^<N>　?「', '「', k)
        TM2[k2] = v
    try:
        import json as _json
        for k, v in _json.load(open('translations/tm.json')).items():
            k2 = re.sub(r'^<N>　?「', '「', k)
            TM2.setdefault(k2, v)
    except Exception:
        pass

    files = sorted(glob.glob(f'{JP}/TKSC*.EUC'))
    hit = miss = 0
    miss_by_file = {}
    out = open('translations/tm_coverage.txt', 'w')
    for fp in files:
        base = os.path.basename(fp)
        txt = open(fp, 'rb').read().decode('euc-jp', errors='ignore')
        segs = [s for s in txt.split('●') if s.strip()]
        m = mm = 0
        for i, s in enumerate(segs):
            key = norm(s)
            if key in TM2:
                m += 1
            else:
                mm += 1
                miss_by_file.setdefault(base, []).append((i, key[:70]))
        hit += m; miss += mm
        out.write(f'{base}: 命中{m} 待翻{mm}\n')
    out.write(f'\n总计: 命中 {hit} ({hit*100//(hit+miss)}%), 待翻 {miss}\n')
    out.close()
    json.dump(miss_by_file, open('translations/pending.json','w'), ensure_ascii=False, indent=0)
    print(f'总段 {hit+miss}, TM 命中 {hit} ({hit*100//(hit+miss)}%), 待翻 {miss}')
    print('待翻最多的文件:')
    for base, lst in sorted(miss_by_file.items(), key=lambda x: -len(x[1]))[:10]:
        print(f'  {base}: {len(lst)} 段')

if __name__ == '__main__':
    main()
