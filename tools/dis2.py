"""Improved 65816 disassembler for SNES LoROM analysis.

Two modes:
  * linear sweep from a file offset, printing addr / bytes / mnemonic
  * optional M/X flag tracking (REP/SEP #$..) so immediate operand sizes are right

CLI:
  python3 tools/dis2.py <rom> <file_off_hex> <len_hex> [base_hex] [--mode8] [--bank=B]

base_hex: SNES 24-bit address to display (default: derived from LoROM bank arg --bank,
          else file offset interpreted as bank $80 with addr=0x8000+ (off&0x7FFF) if off<0x8000)
"""
import sys

# ---------------------------------------------------------------- opcode table
# mode codes and their *extra* byte counts:
#   I   acc/implicit          0
#   U   1-byte unused/imm8    1
#   zp  direct page           1
#   zpx/zpy                   1
#   (zp,X) (zp),Y (zp) [[zp]] [[zp],Y]   1
#   ab    absolute            2
#   abx/aby                   2
#   lng   long $aabbcc        3
#   lngx  long,X              3
#   [ab]  abs indirect (JMP)  2
#   (ab,X) JMP                2
#   rel   branch 8            1
#   rel16 BRA16 (BRL/PER)     2
#   blk   MVN/MVP (2 banks)   2
#   im    immediate: 1 or 2 bytes depending on M (A size)
#   imx   immediate: 1 or 2 bytes depending on X
#   i16   always 2 bytes (PEA)
#   i24   always 3 bytes (JSL, long imm)
#   stz/trb/tsb/bit use zp/ab with A/X size semantics (operand size = reg size)

MN = {}          # opcode -> (mnemonic, mode)
def _r(lo, hi, mn, mode):
    for c in range(lo, hi + 1):
        MN[c] = (mn, mode)

# --- ALU / load-store groups -------------------------------------------------
GROUPS = {0x00: 'ORA', 0x20: 'AND', 0x40: 'EOR', 0x60: 'ADC',
          0x80: 'STA', 0xA0: 'LDA', 0xC0: 'CMP', 0xE0: 'SBC'}
MODES = {  # offset-in-group -> (mode, mnemonic-suffix)
    0x01: ('zpx_i', ''),   # (zp,X)
    0x11: ('zp_iy', ''),   # (zp),Y
    0x02: ('lng_x', ''),   # [$a16,x]   (rare)
    0x12: ('zp_i',  ''),   # (zp)       65C02
    0x03: ('zp_s', ''),    # [[zp]]
    0x13: ('zp_siy', ''),  # [[zp],Y]
    0x05: ('zp', ''),      # zp
    0x15: ('zpx', ''),     # zp,X
    0x06: ('ab', ''),      # abs
    0x16: ('abx', ''),     # abs,X
    0x07: ('zp_s', ''),    # [[zp]]      (65C02 alias slot)
    0x17: ('zp_siy', ''),  # [[zp],Y]
    0x09: ('im', ''),      # #imm
    0x19: ('aby', ''),     # abs,Y
    0x0D: ('ab', ''),
    0x1D: ('abx', ''),
    0x0E: ('lng', ''),     # long
    0x1E: ('lng_x', ''),   # long,X
    0x0F: ('lng', ''),
    0x1F: ('lng_y', ''),   # [a16],Y (rare)
}
for base, mn in GROUPS.items():
    for off, (mode, _) in MODES.items():
        op = base | off
        MN.setdefault(op, (mn, mode))

# --- $8x/$9x STA extras, $Ax/$Bx LDA/LDX/LDY, $Cx/$Dx CMP/CPX/CPY ------------
extra = {
    0x82: ('STB?', 'i16'), 0x83: ('STB?', 'zp_s'),
    0x84: ('STY', 'zp'),    0x85: ('STA', 'zp'),   0x86: ('STX', 'zp'),
    0x87: ('STA', 'zp_s'),  0x88: ('DEY', 'I'),     0x89: ('BIT', 'im'),
    0x8A: ('TXA', 'I'),     0x8B: ('PHB', 'I'),     0x8C: ('STY', 'ab'),
    0x8D: ('STA', 'ab'),    0x8E: ('STX', 'ab'),    0x8F: ('STA', 'lng'),
    0x90: ('BCC', 'rel'),   0x91: ('STA', 'zp_iy'), 0x92: ('STA', 'zp_i'),
    0x93: ('STA', 'zp_siy'),0x94: ('STY', 'zpx'),   0x95: ('STA', 'zpx'),
    0x96: ('STX', 'zpy'),   0x97: ('STA', 'zp_siy'),0x98: ('TYA', 'I'),
    0x99: ('STA', 'aby'),   0x9A: ('TXS', 'I'),     0x9B: ('TXY', 'I'),
    0x9C: ('STZ', 'ab'),    0x9D: ('STA', 'abx'),   0x9E: ('STZ', 'abx'),
    0x9F: ('STA', 'lng_x'),

    0xA0: ('LDY', 'imx'),   0xA1: ('LDA', 'zpx_i'), 0xA2: ('LDX', 'imx'),
    0xA3: ('LDA', 'zp_s'),  0xA4: ('LDY', 'zp'),    0xA5: ('LDA', 'zp'),
    0xA6: ('LDX', 'zp'),    0xA7: ('LDA', 'zp_s'),  0xA8: ('TAY', 'I'),
    0xA9: ('LDA', 'im'),    0xAA: ('TAX', 'I'),     0xAB: ('PLB', 'I'),
    0xAC: ('LDY', 'ab'),    0xAD: ('LDA', 'ab'),    0xAE: ('LDX', 'ab'),
    0xAF: ('LDA', 'lng'),
    0xB0: ('BCS', 'rel'),   0xB1: ('LDA', 'zp_iy'), 0xB2: ('LDA', 'zp_i'),
    0xB3: ('LDA', 'zp_siy'),0xB4: ('LDY', 'zpx'),   0xB5: ('LDA', 'zpx'),
    0xB6: ('LDX', 'zpy'),   0xB7: ('LDA', 'zp_siy'),0xB8: ('CLV', 'I'),
    0xB9: ('LDA', 'aby'),   0xBA: ('TSX', 'I'),     0xBB: ('TYX', 'I'),
    0xBC: ('LDY', 'abx'),   0xBD: ('LDA', 'abx'),   0xBE: ('LDX', 'aby'),
    0xBF: ('LDA', 'lng_x'),

    0xC0: ('CPY?', 'imx'),  0xC1: ('CMP', 'zpx_i'), 0xC2: ('REP', 'U'),
    0xC3: ('CMP', 'zp_s'),  0xC4: ('CPY', 'zp'),    0xC5: ('CMP', 'zp'),
    0xC6: ('DEC', 'zp'),    0xC7: ('CMP', 'zp_s'),  0xC8: ('INY', 'I'),
    0xC9: ('CMP', 'im'),    0xCA: ('DEX', 'I'),     0xCB: ('WAI', 'I'),
    0xCC: ('CPY', 'ab'),    0xCD: ('CMP', 'ab'),    0xCE: ('DEC', 'ab'),
    0xCF: ('CMP', 'lng'),
    0xD0: ('BEQ', 'rel'),   0xD1: ('CMP', 'zp_iy'), 0xD2: ('CMP', 'zp_i'),
    0xD3: ('CMP', 'zp_siy'),0xD4: ('CPY', 'ab'),    0xD5: ('CMP', 'zpx'),
    0xD6: ('CMP', 'abx'),   0xD7: ('CMP', 'zp_siy'),0xD8: ('CLD', 'I'),
    0xD9: ('CMP', 'aby'),   0xDA: ('PHX', 'I'),     0xDB: ('STP', 'I'),
    0xDC: ('CPY', 'abx'),   0xDD: ('CMP', 'abx'),   0xDE: ('CMP', 'aby'),
    0xDF: ('CMP', 'lng_x'),

    0xE0: ('CPX?', 'imx'),  0xE1: ('SBC', 'zpx_i'), 0xE2: ('SEP', 'U'),
    0xE3: ('SBC', 'zp_s'),  0xE4: ('CPX', 'zp'),    0xE5: ('SBC', 'zp'),
    0xE6: ('INC', 'zp'),    0xE7: ('SBC', 'zp_s'),  0xE8: ('INX', 'I'),
    0xE9: ('SBC', 'im'),    0xEA: ('NOP', 'I'),     0xEB: ('XBA', 'I'),
    0xEC: ('CPX', 'ab'),    0xED: ('SBC', 'ab'),    0xEE: ('INC', 'ab'),
    0xEF: ('MVN', 'blk'),
    0xF0: ('BEQ?', 'rel'),  0xF1: ('SBC', 'zp_iy'), 0xF2: ('SBC', 'zp_i'),
    0xF3: ('SBC', 'zp_siy'),0xF4: ('PEA', 'i16'),   0xF5: ('SBC', 'zpx'),
    0xF6: ('SBC', 'abx'),   0xF7: ('SBC', 'zp_siy'),0xF8: ('SED', 'I'),
    0xF9: ('SBC', 'aby'),   0xFA: ('PLX', 'I'),     0xFB: ('SEL', 'I'),
    0xFC: ('JSR', 'abx_i'), 0xFD: ('SBC', 'abx'),   0xFE: ('SBC', 'aby'),
    0xFF: ('SBC', 'lng_x'),
}
MN.update(extra)

sysop = {
    0x00: ('BRK', 'U'),  0x04: ('TSB', 'zp'),   0x08: ('PHP', 'I'),
    0x0C: ('TSB', 'ab'), 0x14: ('TRB', 'zp'),   0x18: ('CLC', 'I'),
    0x1C: ('TRB', 'ab'), 0x1A: ('INC', 'acc'),  0x3A: ('DEC', 'acc'),
    0x20: ('JSR', 'ab'), 0x22: ('JSL', 'lng'),  0x24: ('BIT', 'zp'),
    0x28: ('PLP', 'I'),  0x2A: ('ROL', 'acc'),  0x2C: ('BIT', 'ab'),
    0x34: ('BIT', 'zpx'),0x3C: ('BIT', 'abx'),  0x40: ('RTI', 'I'),
    0x44: ('TML', 'U2'), 0x48: ('PHA', 'I'), 0x4A: ('LSR', 'acc'),  0x4B: ('PHK', 'I'),
    0x50: ('BVC', 'rel'),0x54: ('TMW', 'U2'),   0x58: ('CLI', 'I'),
    0x5A: ('PHY', 'I'),  0x5B: ('TCD', 'I'),    0x5C: ('JMP', 'lng'),
    0x60: ('RTS', 'I'),  0x62: ('PER', 'rel16'),0x64: ('STZ', 'zp'),
    0x68: ('PLA', 'I'),  0x6A: ('ROR', 'acc'),  0x6B: ('RTL', 'I'),
    0x6C: ('JMP', 'ab_i'),0x70: ('BVS', 'rel'), 0x74: ('STZ', 'zpx'),
    0x78: ('SEI', 'I'),  0x7A: ('PLY', 'I'),    0x7B: ('TDC', 'I'),
    0x7C: ('JMP', 'abx_i'),0x80: ('BRA', 'rel'), 0x82: ('BRL', 'rel16'),
    0x84: ('STY', 'zp'), 0x94: ('STY', 'zpx'),  0x9A: ('TXS', 'I'),
    0xA4: ('LDY', 'zp'), 0xB4: ('LDY', 'zpx'),  0xBC: ('LDY', 'abx'),
    0xC4: ('CPY', 'zp'), 0xD4: ('CPY', 'ab'),   0xE4: ('CPX', 'zp'),
    0xF4: ('PEA', 'i16'),0xFA: ('PLX', 'I'),    0x0B: ('PHD', 'I'),
    0x2B: ('PLD', 'I'),  0x5B: ('TCD', 'I'),    0x7B: ('TDC', 'I'),
    0x1B: ('TCS', 'I'),  0x3B: ('TSC', 'I'),    0xBB: ('TYX', 'I'),
    0x9B: ('TXY', 'I'),  0xBA: ('TSX', 'I'),    0xDA: ('PHX', 'I'),
    0x5A: ('PHY', 'I'),  0x7A: ('PLY', 'I'),
}
for op, mn in ((0x0A, 'ASL'), (0x2A, 'ROL'), (0x4A, 'LSR'), (0x6A, 'ROR')):
    sysop[op] = (mn, 'acc')
sysop[0x38] = ('SEC', 'I')   # SEC was missing -> printed as "??? 38"
MN.update(sysop)
MN[0x44] = ('TMB', 'U2')
MN[0x54] = ('TML', 'U2')
for op in (0xF0,):
    MN[op] = ('BEQ', 'rel')
MN[0x90] = ('BCC', 'rel'); MN[0xB0] = ('BCS', 'rel')
MN[0xD0] = ('BNE', 'rel'); MN[0xF0] = ('BEQ', 'rel')
MN[0x10] = ('BPL', 'rel'); MN[0x30] = ('BMI', 'rel')
MN[0x50] = ('BVC', 'rel'); MN[0x70] = ('BVS', 'rel')
MN[0x00] = ('BRK', 'U')
# Optional experimental table overrides, e.g.  D4=2  (opcode: total-instruction-size)
import os
if os.environ.get('D4SZ'):
    _sz = int(os.environ['D4SZ'])
    MN[0xD4] = ('D4?', 'U') if _sz == 2 else ('CPY', 'ab')
if os.environ.get('X16') == '0':
    pass
MN[0xC0] = ('CPY', 'imx'); MN[0xE0] = ('CPX', 'imx')
# $D4 $dd : empirically a 2-byte "push 16-bit direct-page variable" instruction
# (paired with `PLA:STA $dd` epilogues everywhere; see docs/research).  Override with D4SZ=3
MN[0xD4] = ('PSHD', 'zp')
MN[0x4C] = ('JMP', 'ab')

SIZE = {
    'I': 0, 'acc': 0, 'U': 1, 'U2': 2,
    'zp': 1, 'zpx': 1, 'zpy': 1, 'zp_i': 1, 'zpx_i': 1, 'zp_iy': 1,
    'zp_s': 1, 'zp_siy': 1,
    'ab': 2, 'abx': 2, 'aby': 2, 'ab_i': 2, 'abx_i': 2,
    'lng': 3, 'lng_x': 3, 'lng_y': 3,
    'rel': 1, 'rel16': 2, 'blk': 2,
    'im': None, 'imx': None, 'i16': 2, 'i24': 3,
}
SUFFIX = {
    'zp': '', 'zpx': ',X', 'zpy': ',Y', 'zp_i': '', 'zpx_i': '', 'zp_iy': ',Y',
    'zp_s': '', 'zp_siy': ',Y', 'ab': '', 'abx': ',X', 'aby': ',Y',
    'ab_i': '', 'abx_i': ',X', 'lng': '', 'lng_x': ',X', 'lng_y': ',Y',
}

def dis(data, off, n, base, m16=True, x16=True):
    out = []
    i = off
    end = off + n
    while i < end:
        op = data[i]
        e = MN.get(op)
        addr = base + (i - off)
        if e is None:
            out.append('%06X: %02X          ??? %02X' % (addr, op, op))
            i += 1
            continue
        mn, mode = e
        nb = SIZE[mode]
        if nb is None:
            nb = 2 if (m16 if mode == 'im' else x16) else 1
        raw = data[i:i + 1 + nb]
        hexs = ' '.join('%02X' % b for b in raw)
        tail = ''
        rare = ''
        if mode in ('I', 'acc'):
            txt = mn
        elif mode == 'rel':
            d = raw[1]
            d = d - 256 if d > 127 else d
            txt = '%s $%04X' % (mn, (addr + 2 + d) & 0xFFFF)
        elif mode == 'rel16':
            d = int.from_bytes(raw[1:3], 'little', signed=True)
            txt = '%s $%04X' % (mn, (addr + 3 + d) & 0xFFFF)
        elif mode in ('zp', 'zpx', 'zpy'):
            txt = '%s $%02X%s' % (mn, raw[1], SUFFIX[mode])
        elif mode == 'zp_i':
            txt = '%s ($%02X)' % (mn, raw[1])
        elif mode == 'zpx_i':
            txt = '%s ($%02X,X)' % (mn, raw[1])
        elif mode == 'zp_iy':
            txt = '%s ($%02X),Y' % (mn, raw[1])
        elif mode == 'zp_s':
            txt = '%s [$%02X]' % (mn, raw[1])
        elif mode == 'zp_siy':
            txt = '%s [$%02X],Y' % (mn, raw[1])
        elif mode in ('ab', 'abx', 'aby'):
            txt = '%s $%04X%s' % (mn, int.from_bytes(raw[1:3], 'little'), SUFFIX[mode])
        elif mode == 'ab_i':
            txt = '%s ($%04X)' % (mn, int.from_bytes(raw[1:3], 'little'))
        elif mode == 'abx_i':
            txt = '%s ($%04X,X)' % (mn, int.from_bytes(raw[1:3], 'little'))
        elif mode == 'lng':
            txt = '%s $%06X' % (mn, int.from_bytes(raw[1:4], 'little'))
        elif mode in ('lng_x', 'lng_y'):
            txt = '%s $%06X%s' % (mn, int.from_bytes(raw[1:4], 'little'), SUFFIX[mode])
        elif mode == 'im':
            v = int.from_bytes(raw[1:1 + nb], 'little')
            txt = '%s #$%0*X' % (mn, nb * 2, v)
        elif mode == 'imx':
            v = int.from_bytes(raw[1:1 + nb], 'little')
            txt = '%s #$%0*X' % (mn, nb * 2, v)
        elif mode == 'i16':
            txt = '%s #$%04X' % (mn, int.from_bytes(raw[1:3], 'little'))
        elif mode == 'blk':
            txt = '%s $%02X,$%02X' % (mn, raw[2], raw[1])
        elif mode == 'U':
            txt = '%s' % mn
            tail = ' ;$%02X' % raw[1]
        elif mode == 'U2':
            txt = '%s' % mn
            tail = ' ;$%02X $%04X' % (raw[1], int.from_bytes(raw[2:4], 'little'))
        rare = ' <<' if op in (0x02, 0x03, 0x12, 0x13, 0x07, 0x17, 0x0F, 0x1F,
                              0x44, 0x54, 0x62, 0x82, 0x83, 0x93, 0xA3, 0xB3,
                              0xD2, 0xD3, 0xD4, 0xDC, 0xDE, 0xE3, 0xF2, 0xF3,
                              0xFB, 0xEF, 0x00) else ''
        out.append('%06X: %-14s %s%s%s' % (addr, hexs, txt, tail, rare))
        # flag tracking
        # 65816 status bits: bit5 = M (accumulator), bit4 = X (index)
        if mn == 'SEP':
            v = raw[1]
            if v & 0x20: m16 = False
            if v & 0x10: x16 = False
        elif mn == 'REP':
            v = raw[1]
            if v & 0x20: m16 = True
            if v & 0x10: x16 = True
        i += 1 + nb
    return out

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    rom = args[0]
    off = int(args[1], 16)
    ln = int(args[2], 16)
    base = int(args[3], 16) if len(args) > 3 else None
    if base is None:
        bank = 0x80 + (off >> 15)
        base = (bank << 16) | (off & 0x7FFF)
    data = open(rom, 'rb').read()
    for line in dis(data, off, ln, base):
        print(line)
