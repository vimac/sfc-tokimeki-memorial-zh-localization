"""How many glyph slots does the *shipped* (patched) ROM still reference?

allocate() reserves every slot reachable from the ORIGINAL text/name blocks, so slots
that only the Japanese bodies we overwrote used stay reserved.  Re-scan the patched
image: the difference is capacity the patch has already earned back.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import tmtext as T
import build_prologue as BP

orig = BP.Codec(T.Rom(BP.SRC_ROM))
patched = BP.Codec(T.Rom(BP.OUT_ROM))

u_o = BP.used_slots(orig)
u_p = BP.used_slots(patched)
kanji = set(range(T.JIS_KANJI, T.MAX_INDEX))
pool_o = kanji - u_o
pool_p = kanji - u_p
print('used  original %d  patched %d' % (len(u_o & kanji), len(u_p & kanji)))
print('pool  original %d  patched %d   (gain %d)' % (len(pool_o), len(pool_p),
                                                      len(pool_p) - len(pool_o)))
reclaim = sorted(pool_p - pool_o)
print('reclaimable slots now unreferenced: %d' % len(reclaim))
gone = sorted((u_o & kanji) - u_p)
print('slots freed by our own translations: %d' % len(gone))
# how many of the freed ones are still claimed by our Chinese?
alloc_json = 'glyph_alloc.json'
if os.path.exists(alloc_json):
    a = json.load(open(alloc_json))
    fresh = set(int(k, 16) for k in a.get('fresh', {})) if isinstance(a.get('fresh'), dict) else set()
    print('alloc keys:', list(a)[:8])
chars = [T.idx_to_char(i) for i in gone]
print('first 60 freed chars:', ''.join(c or '?' for c in chars[:60]))
print('freed pages:', {i // T.PAGE_SLOTS for i in gone})
