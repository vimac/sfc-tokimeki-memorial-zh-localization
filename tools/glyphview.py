import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
rom = T.Rom()
def art(idx):
    o = T.glyph_offset(idx)
    rows = []
    for r in range(14):
        w = rom.data[o + r * 2] | (rom.data[o + r * 2 + 1] << 8)
        rows.append(''.join('#' if w & (1 << (15 - c)) else '.' for c in range(14)))
    return rows
if __name__ == '__main__':
    for a in sys.argv[1:]:
        idx = int(a, 16)
        print('%s  idx=%s  %r' % (a, hex(idx), T.idx_to_char(idx)))
        for r in art(idx): print('   ' + r)
