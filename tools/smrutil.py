"""What a .srm save slot says: date, attributes, affinity, who has been met and given a
phone number, and every appointment in the diary.

Read-only -- it never writes a save, so a report can be taken before and after an edit
without this tool being the thing that changed the file.

Self-contained: the heroine table is a literal here, and names resolve against the ROM
(the stock index->character band plus the two kana keycap pages read out of it), so the
script travels with nothing but the saves and the image they were written by.

It also says which build the ROM is: on the original image the preset-name pool and the
opening screen's text block decode to hundreds of hiragana, on a localized one to none.
That verdict is what selects the keycap reading, and a save whose filename disagrees with
the ROM it is being read against gets a warning -- names are the only field that depends
on this, everything else is the same bytes on both builds.

Only fields whose identity is established get a name here; the ones that move between
saves but mean nothing I have proved are dumped once, raw, under 身份未确认.  Slots are
4 KB apart, the name lives twice (0x2b0/0x2b8 and 0x300/0x308) and so does the date
(0x1cc day-first, 0x038/0x03a month-first).  A slot whose field area is still all zero
was never saved into, and says nothing.

usage: python3 tools/smrutil.py [srm ...] [--rom PATH]
"""
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_zh as B

STRIDE = 0x1000
ATTR = (0x00, ('体力', '文科', '理科', '艺术', '运动', '杂学', '容姿', '毅力', '压力'))
# The ten heroines in the order the engine numbers them.  Proven, not guessed: the four
# nonzero entries of a played slot are the same four indices as that slot's phone flags,
# and three of those four match the names read off that save's in-game phone book.
GIRLS = ('藤崎诗织', '如月未绪', '纽绪结奈', '片桐彩子', '虹野沙希',
         '古式由加利', '清川望', '镜魅罗', '朝日奈夕子', '美树原爱')
AFFINITY, N_AFF = 0x100, 12          # 10 heroines + 2 records whose characters are unknown;
                                     # on a brand-new game this reads 诗织 50 and record
                                     # 12 a 25, everything else 0
PHONE, N_PHONE = 0x142, 12           # (status, 0x80) per record; the status byte has three
                                     # values on a real save: 00 not met yet, 01 met but no
                                     # number, 0f number in the book.  01 is the 如月 case the
                                     # player described; no slot ever shows affinity > 0 at 00.
PHONE_TIER = {0x01: '登场但没有电话', 0x0F: '有电话'}
APPT, N_APPT = 0x16e, 16             # 16 x 4-byte records (day-1, month-1, 对象, one byte I
                                     # have not identified); nothing booked = first two ff
DATE = 0x1cc                         # day-1, month-1; the same day is kept a second time at
DATE2 = 0x038                        # 0x038/0x03a as (month-1, day-1) words -- both copies
                                     # agree in every slot of every save on disk
FIELD_END = 0x340                    # everything named above lives under this; an untouched
                                     # slot is zero all the way to it (only 0xfe2 on carries
                                     # the 01..0f marker bytes the emulator leaves there)
NAMES = (('姓', 0x2b0, 4), ('名', 0x2b8, 4), ('姓·副本', 0x300, 4),
         ('名·副本', 0x308, 4), ('昵称', 0x310, 6))
# Offsets that move between saves but whose meaning is not established: raw values, read
# and printed as such.  0x22e is the club candidate (it reads 4 = 美术部 on the slot the player
# says is 美术部, 0 on the others) and 0x370/0x376 the birthday candidate pair (two
# 0-based (month, day) words, reading 1/2 and 1/30 there) -- neither is named above until a
# second slot with known answers agrees.
UNCONFIRMED = ((0x042, 3, 'w'), (0x118, 10, 'w'), (0x1ae, 1, 'w'), (0x1ba, 9, 'w'),
               (0x22e, 1, 'w'), (0x370, 6, 'w'),
               (0x15a, 1, 'b'), (0x160, 1, 'b'), (0x264, 1, 'b'))
# Regions whose text the localization rewrote: the preset-name pool and block 144.
VERSION_PROBE = ((0x1F890, 0x1FA40), (0x22F000, 0x22F2D4))


def kana_count(rom, lo, hi):
    fl = ''.join(x for x in T.flatten(T.decode(rom, lo, limit=hi - lo)) if isinstance(x, str))
    return sum(1 for c in fl if 0x3041 <= ord(c) <= 0x3096 or 0x30A1 <= ord(c) <= 0x30FA)


def which_build(rom):
    """'original' or 'localized' -- counted hiragana in two regions the patch rewrote."""
    n = sum(kana_count(rom, lo, hi) for lo, hi in VERSION_PROBE)
    return ('original' if n > 50 else 'localized', n)


def keycaps(data):
    """kana-page cell index -> the character that key draws.

    A name typed on the kana page stores the *key* index, not a font index, so without
    this it reads back as that key's original hiragana (高见公人 would print がぎぐげ).
    """
    map = {}
    for cells, line in zip(B.keycap_cells(data), B.NAME_KEYCAPS):
        map.update(zip(cells, line))
    return map


def girl(i):
    return GIRLS[i] if i < len(GIRLS) else '第%d号' % (i + 1)


def words(b, off, n):
    return [int.from_bytes(b[off + 2 * i:off + 2 * i + 2], 'little') for i in range(n)]


def redrawn(idx, orig, patched):
    """Whether this image's glyph record differs from the original's at the same slot.

    That is how a localized save's kanji-page cell gets flagged without the build's
    allocation table: the bitmap changed, but which character replaced it is not
    recoverable from the image alone, so the report prints the slot and leaves the cell.
    """
    o = T.glyph_offset(idx)
    return orig[o:o + 28] != patched[o:o + 28]


def name(b, off, caps, ncell=4, pair=None):
    """One name record: cells until `$0A` or a blank cell, at most `ncell` of them.

    A cell below the kanji band is a *key* index, and `caps` says what that key draws.
    At or above it the save stores the font slot the key sat on, which is read through
    the image's own index->character table; `pair` (the two images' bytes) lets a
    redrawn slot be left blank instead of printed with the original image's character.
    """
    cells = []
    for i in range(off, off + 2 * ncell, 2):
        if b[i] in (0x0A, 0x00):
            break
        idx = ((b[i] & 0x0F) << 8) | b[i + 1]
        if idx < T.JIS_KANJI and caps.get(idx):
            cells.append((caps[idx], idx))
        elif pair and idx >= T.JIS_KANJI and redrawn(idx, *pair):
            cells.append(('¤', idx))
        else:
            cells.append((T.idx_to_char(idx) or '□', idx))
    return ''.join(c for c, _ in cells), ' '.join('%03x' % i for _, i in cells)


def report(srm, rom_path):
    blob = open(srm, 'rb').read()
    kind, probe, rom = '未判定（没有镜像可读）', -1, None
    if rom_path and os.path.exists(rom_path):
        rom = T.Rom(rom_path)
        build, probe = which_build(rom)
        kind = '日文原版' if build == 'original' else '中文镜像'
    localized = kind == '中文镜像'
    # Only the localized image redraws the two kana keycap pages, so on the original one
    # a key index reads back as the kana the player actually saw.
    caps = keycaps(rom.data) if localized else {}
    pair = None
    if localized and os.path.exists(T.ROM_JP):
        pair = (T.Rom(T.ROM_JP).data, rom.data)
    print('=' * 78)
    print('%s\n  %d bytes  md5 %s  %d 个槽位' % (srm, len(blob),
          hashlib.md5(blob).hexdigest(), len(blob) // STRIDE))
    print('  来源镜像 %s' % (rom_path or '（没找到，名字只能按原镜像的字表读）'))
    print('  镜像版本 %s（两处文本区假名 %d 个）' % (kind, probe))
    if rom_path and ('Chinese Localized' in srm) != ('Chinese Localized' in rom_path):
        print('  警告 存档和镜像不是一对（一个带 (Chinese Localized) 而另一个没有），名字会读错。')
    if localized:
        print('  名字注：假名两页的格存的是键号，已按本镜像的中文键帽读；汉字页的格存的是字库槽号，'
              '该格点阵与原镜像不同则只印「¤」加槽号。')
    for n in range(len(blob) // STRIDE):
        b = blob[n * STRIDE:(n + 1) * STRIDE]
        d, m = b[DATE], b[DATE + 1]
        print('\n-- 槽位 %d（文件 0x%x）--' % (n + 1, n * STRIDE))
        if not b[:FIELD_END].strip(b'\x00'):
            print('  没存过：%s 全零，约会表连 ff 都没写过' % ('0x000–0x%03x' % FIELD_END))
            continue
        print('  日期       %d/%d（两份一致：0x1cc 日,月 / 0x038·0x03a 月,日，都是 0 基）'
              % (m + 1, d + 1))
        print('  属性       ' + '  '.join('%s%d' % (k, v) for k, v in
                                          zip(ATTR[1], words(b, ATTR[0], len(ATTR[1])))))
        for label, off, ncell in NAMES:
            text, raw = name(b, off, caps, ncell, pair)
            if text:
                print('  %-9s %s%s' % (label, text,
                                       '  [%s]' % raw if label in ('姓', '名', '昵称') else ''))
        aff = words(b, AFFINITY, N_AFF)
        tel = [b[PHONE + 2 * i] for i in range(N_PHONE)]
        print('  好感度     ' + '  '.join('%s=%d' % (g, aff[i]) for i, g in enumerate(GIRLS)))
        print('             第 11/12 条（身份未确认）= %d / %d' % (aff[10], aff[11]))
        print('  登场       ' + ('  '.join('%s=%s' % (g, PHONE_TIER.get(t) or '%02x' % t)
                                          for g, t in zip(GIRLS, tel) if t)
                               or '十个女生都未登场（0x142 起全是 00）'))
        print('             第 11/12 条（身份未确认）= %02x / %02x' % (tel[10], tel[11]))
        booked = [(o, b[o + 1], b[o], b[o + 2])      # offset, month, day, 对象
                  for o in range(APPT, APPT + 4 * N_APPT, 4)
                  if (b[o], b[o + 1]) != (0xFF, 0xFF)]
        print('  约会       ' + ('  '.join('%d/%d %s[%03x]' % (mo + 1, da + 1, girl(g), o)
                                           for o, mo, da, g in booked)
                                or '无（0x16e 起 16 条记录的日、月都是 ff）'))
        print('  身份未确认 ' + '  '.join(
            '%s [%s]' % ('0x%03x' % off, ' '.join(str(x) for x in words(b, off, cnt)))
            for off, cnt, k in UNCONFIRMED if k == 'w'))
        print('             ' + '  '.join(
            '%s %s' % ('0x%03x' % off, b[off:off + cnt].hex(' '))
            for off, cnt, k in UNCONFIRMED if k == 'b'))


if __name__ == '__main__':
    argv = sys.argv[1:]
    rom_arg = None
    if '--rom' in argv:
        i = argv.index('--rom')
        rom_arg = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    paths = argv or [os.path.splitext(p)[0] + '.srm' for p in (T.ROM_JP, T.ROM_ZH)]
    for p in paths:
        if not os.path.exists(p):
            print('%s: 没有这个存档文件' % p)
            continue
        report(p, rom_arg or os.path.splitext(p)[0] + '.sfc')
