import sys, collections
d = open(sys.argv[1], 'rb').read()
assert d[:5] == b'PATCH'
recs, i, ext = [], 0, {}
while i < len(d):
    if d[i:i+5] == b'EOF':
        break
    o = int.from_bytes(d[i:i+3], 'big'); n = int.from_bytes(d[i+3:i+5], 'big')
    i += 5
    if n == 0:
        n = int.from_bytes(d[i:i+3], 'big'); i += 3
        o = int.from_bytes(d[i:i+3], 'big'); i += 3
        ext[o] = d[i:i+n]; i += n
        recs.append((o, n, b'<RLE->%04X' % (ext[o])))
    else:
        recs.append((o, n, d[i:i+n])); i += n
print('records:', len(recs), 'rle ext:', len(ext))
def bucket(o): return hex(o >> 15)
cnt = collections.Counter(o >> 15 for o, n, b in recs)
for k in sorted(cnt): print('  0x%04X0000 region: %4d recs' % (k, cnt[k]))
# print records sorted, grouped, only offsets
out = sorted(set((o, n) for o, n, b in recs))
prev = None
for o, n in out:
    if prev is not None and o - prev > 0x40: print(' ---')
    print('%06X %4d' % (o, n))
    prev = o + n
