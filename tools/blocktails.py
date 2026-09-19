"""How much slack does each text block actually leave before its neighbour starts?

A block's base is a 23-bit pointer in the table at $9A25 and every box inside it is
addressed as `base + 2 * operand`, so a whole block can be moved by rewriting one pointer
with no internal change.  That makes the *tails* -- bytes between a block's last segment
and the next block's base -- the only place a short box can grow into.  This measures them.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import block_boxes as BB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rom = T.Rom(os.path.join(ROOT, 'rom_original_japanese.sfc'))
bases = {i: p for i in range(BB.BLOCKS) if (p := rom.text_ptr(i)) is not None}
ordered = sorted(bases.items(), key=lambda kv: kv[1])
print('blocks with a pointer: %d, range %06X..%06X'
      % (len(ordered), ordered[0][1], ordered[-1][1]))

runs = []
unwalked = 0
for n, (blk, base) in enumerate(ordered):
    hi = ordered[n + 1][1] if n + 1 < len(ordered) else base + 0x400
    # A walk that runs off `hi` by an operand width proves the block's bytes continue into
    # its neighbour, so that block has no tail; only a walk that closes exactly at the
    # boundary can report one.
    for extra in (0, 2, 4, 6, 12):
        try:
            segs = BB.segments(rom, base, hi + extra)
        except (AssertionError, IndexError):
            continue
        break
    else:
        unwalked += 1
        runs.append((blk, base, hi, hi, 0))
        continue
    end = base + sum(s[2] for s in segs)
    if extra:
        end = max(end, hi)
    runs.append((blk, base, min(end, hi), hi, len(segs)))

print('%5s %-8s %-8s %-8s %6s  %s' % ('blk', 'base', 'end', 'next', 'slack', 'segs'))
for blk, base, end, hi, ns in runs:
    if hi - end > 16:
        print('%5d %06X   %06X   %06X   %5d  %d' % (blk, base, end, hi, hi - end, ns))
    if blk == 0:
        print('   >> block 0: base %06X end %06X next %06X slack %d' % (base, end, hi, hi - end))
holes = [(end, hi, hi - end) for _, _, end, hi, _ in runs if hi - end > 16]
print('blocks with a tail: %d, total %d B; biggest: %s'
      % (len(holes), sum(h[2] for h in holes),
         ', '.join('%dB@%06X' % (h[2], h[0]) for h in sorted(holes, reverse=True)[:6])))
