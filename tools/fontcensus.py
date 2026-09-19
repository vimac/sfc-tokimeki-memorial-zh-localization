"""Whole-ROM glyph slot census.

Collects every font slot index that the decodable text corpus references
(145 text blocks + 145 name blocks, recursing through phrase/sub macros),
then reports which slots are never referenced and whether they are blank.

A slot is only a *safe* Chinese-glyph target if it is unreferenced here AND
its current bitmap is blank (proof the game never draws it) or a kanji that
appears nowhere in the corpus.
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

rom = T.Rom()
data = rom.data

SB2IDX = {c: rom.sb_entry(c) for c in range(0x40, 0xA0)}
refs = collections.Counter()          # slot idx -> times referenced
visiting = set()


def walk(addr, limit, depth, seen):
    i = addr
    end = min(addr + limit, len(data))
    while i < end:
        b = data[i]
        if b == 0x00:
            return i
        if b < 0x40:                    # control: operands counted as refs-free
            i += 1
            continue
        if b < 0xA0:
            refs[SB2IDX[b]] += 1
            i += 1
            continue
        if b < 0xE8:
            a = rom.phrase_addr(b)
            if a is not None and depth < 4 and a not in seen:
                seen.add(a)
                walk(a, 0x100, depth + 1, seen)
            i += 1
            continue
        if b < 0xF0:
            hi = data[i + 1]
            a = rom.sub_addr(b, hi)
            if a is not None and depth < 4 and a not in seen:
                seen.add(a)
                walk(a, 0x100, depth + 1, seen)
            i += 2
            continue
        refs[((b << 8) | data[i + 1]) & 0x0FFF] += 1
        i += 2
    return end


def main():
    blocks = {}
    for i in range(T.PTR_COUNT):
        a, e = T.block_bytes(rom, i)
        if a is None:
            continue
        blocks[i] = (a, e)
        walk(a, e - a + 8, 0, set())
    for i in range(T.PTR_COUNT):
        a = rom.name_ptr(i)
        if a:
            walk(a, 0x400, 0, set())

    used = set(refs)
    blank = [i for i in range(T.MAX_INDEX)
             if all(v == 0 for v in data[T.glyph_offset(i): T.glyph_offset(i) + T.SLOT_BYTES])]
    free = [i for i in range(T.MAX_INDEX) if i not in used]
    print('blocks decoded: %d   referenced slots: %d' % (len(blocks), len(used)))
    print('blank slots: %d   unreferenced slots: %d' % (len(blank), len(free)))
    print('unreferenced AND blank: %d' % len(set(blank) & set(free)))

    # contiguous runs of unreferenced slots (1 slot = 28 bytes)
    runs = []
    cur = []
    for i in range(T.MAX_INDEX):
        if i not in used:
            cur.append(i)
        else:
            if len(cur) >= 8:
                runs.append((cur[0], len(cur)))
            cur = []
    if len(cur) >= 8:
        runs.append((cur[0], len(cur)))
    runs.sort(key=lambda r: -r[1])
    print('\nlargest contiguous unreferenced runs (start idx, slots, bytes):')
    for s, n in runs[:12]:
        print('  idx %#05x .. %#05x  %4d slots  %6d bytes  file %#x' %
              (s, s + n - 1, n, n * 28, T.glyph_offset(s)))

    json.dump({'used': sorted(used), 'free': free, 'blank': blank},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'docs', 'research', 'slot_census.json'), 'w'))
    print('\nwrote docs/research/slot_census.json')


if __name__ == '__main__':
    main()
