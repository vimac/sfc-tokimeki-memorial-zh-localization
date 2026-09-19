"""Dump the prologue montage stream as an ordered frame list.

Box delimiters: codes $A0-$AD all expand to "<punct> $14" where $14 is the
"advance the dialogue" step, so they are the sentence/box ends.
$AE-$E7 and $E8-$EF pairs are word macros (compressible text, replaceable).
$12/$13 are the player's surname / given-name variables.

usage: python3 tools/prologue_struct.py [start_hex] [end_hex]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T

DELIM = set(range(0xA0, 0xAE)) | {0xAD}
VAR = {0x12: '【姓】', 0x13: '【名】'}


def expand(rom, addr):
    """Decoded text of a macro body, until its $0A return."""
    toks = T.decode(rom, addr, 0x80, 1, 4)
    return tokstr(rom, [t for t in toks if t[0] != 'ret'])


def tokstr(rom, toks):
    out = []
    for t in toks:
        k = t[0]
        if k == 'sb':
            out.append(T.idx_to_char(t[2]) or '')
        elif k == 'kanji':
            out.append(T.idx_to_char(t[3]) or '')
        elif k == 'ctrl':
            out.append(VAR.get(t[1], '[%02X]' % t[1]))
        elif k == 'phrase':
            out.append('«%02X»' % t[1] if t[1] not in DELIM
                       else expand(rom, rom.phrase_addr(t[1])))
        elif k == 'sub':
            a = rom.sub_addr(t[1], t[2])
            out.append('§%02X%02X' % (t[1], t[2]) if a is None else expand(rom, a))
    return ''.join(out)


def walk(rom, start, end):
    """Flat token walk: (token, offset, nbytes). No macro recursion."""
    i = start
    while i < end:
        if rom.data[i] == 0:
            yield ('end', i), i, 1
            return
        t = T.decode(rom, i, 1, maxdepth=0)[0]
        ln = {'ctrl': 1, 'sb': 1, 'phrase': 1, 'sub': 2, 'kanji': 2,
              'end': 1, 'limit': 0}[t[0]]
        yield t, i, ln
        if t[0] == 'end':
            return
        i += ln


def frame_list(rom, start, end):
    """[(offset, nbytes, delim_code, text, ctrl_bytes)] split at $A0-$AD."""
    frames, buf, off = [], [], start
    for t, p, ln in walk(rom, start, end):
        buf.append((t, p, ln))
        if t[0] == 'phrase' and t[1] in DELIM:
            toks = [x[0] for x in buf]
            frames.append((off, sum(x[2] for x in buf), t[1],
                           tokstr(rom, toks),
                           [x[0][1] for x in buf if x[0][0] == 'ctrl']))
            buf, off = [], p + ln
        elif t[0] == 'end':
            break
    if buf:
        toks = [x[0] for x in buf]
        frames.append((off, sum(x[2] for x in buf), None,
                       tokstr(rom, toks),
                       [x[0][1] for x in buf if x[0][0] == 'ctrl']))
    return frames


if __name__ == '__main__':
    start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x22F1AB
    end = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x22F944
    rom = T.Rom()
    fr = frame_list(rom, start, end)
    lines = ['region %06X..%06X = %d bytes, %d frames'
             % (start, end, end - start, len(fr))]
    for n, (off, nb, d, txt, ctrl) in enumerate(fr):
        lines.append('%3d @%06X %4dB %s %s | %s'
                     % (n, off, nb, 'end=%02X' % d if d is not None else 'tail',
                        ''.join(sorted(set('[%02X]' % c for c in ctrl))), txt))
    out = '\n'.join(lines)
    open('docs/research/prologue_frames.txt', 'w').write(out + '\n')
    print(out)
