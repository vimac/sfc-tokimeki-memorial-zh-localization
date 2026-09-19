"""Census which glyph slots the game's Japanese text actually references.

Scans the 145 pointer-table blocks plus both compression dictionaries
(phrase-macro bodies in bank $B9, sub-table bodies in bank $C3).

Slots never referenced by any Japanese text are free real estate for
WenQuanYi injection.

usage: python3 tools/census.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

BLOCKS = 145
PROLOGUE_BLOCK = 144


def scan(rom, a, limit, dst, depth=0):
    """Add every glyph index reachable from text stream at `a` to `dst`."""
    i, end = a, a + limit
    while i < end:
        b = rom.data[i]
        if b == 0 or (b == 0x0A and depth):
            return
        if b < 0x40:
            i += 1
        elif b < 0xA0:
            dst.add(rom.sb_entry(b))
            i += 1
        elif b < 0xE8:
            if depth < 3:
                body = rom.phrase_addr(b)
                if body is not None:
                    scan(rom, body, 0x30, dst, depth + 1)
            i += 1
        elif b < 0xF0:
            if depth < 3:
                body = rom.sub_addr(b, rom.data[i + 1])
                if body is not None:
                    scan(rom, body, 0x30, dst, depth + 1)
            i += 2
        else:
            dst.add(((b << 8) | rom.data[i + 1]) - 0xF000)
            i += 2


def main():
    rom = T.Rom()
    used_all, used_pro = set(), set()
    for i in range(BLOCKS):
        a, e = T.block_bytes(rom, i)
        if a is None:
            continue
        scan(rom, a, e - a + 1, used_all)
        if i == PROLOGUE_BLOCK:
            scan(rom, a, e - a + 1, used_pro)
    # dictionary bodies are reached from the streams above; add the full
    # tables too so that words defined but unused elsewhere stay marked
    for c in range(0xA0, 0xE8):
        b = rom.phrase_addr(c)
        if b is not None:
            scan(rom, b, 0x30, used_all, 1)
    for h in range(0xE8, 0xF0):
        for l in range(0x100):
            b = rom.sub_addr(h, l)
            if b is not None:
                scan(rom, b, 0x30, used_all, 1)

    kanji = set(range(T.JIS_KANJI, T.MAX_INDEX))
    free = sorted(kanji - used_all)
    only_pro = sorted(kanji & used_pro - (used_all - used_pro))
    print('glyph indices referenced  : %d' % len(used_all))
    print('kanji slots total         : %d' % len(kanji))
    print('never referenced anywhere : %d  -> docs/research/free_slots.txt' % len(free))
    print('referenced ONLY by prologue block : %d' % len(only_pro))
    print('usable pool (never + prologue-only): %d' % (len(free) + len(only_pro)))
    print('free sample :', ''.join(T.idx_to_char(i) or '?' for i in free[:80]))
    print('prologue-only sample:', ''.join(T.idx_to_char(i) or '?' for i in only_pro[:60]))
    with open('docs/research/free_slots.txt', 'w') as f:
        f.write(' '.join('%04X' % i for i in free + only_pro) + '\n')


if __name__ == '__main__':
    main()
