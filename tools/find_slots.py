"""Find font slot indices for target characters by matching against Unifont renders."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import romlib
data = romlib.load()
from PIL import Image, ImageDraw, ImageFont

FONT = 0x3E8002
ufont = ImageFont.truetype('/usr/share/fonts/unifont/unifont.otf', 16)

def ref(ch):
    img = Image.new('L', (16,16), 0)
    d = ImageDraw.Draw(img)
    d.text((8,8), ch, fill=255, font=ufont, anchor='mm')
    return [[1 if img.getpixel((x,y))>80 else 0 for x in range(16)] for y in range(16)]

def gg(idx):
    off = FONT + idx*32
    return [[1 if int.from_bytes(data[off+r*2:off+r*2+2],'big')&(0x8000>>x) else 0
             for x in range(16)] for r in range(16)]

def f1(a,b):
    tp=sum(1 for r in range(16) for x in range(16) if a[r][x] and b[r][x])
    fa=sum(1 for r in range(16) for x in range(16) if a[r][x] and not b[r][x])
    fb=sum(1 for r in range(16) for x in range(16) if not a[r][x] and b[r][x])
    return 2*tp/(2*tp+fa+fb) if (2*tp+fa+fb) else 0

targets = list('あなたの名字を教えてくれる')
results = {}
for ch in targets:
    ref = ref(ch)
    best_i, best_s = -1, 0
    for idx in range(0, 3072):
        s = f1(ref, gg(idx))
        if s > best_s:
            best_s, best_i = s, idx
    results[ch] = {'idx': best_i, 'score': round(best_s, 3)}
    print(f'{ch}: idx={best_i} (0x{best_i:03X}) F1={best_s:.3f}')

json.dump(results, open('/tmp/play/font_map.json', 'w', ensure_ascii=False),
          ensure_ascii=False)
print('saved /tmp/play/font_map.json')
