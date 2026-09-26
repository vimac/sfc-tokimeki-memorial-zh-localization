"""Per-control-code cursor advance, read off the dispatcher's own handler tails.

The dispatcher at $80:CA6D classifies the byte at [$B4/$B6] and the table at file
0x4B0B holds 47 handlers -- one per code $00-$2E.  $30 and up branch off *before*
that lookup ($30-$37 to $CD8C with an operand, $38+ to $CD67 without one), so they
are not in the table at all.  Each handler finishes with JMP/BRA into the advance
chain at $CA9A..$CAA2, where $CAA0 is `INC $B4` and $CAA2 another one.  So the
tail target says how many bytes the code eats: JMP $CAA2 -> 1, JMP $CAA0 -> 2, and
$CA9E/$CA9C/$CA9A -> 3/4/5.

Slot 48 is printed too, as the guard it is: reading one word past the table end
gives $00A9, which is the first two bytes of the $00 handler's own code at $CB69.
It is not a handler, and $2F is therefore a 1-byte code with no dispatch target.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

ROM = sys.argv[1] if len(sys.argv) > 1 else T.ROM_JP
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
    print('$%02X%s -> $%04X  %s' % (k, '  (past the table end)' if k == 47 else '',
                                    a, '  '.join(hits) or '???'))
