"""Per-control-code cursor advance, read off the dispatcher's own handler tails.

The dispatcher at $80:CA6D classifies the byte at [$B4/$B6] and the 48-entry
table at file 0x4B0B sends $00-$2F to a handler; each handler finishes with
JMP/BRA into the advance chain at $CA9A..$CAA2, where $CAA0 is `INC $B4` and
$CAA2 another one.  So the tail target says how many bytes the code eats:
JMP $CAA2 -> 1, JMP $CAA0 -> 2, and $CA9E/$CA9C/$CA9A -> 3/4/5.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

ROM = sys.argv[1] if len(sys.argv) > 1 else 'rom_original_japanese.sfc'
rom = T.Rom(ROM)
d = rom.data
TAILS = [(b'\x4c\xa2\xca', 1, 'JMP $CAA2'), (b'\x4c\xa0\xca', 2, 'JMP $CAA0'),
         (b'\x80\xb5', 4, 'BRA $CAA0'), (b'\x80\xb7', 2, 'BRA $CAA2'),
         (b'\x4c\xa4\xca', 0, 'JMP $CA6D'), (b'\x4c\xa6\xca', 0, 'JMP $CAA6'),
         (b'\x4c\xc0\xca', 0, 'JMP $CAC0'), (b'\x4c\xde\xca', 0, 'JMP $CADE'),
         (b'\x4c\xeb\xca', 0, 'JMP $CAEB')]
for k in range(48):
    lo, hi = d[T.CTRL_TABLE + k * 2], d[T.CTRL_TABLE + k * 2 + 1]
    a = (hi << 8) | lo
    f = a - 0x8000
    win = d[f:f + 0x80]
    hits = ['%s=%d' % (lab, n) for pat, n, lab in TAILS if pat in win]
    print('$%02X -> $%04X  %s' % (k, a, '  '.join(hits) or '???'))
