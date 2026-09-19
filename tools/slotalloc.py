"""Find glyph slots that no Japanese text uses -> the WenQuanYi injection pool.

Two censuses are combined:
  1. exact  - the 145 pointer-table blocks plus both compression dictionaries
  2. extra  - every byte sequence in the ROM that *parses* as a >=14-token
              text stream terminated by $00, excluding the font region
              (0x3E8000-$400000) whose bitmap bytes alias to random codes.

usage: python3 tools/slotalloc.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

FONT_LO, FONT_HI = 0x3E8000, 0x400000
CTRL = set(range(0x30)) | {0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
                           0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F}


def scan(rom, a, limit, dst, depth=0):
    d, i, end = rom.data, a, a + limit
    while i < end:
        b = d[i]
        if b == 0 or (b == 0x0A and depth):
            return
        if b < 0x40:
            i += 1
        elif b < 0xA0:
            dst.add(rom.sb_entry(b)); i += 1
        elif b < 0xE8:
            if depth < 3:
                body = rom.phrase_addr(b)
                if body is not None:
                    scan(rom, body, 0x30, dst, depth + 1)
            i += 1
        elif b < 0xF0:
            if depth < 3:
                body = rom.sub_addr(b, d[i + 1])
                if body is not None:
                    scan(rom, body, 0x30, dst, depth + 1)
            i += 2
        else:
            idx = ((b << 8) | d[i + 1]) - 0xF000
            if idx >= T.MAX_INDEX:
                return
            dst.add(idx); i += 2


def grammar_streams(d):
    """All $00-terminated, >=14-token text-looking runs outside the font."""
    n = len(d)
    out, i = [], 0
    while i < n - 2:
        if FONT_LO <= i < FONT_HI:
            i = FONT_HI
            continue
        b = d[i]
        if b >= 0xF0 and ((b << 8) | d[i + 1]) - 0xF000 < T.MAX_INDEX:
            j, toks, ok = i, 0, True
            while j < n - 2 and toks < 400:
                c = d[j]
                if c == 0:
                    break
                if c < 0x40:
                    if c not in CTRL:
                        ok = False; break
                    j += 1
                elif c < 0xA0:
                    j += 1
                elif c < 0xE8:
                    j += 1
                elif c < 0xF0:
                    j += 2
                else:
                    if ((c << 8) | d[j + 1]) - 0xF000 >= T.MAX_INDEX:
                        ok = False; break
                    j += 2
                toks += 1
            if ok and toks >= 14 and d[j] == 0:
                out.append((i, j))
                i = j + 1
                continue
        i += 1
    return out


def main():
    rom = T.Rom()
    d = bytes(rom.data)
    used = set()
    for i in range(T.PTR_COUNT):
        a, e = T.block_bytes(rom, i)
        if a is not None:
            scan(rom, a, e - a + 1, used)
    for c in range(0xA0, 0xE8):
        b = rom.phrase_addr(c)
        if b is not None:
            scan(rom, b, 0x30, used, 1)
    for h in range(0xE8, 0xF0):
        for l in range(0x100):
            b = rom.sub_addr(h, l)
            if b is not None:
                scan(rom, b, 0x30, used, 1)
    exact = set(used)

    st = grammar_streams(d)
    for a, b in st:
        p = a
        while p < b:
            c = d[p]
            if c < 0x40:
                p += 1
            elif c < 0xA0:
                used.add(rom.sb_entry(c)); p += 1
            elif c < 0xE8:
                p += 1
            elif c < 0xF0:
                p += 2
            else:
                used.add(((c << 8) | d[p + 1]) - 0xF000); p += 2
    print('grammar streams: %d  (%d bytes)'
          % (len(st), sum(b - a for a, b in st)))
    print('glyph idx used - exact census : %d' % len(exact))
    print('glyph idx used - with streams : %d' % len(used))

    kanji = range(T.JIS_KANJI, T.MAX_INDEX)
    free_exact = [i for i in kanji if i not in exact]
    free = [i for i in kanji if i not in used]
    print('free kanji slots (exact)      : %d' % len(free_exact))
    print('free kanji slots (conservative): %d' % len(free))
    json.dump({'exact': sorted(exact), 'used': sorted(used)},
              open('docs/research/glyph_usage.json', 'w'))
    with open('docs/research/free_slots.txt', 'w') as f:
        f.write(' '.join('%04X' % i for i in free) + '\n')
    print('-> docs/research/free_slots.txt')


if __name__ == '__main__':
    main()
