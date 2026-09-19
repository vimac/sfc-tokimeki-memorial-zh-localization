"""Extract the prologue (text block 144) as a translatable box list.

Box model, proven from the dispatcher at $80:CA6D and the macro dictionary:
  $14          line break inside a box
  $A0..$A7     "<punct> $0C"  -> $0C = the big ● "press A" marker = BOX END
  $A8..$AD     "<punct> $14"  -> sentence end + line break, box continues
  $0A          end of this script step (the engine moves on to the next one)
  $12 / $13    player surname / given name
  $25          short pause, $2E no-op, $09 full-width space
  $AE..$E7     word macro (1 byte)      $E8xx..$EFxx  word macro (2 bytes)

Each emitted box carries the exact original byte range so the patcher can
reconstruct the control skeleton.

usage: python3 tools/prologue_boxes.py [end_hex] > docs/research/prologue_boxes.txt
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

BOX_END = set(range(0xA0, 0xA8))
LINE_END = set(range(0xA8, 0xAE)) | {0xAD}
PUNCT = {0xA0: '。', 0xA1: '？', 0xA2: '！', 0xA3: '。）', 0xA4: '。」',
         0xA5: '…」', 0xA6: '？」', 0xA7: '！」',
         0xA8: '。', 0xA9: '？', 0xAA: '！', 0xAB: '…', 0xAC: '、', 0xAD: '…'}
CTRL_CH = {0x12: '〔姓〕', 0x13: '〔名〕', 0x09: '　', 0x14: '\n',
           0x25: '†', 0x2E: '', 0x00: '', 0x0A: '\x00'}

_CACHE = {}


def macro_text(rom, key, depth=0, seen=()):
    """Flat text of a word macro; $AE-$E7 keys are ints, $E8xx-$EFxx are ints."""
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if key in BOX_END or key in LINE_END:
        _CACHE[key] = PUNCT[key]
        return PUNCT[key]
    if key in seen or depth > 4:
        _CACHE[key] = ''
        return ''
    addr = (rom.phrase_addr(key) if key < 0xE8
            else rom.sub_addr(key >> 8, key & 0xFF))
    if addr is None:
        _CACHE[key] = ''
        return ''
    s = _flat(rom, addr, depth + 1, seen + (key,))
    _CACHE[key] = s
    return s


def _flat(rom, addr, depth, seen):
    d, out, i = rom.data, [], addr
    while i < addr + 0x60:
        b = d[i]
        if b == 0x00 or b == 0x0A:
            break
        if b < 0x40:
            out.append(CTRL_CH.get(b, ''))
            i += 1
        elif b < 0xA0:
            out.append(T.idx_to_char(rom.sb_entry(b)) or '')
            i += 1
        elif b < 0xE8:
            out.append(macro_text(rom, b, depth, seen) if depth <= 4 else '')
            i += 1
        elif b < 0xF0:
            out.append(macro_text(rom, (b << 8) | d[i + 1], depth, seen))
            i += 2
        else:
            out.append(T.idx_to_char(((b << 8) | d[i + 1]) - 0xF000) or '')
            i += 2
    return ''.join(out).split('\n')[0]


def main():
    rom = T.Rom()
    start = rom.text_ptr(144)
    end = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x22FA20
    d = rom.data
    boxes, lines, cur, off = [], [], [], start
    i = start
    while i < end:
        b = d[i]
        if b == 0x0A:
            lines.append(''.join(cur))
            boxes.append(('STEP', off, i + 1 - off, lines))
            lines, cur, off = [], [], i + 1
            i += 1
        elif b in BOX_END:
            lines.append(''.join(cur) + PUNCT[b])
            boxes.append(('BOX', off, i + 1 - off, lines))
            lines, cur, off = [], [], i + 1
            i += 1
        elif b in LINE_END:
            lines.append(''.join(cur) + PUNCT[b])
            cur = []
            i += 1
        elif b < 0x40:
            cur.append(CTRL_CH.get(b, ''))
            i += 1
        elif b < 0xA0:
            cur.append(T.idx_to_char(rom.sb_entry(b)) or '')
            i += 1
        elif b < 0xE8:
            cur.append(macro_text(rom, b))
            i += 1
        elif b < 0xF0:
            cur.append(macro_text(rom, (b << 8) | d[i + 1]))
            i += 2
        else:
            cur.append(T.idx_to_char(((b << 8) | d[i + 1]) - 0xF000) or '')
            i += 2
    if cur or lines:
        lines.append(''.join(cur))
        boxes.append(('TAIL', off, end - off, lines))
    out = [{'n': n, 'kind': k, 'off': o, 'bytes': nb,
            'lines': [x for x in ls if x != '']}
           for n, (k, o, nb, ls) in enumerate(boxes)]
    json.dump(out, open('docs/research/prologue_boxes.json', 'w'),
              ensure_ascii=False, indent=0)
    for e in out:
        print('%3d %-4s @%06X %4dB | %s' % (e['n'], e['kind'], e['off'],
                                            e['bytes'], ' / '.join(e['lines'])))
    print('boxes:', len(out), 'total bytes:', sum(e['bytes'] for e in out),
          file=sys.stderr)


if __name__ == '__main__':
    main()
