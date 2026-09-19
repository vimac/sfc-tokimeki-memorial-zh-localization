"""全游戏文本抽取器 — 复刻 J2E TOKISEQ.BAS 逻辑 + 本项目解码器.

指针表结构 (破解自 TOKINS.BAS liist 子程序):
  名字指针表 @0x9872, 文本指针表 @0x9872+435, 各 145 项 × 3 字节 LE (lo, hi, bank)
  文件偏移 = (bank-0x80)*0x8000 - 0x7E00 + (hi<<8|lo)     [J2E 档案含 0x200 头, 已抵消]

输出:
  out/script/all_blocks.txt   全文可读版 (块号+范围+文本)
  out/script/strings.tsv      翻译模板 (块号, 偏移, 字节长, 原始hex, 解码文本)
  out/script/pointers.json    指针表数据
"""
import struct, json, os

ROM = 'Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc'
NAME_PTR = 0x9872        # 名字块指针表 (145 项)
TEXT_PTR = 0x9872 + 435  # 文本块指针表
NBLOCK = 145

seq = ("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとど"
       "なにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわを")
T1 = {0x50+i: c for i, c in enumerate(seq)}
T1.update({0x4F:'ん', 0x44:'、', 0x47:'…', 0x25:'…', 0x22:'「', 0x23:'」'})
# 实证修正: 0x54=こ(今日), F0E7=ま(ございました) 等
T1[0x54] = 'こ'
OVERRIDE = {0xF0E7:'ま', 0xF9B3:'日', 0xF6D4:'所', 0xFBEA:'本', 0xFB85:'辺', 0xFB5C:'分',
            0xF8A7:'大', 0xFA29:'難', 0xFCB8:'落'}
try:
    import json as _j
    OVERRIDE.update({int(k,16): v for k, v in _j.load(open('out/script/char_overrides.json')).items()})
except Exception:
    pass
ROWDELTA = {0x81:0x72D8,0x82:0x7082,0x83:0x6DBD,0x8A:0x689E,0x8B:0x685A,0x8C:0x6816,0x8D:0x67D3,
            0x8E:0x678E,0x8F:0x674B,0x90:0x6706,0x91:0x66C3,0x92:0x667E,0x93:0x663A,
            0x95:0x65B3,0x96:0x656E,0x97:0x652A,0x98:0x64E7}

data = open(ROM, 'rb').read()

def parse_ptr(off):
    b0, b1, b2 = data[off], data[off+1], data[off+2]
    return (b2 - 0x80) * 0x8000 - 0x7E00 + (b1 << 8 | b0)

name_ptrs = [parse_ptr(NAME_PTR + i*3) for i in range(NBLOCK)]
text_ptrs = [parse_ptr(TEXT_PTR + i*3) for i in range(NBLOCK)]

print('文本块指针(前12):', [hex(p) for p in text_ptrs[:12]])
print('名字块指针(前8):', [hex(p) for p in name_ptrs[:8]])
print('范围: 文本 min=%X max=%X' % (min(text_ptrs), max(text_ptrs)))
print('范围: 名字 min=%X max=%X' % (min(name_ptrs), max(name_ptrs)))
json.dump({'name_ptrs': name_ptrs, 'text_ptrs': text_ptrs},
          open('out/script/pointers.json','w'))

# ---------- 解码器 ----------
def decode_byte(i):
    """解码 @i 的一个码, 返回 (文本, 消耗字节数). 文本为 None 表示控制/未知码."""
    b = data[i]
    if b == 0x00: return '□', 1          # 段结束标记 (调用方处理)
    if b == 0x0A: return '⏎', 1
    if b == 0x09: return '　', 1
    if 0x40 <= b <= 0x9F:
        return T1.get(b, f'⟨{b:02X}⟩'), 1
    if b >= 0xF0:
        code = (b << 8) | data[i+1]
        ch = OVERRIDE.get(code)
        for row, dl in (ROWDELTA.items() if ch is None else ()):
            sj = code - dl
            if 0 <= sj < 0x10000 and (sj >> 8) == row and 0x889F <= sj <= 0x9872:
                try: ch = sj.to_bytes(2,'big').decode('cp932')
                except Exception: ch = None
                break
        if not ch and (code >> 8) in (0xF0, 0xF1):
            sj = (code - 0x6E0B) & 0xFFFF
            if (sj >> 8) in (0x82, 0x83):
                try: ch = sj.to_bytes(2,'big').decode('cp932')
                except Exception: pass
        return (ch if ch else f'⟦{code:04X}⟧'), 2
    return f'~{b:02X}', 1

def decode_block(start, end):
    """解码 [start,end); 返回 (全文, 段列表). 段 = (rom偏移, 字节长, 文本)."""
    all_txt = []
    segs = []
    i = start
    seg_off = start
    cur = []
    while i < end:
        b = data[i]
        if b == 0x00:                       # 段结束
            txt = ''.join(cur)
            all_txt.append(txt)
            if txt: segs.append((seg_off, i - seg_off, txt))
            cur = []
            i += 1
            seg_off = i
            continue
        txt, n = decode_byte(i)
        cur.append(txt)
        i += n
    if cur:
        txt = ''.join(cur)
        all_txt.append(txt)
        segs.append((seg_off, i - seg_off, txt))
    return '⏎'.join(all_txt), segs

# 按地址排序, 相邻指针 = 块边界
order = sorted(range(NBLOCK), key=lambda i: text_ptrs[i])
blocks = []
for idx, i in enumerate(order):
    st = text_ptrs[i]
    en = text_ptrs[order[idx+1]] if idx+1 < len(order) else st + 0x2000
    blocks.append((i, st, min(en, st+0x8000)))

os.makedirs('out/script', exist_ok=True)
total_chars = 0
total_segs = 0
with open('out/script/all_blocks.txt', 'w') as fb, \
     open('out/script/strings.tsv', 'w') as ft:
    ft.write('block\toffset\tbytes\ttext\thex\n')
    for i, st, en in blocks:
        txt, segs = decode_block(st, en)
        total_chars += len(txt)
        total_segs += len(segs)
        fb.write(f'===== 块{i:03d} 文件0x{st:06X}-0x{en:06X} ({en-st}字节, {len(segs)}段) =====\n{txt}\n\n')
        for off, ln, stx in segs:
            raw = data[off:off+ln]
            ft.write(f'{i:03d}\t0x{off:06X}\t{ln}\t{stx}\t{raw.hex()}\n')
print(f'145 块解码完成: 总字符 {total_chars}, 总段数 {total_segs}')
print('输出: out/script/all_blocks.txt, out/script/strings.tsv')
