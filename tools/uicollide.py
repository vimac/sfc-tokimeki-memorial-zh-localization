"""Compare one screen captured from two ROMs, cell by cell, and say why they differ.

The name-entry, file-select and status screens draw their labels straight out of the
shared 3510-record font array, so `allocate()`'s text-reachability scan does not cover
them: a build handed 干 the slot the keyboard's 漢字 tab reads, and the tab silently
became 干字.  tools/ui_refs.py keeps the slots the screens use out of the pool; this is
the gate that proves it, and `--pairs` runs it over a whole captured flow.

Both frames are decoded to font indices with the same exact-match reader (`ui_refs.cells`),
then each cell is classified:

  COLLISION  the Japanese screen reads index i, we hold i for a *text* character, and
             the label changed shape because of us -- the defect this gate exists for;
  in-place   we rewrote i on purpose: it is one of the stock slots the build redraws in
             WenQuanYi (the $E8 sub-text glyphs, the 漢字 tab), so the cell is meant to
             look different while keeping its character;
  data       the two frames put different indices in the cell, so the difference comes
             from bytes we re-pointed on purpose (preset names, the prompt boxes);
  art        a cell only one side decodes -- sprite/tile graphics or an animation.

usage: python3 tools/uicollide.py <jp.png> <zh.png> [patched_rom]
       python3 tools/uicollide.py --pairs <jp_dir> <zh_dir> [patched_rom]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import ui_refs as U

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOC = json.load(open(os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json')))
SRC = os.path.join(ROOT, 'rom_original_japanese.sfc')
ORIG = open(SRC, 'rb').read()


def allocation(rom_path):
    """What the written build claims: every slot whose record differs, split by why.

    The split comes from the allocation file, not from the diff: a slot listed under
    `fresh` backs a Chinese *character*, so the UI must never read it, while `inplace`
    and `at_stock` are the slots the build deliberately redraws in WenQuanYi.
    """
    patched = open(rom_path, 'rb').read()
    rewritten = {i for i in range(T.MAX_INDEX)
                 if ORIG[T.glyph_offset(i):T.glyph_offset(i) + 28]
                 != patched[T.glyph_offset(i):T.glyph_offset(i) + 28]}
    ours, fresh, stock = {}, set(), set()
    for ch, i in ALLOC.get('fresh', {}).items():
        ours[int(i, 16)] = ch
        fresh.add(int(i, 16))
    for table in ('inplace', 'at_stock'):
        for ch, i in ALLOC.get(table, {}).items():
            ours.setdefault(int(i, 16), ch)
            stock.add(int(i, 16))
    return patched, rewritten, ours, fresh, stock


def compare(jp_png, zh_png, rom_path, verbose=True):
    """Print every cell the two screens disagree about; return the collision count."""
    patched, REWRITTEN, ours, FRESH, STOCK = allocation(rom_path)
    to, wo = U.record_map(SRC)
    tp, wp = U.record_map(rom_path)
    a = U.cells(jp_png, to, wo)
    b = U.cells(zh_png, tp, wp)
    hurt = stock = same = data = art = 0
    rows = []
    for pos in sorted(set(a) | set(b), key=lambda p: (p[1], p[0])):
        ia, ib = set(a.get(pos, ())), set(b.get(pos, ()))
        if not ia or not ib:
            art += 1
            continue
        # Judge the cell by the slot the *Japanese* screen reads: if we hold that slot for
        # a text character the label changed shape because of us, while a slot in the
        # build's own in-place list was redrawn on purpose.  (A deliberate in-place glyph
        # then decodes on both its stock slot and its fresh twin, the bitmaps being equal.)
        rew = sorted(ia & REWRITTEN)
        bad = [i for i in rew if i in FRESH]
        made = [i for i in rew if i not in FRESH]
        if bad:
            hurt += 1
            rows.append('  x%3d y%3d COLLISION slot %s %s -> our text char %s' % (
                pos[0], pos[1], ' '.join('%03X' % i for i in bad),
                ' '.join(T.idx_to_char(i) or '?' for i in bad),
                ' '.join(ours[i] for i in bad)))
        elif made:
            stock += 1
            rows.append('  x%3d y%3d in-place  slot %s %s redrawn as %s' % (
                pos[0], pos[1], ' '.join('%03X' % i for i in made),
                ' '.join(T.idx_to_char(i) or '?' for i in made),
                ' '.join(ours[i] for i in made)))
        elif ia != ib:
            data += 1
            rows.append('  x%3d y%3d data      %s(%s) -> %s(%s)' % (
                pos[0], pos[1],
                ' '.join('%03X' % i for i in sorted(ia)),
                ' '.join(T.idx_to_char(i) or '?' for i in sorted(ia)),
                ' '.join('%03X' % i for i in sorted(ib)),
                ' '.join(ours.get(i) or T.idx_to_char(i) or '?' for i in sorted(ib))))
        else:
            same += 1
    if verbose:
        print('%s vs %s: %d cells decoded on the jp screen, %d on ours' % (
            os.path.basename(jp_png), os.path.basename(zh_png), len(a), len(b)))
        print('\n'.join(rows))
        print('  %d cells identical, %d re-pointed, %d undecodable on one side, '
              '%d in-place, %d collision(s)' % (same, data, art, stock, hurt))
    return hurt


def screens(d):
    """{step name: path} for a capture directory; name_entry.py prefixes each frame."""
    out = {}
    for n in sorted(os.listdir(d)):
        if n.endswith('.png'):
            out[n.split('_')[0]] = os.path.join(d, n)
    return out


if __name__ == '__main__':
    argv = sys.argv[1:]
    if argv and argv[0] == '--pairs':
        _, A, B = argv[:3]
        rom = argv[3] if len(argv) > 3 else os.path.join(ROOT, 'rom_prologue_zh.sfc')
        a, b = screens(A), screens(B)
        total = 0
        for k in sorted(set(a) & set(b), key=lambda s: (len(s), s)):
            if a[k] == b[k]:
                print('%-6s identical frame' % k)
                continue
            n = compare(a[k], b[k], rom)
            total += n
        only = set(a) ^ set(b)
        print('%d screens compared, %d collision(s)%s' % (
            len(set(a) & set(b)) - sum(1 for k in set(a) & set(b) if a[k] == b[k]),
            total, '; %d step(s) only on one side: %s' % (len(only), ' '.join(sorted(only)))
            if only else ''))
        sys.exit(1 if total else 0)
    JP, ZH = argv[0], argv[1]
    ROM = argv[2] if len(argv) > 2 else os.path.join(ROOT, 'rom_prologue_zh.sfc')
    sys.exit(1 if compare(JP, ZH, ROM) else 0)
