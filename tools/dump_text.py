"""Full ROM text dumper for Tokimeki Memorial SFC.

Encoding (fully cracked):
  - 1-byte codes 0x40-0x9F: DTE shorthand, defined by the table at file
    0x18000 (2 bytes per entry, big-endian = the equivalent 2-byte code).
    Covers symbols, ん and all kana (with dakuten), incl. custom slots.
  - 2-byte codes (hi, lo): Shift-JIS with page remap
        SJIS_hi = (hi + 0x92) & 0xFF,  SJIS_lo = (lo - 0x0B) & 0xFF
    F0 page = SJIS 82 (digits/letters/hiragana), F1..FF = 83..91,
    00..0D = wrapped 92..9F (JIS L2 kanji), E0-EA rows would wrap to
    72..7C but are unused by this game.
  - Bytes 0x0E-0x3F: control codes (0x0A newline, 0x09 fullwidth space,
    0x14 wait, ...).

Scans every bank for text-like regions and writes decoded dumps to
out/text/rom_dump/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import romlib

data = romlib.load()

# ---- 1-byte code table (0x18000, 96 entries, BE 2-byte codes) ----
SINGLE = []
for k in range(0x60):
    e = int.from_bytes(data[0x18000 + k * 2: 0x18000 + k * 2 + 2], "big")
    SINGLE.append(e)


def code2char(code):
    hi = ((code >> 8) + 0x92) & 0xFF
    lo = ((code & 0xFF) - 0x0B) & 0xFF
    try:
        return ((hi << 8) | lo).to_bytes(2, "big").decode("cp932")
    except Exception:
        return None


CTRL = {0x09: "　", 0x0A: "\n", 0x0B: "<c0B>", 0x0C: "<c0C>", 0x0D: "<c0D>",
        0x0E: "<c0E>", 0x0F: "<c0F>", 0x14: "<wait>", 0x17: "<c17>",
        0x18: "<c18>", 0x19: "<c19>", 0x1A: "<c1A>", 0x1B: "<c1B>",
        0x1C: "<c1C>", 0x1D: "<c1D>", 0x1E: "<c1E>", 0x1F: "<c1F>",
        0x25: "<c25>", 0x2E: "<c2E>", 0x34: "…", 0x35: "…", 0x36: "<c36>",
        0x39: "<c39>", 0x3A: "<c3A>", 0x3B: "<c3B>", 0x3D: "<c3D>"}


def decode(off, nbytes):
    out = []
    i = off
    end = off + nbytes
    while i < end:
        b = data[i]
        if 0x40 <= b <= 0x9F:
            ch = code2char(SINGLE[b - 0x40])
            out.append(ch if ch else f"<{b:02X}>")
            i += 1
        elif b <= 0x0D or b >= 0xF0:
            if i + 1 >= end:
                break
            code = (b << 8) | data[i + 1]
            if b == 0xF0 and data[i + 1] < 0x40:
                out.append(CTRL.get(data[i + 1], f"[F0{data[i+1]:02X}]"))
            else:
                ch = code2char(code)
                out.append(ch if ch else f"[{code:04X}]")
            i += 2
        else:
            out.append(CTRL.get(b, f"<{b:02X}>"))
            i += 1
    return "".join(out)


def text_score(off, window=0x80):
    """Heuristic: ratio of decodable-to-valid tokens in a window."""
    ok = total = 0
    i = off
    while i < off + window and i < len(data) - 1:
        b = data[i]
        if 0x40 <= b <= 0x9F:
            ok += 1; total += 1; i += 1
        elif b <= 0x0D or b >= 0xF0:
            code = (b << 8) | data[i + 1]
            if code2char(code): ok += 1
            total += 1; i += 2
        elif b in CTRL:
            ok += 1; total += 1; i += 1
        else:
            total += 1; i += 1
    return ok / max(total, 1)


def main():
    outdir = os.path.join(os.path.dirname(__file__), "..", "out", "text", "rom_dump")
    os.makedirs(outdir, exist_ok=True)
    # scan banks in 0x400-byte steps for text-like windows
    regions = []
    off = 0x8000
    step = 0x400
    inreg = False
    while off < len(data) - step:
        s = text_score(off)
        if s >= 0.75 and not inreg:
            start = off; inreg = True
        elif s < 0.6 and inreg:
            if off - start >= 0x200:
                regions.append((start, off))
            inreg = False
        off += step
    print(f"text-like regions found: {len(regions)}")
    index = []
    for start, end in regions:
        # trim to 0x100 granularity
        txt = decode(start, end - start)
        # quality metric: fraction of non-placeholder chars
        ph = sum(1 for c in txt if c in "<[")
        if len(txt) - ph < 40:
            continue
        fn = f"{start:06X}.txt"
        with open(os.path.join(outdir, fn), "w", encoding="utf-8") as f:
            f.write(txt)
        index.append((start, end, len(txt), ph))
        print(f"  0x{start:06X}-0x{end:06X}  {len(txt)} chars ({ph} placeholders)")
    with open(os.path.join(outdir, "index.txt"), "w") as f:
        for s, e, n, ph in index:
            f.write(f"0x{s:06X}-0x{e:06X} chars={n} placeholders={ph}\n")
    # also dump the 1-byte table as table.txt (code -> char)
    with open(os.path.join(os.path.dirname(__file__), "..", "out", "table.txt"), "w", encoding="utf-8") as f:
        f.write("# 1-byte DTE codes (0x40-0x9F) -> character\n")
        for k, e in enumerate(SINGLE):
            ch = code2char(e)
            f.write(f"{0x40+k:02X} = {ch if ch else 'Ø'}    (2byte {e:04X})\n")
        f.write("\n# 2-byte codes: SJIS = (hi+0x92, lo-0x0B) per byte\n")
    print("done")


if __name__ == "__main__":
    main()
