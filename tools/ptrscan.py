"""Locate every 3-byte pointer array in the ROM and report which of them can be
rewritten safely (i.e. which point into a given text region).

A record is [lo][hi][bank] -> file = (bank-$80)*$8000 - $7E00 + (hi<<8|lo),
the formula used by J2E's TOKINS.BAS `SUB liist`.

An "array" is >=4 consecutive records whose decoded addresses are all plausible
text addresses and clustered in one bank window.  This kills the byte-triple
coincidences that litter the graphics banks.

usage: python3 tools/ptrscan.py [lo_hex hi_hex]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

LO = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x22F1AB
HI = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x22FA45


def main():
    rom = T.Rom()
    d = bytes(rom.data)
    n = len(d)

    def rec(k):
        lo, hi, bk = d[k], d[k + 1], d[k + 2]
        if bk < 0x80:
            return None
        a = (bk - 0x80) * 0x8000 - 0x8000 + ((hi << 8) | lo)
        return a if 0x10000 <= a < T.GLYPH_BASE else None

    arrays, k = [], 0
    while k < n - 12:
        four = [rec(k + 3 * j) for j in range(4)]
        if all(four) and max(four) - min(four) < 0x20000:
            base, m, cnt = k, k, 0
            while m + 2 < n:
                a = rec(m)
                if a is not None and abs(a - four[0]) < 0x40000:
                    cnt += 1
                    m += 3
                else:
                    break
            if cnt >= 4:
                arrays.append((k, cnt))
                k = m
                continue
        k += 1

    print('%d pointer arrays' % len(arrays))
    total = 0
    for k, cnt in arrays:
        hits = [(k + 3 * j, rec(k + 3 * j)) for j in range(cnt)]
        ins = [(p, a) for p, a in hits if a is not None and LO <= a <= HI]
        span = [a for _, a in hits if a is not None]
        if ins:
            total += len(ins)
            print('array @%06X n=%3d span %06X-%06X' %
                  (k, cnt, min(span), max(span)))
            for p, a in ins:
                print('    idx %3d  @%06X -> %06X' % ((p - k) // 3, p, a))
    print('records pointing into %06X..%06X : %d' % (LO, HI, total))


if __name__ == '__main__':
    main()
