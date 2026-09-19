"""Human-cadence prologue walk: one A press per step, record every distinct page.

boxpair2.mash() sends 8 presses per sample to stay responsive on long pages, and
that is fast enough to be swallowed by the delay codes, so a mid-parse resume
looks like a pointer defect.  This walks the dialog the way a player does -- one
press, then enough settle time for the box to finish drawing -- and records the
frame hash so a repeated page (the endless-loop symptom) shows up as a streak.

usage: python3 tools/prologue_play.py <rom> [presses]
"""
import sys, os, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import tmtext as T
import screen_ocr as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM = sys.argv[1] if len(sys.argv) > 1 else 'rom_prologue_zh.sfc'
NP = int(sys.argv[2]) if len(sys.argv) > 2 else 90
ENVDIR = os.path.expanduser(
    '~/.local/lib/python3.14/site-packages/stable_retro/data/stable/TokimekiSFC-Snes-v0')
import slot                                                # noqa: E402
slot.use(ROM)
from play import env, step, load_state, press, save_state  # noqa: E402

FM, LABELS = S.font_map(ROM, os.path.join(ROOT, 'docs/research/glyph_alloc.json'))
OUT = '/tmp/play/pp_' + os.path.splitext(os.path.basename(ROM))[0]
os.makedirs(OUT, exist_ok=True)
seen_at = {}                                          # (pointer, text) -> how often shown


def name(idx):
    return LABELS.get(idx) or T.idx_to_char(idx) or ''


def page(im):
    rows = []
    for y in (161, 177, 193):
        # Cell 3 carries the stock box-open 「, or a line-initial （ that hangs left over it;
        # the text itself starts in cell 4.  Read from cell 3 so both are visible.
        cells = S.cells(im, 111, y, x1=495)[0]
        rows.append(''.join(name(FM[p][0]) if p and FM.get(p) else ' '
                            for p in cells))
    return rows


def sample(k, phase, out, state):
    """Record the frame if it differs from the last one we saw."""
    im = S.Image.fromarray(env.get_screen())
    h = hashlib.md5(np.asarray(im).tobytes()).hexdigest()[:8]
    r = bytes(env.get_ram())
    d24 = sum(r[0xD24 + i] << (8 * i) for i in range(3))
    streak, prev = state
    streak = streak + 1 if h == prev[0] else 1
    prev[0], prev[1] = h, max(prev[1], streak)
    if streak == 1:
        rows = page(im)
        text = ' // '.join(x.rstrip() for x in rows)
        im.save('%s/%03d%s_%s.png' % (OUT, k, phase, h))
        print('%3d%-2s %s d24=%06X | %s' % (k, phase, h, d24, text), flush=True)
        seen_at[(d24, text)] = seen_at.get((d24, text), 0) + 1
        out.append({'press': k, 'phase': phase, 'd24': '%06X' % d24, 'rows': rows})
    return streak


def cursor():
    """Centre of the pink arrow the game drives as a pointer, or None if off-screen.

    It is the only magenta thing these scenes draw, so a colour test locates it
    without reading sprite RAM.
    """
    a = np.asarray(S.Image.fromarray(env.get_screen()).convert('RGB')).astype(int)
    m = (a[..., 0] > 170) & (a[..., 2] > 120) & (a[..., 1] < 110)
    ys, xs = np.nonzero(m)
    return (int(xs.mean()), int(ys.mean())) if len(xs) else None


def click(x, y, btn='A'):
    """Move the arrow onto (x, y) and press `btn`.

    The new-game blackboard is not a D-pad menu: the options answer a mouse-style
    hit test, so A does nothing until the arrow sits on the text.  The arrow travels
    about 2 px per frame it is held.
    """
    for _ in range(16):
        c = cursor()
        if c is None:
            return False                       # no arrow: the screen already moved on
        if abs(c[0] - x) <= 6 and abs(c[1] - y) <= 4:
            break
        if abs(c[0] - x) > 6:
            press('RIGHT' if x > c[0] else 'LEFT', n=max(3, abs(c[0] - x) // 2), settle=60)
        if abs(c[1] - y) > 4:
            press('DOWN' if y > c[1] else 'UP', n=max(3, abs(c[1] - y) // 2), settle=60)
    press(btn, n=8, settle=400)
    return True


OPTION1 = (110, 165)             # '从序章开始' / プロローグからはじめる
OPTION2 = (110, 181)             # '跳过序章' / プロローグは見ない


def enter():
    """Walk in from a cold boot and answer the new-game blackboard.

    Needed because a resumed save state still holds the *previous* ROM's VRAM, so box 0
    never redraws and looks like the old translation.
    """
    step(2600)
    press('START')
    press('START')
    press('A', 150)
    press('A', 200)
    for _ in range(16):
        press('START')
    press('START', 200)
    for _ in range(4):
        press('DOWN', 55)
    press('UP', 60)
    press('UP', 60)
    press('A', 200)
    return click(*OPTION1)


def main():
    stem = os.path.splitext(os.path.basename(ROM))[0]
    for f in os.listdir(OUT):                        # frames are keyed by press number
        if f.endswith('.png'):
            os.remove(os.path.join(OUT, f))
    if '--boot' in sys.argv:
        print('blackboard answered: %s' % ('yes' if enter() else 'no arrow'))
        save_state('trace_entered_%s' % stem)
    else:
        load_state('trace_entered_%s' % stem)
    step(60)
    out, state = [], [0, [None, 0]]
    for k in range(NP):
        sample(k, '', out, state)
        press('A', settle=0, n=6)
        for _ in range(12):                          # the box draws over ~480 frames
            step(40)
            sample(k, 'b', out, state)
    # A dead loop is the same (pointer, text) recurring; the raw frame hash flickers with
    # the advance arrow and partial draws, so it is the wrong thing to count.
    rep = max(seen_at.values()) if seen_at else 0
    print('%d presses, %d distinct (pointer, text) pages, most-seen %d time(s)'
          % (NP, len(seen_at), rep))
    json.dump(out, open('%s/pages.json' % OUT, 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
