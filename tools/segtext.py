"""Prove: is a punctuation seam on screen ours, or is it the script's own step boundary?

`render_boxes.py` answers "what does a box show", and it must -- that is the
acceptance gate.  But it throws away two things this question needs: which *script
step* (a `blockN_work.tsv` row, the span the pointer grid freezes) each character came
from, and every name/pool insertion it skips.  So a box label like 「、、送我礼物了。」 or
「那个…，同学。」 reads as a text bug when it is really ⟦E803⟧⟦E804⟧ drawn with the pools
left out, and 「。」 doubled looks Chinese when the same dump of the *Japanese* block does it
too (block 8 step 3: 「明日から何をしようかな。。」).

This walks the same bytes through the same `Codec.walk`, one step at a time, and keeps
the identity of every atom.  Three numbers come out per class:

* INSIDE  -- the seam sits in one step's own text.  That is authored, and only a
  wording edit fixes it (the 「啊，|。」 family: run 1 ends in a comma, run 2 is the
  step's own 「。」, so the screen shows 「，。」).
* JOIN    -- the seam appears only where step k meets step k+1 inside one box, i.e.
  the engine's own terminator punctuation colliding with the next step's first
  character.  Fix is the fold choice, not the sentence.
* KEPT    -- characters a name/pool macro would draw.  Listed so nobody counts them
  as missing text again.

usage: python3 tools/segtext.py [rom] [--blocks 0,8] [--json out.json]   # bare --blocks = every block
       python3 tools/segtext.py [rom] --dict      # dictionary calls + glossary coverage
"""
import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_zh as B

SEAM = re.compile(r'，。|。，|、。|。。|…，|？。|！。|，，|、，')
CJK = re.compile(r'[一-鿿]')
ROM = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else B.OUT_ROM
# --blocks with a list narrows the sweep to those blocks; bare --blocks is the whole
# corpus, which is what the acceptance gate asks for.
_HAS = '--blocks' in sys.argv
_ARG = sys.argv.index('--blocks') + 1 if _HAS else 1
ONLY = ([int(x) for x in sys.argv[_ARG].split(',')]
        if _HAS and _ARG < len(sys.argv) and not sys.argv[_ARG].startswith('-') else [])
DICT = '--dict' in sys.argv


def codec(path):
    """A reader whose span tables come from the source ROM, like every other gate.

    Records for the name and place pools live inside the patched image's sub-text
    span table, so re-deriving the table from the image we wrote shifts spans
    (build_zh.patched_codec documents the mangle).
    """
    rom = T.Rom(path)
    code = B.Codec(rom)
    if path != B.SRC_ROM:
        ref = B.Codec(B.T.Rom(B.SRC_ROM))
        code.ph_off, code.ph_next = ref.ph_off, ref.ph_next
        code.sub_off, code.sub_next = ref.sub_off, ref.sub_next
        # Same names the engine draws with: half the slots in this image are characters
        # JIS never had, and `parse_body` calls a body holding one "not plain text", so
        # without them the walk files that call site as a variable and --dict loses the
        # whole dictionary entry (批次 AL: e97d 「（好像没留下什么」 dropped over its 么).
        code.names = slot_chars(code, path)
    return rom, code


def slot_chars(code, path):
    """Glyph index -> the character that slot actually paints on this image.

    Empty for the source ROM: there every slot still holds its own JIS glyph, so
    `idx_to_char` is already the truth and applying our allocation to it would
    rewrite Japanese punctuation into Chinese and ruin the baseline comparison.
    """
    if path == B.SRC_ROM:
        return {}
    m = {}
    p = os.path.join(B.ROOT, 'docs/research/glyph_alloc.json')
    alloc = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    for kind in ('fresh', 'inplace'):
        for ch, idx in alloc.get(kind, {}).items():
            m[int(idx, 16)] = ch
    return m


def render_atoms(code, painted, atoms):
    """atoms -> (text, kept) where `kept` marks what a pool/name macro stands for.

    The marker is written into `text` at its own position too: 「我，〔姓〕〔名〕。」 has
    no seam in it, and a reader that drops the insertion point invents one (「我，。」).
    """
    out, kept = [], []
    for a in atoms:
        k = a['k']
        if k == 'g':
            r = a['raw']
            idx = code.sb[r[0]] if len(r) == 1 else ((r[0] << 8) | r[1]) & 0x0FFF
            out.append(painted.get(idx) or T.idx_to_char(idx) or '?')
        elif k == 'm':
            for tag, v in a['toks']:
                if tag == 'g':
                    out.append(painted.get(v) or T.idx_to_char(v) or '?')
                elif tag == 'n':
                    kept.append('⟦%s⟧' % a['code'])
                    out.append(B.MARK.get(v, ''))
        elif k == 'v':
            kept.append(a['ch'])
            out.append(a['ch'])
        elif k == 'n':
            kept.append(a['ch'])
            out.append(a['ch'])
        elif k == 'c':
            b = a['raw'][0]
            if b == 0x14:
                out.append('\n')
            elif b in (0x0C, 0x0A):
                out.append('\x00')
    return ''.join(out), ''.join(kept)


def steps(rom, code, painted, blk, cov):
    """The block's translated prefix -> [(step, off, span, text, pool markers)].

    The whole range is walked once and the atoms are then handed to the step that
    contains them: walking a step in isolation can start a 2-byte glyph pair on the
    step's last byte, and `walk` asserts a byte-exact reconstruction of its range.
    """
    rows = [l.rstrip('\n').split('\t')
            for l in open(os.path.join(B.ROOT, 'docs/research',
                                       'block%d_work.tsv' % blk), encoding='utf-8')][1:]
    rows = [(int(r[0]), int(r[1], 16), int(r[2])) for r in rows
            if r[0].strip().isdigit() and int(r[0]) < cov]
    per = collections.defaultdict(list)
    pos = rows[0][1]
    for a in code.walk(rows[0][1], rows[-1][1] + rows[-1][2]):
        for n, off, span in rows:
            if off <= pos < off + span:
                per[n].append(a)
                break
        pos += len(a['raw'])
    return [(n, off, span) + render_atoms(code, painted, per[n]) + (per[n],)
            for n, off, span in rows]


def dict_audit(rom, code, painted, jobs):
    """Every dictionary entry the Chinese steps call: body, capacity, who owns it."""
    gloss = B.phrase_glossary()
    calls = collections.defaultdict(lambda: {'refs': 0, 'steps': set(), 'jp': ''})
    for blk, rows in jobs:
        for n, off, span, text, kept, atoms in rows:
            for a in atoms:
                if a['k'] != 'm':
                    continue
                e = calls[a['code']]
                e['refs'] += 1
                e['steps'].add((blk, n))
                e['jp'] = e['jp'] or ''.join(
                    (painted.get(v) or T.idx_to_char(v) or '?')
                    for tag, v in a['toks'] if tag == 'g')
    rows = []
    for key, e in sorted(calls.items(), key=lambda kv: (-kv[1]['refs'], kv[0])):
        codes = [int(x, 16) for x in (key[i:i + 2] for i in range(0, len(key), 2))]
        lo, hi = (code.phrase_span(codes[0]) if len(codes) == 1
                  else code.sub_span(*codes))
        raw = code.rom.data[lo:hi]
        body = raw[:raw.index(0x0A) + 1] if 0x0A in raw else raw
        rows.append({'key': key, 'refs': e['refs'], 'steps': len(e['steps']),
                     'cap': hi - lo, 'body': body.hex(' '),
                     'shown': e['jp'], 'glossary': gloss.get(key.lower(), '')})
    return rows


def main():
    rom, code = codec(ROM)
    painted = slot_chars(code, ROM)
    jobs, tot = [], collections.Counter()
    seam_kinds = collections.defaultdict(list)
    for blk, _zf, _hi in B.BLOCKS:
        if ONLY and blk not in ONLY:
            continue
        p = os.path.join(B.ROOT, 'docs/research', 'block%d_enc.json' % blk)
        if not os.path.exists(p):
            continue
        cov = json.load(open(p, encoding='utf-8'))['cov']
        rs = steps(rom, code, painted, blk, cov)
        jobs.append((blk, rs))
        for n, off, span, text, kept, _at in rs:
            if kept:
                tot['POOL-steps'] += 1
            for m in SEAM.finditer(text):
                tot['INSIDE'] += 1
                if len(seam_kinds['INSIDE']) < 12:
                    seam_kinds['INSIDE'].append('b%d#%d %s' % (blk, n, text))
        # A join only matters while the box is still open: $0C/$0A became NUL in the
        # step's own text, and past one of those the next step draws a new frame.
        for (n1, _o, _s, t1, k1, _a1), (n2, _o2, _s2, t2, k2, _a2) in zip(rs, rs[1:]):
            if '\x00' in t1:
                continue
            join = t1.rstrip('\n\x00')[-1:] + t2.lstrip('\n\x00')[:1]
            if SEAM.fullmatch(join):
                tot['JOIN'] += 1
                if len(seam_kinds['JOIN']) < 12:
                    seam_kinds['JOIN'].append('b%d#%d+%d %s|%s' % (blk, n1, n2, t1, t2))
    tot['steps'] = sum(len(r) for _b, r in jobs)
    print('%s: %d translated steps in %d blocks' %
          (os.path.basename(ROM), tot['steps'], len(jobs)))
    if DICT:
        rows = dict_audit(rom, code, painted, jobs)
        miss = [r for r in rows if not r['glossary']]
        jp = [r for r in rows if re.search(r'[ぁ-んァ-ヶ]', r['shown'])]
        print('%d distinct dictionary entries over %d calls; %d have no glossary row, '
              '%d still draw kana' % (len(rows), sum(r['refs'] for r in rows),
                                      len(miss), len(jp)))
        for r in miss[:25]:
            print('  no glossary  %s x%-5d cap%-4d %s' % (r['key'], r['refs'], r['cap'],
                                                          r['shown']))
        for r in jp[:25]:
            print('  still kana   %s x%-5d cap%-4d %s -> %s'
                  % (r['key'], r['refs'], r['cap'], r['shown'], r['glossary']))
        if '--json' in sys.argv:
            json.dump(rows, open(sys.argv[sys.argv.index('--json') + 1], 'w'),
                      ensure_ascii=False, indent=1)
    else:
        for k in ('INSIDE', 'JOIN', 'POOL-steps'):
            print('%s: %d' % (k, tot[k]))
            for s in seam_kinds[k]:
                print('   ', s)


main()
