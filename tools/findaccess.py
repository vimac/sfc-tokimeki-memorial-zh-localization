"""Find every code location that reads or writes a WRAM address, across all banks.

usage: python3 tools/findaccess.py <rom> <wram-addr-hex>   e.g. 0D24
"""
import sys
sys.path.insert(0, 'REPO_ROOT/tools')
import tmtext as T

STORE = {0x8D: 'STA', 0x8E: 'STX', 0x8C: 'STY'}
LOAD = {0xAD: 'LDA', 0xAE: 'LDX', 0xAC: 'LDY', 0xCD: 'CMP', 0xED: 'ADC',
        0x6D: 'ADC', 0x2D: 'AND', 0x0D: 'ORA', 0x4D: 'EOR', 0xEC: 'CPX',
        0x2C: 'BIT', 0x0C: 'TSB', 0x1C: 'TRB', 0xEE: 'INC', 0xFE: 'INC',
        0xDC: 'CPX', 0xFC: 'CPY', 0x1D: 'ORA', 0x3D: 'AND'}

def main():
    d = bytes(T.Rom(sys.argv[1]).data)
    a = int(sys.argv[2], 16)
    lo, hi = a & 0xFF, a >> 8
    n = 0
    for i in range(len(d) - 3):
        if d[i + 1] == lo and d[i + 2] == hi:
            op = d[i]
            k = STORE.get(op) or LOAD.get(op)
            if k:
                bank = 0x80 + i // 0x8000
                print('$%02X:%04X  %02X %02X %02X   %s $%04X'
                      % (bank, 0x8000 + i % 0x8000, op, lo, hi, k, a))
                n += 1
    print('%d hits' % n)


main()
