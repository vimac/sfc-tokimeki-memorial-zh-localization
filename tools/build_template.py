"""翻译模板生成器.

源: J2E 日文 .EUC 脚本(真值原文, 控制码 <$XX> 直通)
验证: EUC 段字符集 vs ROM 块解码段字符集 的重叠率 → TKSC n ↔ 块 n 对应确认
产出: out/script/template.tsv (翻译稿: 块/段/日文/控制码/字节预算/中文列)
"""
import struct, json, os, re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
ROM = 'Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc'
EUC_DIR = 'reference/j2e_full/scripts_x/Scripts/Japanese/Tksc'
NAME_PTR = 0x9872
TEXT_PTR = 0x9872 + 435
NBLOCK = 145

seq = ("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとど"
       "なにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑを")
T1 = {0x50+i: c for i, c in enumerate(seq)}
T1.update({0x4F:'ん', 0x44:'、', 0x47:'…', 0x25:'…', 0x22:'「', 0x23:'」'})
ROWDELTA = {0x81:0x72D8,0x82:0x7082,0x83:0x6DBD,0x8A:0x689E,0x8B:0x685A,0x8C:0x6816,0x8D:0x67D3,
            0x8E:0x678E,0x8F:0x674B,0x90:0x6706,0x91:0x66C3,0x92:0x667E,0x93:0x663A,
            0x95:0x65B3,0x96:0x656E,0x97:0x652A,0x98:0x64E7}

data = open(ROM,'rb').read()

def parse_ptr(off):
    b0, b1, b2 = data[off], data[off+1], data[off+2]
    return (b2 - 0x80) * 0x8000 - 0x7E00 + (b1 << 8 | b0)

text_ptrs = [parse_ptr(TEXT_PTR + i*3) for i in range(NBLOCK)]
order = sorted(range(NBLOCK), key=lambda i: text_ptrs[i])
bounds = {}
for idx, i in enumerate(order):
    st = text_ptrs[i]
    en = text_ptrs[order[idx+1]] if idx+1 < len(order) else st + 0x2000
    bounds[i] = (st, min(en, st+0x8000))

def rom_segments(bidx):
    """块内按 0x00 切段, 返回 [(offset, nbytes, 解码文本)]"""
    st, en = bounds[bidx]
    segs = []
    i = st
    seg_start = st
    cur = []
    while i < en:
        b = data[i]
        if b == 0x00:
            if cur: segs.append((seg_start, i-seg_start, ''.join(cur)))
            cur = []; i += 1; seg_start = i
            continue
        if b == 0x0A: cur.append('⏎'); i += 1; continue
        if b == 0x09: cur.append('　'); i += 1; continue
        if 0x40 <= b <= 0x9F: cur.append(T1.get(b, '')); i += 1; continue
        if b >= 0xF0:
            code = (b << 8) | data[i+1]
            ch = ''
            for row, dl in ROWDELTA.items():
                sj = code - dl
                if 0 <= sj < 0x10000 and (sj >> 8) == row and 0x889F <= sj <= 0x9872:
                    try: ch = sj.to_bytes(2,'big').decode('cp932')
                    except Exception: ch = ''
                    break
            if not ch and (code >> 8) in (0xF0, 0xF1):
                sj = (code - 0x6E0B) & 0xFFFF
                if (sj >> 8) in (0x82, 0x83):
                    try: ch = sj.to_bytes(2,'big').decode('cp932')
                    except Exception: pass
            cur.append(ch); i += 2; continue
        i += 1   # 控制码跳过
    if cur: segs.append((seg_start, i-seg_start, ''.join(cur)))
    return segs

def euc_segments(path):
    txt = open(path,'rb').read().decode('euc-jp', errors='replace')
    out = []
    for seg in txt.split('●'):
        s = re.sub(r'<\$[0-9A-Fa-f]{2}>', lambda m: m.group(0), seg)
        out.append(s.replace('\r','').replace('\n','').replace('　',''))
    return [s for s in out if s.strip()]

def charset_overlap(a, b):
    ca, cb = Counter(a), Counter(b)
    if not ca or not cb: return 0.0
    inter = sum((ca & cb).values())
    return inter / max(sum(ca.values()), sum(cb.values()))

scores = []
for n in range(NBLOCK):
    p = os.path.join(EUC_DIR, f'TKSC{n}.EUC')
    if not os.path.exists(p):
        scores.append((n, -1)); continue
    esegs = euc_segments(p)
    if not esegs: scores.append((n, -1)); continue
    etxt = ''.join(esegs)
    rsegs = rom_segments(n)
    rtxt = ''.join(r[2] for r in rsegs)
    scores.append((n, charset_overlap(etxt, rtxt)))

good = sum(1 for _, s in scores if s >= 0.5)
mid  = sum(1 for _, s in scores if 0.2 <= s < 0.5)
bad  = sum(1 for _, s in scores if 0 <= s < 0.2)
miss = sum(1 for _, s in scores if s < 0)
print(f'TKSC↔块 对应度: 高(>=0.5) {good}, 中 {mid}, 低(<0.2) {bad}, 无文件 {miss}')
for n, s in scores[:20]:
    print(f'  块{n:03d}: {s:.2f}')
json.dump({str(n): s for n, s in scores}, open('out/script/match_scores.json','w'))
