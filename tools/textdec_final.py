"""FINAL text decoder — Tokimeki Memorial SFC.

Complete model (verified by alignment + prompt text):
  - 1-byte codes 0x40-0x9F: kana via gojuon table @0x18000
  - 2-byte codes: SJIS = code - rowdelta[page], per-page linear mapping
    Known pages: 82:+6E0B  83:+6DBD  8A:+689E  8B:+685A  8C:+6816  8D:+67D3
                 8E:+678E  8F:+674B  90:+6706  91:+66C3  92:+667E  93:+663A
                 95:+65B3  96:+656E  97:+652A  98:+64E7  (+ interpolation)
  - 0x0A newline, 0x09 space, 0x14 wait, other 0x0B-0x3F = controls
  - 0xA0-0xE7: word codes -> strings @0x1CCB33+ via ptr table @0x1CCAA3
"""
import os
import sys
import struct
import collections

sys.path.insert(0, os.path.dirname(__file__))
import romlib

data = romlib.load()

# --- per-row deltas (verified by 清川/デマ/話 alignment + name prompt) ---
ROWDELTA = {
    0x81: 0x72D8, 0x82: 0x7082, 0x83: 0x6DBD,
    0x8A: 0x689E, 0x8B: 0x685A, 0x8C: 0x6816, 0x8D: 0x67D3,
    0x8E: 0x678E, 0x8F: 0x674B, 0x90: 0x6706, 0x91: 0x66C3,
    0x92: 0x667E, 0x93: 0x663A, 0x95: 0x65B3, 0x96: 0x656E,
    0x97: 0x652A, 0x98: 0x64E7,
}

# --- 1-byte kana table ---
seq = ("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとど"
       "なにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑを")
T1 = {0x4F: "ん", 0x44: "、", 0x47: "…", 0xA8: "。"}
for i, c in enumerate(seq):
    T1[0x50 + i] = c

# --- word table @0x1CCAA3 ---
WPT = 0x1CCAA3
WPTRS = [struct.unpack("<H", data[WPT + i * 2: WPT + i * 2 + 2])[0] for i in range(0x48)]


def sj_char(sjis):
    try:
        return sjis.to_bytes(2, "big").decode("cp932")
    except Exception:
        return None


def decode_2byte(code):
    hi = code >> 8
    if hi in ROWDELTA:
        sj = (code - ROWDELTA[hi]) & 0xFFFF
        ch = sj_char(sj)
        if ch:
            return ch
    # fallback: try -6E0B
    ch = sj_char((code - 0x6E0B) & 0xFFFF)
    return ch


def decode_word(code):
    """A0-E7 word code -> expanded string."""
    idx = code - 0xA0
    if idx >= len(WPTRS):
        return f"⟨W{code:02X}⟩"
    off = 0x1C8000 + (WPTRS[idx] - 0x8000)
    out = []
    for _ in range(40):
        b = data[off]
        if b == 0x00:
            break
        if 0x40 <= b <= 0x9F:
            out.append(T1.get(b, "?")); off += 1
        elif 0xF0 <= b <= 0xFF:
            code2 = (b << 8) | data[off + 1]
            out.append(decode_2byte(code2) or "?"); off += 2
        else:
            off += 1
    return "".join(out)


def decode_text(off, nbytes):
    out = []
    i = off
    end = off + nbytes
    while i < end:
        b = data[i]
        if b == 0x0A:
            out.append("\n"); i += 1; continue
        if b == 0x09:
            out.append("　"); i += 1; continue
        if 0x40 <= b <= 0x9F:
            out.append(T1.get(b, f"⟦{b:02X}⟧")); i += 1; continue
        if 0xA0 <= b <= 0xE7:
            # word code: expand
            idx = b - 0xA0
            if idx < len(WPTRS):
                ptr = WPTRS[idx]
                woff = 0x1C8000 + (ptr - 0x8000)
                wtext = []
                for _ in range(30):
                    wb = data[woff]
                    if wb == 0x00: break
                    if 0x40 <= wb <= 0x9F:
                        wtext.append(T1.get(wb, "?")); woff += 1
                    elif wb >= 0xF0:
                        c2 = (wb << 8) | data[woff + 1]
                        wtext.append(decode_2byte(c2) or "?"); woff += 2
                    else:
                        woff += 1
                out.append("".join(wtext))
            else:
                out.append(f"⟨W{b:02X}⟩")
            i += 2
            continue
        if 0xF0 <= b <= 0xFF:
            code = (b << 8) | data[i + 1]
            ch = decode_2byte(code)
            out.append(ch if ch else f"⟦{code:04X}⟧")
            i += 2; continue
        if b == 0x14:
            out.append("<wait>")
        elif b == 0x2E:
            out.append("\n◆ ")
        elif b == 0x42:
            out.append("\n── ")
        elif b == 0x23:
            out.append("」")
        elif b == 0x22:
            out.append("「")
        elif b == 0x25:
            out.append("…")
        else:
            out.append(f"⟦{b:02X}⟧")
        i += 1
    return "".join(out)


if __name__ == "__main__":
    regions = [
        (0x0D7000, 0x1000, "電話会話"),
        (0x1CC600, 0x800, "TOKSC65 清川プール"),
        (0x1D0000, 0x2000, "bank3 テキスト"),
        (0x1DB400, 0x1000, "シーン"),
        (0x1E3400, 0x2000, "テキスト"),
        (0x2096C0, 0x400, "block 30 near"),
        (0x20A300, 0x400, "block 30 Nijino"),
        (0x035000, 0x800, "bank06"),
    ]
    outdir = os.path.join(os.path.dirname(__file__), "..", "out", "text", "rom_final")
    os.makedirs(outdir, exist_ok=True)
    for off, ln, name in regions:
        txt = decode_text(off, ln)
        fn = os.path.join(outdir, f"{off:06X}.txt")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n{txt}")
        print(f"\n=== 0x{off:06X} {name} ===")
        print(txt[:500])
        print("...")
