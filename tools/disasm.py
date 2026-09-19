"""Minimal 65816 disassembler for analyzing the Tokimeki Memorial text engine.

Handles the common addressing modes and opcodes used in the
text rendering dispatch code at file offset 0x12500 (bank $02).
"""
import sys

# 65816 opcode table (subset - common opcodes)
# Format: (mnemonic, addressing_mode, length)
# Addressing modes:
#   imm8, imm16, imm8/16 (depends on M/X flag), abs, absx, absy,
#   long, longx, dp, dpx, dpy, ind, indx, indy, indlong, indlongy,
#   impl, acc, rel, rell, indai, absai, absail, stack, blockmove

Opcodes = {}
def op(code, mn, am, ln):
    Opcodes[code] = (mn, am, ln)

# Load/Store
for c in range(0x80, 0x88): pass  # placeholder
op(0xA9, "LDA", "imm16", 3)  # LDA #imm16 (assuming 16-bit A)
op(0xA9, "LDA", "imm8", 2)   # ambiguous, default to 16-bit
op(0xA5, "LDA", "dp", 2)
op(0xB5, "LDA", "dpx", 2)
op(0xAD, "LDA", "abs", 3)
op(0xBD, "LDA", "absx", 3)
op(0xB9, "LDA", "absy", 3)
op(0xAF, "LDA", "long", 4)
op(0xBF, "LDA", "longx", 4)
op(0xA1, "LDA", "dpxi", 2)
op(0xB1, "LDA", "dpiy", 2)
op(0xA7, "LDA", "dpii", 2)
op(0xB7, "LDA", "dpliy", 2)
op(0xA2, "LDX", "imm16", 3)
op(0xAE, "LDX", "abs", 3)
op(0xA0, "LDY", "imm16", 3)
op(0xAC, "LDY", "abs", 3)
op(0x85, "STA", "dp", 2)
op(0x95, "STA", "dpx", 2)
op(0x8D, "STA", "abs", 3)
op(0x9D, "STA", "absx", 3)
op(0x99, "STA", "absy", 3)
op(0x8F, "STA", "long", 4)
op(0x9F, "STA", "longx", 4)
op(0x81, "STA", "dpxi", 2)
op(0x91, "STA", "dpiy", 2)
op(0x86, "STX", "dp", 2)
op(0x8E, "STX", "abs", 3)
op(0x84, "STY", "dp", 2)
op(0x8C, "STY", "abs", 3)
# Arithmetic
op(0x69, "ADC", "imm16", 3)
op(0x65, "ADC", "dp", 2)
op(0x6D, "ADC", "abs", 3)
op(0x7D, "ADC", "absx", 3)
op(0xE9, "SBC", "imm16", 3)
op(0xE5, "SBC", "dp", 2)
op(0xED, "SBC", "abs", 3)
op(0xC9, "CMP", "imm16", 3)
op(0xC5, "CMP", "dp", 2)
op(0xCD, "CMP", "abs", 3)
op(0xD5, "CMP", "dpx", 2)
op(0xDD, "CMP", "absx", 3)
op(0x29, "AND", "imm16", 3)
op(0x25, "AND", "dp", 2)
op(0x2D, "AND", "abs", 3)
op(0x35, "AND", "dpx", 2)
op(0x09, "ORA", "imm16", 3)
op(0x05, "ORA", "dp", 2)
op(0x0D, "ORA", "abs", 3)
op(0x15, "ORA", "dpx", 2)
op(0x49, "EOR", "imm16", 3)
op(0x4D, "EOR", "abs", 3)
# Branches
op(0x90, "BCC", "rel", 2)
op(0xB0, "BCS", "rel", 2)
op(0xD0, "BNE", "rel", 2)
op(0xF0, "BEQ", "rel", 2)
op(0x30, "BMI", "rel", 2)
op(0x10, "BPL", "rel", 2)
op(0x80, "BRA", "rel", 2)
op(0x82, "BRL", "rell", 3)
# Jumps/Subroutines
op(0x4C, "JMP", "abs", 3)
op(0x5C, "JMP", "long", 4)
op(0x20, "JSR", "abs", 3)
op(0x22, "JSL", "long", 4)
op(0x60, "RTS", "impl", 1)
op(0x6B, "RTL", "impl", 1)
op(0x40, "RTI", "impl", 1)
# Register
op(0xAA, "TAX", "impl", 1)
op(0xA8, "TAY", "impl", 1)
op(0x8A, "TXA", "impl", 1)
op(0x98, "TYA", "impl", 1)
op(0xBA, "TSX", "impl", 1)
op(0x9A, "TXS", "impl", 1)
op(0xEB, "XBA", "impl", 1)
op(0x1B, "TCS", "impl", 1)
# Increment/Decrement
op(0xE8, "INX", "impl", 1)
op(0xC8, "INY", "impl", 1)
op(0xCA, "DEX", "impl", 1)
op(0x88, "DEY", "impl", 1)
op(0x1A, "INC", "impl", 1)  # INC A
op(0x3A, "DEC", "impl", 1)  # DEC A
op(0xE6, "INC", "dp", 2)
op(0xCE, "DEC", "abs", 3)
# Flags
op(0x18, "CLC", "impl", 1)
op(0x38, "SEC", "impl", 1)
op(0x58, "CLI", "impl", 1)
op(0x78, "SEI", "impl", 1)
op(0xC2, "REP", "imm8", 2)
op(0xE2, "SEP", "imm8", 2)
# Stack
op(0x48, "PHA", "impl", 1)
op(0x68, "PLA", "impl", 1)
op(0x08, "PHP", "impl", 1)
op(0x28, "PLP", "impl", 1)
op(0x5A, "PHY", "impl", 1)
op(0x7A, "PLY", "impl", 1)
op(0xDA, "PHX", "impl", 1)
op(0xFA, "PLX", "impl", 1)
# Shifts
op(0x0A, "ASL", "acc", 1)
op(0x4A, "LSR", "acc", 1)
op(0x2A, "ROL", "acc", 1)
op(0x6A, "ROR", "acc", 1)
op(0x06, "ASL", "dp", 2)
op(0x46, "LSR", "dp", 2)
# Bit
op(0x24, "BIT", "dp", 2)
op(0x2C, "BIT", "abs", 3)
op(0x89, "BIT", "imm8", 2)
# Other
op(0xEA, "NOP", "impl", 1)
op(0x64, "STZ", "dp", 2)
op(0x9C, "STZ", "abs", 3)
op(0x7B, "TDC", "impl", 1)
op(0x5B, "TCD", "impl", 1)
op(0xAB, "PLB", "impl", 1)
op(0x0B, "PHB", "impl", 1)
op(0x0E, "ASL", "abs", 3)
op(0x4E, "LSR", "abs", 3)
op(0xEE, "INC", "abs", 3)
op(0xCE, "DEC", "abs", 3)
op(0xC6, "DEC", "dp", 2)
op(0x03, "ORA", "sr", 2)
op(0x13, "ORA", "sriy", 2)
op(0x23, "AND", "sr", 2)
op(0x63, "ADC", "sr", 2)
op(0xE3, "SBC", "sr", 2)
op(0xC3, "CMP", "sr", 2)
op(0x43, "EOR", "sr", 2)
op(0x07, "ORA", "dpi", 2)
op(0x27, "AND", "dpi", 2)
op(0x47, "EOR", "dpi", 2)
op(0x67, "ADC", "dpi", 2)
op(0x87, "STA", "dpi", 2)
op(0xA7, "LDA", "dpi", 2)
op(0xC7, "CMP", "dpi", 2)
op(0xE7, "SBC", "dpi", 2)


def disassemble(data, offset, length, base_addr=None):
    """Disassemble `length` bytes starting at `offset` in `data`."""
    if base_addr is None:
        base_addr = offset
    out = []
    i = offset
    end = offset + length
    while i < end:
        addr = base_addr + (i - offset)
        b = data[i]
        if b in Opcodes:
            mn, am, ln = Opcodes[b]
            raw = data[i:i+ln]
            hexstr = ' '.join(f'{x:02X}' for x in raw)
            operand = ''
            target = ''
            if am == 'imm16' or am == 'imm8':
                if ln > 2:
                    val = int.from_bytes(raw[1:3], 'little')
                    operand = f'#${val:04X}'
                elif ln > 1:
                    val = raw[1]
                    operand = f'#${val:02X}'
            elif 'abs' in am and 'ind' not in am:
                if ln >= 3:
                    val = int.from_bytes(raw[1:3], 'little')
                    operand = f'${val:04X}'
                    if 'x' in am: operand += ',X'
                    elif 'y' in am: operand += ',Y'
            elif 'long' in am and 'ind' not in am:
                if ln >= 4:
                    val = int.from_bytes(raw[1:4], 'little')
                    operand = f'${val:06X}'
                    if 'x' in am: operand += ',X'
            elif am == 'rel':
                off = raw[1] if raw[1] < 128 else raw[1] - 256
                target_addr = addr + 2 + off
                operand = f'${target_addr:04X}'
            elif am == 'rell':
                off = int.from_bytes(raw[1:3], 'little')
                if off > 32767: off -= 65536
                target_addr = addr + 3 + off
                operand = f'${target_addr:04X}'
            elif am == 'dp' or am == 'dpx' or am == 'dpi':
                operand = f'${raw[1]:02X}'
                if 'x' in am: operand += ',X'
                elif 'y' in am: operand += ',Y'
            elif am == 'impl' or am == 'acc':
                pass
            opstr = f'{mn} {operand}'.strip()
            out.append(f'{addr:06X}  {hexstr:<12s}  {opstr}')
            i += ln
        else:
            out.append(f'{addr:06X}  {b:02X}           ???')
            i += 1
    return '\n'.join(out)


if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    off = int(sys.argv[2], 16)
    ln = int(sys.argv[3], 16)
    base = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    print(disassemble(data, off, ln, base))
