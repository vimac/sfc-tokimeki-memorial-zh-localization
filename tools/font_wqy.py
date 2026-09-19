"""文泉驿 13px → 28B 字形转换器 + 字库写入.

游戏字形格式: 14x16 1bpp (28B, 每行 2B big-endian, 高14位有效)
上下各空1行 → 中间14行墨迹

用法:
  python3 tools/font_wqy.py test        # 渲染测试字样
  python3 tools/font_wqy.py patch       # 替换字库中翻译需要的简体字
"""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

PCF = '/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf'
ROM = 'Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc'
FONT_BASE = 0x3E8002  # 字形0, 32B/槽

# 需要替换的简体字 → JIS 对应字(占用其槽位)
# 策略: 用 JIS 内的罕用同音/形近字槽位放简体字形
S2J_SLOT = {
    '你': '仁',   # 仁 = JIS 0x8B60, 少用
    '说': '説',   # 説 = JIS 常用, 但「説」已有槽位
    '这': '适',   # 适 = JIS 0x9C4B
    '们': '倆',   # 倆 = JIS
    '签': '籤',   # 籤 = JIS
    '谢': '謝',   # 謝 = JIS 常用
    '边': '邊',   # 邊 = JIS
    '头': '頭',   # 頭 = JIS
    '关': '關',   # 關 = JIS
    '门': '門',   # 門 = JIS
    '问': '問',   # 問 = JIS
    '间': '間',   # 間 = JIS
    '时': '時',   # 時 = JIS
    '见': '見',   # 見 = JIS
    '贝': '貝',   # 貝 = JIS
    '长': '長',   # 長 = JIS
    '车': '車',   # 車 = JIS
    '东': '東',   # 東 = JIS
    '两': '兩',   # 兩 = JIS
    '来': '來',   # 來 = JIS
    '乐': '樂',   # 樂 = JIS
    '书': '書',   # 書 = JIS
    '画': '畫',   # 畫 = JIS
    '话': '話',   # 話 = JIS
    '优': '優',   # 優 = JIS
    '会': '會',   # 會 = JIS
    '后': '後',   # 後 = JIS
    '报': '報',   # 報 = JIS
}

def get_pcf_font():
    return ImageFont.truetype(PCF, 14)

def render_glyph(ch, font):
    """渲染字符到 14x16 1bpp → 28B"""
    img = Image.new('L', (14, 14), 0)
    d = ImageDraw.Draw(img)
    d.text((7, 7), ch, fill=255, font=font, anchor='mm')
    # 提取 14x14 点阵 → 28B (跳过首尾空行)
    out = bytearray(28)
    for r in range(14):
        v = 0
        for x in range(14):
            if img.getpixel((x, r)):
                v |= (0x8000 >> x)
        out[r*2] = (v >> 8) & 0xFF
        out[r*2+1] = v & 0xFF
    return bytes(out)

def find_slot(data, jis_ch):
    """找 JIS 字在字库中的槽位: 通过码表反推"""
    try:
        sj = int(jis_ch.encode('cp932').hex(), 16)
    except:
        return None
    row = sj >> 8
    # 窗口行表
    UI = {0x81:0x72D8,0x82:0x7082,0x83:0x6DBD,0x8A:0x689E,0x8B:0x685A,0x8C:0x6816,
          0x8D:0x67D3,0x8E:0x678E,0x8F:0x674B,0x90:0x6706,0x91:0x66C3,0x92:0x667E,
          0x93:0x663A,0x95:0x65B3,0x96:0x656E,0x97:0x652A,0x98:0x64E7}
    # 对话行表
    DL = {0x89:0x68E2,0x8B:0x685A,0x8F:0x674A,0x91:0x66C2,0x95:0x65B2,
          0x96:0x656F,0x94:0x65F6,0x9A:0x64BE,0x98:0x64E7,0x88:0x6926}
    if row in (0x82, 0x83):
        return None  # 假名另行处理
    for table in [DL, UI]:
        if row in table:
            code = sj + table[row]
            seq = code & 0xFF
            # 字形库区
            for font_base in [0x3E8000, 0x3F0000, 0x3F8000]:
                off = font_base + seq * 28
                if off + 28 <= len(data):
                    return off
    return None

def do_patch():
    font = get_pcf_font()
    data = bytearray(open(ROM, 'rb').read())
    patched = 0
    for zh, jis in S2J_SLOT.items():
        off = find_slot(data, jis)
        if off is None:
            print(f'  {zh}({jis}): 槽位未找到'); continue
        glyph = render_glyph(zh, font)
        old = bytes(data[off:off+28])
        if old == bytes(glyph):
            print(f'  {zh}({jis}): 已是最新'); continue
        data[off:off+28] = glyph
        patched += 1
        print(f'  {zh}({jis}): 槽位 {hex(off)} 已替换')
    open(ROM, 'wb').write(bytes(data))
    print(f'替换 {patched} 个字形')

def do_test():
    font = get_pcf_font()
    sheet = Image.new('L', (8*40+8, 3*56+8), 180)
    for i, ch in enumerate('你说话这们签谢边头'):
        g = render_glyph(ch, font)
        img = Image.new('L', (14,16), 255)
        p = img.load()
        # 中间 14 行
        for r in range(14):
            v = int.from_bytes(g[r*2:r*2+2], 'big')
            for x in range(14):
                if v & (0x8000>>x): p[x, r+1] = 0
        sheet.paste(img.resize((28,32), Image.NEAREST), ((i%8)*40+4, (i//8)*56+4))
    sheet.save('/tmp/play/wqy_glyphs.png')
    print('saved /tmp/play/wqy_glyphs.png')

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'test'
    if cmd == 'test': do_test()
    elif cmd == 'patch': do_patch()
