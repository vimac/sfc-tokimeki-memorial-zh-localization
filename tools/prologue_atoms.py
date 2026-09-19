"""Flatten text block 144 (the prologue) into a byte-exact, re-encodable script.

Every source byte is preserved as an *atom*, so the original block can be
reconstructed byte-for-byte (that is the regression test), and so the Chinese
patch can be built by swapping only the text atoms and copying every control
byte verbatim -- the dispatcher's box/step state machine then cannot drift.

Atom kinds
  ['g', char, rawhex]            one glyph, via an SB code (1B) or K2 code (2B)
  ['c', byte, rawhex]            control byte ($14 line, $0C box end, $0A entry, $25 pause...)
  ['n', marker, rawhex]          $12/$13 player surname / given name
  ['v', token, rawhex]           opaque $E8xx variable code (birthday, blood type...)
  ['m', code, text, [ctrls], rawhex]
                                 phrase macro $A0-$A5/$A8-$AD: expands to text AND
                                 control bytes, so it can replace 2-3 bytes with 1

Output: docs/research/prologue_atoms.json
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

BLOCK = 144
END = 0x22FA1F            # text_ptr(71): first byte after the prologue block
MARK = {0x12: '〔姓〕', 0x13: '〔名〕', 0x09: '　'}
LINE_CTRL = (0x14, 0x0C, 0x0A)
PHRASE_CTRL = (0x0A, 0x0C, 0x14)


def sb_code_map(rom):
    m = {}
    for c in range(0x40, 0xA0):
        ch = T.idx_to_char(rom.sb_entry(c))
        if ch and ch not in m:
            m[ch] = c
    return m


def macro_expand(rom, addr, code, seen, depth):
    """Phrase/sub body -> (text, ctrl bytes).  Stops at the body's own $0A/$0C."""
    d = rom.data
    i, chars, ctrls = addr, [], []
    while d[i] != 0x00 and i < addr + 0x60:
        b = d[i]
        if b == 0x0A:
            return ''.join(chars), ctrls
        if b < 0x40:
            if b in PHRASE_CTRL and not chars and not ctrls:
                pass
            if b in MARK:
                chars.append(MARK[b])
            else:
                ctrls.append(b)
                if b in PHRASE_CTRL:
                    return ''.join(chars), ctrls
            i += 1
        elif b < 0xA0:
            chars.append(T.idx_to_char(rom.sb_entry(b)) or '')
            i += 1
        elif b < 0xE8:
            if depth < 3 and b not in seen:
                a = rom.phrase_addr(b)
                if a:
                    t, k = macro_expand(rom, a, b, seen | {b}, depth + 1)
                    chars.append(t)
                    ctrls += k
            i += 1
        elif b < 0xF0:
            i += 2
        else:
            chars.append(T.idx_to_char(((b << 8) | d[i + 1]) & 0x0FFF) or '')
            i += 2
    return ''.join(chars), ctrls


def body_atoms(rom, addr, code, raw):
    """A phrase macro used in-line: keep it as one atom."""
    text, ctrls = macro_expand(rom, addr, code, {code}, 0)
    return ['m', '%02X' % code, text, ctrls, raw]


def walk_block(rom):
    d = rom.data
    atoms = []
    i = rom.text_ptr(BLOCK)
    atoms.append(['c', d[i], '%02x' % d[i]])       # leading block marker $0A
    i += 1
    while i < END:
        b = d[i]
        if b < 0x40:
            if b in MARK:
                atoms.append(['n', MARK[b], '%02x' % b])
            else:
                atoms.append(['c', b, '%02x' % b])
            i += 1
        elif b < 0xA0:
            ch = T.idx_to_char(rom.sb_entry(b)) or ''
            atoms.append(['g', ch, '%02x' % b])
            i += 1
        elif b < 0xE8:
            a = rom.phrase_addr(b)
            if a is None:
                atoms.append(['c', b, '%02x' % b])
            else:
                atoms.append(body_atoms(rom, a, b, '%02x' % b))
            i += 1
        elif b < 0xF0:
            hi = d[i + 1]
            raw = '%02x%02x' % (b, hi)
            a = rom.sub_addr(b, hi)
            text, ctrls = macro_expand(rom, a, b, set(), 1) if a else ('', [])
            if ctrls or not text:
                atoms.append(['v', '⟦%02X%02X⟧' % (b, hi), raw])
            else:
                atoms.append(['m', '%02X%02X' % (b, hi), text, ctrls, raw])
            i += 2
        else:
            idx = ((b << 8) | d[i + 1]) & 0x0FFF
            atoms.append(['g', T.idx_to_char(idx) or '', '%02x%02x' % (b, d[i + 1])])
            i += 2
    return atoms


def segmentize(atoms):
    """Split after every atom that ends a line ($14), box ($0C) or entry ($0A)."""
    segs, cur = [], []
    for a in atoms:
        cur.append(a)
        tail = ctrl_tail(a)
        if tail and tail[-1] in LINE_CTRL:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


def ctrl_tail(a):
    if a[0] == 'c':
        return [a[1]]
    if a[0] == 'm':
        return a[3]
    return []


def main():
    rom = T.Rom()
    atoms = walk_block(rom)
    segs = segmentize(atoms)
    raw = ''.join(a[-1] for a in atoms)
    a0 = rom.text_ptr(BLOCK)
    src = rom.data[a0:END].hex()
    print('atoms %d  segments %d  reconstructed %d/%d bytes  %s' %
          (len(atoms), len(segs), len(raw) // 2, END - a0,
           'BYTE-EXACT' if raw == src else 'MISMATCH'))
    out = []
    for seg in segs:
        # flatten
        tx, ctl = [], []
        for a in seg:
            if a[0] == 'g':
                tx.append(a[1]); ctl = []
            elif a[0] == 'n':
                tx.append(a[1]); ctl = []
            elif a[0] == 'v':
                tx.append(a[1]); ctl = []
            elif a[0] == 'm':
                tx.append(a[2]); ctl += a[3]
            elif a[0] == 'c':
                ctl.append(a[1])
        out.append({'jp': ''.join(tx), 'zh': '', 'ctl': ctl,
                    'atoms': seg})
    json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     'docs', 'research', 'prologue_atoms.json'), 'w'),
              ensure_ascii=False, indent=1)
    print('segments:', len(out), 'ctl bytes:', sum(len(s['ctl']) for s in out))


if __name__ == '__main__':
    main()
