"""Flatten text block 144 (the prologue) into a re-encodable script.

Output: docs/research/prologue_script.json = [{"jp":..., "zh":..., "ctl":[..]}]
The Chinese patch is built by concatenating, for every segment, its zh text
encoded to bytes followed by the ORIGINAL control bytes in "ctl".  Because the
control skeleton is copied verbatim, the patched script cannot drift out of the
dispatcher's box/step state machine.

ctl is the list of control bytes that follow the segment's text ($14 line
break, $0C box end / press-A, $0A entry end, $25 pause).  $12/$13 (name
variables) stay inline in the text as 〔姓〕/〔名〕.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

BLOCK = 144
END = 0x22FA1F          # == text_ptr(71): first byte after the prologue
MARK = {0x12: '〔姓〕', 0x13: '〔名〕', 0x09: '　'}
LINE_CTRL = (0x14, 0x0C, 0x0A)


def body(rom, addr, depth=0, seen=()):
    """Macro body -> (chars, ctrl bytes).  A body ends at its first $0C/$0A."""
    d, i, chars, ctrls = rom.data, addr, [], []
    while i < addr + 0x40 and d[i] != 0x00:
        b = d[i]
        if b == 0x0A:
            return chars, ctrls
        if b == 0x0C:
            ctrls.append(b)
            return chars, ctrls
        if b < 0x40:
            ctrls.append(b)
            i += 1
        elif b < 0xA0:
            chars.append(T.idx_to_char(rom.sb_entry(b)) or '')
            i += 1
        elif b < 0xE8:
            if b in seen or depth > 3:
                i += 1
                continue
            a = rom.phrase_addr(b)
            if a is not None:
                c, k = body(rom, a, depth + 1, seen + (b,))
                chars += c
                ctrls += k
            i += 1
        elif b < 0xF0:
            key = (b << 8) | d[i + 1]
            if key not in seen and depth <= 3:
                a = rom.sub_addr(b, d[i + 1])
                if a is not None:
                    c, k = body(rom, a, depth + 1, seen + (key,))
                    chars += c
                    ctrls += k
            i += 2
        else:
            chars.append(T.idx_to_char(((b << 8) | d[i + 1]) - 0xF000) or '')
            i += 2
    return chars, ctrls


def main():
    rom = T.Rom()
    d = rom.data
    segs, cur, ctl = [], [], []
    i = rom.text_ptr(BLOCK) + 1          # skip the leading $0A
    while i < END:
        b = d[i]
        if b < 0x40:
            if b in MARK:
                cur.append(MARK[b])
            else:
                ctl.append(b)
            i += 1
        elif b < 0xA0:
            cur.append(T.idx_to_char(rom.sb_entry(b)) or '')
            i += 1
        elif b < 0xE8:
            a = rom.phrase_addr(b)
            c, k = body(rom, a) if a is not None else ([], [])
            cur += c
            ctl += k
            i += 1
        elif b < 0xF0:
            a = rom.sub_addr(b, d[i + 1])
            c, k = body(rom, a) if a is not None else ([], [])
            if k:                      # a variable/format code, not a word
                cur.append('⟦%02X%02X⟧' % (b, d[i + 1]))
            else:
                cur += c
                ctl += k
            i += 2
        else:
            cur.append(T.idx_to_char(((b << 8) | d[i + 1]) - 0xF000) or '')
            i += 2
        if ctl and any(c in LINE_CTRL for c in ctl):
            segs.append({'jp': ''.join(cur), 'zh': '', 'ctl': ctl})
            cur, ctl = [], []
    if cur:
        segs.append({'jp': ''.join(cur), 'zh': '', 'ctl': ctl})
    # fold the leading entry terminator into segment 0
    json.dump(segs, open('docs/research/prologue_script.json', 'w'),
              ensure_ascii=False, indent=1)
    for n, s in enumerate(segs):
        print('%3d %-30s %s' % (n, s['jp'], ' '.join('$%02X' % c for c in s['ctl'])))
    print('segments:', len(segs), file=sys.stderr)
    print('ctl bytes:', sum(len(s['ctl']) for s in segs), file=sys.stderr)


if __name__ == '__main__':
    main()
