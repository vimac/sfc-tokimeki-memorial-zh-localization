"""Rigorous validation of the cracked text encoding.

Method: extract phrases from the J2E scripts (independent ground truth),
encode them under several candidate transforms, and count exact hits in the
ROM. If the cracked transform is correct it must hit far more often than
control transforms; a wrong transform hits ~0.

Controls:
  A) raw Shift-JIS (no remap)          - what naive decoders would try
  B) remap with wrong lo offset (+0x00 instead of +0x0B)
  C) remap with wrong page offset (+0x6E00 only, no lo offset)
  D) the cracked transform (+0x6E0B)   - our claim
"""
import os
import re
import sys
import glob
import random

sys.path.insert(0, os.path.dirname(__file__))
import romlib

data = romlib.load()

KANA_OK = re.compile(r'^[ぁ-んァ-ヶー一-鿆々〆〤]+$')  # kana + kanji only


def load_phrases():
    """Extract kana/kanji-only substrings (4-12 chars) from J2E scripts."""
    random.seed(42)
    phrases = set()
    files = glob.glob(os.path.join(os.path.dirname(__file__), "..",
                                   "out", "text", "japanese_utf8", "Toksc__*.EUC"))
    for fp in files:
        try:
            txt = open(fp, encoding="utf-8").read()
        except Exception:
            continue
        txt = re.sub(r'<[^>]*>', '', txt)          # strip control markers
        txt = re.sub(r'[□♪●…†]', '', txt)
        for chunk in re.split(r'[\s　。、！？\n「」『』（）～…]', txt):
            chunk = chunk.strip()
            if 4 <= len(chunk) <= 12 and KANA_OK.match(chunk):
                phrases.add(chunk)
    return sorted(phrases)


def enc_transform(text, page_add, lo_add):
    out = bytearray()
    for ch in text:
        try:
            b = ch.encode("cp932")
        except Exception:
            return None
        if len(b) != 2:
            return None
        hi = ((b[0] + page_add) & 0xFF)
        lo = ((b[1] + lo_add) & 0xFF)
        out += bytes([hi, lo])
    return bytes(out)


def count_hits(pat):
    n = 0
    s = 0
    while True:
        i = data.find(pat, s)
        if i < 0:
            break
        n += 1
        s = i + 1
        if n >= 50:
            break
    return n


def main():
    phrases = load_phrases()
    print(f"test phrases from J2E scripts: {len(phrases)}")
    sample = random.sample(phrases, min(400, len(phrases)))

    variants = [
        ("A raw SJIS (no remap)      ", 0x00, 0x00),
        ("B wrong lo (+0x00)         ", 0x6E, 0x00),
        ("C wrong hi only (+0x6E00)  ", 0x00, 0x0B),
        ("D cracked (+0x6E0B)        ", 0x6E, 0x0B),
    ]
    results = {name: 0 for name, _, _ in variants}
    tested = 0
    for ph in sample:
        for name, pa, la in variants:
            pat = enc_transform(ph, pa, la)
            if pat is None:
                continue
            if name.startswith("D") and tested < len(sample):
                pass
            if count_hits(pat) > 0:
                results[name] += 1
        tested += 1
    print(f"phrases tested: {tested}")
    print()
    for name, _, _ in variants:
        n = results[name]
        bar = "#" * int(n / max(1, tested) * 50)
        print(f"{name} {n:4d}/{tested} phrases found in ROM  {bar}")

    # list some found phrases under D with hit locations
    print()
    print("examples found with cracked transform:")
    shown = 0
    for ph in sample:
        pat = enc_transform(ph, 0x6E, 0x0B)
        if pat is None:
            continue
        i = data.find(pat)
        if i >= 0:
            print(f"  「{ph}」 @ 0x{i:06X}")
            shown += 1
            if shown >= 10:
                break


if __name__ == "__main__":
    main()
