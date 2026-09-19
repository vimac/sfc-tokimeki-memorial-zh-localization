"""Find every WRAM word holding a pointer into the prologue text block.

The engine's own cursor ($B4/$B6) and its saved resume pointer are what decide
where a box starts, so locating every copy of a block address in WRAM at a pause
shows which variable the next box is read from -- and which value is wrong.

usage: python3 tools/ramprobe.py <rom> [presses]
"""
import sys, os, re, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slot
slot.use(sys.argv[1])
from play import env, step, press, load_state

LO, HI = 0xF1AC, 0xFA1F          # block 144 as $C5:$F1AC..$C5:$FA1F


def in_block(v):
    return (v >> 16) == 0xC5 and LO <= (v & 0xFFFF) <= HI


def scan(r):
    """All 24-bit little-endian pointers into the block, plus $B4/$B6."""
    hits = []
    for i in range(len(r) - 3):
        v = r[i] | (r[i + 1] << 8) | (r[i + 2] << 16)
        if in_block(v):
            hits.append((i, v))
    return hits


def main():
    rom = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    stem = os.path.splitext(os.path.basename(rom))[0]
    load_state('trace_entered_%s' % stem)
    step(60)
    prev = None
    shown = 0
    for k in range(120):
        r = bytes(env.get_ram())
        cur = r[0xB4] | (r[0xB6] << 8)
        h = hashlib_frame(r)
        if shown < n and h != prev:
            prev = h
            print('=== press %d  ptr@B4=%02X%02X:%02X%02X  $0D24=%06X  '
                  '$0A26=%04X $0A28=%04X'
                  % (k, r[0xB7], r[0xB6], r[0xB5], r[0xB4],
                     sum(r[0xD24 + i] << (8 * i) for i in range(3)),
                     r[0xA26] | (r[0xA27] << 8), r[0xA28] | (r[0xA29] << 8)))
            for off, v in scan(r):
                print('    $7E:%04X = %06X' % (off, v))
            shown += 1
        if shown >= n:
            break
        press('A', settle=500, n=6)


def hashlib_frame(r):
    return hash(r[0xA00:0xE00])


main()
