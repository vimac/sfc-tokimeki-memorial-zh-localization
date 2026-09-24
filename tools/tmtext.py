"""Tokimeki Memorial (SFC, JP Rev1) text codec.

Bands proven from the text dispatcher at $80:CA6D (file 0x4A6D):
  00-3F  control code          (handler table: file 0x4B0B, 47 x LE16 = $00-$2E;
                                $2F is past the table end, $30+ branch before the lookup)
  40-9F  single-byte glyph     (table: file 0x18000, 96 x BE16, idx = BE16 & $0FFF)
  A0-E7  phrase macro (call)   (table: file 0x1CCAA5, 72 x LE16 offset in bank $B9)
  E8-EF  2-byte sub-text call  (table: file 0x2196A8, 2048 x LE16 offset in bank $C3)
  F0-FF  2-byte glyph code     idx = BE16(bytes) - $F000   (no table)

idx -> glyph record:  0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28
"""
import sys, os

ROM_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'rom_original_japanese.sfc')

CTRL_TABLE   = 0x4B0B
SB_TABLE     = 0x18000
PHRASE_TABLE = 0x1CCAA5
SUB_TABLE    = 0x2196A8
GLYPH_BASE   = 0x3E8000
PAGE_SLOTS   = 0x492
SLOT_BYTES   = 28
NUM_PAGES    = 3
MAX_INDEX    = NUM_PAGES * PAGE_SLOTS          # 0x0DB6 exclusive
# The last 16 slots are NOT glyphs.  $80:CD8C, the handler for the `$30-$37 xx`
# pen family, loads a colour triple for every text pen out of a table at
# $FF:FE38 (= glyph_offset(0xDA6)) -- that is where 周日粉红/周六蓝 get their RGB.
# Writing a bitmap from 0xDA6 up repaints the palette, so the writable band ends here.
GLYPH_WRITABLE_MAX = 0x0DA6
NAME_PTRS    = 0x9872
PTR_COUNT    = 145
TEXT_PTRS    = NAME_PTRS + PTR_COUNT * 3       # 0x9A25

# glyph index space is a JIS X0208-ordered font.
# idx -> (ku, cell) piecewise; 0x0153-0x01C4 are non-JIS extras, >=0x01C5 is kanji.
JIS_RANGES = [
    (0x0001, 0x005D, 1, 2),    # ku1 cells 2..94   、。「」…
    (0x005E, 0x006B, 2, 1),    # ku2 cells 1..14   ◆□■△…
    (0x006C, 0x0075, 3, 16),   # ０-９
    (0x0076, 0x008F, 3, 33),   # Ａ-Ｚ
    (0x0090, 0x00A9, 3, 65),   # ａ-ｚ
    (0x00AA, 0x00FC, 4, 1),    # hiragana ぁ-ん
    (0x00FD, 0x0152, 5, 1),    # katakana ァ-ヶ
    (0x01C5, MAX_INDEX - 1, 16, 1),   # kanji, ku 16 cell 1 (亜) upwards
]
JIS_HIRA   = 0x00AA
JIS_KATA   = 0x00FD
JIS_KANJI  = 0x01C5
EXTRA_LO, EXTRA_HI = 0x0153, 0x01C4


def idx_to_jis(i):
    for lo, hi, ku0, cell0 in JIS_RANGES:
        if lo <= i <= hi:
            k = i - lo
            return ku0 + k // 94, cell0 + k % 94
    return None


def jis_to_idx(ku, cell):
    if not (1 <= ku <= 16 and 1 <= cell <= 94) and ku >= 16:
        return JIS_KANJI + (ku - 16) * 94 + (cell - 1)
    for lo, hi, ku0, cell0 in JIS_RANGES:
        k = (ku - ku0) * 94 + (cell - cell0)
        if 0 <= k <= hi - lo:
            return lo + k
    return None


def idx_to_char(i):
    """Unicode char for a glyph index, or None for the non-JIS extras."""
    if i == 0:
        return ' '
    jc = idx_to_jis(i)
    if jc is None:
        return None
    try:
        return bytes([0xA0 + jc[0], 0xA0 + jc[1]]).decode('euc_jp')
    except UnicodeDecodeError:
        return None


_CHAR2IDX = {}


def char_to_idx(ch):
    """Glyph index for a unicode char (JIS X0208), or None."""
    if ch == ' ':
        return 0
    if not _CHAR2IDX:
        for i in range(MAX_INDEX):
            c = idx_to_char(i)
            if c and c not in _CHAR2IDX:
                _CHAR2IDX[c] = i
    return _CHAR2IDX.get(ch)


def glyph_offset(idx):
    return GLYPH_BASE + (idx // PAGE_SLOTS) * 0x8000 + (idx % PAGE_SLOTS) * SLOT_BYTES


class Rom:
    def __init__(self, path=ROM_DEFAULT):
        self.data = bytearray(open(path, 'rb').read())

    def __getitem__(self, sl):
        return self.data[sl]

    def ptr(self, i):
        """Decoded block address for entry i of a pointer table base."""
        return self._ptr_at(i)

    def _ptr_at(self, i, base=0):
        lo, hi, bank = self.data[base + i * 3: base + i * 3 + 3]
        if bank == 0:
            return None
        return (bank - 0x80) * 0x8000 - 0x8000 + ((hi << 8) | lo)

    def text_ptr(self, i):
        return self._ptr_at(i, TEXT_PTRS)

    def name_ptr(self, i):
        return self._ptr_at(i, NAME_PTRS)

    def sb_entry(self, code):
        b0, b1 = self.data[SB_TABLE + (code - 0x40) * 2: SB_TABLE + (code - 0x40) * 2 + 2]
        return ((b0 << 8) | b1) & 0x0FFF

    def phrase_addr(self, code):
        lo, hi = self.data[PHRASE_TABLE + (code - 0xA0) * 2: PHRASE_TABLE + (code - 0xA0) * 2 + 2]
        addr = (hi << 8) | lo
        return (0xB9 - 0x80) * 0x8000 + addr - 0x8000 if addr >= 0x8000 else None

    def sub_addr(self, code_hi, code_lo):
        idx = (((code_hi << 8) | code_lo) & 0x07FF)
        lo, hi = self.data[SUB_TABLE + idx * 2: SUB_TABLE + idx * 2 + 2]
        addr = (hi << 8) | lo
        return (0xC3 - 0x80) * 0x8000 + addr - 0x8000 if addr >= 0x8000 else None


def decode(rom, addr, limit=0x800, depth=0, maxdepth=3):
    """Decode a text stream into tokens. Returns list of (kind, ...) tuples."""
    out = []
    i = addr
    end = addr + limit
    while i < end:
        b = rom.data[i]
        if b == 0x00 and i > addr:
            out.append(('end', i))
            return out
        if b == 0x0A and depth > 0:
            out.append(('ret', i))
            return out
        if b < 0x40:
            out.append(('ctrl', b, i))
            i += 1
        elif b < 0xA0:
            out.append(('sb', b, rom.sb_entry(b), i))
            i += 1
        elif b < 0xE8:
            if depth < maxdepth and rom.phrase_addr(b) is not None:
                out.append(('phrase', b, i))
                sub = decode(rom, rom.phrase_addr(b), 0x80, depth + 1, maxdepth)
                out.append(('phrase_end', b, sub))
            else:
                out.append(('phrase', b, i))
            i += 1
        elif b < 0xF0:
            hi = rom.data[i + 1]
            out.append(('sub', b, hi, i))
            if depth < maxdepth and rom.sub_addr(b, hi) is not None:
                out.append(('sub_end', b, hi,
                            decode(rom, rom.sub_addr(b, hi), 0x80, depth + 1, maxdepth)))
            i += 2
        else:
            idx = ((b << 8) | rom.data[i + 1]) - 0xF000
            out.append(('kanji', b, rom.data[i + 1], idx, i))
            i += 2
    out.append(('limit', i))
    return out


def render(rom, toks):
    s = []
    for t in toks:
        if t[0] == 'sb':
            c = idx_to_char(t[2])
            s.append(c if c else '{%02X}' % t[1])
        elif t[0] == 'kanji':
            c = idx_to_char(t[3])
            s.append(c if c else '<%04X>' % t[3])
        elif t[0] == 'ctrl':
            s.append('[%02X]' % t[1])
        elif t[0] == 'phrase':
            s.append('(ph%02X' % t[1] + ')')
        elif t[0] == 'sub':
            s.append('(sub%02X%02X)' % (t[1], t[2]))
        elif t[0] == 'end':
            break
    return ''.join(s)


def flatten(toks):
    """Recursive token list -> plain string of decoded chars (phrases inlined)."""
    s = []
    for t in toks:
        if t[0] == 'sb':
            c = idx_to_char(t[2]); s.append(c or '')
        elif t[0] == 'kanji':
            c = idx_to_char(t[3]); s.append(c or '')
        elif t[0] == 'ctrl':
            s.append('[%02X]' % t[1])
        elif t[0] == 'phrase':
            s.append('«%02X»' % t[1])
        elif t[0] == 'phrase_end':
            s.append(flatten(t[2]))
        elif t[0] == 'sub':
            s.append('§%02X%02X' % (t[1], t[2]))
        elif t[0] == 'sub_end':
            s.append(flatten(t[3]))
        elif t[0] == 'end':
            break
    return ''.join(s)


def block_bytes(rom, i):
    """Raw bytes of text block i, up to the 0x00 terminator (or next block)."""
    a = rom.text_ptr(i)
    if a is None:
        return None, None
    b = rom.text_ptr(i + 1)
    j = a
    limit = b if (b and b > a and b - a < 0x4000) else a + 0x2000
    while j < limit and rom.data[j] != 0x00:
        j += 1
    return a, j


if __name__ == '__main__':
    rom = Rom()
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'blocks'
    if cmd == 'blocks':
        for i in range(PTR_COUNT):
            a, e = block_bytes(rom, i)
            if a is None:
                continue
            toks = decode(rom, a, min(e - a + 1, 0x900))
            txt = flatten(toks)
            print(f"[{i:3d}] file={a:#07x} len={e-a:5d}  {txt[:110]}")
    elif cmd == 'block':
        i = int(sys.argv[2])
        a, e = block_bytes(rom, i)
        print(f"block {i}: file {a:#x} .. {e:#x} ({e-a} bytes)")
        for t in decode(rom, a, e - a + 1):
            print('  ', t)
    elif cmd == 'sbtable':
        for c in range(0x40, 0xA0):
            i = rom.sb_entry(c)
            print(f"{c:#04x} -> {i:#06x} {idx_to_char(i) or '?'}")
