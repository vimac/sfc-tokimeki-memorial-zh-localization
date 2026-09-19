"""Who references a font slot?  Prints every code site that resolves to it."""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

rom = T.Rom()
data = rom.data
SB2IDX = {c: rom.sb_entry(c) for c in range(0x40, 0xA0)}
IDX2SB = collections.defaultdict(list)
for c, i in SB2IDX.items():
    IDX2SB[i].append(c)

sites = collections.defaultdict(list)     # idx -> [(file addr, kind, block)]
blocks = {}
for i in range(T.PTR_COUNT):
    a, e = T.block_bytes(rom, i)
    if a is not None:
        blocks[i] = (a, e)
starts = sorted((a, i) for i, (a, e) in blocks.items())


def owner(addr):
    lo = None
    for a, i in starts:
        if a <= addr:
            lo = i
        else:
            break
    return lo


def walk(addr, limit, depth, block, seen):
    i = addr
    end = min(addr + limit, len(data))
    while i < end:
        b = data[i]
        if b == 0x00:
            return
        if b < 0x40:
            i += 1
            continue
        if b < 0xA0:
            sites[SB2IDX[b]].append((i, 'sb', block)); i += 1; continue
        if b < 0xE8:
            a = rom.phrase_addr(b)
            if a is not None and depth < 4 and a not in seen:
                seen.add(a); walk(a, 0x100, depth + 1, block, seen)
            i += 1; continue
        if b < 0xF0:
            hi = data[i + 1]
            a = rom.sub_addr(b, hi)
            if a is not None and depth < 4 and a not in seen:
                seen.add(a); walk(a, 0x100, depth + 1, block, seen)
            i += 2; continue
        sites[((b << 8) | data[i + 1]) & 0x0FFF].append((i, 'k2', block))
        i += 2


def main():
    for i in range(T.PTR_COUNT):
        a, e = blocks.get(i, (None, None))
        if a:
            walk(a, e - a + 8, 0, i, set())
        a = rom.name_ptr(i)
        if a:
            walk(a, 0x400, 0, 'name%d' % i, set())
    for arg in sys.argv[1:]:
        idx = int(arg, 16)
        hits = sites.get(idx, [])
        print('idx %#05x (%s)  %d sites  char=%r  sbcodes=%s' %
              (idx, 'ku%s c%s' % T.idx_to_jis(idx) if T.idx_to_jis(idx) else '?',
               len(hits), T.idx_to_char(idx),
               [hex(c) for c in IDX2SB.get(idx, [])]))
        seenb = collections.Counter(str(h[2]) for h in hits)
        for addr, kind, blk in hits[:20]:
            ctx = data[max(0, addr - 3):addr + 4].hex(' ')
            print('   %#07x %-3s block %-5s  ctx %s' % (addr, kind, blk, ctx))
        if len(hits) > 20:
            print('   ... blocks: %s' % dict(seenb))


if __name__ == '__main__':
    main()
