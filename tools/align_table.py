"""Empirical code->char table extraction via J2E alignment (v3, opcode-based).

Core idea: ROM kana tokens project to a kana string RK; the J2E line projects
to SK (kanji + kana). difflib equal blocks anchor the two; unknown ROM tokens
(2-byte kanji codes, 1-byte kanji DTE) consume the non-kana SK chars inside
the corresponding gaps, yielding (code -> char) assignments.
"""
import os
import sys
import re
import glob
import difflib
import collections

sys.path.insert(0, os.path.dirname(__file__))
import romlib

data = romlib.load()

SINGLE = []
for k in range(0x60):
    e = int.from_bytes(data[0x18000 + k * 2: 0x18000 + k * 2 + 2], "big")
    SINGLE.append(e)


def c2ch(code):
    hi = ((code >> 8) + 0x92) & 0xFF
    lo = ((code & 0xFF) - 0x0B) & 0xFF
    try:
        return ((hi << 8) | lo).to_bytes(2, "big").decode("cp932")
    except Exception:
        return None


seq = ("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとど"
       "なにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑを")
TABLE = {0x4F: "ん", 0x44: "、", 0x47: "…", 0xA8: "。", 0x48: "「", 0x22: "「",
         0x23: "」", 0x20: "〈", 0x21: "〉"}
for i, ch in enumerate(seq):
    TABLE[0x50 + i] = ch
for k in range(0x0F):
    ch = c2ch(SINGLE[k])
    if ch:
        TABLE.setdefault(0x40 + k, ch)

KANA_RE = re.compile(r"[ぁ-んー]")
SKIP_CHARS = set("、。！？…〜♪♡※〆")

# token kinds: ('k', code, ch) known consume-kana-or-self; ('u', code, None)
# unknown consume-1; ('c', code, None) control skip.


def tokenize(off, nbytes):
    """J2E 日志确认的令牌语法:
      0x40-0x9F  单字节假名 (表 @0x18000)
      0xA0-0xBF  双字节 (前缀A0/B0 + 字节)
      0xC0-0xCF  说话人标记 (C0 + byte = person)
      0xD0-0xDF  单字节特殊码 (Dx uses x as the byte)
      0xE0-0xEF  控制跳转表
      0xF0-0xFF  双字节假名/汉字族 (F0AB=あ 已实测)
      0x00-0x3F  控制 (0x0A=换行 0x09=空格 0x14=wait)
    kind: 'k'=已知字符(消耗) 'u'=未知(消耗1字符) 'c'=控制(不消耗)
    """
    toks = []
    i = off
    end = off + nbytes
    while i < end:
        b = data[i]
        if 0x40 <= b <= 0x9F:
            ch = TABLE.get(b)
            toks.append(("k" if ch else "u", ("s", b), ch))
            i += 1
        elif 0xA0 <= b <= 0xBF or 0xF0 <= b <= 0xFF:
            code = (b << 8) | data[i + 1]
            ch = TABLE.get(("d", code))
            if ch is None and b == 0xF0:
                ch = c2ch(code)  # F0 族 = SJIS 82 行 +6E0B (实测)
            toks.append(("k" if ch else "u", ("d", code), ch))
            i += 2
        elif 0xC0 <= b <= 0xCF:
            # 说话人/控制: C0 xx = person
            toks.append(("c", ("c", (b << 8) | data[i + 1]), None))
            i += 2
        elif 0xD0 <= b <= 0xDF:
            toks.append(("u", ("s", b), None))
            i += 1
        elif 0xE0 <= b <= 0xEF:
            toks.append(("c", ("c", (b << 8) | data[i + 1]), None))
            i += 2
        elif b == 0x0A:
            toks.append(("c", ("c", 0x0A), "\n"))
            i += 1
        elif b == 0x09:
            toks.append(("c", ("c", 0x09), "　"))
            i += 1
        elif b in (0x14, 0xA8, 0x2E, 0x42, 0x23, 0x3A, 0x40, 0x48, 0x25,
                   0x17, 0x12, 0x13, 0x1F, 0x36, 0x0E, 0x0F, 0x2C, 0x4C,
                   0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08):
            ch = {0x14: "<wait>"}.get(b)
            toks.append(("c" if ch is None else "k", ("c", b), ch))
            i += 1
        else:
            toks.append(("u", ("c", b), None))
            i += 1
    return toks


def split_sents(tokens):
    lines = [[]]
    for t in tokens:
        lines[-1].append(t)
        if t[2] in ("。", "…", "！", "？"):
            lines.append([])
    return [l for l in lines if l]


def load_scene(path):
    txt = open(path, encoding="utf-8").read()
    txt = re.sub(r"<[^>]*>", "", txt).replace("●", "")
    lines = []
    for ln in re.split(r"[。\n]", txt):
        ln = re.sub(r"[\s　]", "", ln)
        if ln:
            lines.append(ln)
    return lines


def kana_proj(s):
    return "".join(c for c in s if KANA_RE.match(c))


def sk_proj(s):
    """J2E projection: kana (for matching) + kanji/unknown (for consumption);
    drop known punct."""
    return "".join(c for c in s if c not in SKIP_CHARS)


def align_sentence(rtoks, sl):
    """Try to align one ROM sentence to one J2E sentence.
    Returns list of (kind, code, char) assignments or None."""
    sk = "".join(c for c in sl if c not in SKIP_CHARS)
    # build rk and eqmap candidates
    rk = ""
    tokinfo = []  # (ti, rk_start) for kana tokens
    for ti, (kind, code, ch) in enumerate(rtoks):
        if kind == "k" and ch and KANA_RE.match(ch):
            tokinfo.append((ti, len(rk), len([c for c in ch if KANA_RE.match(c)])))
            rk += "".join(c for c in ch if KANA_RE.match(c))
    if len(rk) < 3:
        return None
    sm = difflib.SequenceMatcher(None, rk, sk)
    if sm.ratio() < 0.55:
        return None
    # eqmap: rk idx -> sk idx
    eqmap = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                eqmap[i1 + d] = j1 + d
    pairs = []
    prev_sk = 0
    unknown_run = []
    for ti, (kind, code, ch) in enumerate(rtoks):
        if ti in [t[0] for t in tokinfo] and kind == "k" and ch and KANA_RE.match(ch):
            # kana token: flush unknown run before its rk start
            rstart = None
            for t, rs, ln in tokinfo:
                if t == ti:
                    rstart = rs
                    break
            # consume sk gap between prev_sk and eqmap.get(rstart)
            tgt = eqmap.get(rstart, prev_sk)
            gap = [c for c in sk[prev_sk:tgt] if not KANA_RE.match(c)]
            for u in unknown_run:
                if gap:
                    pairs.append((u[0], u[1], gap.pop(0)))
                else:
                    return None
            unknown_run = []
            prev_sk = tgt + 1 if tgt in eqmap.values() else tgt
            # advance prev_sk properly: eqmap[rstart+len)-1 +1
            for t, rs, ln in tokinfo:
                if t == ti:
                    last = eqmap.get(rs + ln - 1)
                    if last is not None:
                        prev_sk = last + 1
                    break
        elif kind == "k":
            continue  # known punct: consumes its own known char (aligned already)
        else:
            unknown_run.append((kind, code))
    # flush tail
    gap = [c for c in sk[prev_sk:] if not KANA_RE.match(c)]
    for u in unknown_run:
        if gap:
            pairs.append((u[0], u[1], gap.pop(0)))
        else:
            return None
    return pairs


def align_region(region_off, region_len, scenes, assign, stats):
    tokens = tokenize(region_off, region_len)
    rom_sents = split_sents(tokens)
    scene_proj = [(sl, kana_proj(sl)) for sl in scenes]
    for rs in rom_sents:
        rk = "".join(ch for kind, code, ch in rs
                     if kind == "k" and ch and KANA_RE.match(ch))
        if len(rk) < 3:
            continue
        best, br = None, 0.0
        for sl, sk in scene_proj:
            if not sk:
                continue
            r = difflib.SequenceMatcher(None, rk, sk).ratio()
            if r > br:
                br, best = r, sl
        if best is None or br < 0.6:
            continue
        pairs = align_sentence(rs, best)
        if pairs is None:
            stats["walk_fail"] += 1
            continue
        stats["matched"] += 1
        for kind, code, ch in pairs:
            assign[(kind, code)][ch] += 1
            stats["pairs"] += 1
    stats["sents"] += len(rom_sents)


def main():
    scene_glob = sys.argv[1]
    regions = []
    for a in sys.argv[2:]:
        off, ln = a.split(":")
        regions.append((int(off, 16), int(ln, 16)))
    scenes = []
    for fp in sorted(glob.glob(scene_glob)):
        scenes.extend(load_scene(fp))
    print(f"scene sentences: {len(scenes)}")
    assign = collections.defaultdict(collections.Counter)
    stats = collections.Counter()
    for off, ln in regions:
        align_region(off, ln, scenes, assign, stats)
    print(f"stats: {dict(stats)}")
    rows = []
    for (kind, code), ctr in assign.items():
        ch, n = ctr.most_common(1)[0]
        rows.append((kind, code, ch, n, len(ctr)))
    rows.sort(key=lambda r: (r[0], r[1]))
    for kind, code, ch, n, alt in rows:
        kk = "1B" if kind == "s" else ("2B" if kind == "d" else "c")
        alts = f"  alts={'|'.join(c for c, _ in ctr.most_common(3))}" if alt > 1 else ""
        print(f"{kk} {code:04X} -> {ch} ({n}){alts}")


if __name__ == "__main__":
    main()
