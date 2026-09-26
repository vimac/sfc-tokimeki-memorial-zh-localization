"""Every disassembly listing in the docs still matches the bytes in the master ROM.

Hand-copied and hand-condensed listings drift: two lines in `control-codes.md` and
`calendar-colour.md` carried operand bytes under the wrong address.  This walks
`docs/**/*.md`, `AGENTS.md` and `PROGRESS.md`, reads each `ADDR: BB BB BB`
line, applies the LoROM map `file = (bank-0x80)*0x8000 + (addr & 0x7FFF)`, and
compares against the read-only master.  A 4-digit address is assumed to be bank $80.

usage: python3 tools/doclistings.py            # exits 1 on any mismatch
"""
import re
import sys
import glob
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM = T.ROM_JP
LINE = re.compile(r'^'
                  r'(?:\$?([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})'
                  r'|([0-9A-Fa-f]{6})'
                  r'|([0-9A-Fa-f]{4}))'
                  r':\s+((?:[0-9A-Fa-f]{2}[ ]?)+)')


def listings():
    docs = sorted(glob.glob(os.path.join(ROOT, 'docs', '**', '*.md'), recursive=True))
    for name in ('AGENTS.md', 'PROGRESS.md'):
        docs.append(os.path.join(ROOT, name))
    for path in docs:
        with open(path, encoding='utf-8') as handle:
            for number, text in enumerate(handle, 1):
                match = LINE.match(text.strip())
                if not match:
                    continue
                if match.group(1):
                    bank, addr = int(match.group(1), 16), int(match.group(2), 16)
                elif match.group(3):
                    bank = int(match.group(3)[:2], 16)
                    addr = int(match.group(3)[2:], 16)
                else:
                    bank, addr = 0x80, int(match.group(4), 16)
                yield path, number, bank, addr, match.group(5).split()


def main():
    with open(ROM, 'rb') as handle:
        rom = handle.read()
    bad = checked = 0
    for path, number, bank, addr, want in listings():
        if not 0x80 <= bank <= 0xFF:
            continue
        offset = (bank - 0x80) * 0x8000 + (addr & 0x7FFF)
        got = rom[offset:offset + len(want)]
        checked += 1
        if got.hex(' ').upper() != ' '.join(want).upper():
            bad += 1
            print('%s:%d  $%02X:%04X  doc=%s  rom=%s' % (
                os.path.relpath(path, ROOT), number, bank, addr,
                ' '.join(want).upper(), got.hex(' ').upper()))
    print('%d listing lines checked, %d mismatch' % (checked, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
