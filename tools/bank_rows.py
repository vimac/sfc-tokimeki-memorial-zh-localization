"""List the draw-script runs in $180C0-$20000 that the patch has not touched.

Every edit the build makes in this bank changes its bytes, so comparing the shipped file against
the stock one *is* the coverage test -- no need to keep a list of tables in sync here, and a run
missed by that list could not hide from this one.  Stock runs whose bytes survive unchanged are
what still reaches the screen in Japanese, printed with their decoded text so a row can be
authored straight off the output.

Runs shorter than --min (3 codes) are usually an opcode operand or a one-glyph label, and a good
share of what survives that floor are fragments: the placement opcodes carry operand bytes, and an
operand >= $F0 gets swallowed by any run scan, so one real sentence can be reported as two pieces.
Those need a hexdump to resolve, not another batch.

usage: python3 tools/bank_rows.py [--min N]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_prologue as B

LO, HI = B.BANK_ALL
MIN = 3
if '--min' in sys.argv:
    MIN = int(sys.argv[sys.argv.index('--min') + 1])
stock = open(B.SRC_ROM, 'rb').read()
patched = open(B.OUT_ROM, 'rb').read()


def run_text(data, lo, hi):
    return ''.join(T.idx_to_char(((data[k] << 8) | data[k + 1]) & 0x0FFF) or '\ue000'
                   for k in range(lo, hi, 2))


untouched, touched = [], 0
i = LO
while i < HI - 1:
    if stock[i] >= 0xF0:
        j = i
        while j < HI - 1 and stock[j] >= 0xF0:
            j += 2
        if stock[i:j] == patched[i:j]:
            text = run_text(stock, i, j).strip('\ue000 ')
            if len(text) >= MIN:
                untouched.append((i, (j - i) // 2, text))
        else:
            touched += 1
        i = j
    else:
        i += 1

for addr, n, text in sorted(untouched, key=lambda r: (-r[1], r[0])):
    print("    (%#X, %d, %r, '', 'R')," % (addr, n, text))
print('# %d untouched runs of >= %d codes still in Japanese, %d runs changed by the patch'
      % (len(untouched), MIN, touched))
