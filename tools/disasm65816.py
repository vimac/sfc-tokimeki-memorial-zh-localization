"""65816 反汇编器完善版 (ANAMB 会话用).

用法:
  python3 tools/disasm65816.py <romfile> <file_offset_hex> <length_hex> [base_addr_hex]
输出: 地址  机器码  助记符 操作数
"""
import sys

# (mnemonic, mode, length)  mode: imm8 imm16 abs absx absy long longx dp dpx dpy
#   dpi(dpi,Y) dpxi(ind,X) dpii(ind) idl(ind long) idly rel rell impl acc blk pee
OPS = {}
def _o(start, end, mn, mode, ln):
    for c in range(start, end+1):
        OPS[c] = (mn, mode, ln)

# 系统指令
for op_, mn in [(0x00,'BRK'),(0xEB,'XBA'),(0xDB,'STP'),(0xCB,'WAI'),(0xFF,'??F')]:
    OPS[op_] = (mn, 'impl', 1)
OPS[0x18] = ('CLC','impl',1); OPS[0x38] = ('SEC','impl',1)
OPS[0x58] = ('CLI','impl',1); OPS[0x78] = ('SEI','impl',1)
OPS[0xB8] = ('CLV','impl',1); OPS[0xD8] = ('CLD','impl',1)
OPS[0xF8] = ('SED','impl',1); OPS[0xC2] = ('REP','imm8',2)
OPS[0xE2] = ('SEP','imm8',2)
OPS[0x5A] = ('PHY','impl',1); OPS[0x7A] = ('PLY','impl',1)
OPS[0xDA] = ('PHX','impl',1); OPS[0xFA] = ('PLX','impl',1)
OPS[0x5B] = ('TCD','impl',1); OPS[0x7B] = ('TDC','impl',1)
OPS[0x1B] = ('TCS','impl',1); OPS[0x3B] = ('TSC','impl',1)
OPS[0xBA] = ('TSX','impl',1); OPS[0x9A] = ('TXS','impl',1)
OPS[0xBB] = ('TYX','impl',1); OPS[0xA2] = ('LDX','imm16',3)
OPS[0xA0] = ('LDY','imm16',3)
OPS[0x8A] = ('TXA','impl',1); OPS[0x98] = ('TYA','impl',1)
OPS[0xA8] = ('TAY','impl',1); OPS[0xAA] = ('TAX','impl',1)
OPS[0x8B] = ('PHB','impl',1); OPS[0xAB] = ('PLB','impl',1)
OPS[0x0B] = ('PHD','impl',1); OPS[0x2B] = ('PLD','impl',1)
OPS[0x4B] = ('PHK','impl',1); OPS[0x08] = ('PHP','impl',1)
OPS[0x28] = ('PLP','impl',1)
OPS[0x40] = ('RTI','impl',1); OPS[0x6B] = ('RTL','impl',1)
OPS[0x60] = ('RTS','impl',1)
# 载入/存储 (16位 A 假设)
OPS[0xA9] = ('LDA','imm16',3); OPS[0xA5] = ('LDA','dp',2)
OPS[0xB5] = ('LDA','dpx',2); OPS[0xAD] = ('LDA','abs',3)
OPS[0xBD] = ('LDA','absx',3); OPS[0xB9] = ('LDA','absy',3)
OPS[0xAF] = ('LDA','long',4); OPS[0xBF] = ('LDA','longx',4)
OPS[0xA1] = ('LDA','dpxi',2); OPS[0xB1] = ('LDA','dpiy',2)
OPS[0xA7] = ('LDA','dpi',2); OPS[0xB7] = ('LDA','dpliy',2)
OPS[0x85] = ('STA','dp',2); OPS[0x95] = ('STA','dpx',2)
OPS[0x8D] = ('STA','abs',3); OPS[0x9D] = ('STA','absx',3)
OPS[0x99] = ('STA','absy',3); OPS[0x8F] = ('STA','long',4)
OPS[0x9F] = ('STA','longx',4); OPS[0x81] = ('STA','dpxi',2)
OPS[0x91] = ('STA','dpiy',2); OPS[0x87] = ('STA','dpi',2)
OPS[0x97] = ('STA','dpliy',2)
OPS[0xA2] = ('LDX','imm16',3); OPS[0xAE] = ('LDX','abs',3)
OPS[0xBE] = ('LDX','absy',3); OPS[0xA6] = ('LDX','dp',2)
OPS[0xB6] = ('LDX','dpy',2)
OPS[0xA0] = ('LDY','imm16',3); OPS[0xAC] = ('LDY','abs',3)
OPS[0xBC] = ('LDY','absx',3); OPS[0xA4] = ('LDY','dp',2)
OPS[0xB4] = ('LDY','dpx',2)
OPS[0x86] = ('STX','dp',2); OPS[0x8E] = ('STX','abs',3)
OPS[0x96] = ('STX','dpy',2); OPS[0x84] = ('STY','dp',2)
OPS[0x8C] = ('STY','abs',3); OPS[0x94] = ('STY','dpx',2)
# 算术
for base, mn in [(0x69,'ADC'),(0x65,'ADC'),(0x75,'ADC'),(0x6D,'ADC'),
                 (0x7D,'ADC'),(0x79,'ADC'),(0x6F,'ADC'),(0x7F,'ADC'),
                 (0x61,'ADC'),(0x71,'ADC'),(0x67,'ADC'),(0x77,'ADC'),
                 (0x63,'ADC'),(0x63,'ADC'),(0xE9,'SBC'),(0xE5,'SBC'),
                 (0xF5,'SBC'),(0xED,'SBC'),(0xFD,'SBC'),(0xF9,'SBC'),
                 (0xEF,'SBC'),(0xFF,'SBC'),(0xE1,'SBC'),(0xF1,'SBC'),
                 (0xE7,'SBC'),(0xF7,'SBC'),(0xEB,'SBC'),(0xEB,'SBC'),
                 (0xE3,'SBC'),(0xE3,'SBC'),(0xC9,'CMP'),(0xC5,'CMP'),
                 (0xD5,'CMP'),(0xCD,'CMP'),(0xDD,'CMP'),(0xD9,'CMP'),
                 (0xCF,'CMP'),(0xDF,'CMP'),(0xC1,'CMP'),(0xD1,'CMP'),
                 (0xC7,'CMP'),(0xD7,'CMP'),(0xD3,'CMP'),(0xD3,'CMP'),
                 (0xC3,'CMP'),(0xC3,'CMP'),(0x29,'AND'),(0x25,'AND'),
                 (0x35,'AND'),(0x2D,'AND'),(0x3D,'AND'),(0x39,'AND'),
                 (0x2F,'AND'),(0x3F,'AND'),(0x21,'AND'),(0x31,'AND'),
                 (0x27,'AND'),(0x37,'AND'),(0x23,'AND'),(0x23,'AND'),
                 (0x09,'ORA'),(0x05,'ORA'),(0x15,'ORA'),(0x0D,'ORA'),
                 (0x1D,'ORA'),(0x19,'ORA'),(0x0F,'ORA'),(0x1F,'ORA'),
                 (0x01,'ORA'),(0x11,'ORA'),(0x07,'ORA'),(0x17,'ORA'),
                 (0x03,'ORA'),(0x03,'ORA'),(0x49,'EOR'),(0x45,'EOR'),
                 (0x55,'EOR'),(0x4D,'EOR'),(0x5D,'EOR'),(0x59,'EOR'),
                 (0x4F,'EOR'),(0x5F,'EOR'),(0x41,'EOR'),(0x51,'EOR'),
                 (0x47,'EOR'),(0x57,'EOR'),(0x43,'EOR'),(0x43,'EOR'),
                 (0xE6,'INC'),(0xEC,'INC'),(0xEE,'INC'),(0xC6,'DEC'),
                 (0xCE,'DEC'),(0xDE,'DEC'),(0xCA,'DEX'),(0x88,'DEY'),
                 (0xE8,'INX'),(0xC8,'INY'),(0x0A,'ASL'),(0x4A,'LSR'),
                 (0x06,'ASL'),(0x46,'LSR'),(0x16,'ASL'),(0x56,'LSR'),
                 (0x0E,'ASL'),(0x4E,'LSR'),(0x1E,'ASL'),(0x5E,'LSR'),
                 (0x06,'ASL'),(0x46,'LSR')]:
    OPS.setdefault(base, (mn, 'x', 2))
# 修正常见的
for c, mn in [(0x0A,'ASL A'),(0x4A,'LSR A'),(0x2A,'ROL A'),(0x6A,'ROR A')]:
    OPS[c] = (mn, 'acc', 1)
# 分支
for c, mn in [(0x90,'BCC'),(0xB0,'BCS'),(0xD0,'BNE'),(0xF0,'BEQ'),
              (0x30,'BMI'),(0x10,'BPL'),(0x50,'BVC'),(0x70,'BVS')]:
    OPS[c] = (mn, 'rel', 2)
OPS[0x80] = ('BRA','rel',2); OPS[0x82] = ('BRL','rell',3)
OPS[0x20] = ('JSR','abs',3); OPS[0xFC] = ('JSR','absx',3)
OPS[0x22] = ('JSL','long',4); OPS[0x6C] = ('JMP','ind',3)
OPS[0x4C] = ('JMP','abs',3); OPS[0x5C] = ('JMP','long',4)
OPS[0x7C] = ('JMP','absx',3); OPS[0x6B] = ('RTL','impl',1)
OPS[0x44] = ('MVN','blk',3); OPS[0x54] = ('MVN','blk',3)
OPS[0x54] = ('PEA','imm16',3); OPS[0xD4] = ('PEA','imm16',3)
OPS[0x62] = ('PER','rell',3); OPS[0x64] = ('STZ','dp',2)
OPS[0x9C] = ('STZ','abs',3); OPS[0x74] = ('STZ','dpx',2)
OPS[0x9E] = ('STZ','absx',3)
OPS[0x89] = ('BIT','imm16',3); OPS[0x24] = ('BIT','dp',2)
OPS[0x2C] = ('BIT','abs',3)
OPS[0x3A] = ('DEC A','acc',1); OPS[0x1A] = ('INC A','acc',1)
OPS[0xEA] = ('NOP','impl',1)

MODELN = 2  # 默认 M=0 (16位 A): imm = 3B
XLEN = 2    # 默认 X/Y 16位: imm = 3B

def disasm(data, off, length, base=None):
    if base is None: base = off
    out = []
    i = off; end = off + length
    while i < end:
        addr = base + (i - off)
        b = data[i]
        e = OPS.get(b)
        if e is None:
            out.append('%06X  %02X            ???' % (addr, b))
            i += 1; continue
        mn, mode, ln = e
        raw = data[i:i+ln]
        hexs = ' '.join('%02X' % x for x in raw)
        opnd = ''
        if mode == 'imm16':
            v = int.from_bytes(raw[1:3], 'little')
            opnd = '#$%04X' % v
        elif mode == 'abs':
            v = int.from_bytes(raw[1:3], 'little')
            opnd = '$%04X' % v
        elif mode == 'absx':
            v = int.from_bytes(raw[1:3], 'little')
            opnd = '$%04X,X' % v
        elif mode == 'absy':
            v = int.from_bytes(raw[1:3], 'little')
            opnd = '$%04X,Y' % v
        elif mode == 'long':
            v = int.from_bytes(raw[1:4], 'little')
            opnd = '$%06X' % v
        elif mode == 'longx':
            v = int.from_bytes(raw[1:4], 'little')
            opnd = '$%06X,X' % v
        elif mode in ('dp','dpx','dpy'):
            opnd = '$%02X' % raw[1]
            if mode == 'dpx': opnd += ',X'
            elif mode == 'dpy': opnd += ',Y'
        elif mode == 'dpxi':
            opnd = '($%02X,X)' % raw[1]
        elif mode == 'dpiy':
            opnd = '($%02X),Y' % raw[1]
        elif mode == 'dpi':
            opnd = '($%02X)' % raw[1]
        elif mode == 'dpliy':
            opnd = '[$%02X],Y' % raw[1]
        elif mode == 'rel':
            d = raw[1] if raw[1] < 128 else raw[1]-256
            opnd = '$%04X' % ((addr+2+d) & 0xFFFF)
        elif mode == 'rell':
            d = int.from_bytes(raw[1:3], 'little')
            if d > 32767: d -= 65536
            opnd = '$%04X' % ((addr+3+d) & 0xFFFF)
        elif mode == 'blk':
            opnd = '$%02X,$%02X' % (raw[2], raw[1])
        txt = ('%s %s' % (mn, opnd)).strip()
        out.append('%06X  %-12s  %s' % (addr, hexs, txt))
        i += ln
    return '\n'.join(out)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    off = int(sys.argv[2], 16)
    ln = int(sys.argv[3], 16)
    base = int(sys.argv[4], 16) if len(sys.argv) > 4 else None
    print(disasm(data, off, ln, base))
