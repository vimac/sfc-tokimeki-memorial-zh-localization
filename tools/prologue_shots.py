"""Cut the walk's raw frame dump down to one sheet per translated box.

`prologue_play` saves a PNG for every frame that *differs* from the last, so a 96-press
walk leaves ~500 near-duplicates.  This attributes each saved frame to its block-144 box
by the `$D24` read pointer (the same resolution `pagediff` uses), keeps the fullest
rendering of every distinct page of that box, and copies it out with the box number and
its intended text in the filename, so the whole prologue can be read off one directory.

usage: python3 tools/prologue_shots.py [transcript] [outdir]
"""
import sys, os, re, shutil, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boxbudget as BB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else '/tmp/play/boot_walk_zh.txt'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'docs/prologue_zh')
FRAMES = os.path.dirname(SRC) + '/pp_rom_prologue_zh'

HEAD, LAST = 0x22F1AB, 0x22FA1E            # block 144: head $0A, then 88 contiguous boxes
boxes, spans, zh = BB.pack()[:3]
off, starts = HEAD + 1, {}
for bi, bx in enumerate(boxes[1:]):
    starts[off] = bi
    off += bx['bytes']

LINE = re.compile(r'^\s*(\d+)(\w*)\s+([0-9a-f]{8}) d24=([0-9A-F]{6}) \| (.*)$')
per_box = collections.defaultdict(dict)          # box -> normalised page -> (fill, filename)
for ln in open(SRC, encoding='utf-8'):
    m = LINE.match(ln.rstrip())
    if not m:
        continue
    press, phase, h, d24, text = m.groups()
    f = (int(d24, 16) & 0xFFFF) + 0x220000
    bi = starts.get(max([s for s in starts if s <= f], default=None)) if f <= LAST else None
    if bi is None:
        continue
    # 佗 is the blinking advance arrow and 「 on row 0 is the box-open decoration;
    # neither is text, so strip them before comparing pages.
    clean = ' / '.join(c for c in (r.replace('佗', '').replace(' ', '').lstrip('「')
                                   for r in text.split(' // ')) if c)
    page = per_box[bi].get(clean)
    fill = sum(len(c) for c in clean.split(' / '))
    if page is None or fill > page[0]:
        per_box[bi][clean] = (fill, '%03d%s_%s.png' % (int(press), phase, h))

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
index, missing = [], []
for bi in sorted(starts.values()):
    pages = sorted(per_box.get(bi, {}).items(), key=lambda kv: -kv[1][0])
    want = ' / '.join(x.replace('|', '') for x in zh[spans[bi][0]:spans[bi][1]] if x.strip())
    if not pages:
        missing.append(bi)
        index.append('%3d  (never shown)  %s' % (bi, want))
        continue
    for pi, (clean, (_, fn)) in enumerate(pages[:3]):
        src = os.path.join(FRAMES, fn)
        if not os.path.exists(src):
            missing.append(bi)
            continue
        dst = '%s/box%02d%s.png' % (OUT, bi, 'abc'[pi] if pi else '')
        shutil.copyfile(src, dst)
        index.append('%3d  %-21s %s   %s' % (bi, os.path.basename(dst), clean,
                                             '<< want ' + want if pi == 0 and want and want != clean else ''))
open('%s/index.txt' % OUT, 'w', encoding='utf-8').write('\n'.join(index) + '\n')
print('%d boxes, %d sheets -> %s' % (len(starts), len(index) - len(missing), OUT))
if missing:
    print('no frame for: %s' % ' '.join(str(b) for b in missing))
