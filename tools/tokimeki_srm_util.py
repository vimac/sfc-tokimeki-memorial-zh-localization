"""Every field a .srm save slot says, read out of the bytes: the date, the nine
attributes, affinity per record, who has been met and who has a phone number, and every
appointment in the diary.  It can also write back the fields whose offset is proven.

Nothing here needs a path baked in: the saves come from argv, the image they were written
by comes from --rom (or each save's own sibling .sfc), and the original image used only for
the "this glyph was redrawn" diff comes from --orig.  Without an image the names still
read, just through the original image's index->character table.

  python3 tools/tokimeki_srm_util.py [--rom 镜像.sfc] [--orig 原镜像.sfc] 存档.srm [存档.srm ...]
  python3 tools/tokimeki_srm_util.py --export [--out 导出.yaml] 存档.srm [存档.srm ...]
  python3 tools/tokimeki_srm_util.py --import 导出.yaml [存档.srm ...] [--dry-run] [--year 96] [--force]

--export writes ONE file for every save named on the command line, each save keyed by its
own path plus md5, so the Japanese-version and the localized save of the same slot number
stay distinguishable.  The YAML is a hand-rolled subset (block mappings, block or inline
sequences, flow maps of scalars, quoted strings, ints, true/false/null) so no pyyaml is
needed; --import reads that same subset back.  Comment lines are safe to add, tabs are not.

--import writes only these four keys, and only into slots that were actually saved into --
any key you leave out of the file stays untouched, which is what makes export→import a no-op:
  date          both copies, 0x1cc (day, month) and 0x038/0x03a (month, day as words)
  affinity      the 12 words at 0x100 -- all 12, or none
  visibility    the 12 status bytes at 0x142 -- all 12, or none
                (00 未登场 / 01 登场没电话 / 0f 有电话)
  appointments  up to 16 records for 0x16e: {month, day, girl, place}.  `girl` is a name or
                an index 0-11.  Writing the list rewrites the whole table, because a
                cancelled booking keeps its 对象 byte and the game still counts it.
Everything else in the file (attributes, names, unconfirmed) is dumped for reference only.
Before a byte is written the slot's dates are proved against the calendar: 当前日期 must be a
Sunday between 1996/4/4 and 1999/3/1 (4/4 itself passes -- it is 开学第一天, a Thursday in the
real calendar), and every appointment must fall within 28 days AFTER that date.  A save stores
no year, so --year pins one; without it the Sunday rule usually leaves a single candidate.
Dates the YAML does not mention are checked too, because changing 当前日期 can push a booking
that is already in the file out of the window.  --force turns every complaint into a warning.
Writes make `<存档>.srm.bak` from the pre-write bytes; --dry-run shows the byte diff only.

Slots are 4 KB apart.  The name lives twice (0x2b0/0x2b8 and 0x300/0x308) and so does the
date.  A slot whose field area is still all zero was never saved into and says nothing.
Only fields whose identity is established get a name; the offsets that move between saves
without a proven meaning are dumped once, raw, under 身份未确认 -- including the 4th byte
of an appointment record, which --export calls `place` because the player reads it as the
约会地点, which is NOT proved.
"""
import sys, os, re, hashlib, argparse, datetime

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
N_REC = 12                           # affinity and phone tables are both 12 records; the
                                     # identity of records 11 and 12 is not established,
                                     # so those two take an index, never a name
AFFINITY = 0x100
PHONE = 0x142                        # (status, 0x80) per record; three status values on a
                                     # real save -- 00 not met yet, 01 met but no number,
                                     # 0f number in the book.  No slot ever shows
                                     # affinity > 0 at status 00.
PHONE_TIER = {0x00: '未登场', 0x01: '登场但没有电话', 0x0F: '有电话'}
APPT, N_APPT = 0x16e, 16             # 16 x 4-byte records (day-1, month-1, 对象, 未确认)
DATE = 0x1cc                         # day-1, month-1; the same day is kept a second time
DATE2 = 0x038                        # at 0x038/0x03a as (month-1, day-1) words -- both
                                     # copies agree in every slot of every save on disk
FIELD_END = 0x340                    # everything named above lives under this; an
                                     # untouched slot is zero all the way to it (only
                                     # 0xfe2 on carries the 01..0f marker bytes the
                                     # emulator leaves there)
NAMES = (('姓', 0x2b0, 4), ('名', 0x2b8, 4), ('姓·副本', 0x300, 4),
         ('名·副本', 0x308, 4), ('昵称', 0x310, 6))
# Offsets that move between saves but whose meaning is not established: raw values, printed
# as such and never written by --import.
UNCONFIRMED = ((0x042, 3, 'w'), (0x118, 10, 'w'), (0x1ae, 1, 'w'), (0x1ba, 9, 'w'),
               (0x22e, 1, 'w'), (0x370, 6, 'w'),
               (0x15a, 1, 'b'), (0x160, 1, 'b'), (0x264, 1, 'b'))
# Regions whose text the localization rewrote: the preset-name pool and block 144.
VERSION_PROBE = ((0x1F890, 0x1FA40), (0x22F000, 0x22F2D4))
EXPORT_DEFAULT = 'tokimeki_srm.yaml'
# The calendar the writes are proved against.  A slot stores month and day only, and has
# neither a year nor an elapsed-day counter (measured: no 16-bit window in either slot tracks
# the gap between two saves), so the year is supplied by --year or inferred.  The inference
# rests on the game using the real Gregorian week: every played day and every booked day on
# disk (96/4/7, 96/10/13, 96/12/29 / 4/14, 10/20, 10/27, 11/3) is a real Sunday.
TERM = (datetime.date(1996, 4, 4), datetime.date(1999, 3, 1))    # 开学第一天 – 毕业典礼
WEEK = '一二三四五六日'
SUNDAY = 6
APPT_WINDOW = 28


def span_text():
    return '%d/%d/%d–%d/%d/%d' % (TERM[0].year, TERM[0].month, TERM[0].day,
                                  TERM[1].year, TERM[1].month, TERM[1].day)


HEADER = (
    '心跳回忆 .srm 存档导出 -- tools/tokimeki_srm_util.py --export',
    '导入只认 date／affinity／visibility／appointments 这四个键，没写的键不动；'
    'affinity／visibility 要给满 12 条。',
    '12 条按引擎下标排：0–9＝十位女主（约会记录里 girl 可写中文名），10、11 的人物身份未确认。',
    'date 是 1 基的月/日；存档里存 0 基，写在两处（0x1cc 日,月 与 0x038/0x03a 月,日字）。',
    'visibility＝0x142 起 12 个状态字节（0 未登场／1 登场没电话／15 有电话）。',
    '约会的 place 是记录第 4 字节：玩家把它读作约会地点，但这个含义尚未证实，导入按原值写回。',
    '约会整张表重写：导出里没列出来的记录就当没有（取消过的预约会留下对象字节）。',
    'attributes／names／unconfirmed 是给人看的，导入不写。',
    '写之前过日历：date 要是 %s 之间的周日，%s 开学第一天例外（真实公历上是周四）；'
    '每条约会要落在 date 之后 %d 天之内。存档不存年份，所以没给 --year 时按'
    '「哪一年的这一天是周日」推——同一个月/日在这三年里各落一个不同的星期，推得唯一。'
    % (span_text(), '%d/%d' % (TERM[0].month, TERM[0].day), APPT_WINDOW),
)


# ---------------------------------------------------------------- YAML subset

def _scalar(text):
    text = text.strip()
    if len(text) > 1 and text[0] == '"' and text[-1] == '"':
        out, i = '', 1
        while i < len(text) - 1:
            if text[i] == '\\':
                out += {'n': '\n', 't': '\t'}.get(text[i + 1], text[i + 1])
                i += 2
            else:
                out += text[i]
                i += 1
        return out
    if text in ('true', 'false'):
        return text == 'true'
    if text in ('null', '~', ''):
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _cut_comment(line):
    quoted, i = False, 0
    while i < len(line):
        c = line[i]
        if quoted:
            if c == '\\':
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == '#' and (i == 0 or line[i - 1] in ' \t'):
            return line[:i]
        i += 1
    return line


def _split_commas(body):
    parts, depth, quoted, start, i = [], 0, False, 0, 0
    while i < len(body):
        c = body[i]
        if quoted:
            if c == '\\':
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in '[{':
            depth += 1
        elif c in ']}':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(body[start:i])
            start = i + 1
        i += 1
    parts.append(body[start:])
    return [p.strip() for p in parts if p.strip()]


def _split_key(content):
    """`k: v` -> (_scalar(k), 'v'); the colon must be followed by a space or end of line."""
    quoted, i = False, 0
    while i < len(content):
        c = content[i]
        if quoted:
            if c == '\\':
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == ':' and not quoted and (i + 1 == len(content) or content[i + 1] in ' \t'):
            return _scalar(content[:i]), content[i + 1:].strip()
        i += 1
    return None, content.strip()


def _flow(body):
    """`[a, b]` or `{k: v, ...}` -- depth 1, which is all the emitter writes."""
    if body.startswith('['):
        return [_scalar(x) for x in _split_commas(body[1:-1])]
    out = {}
    for part in _split_commas(body[1:-1]):
        k, v = _split_key(part)
        out[k] = _scalar(v)
    return out


def _lines(text):
    out = []
    for raw in text.splitlines():
        line = _cut_comment(raw.rstrip('\n')).rstrip()
        if line.strip():
            out.append((len(line) - len(line.lstrip()), line.strip()))
    return out


def _is_map_line(body):
    return not body.startswith(('[', '{', '"')) and _split_key(body)[0] is not None


def _block(lines, i, indent):
    """Parse lines[i:] whose block indent is `indent`; return (value, index-after)."""
    if lines[i][1].startswith('- '):
        seq = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith('- '):
            body = lines[i][1][2:].strip()
            j = i + 1
            while j < len(lines) and lines[j][0] > indent:
                j += 1
            inner = lines[i + 1:j]
            if body.startswith(('[', '{')):
                seq.append(_flow(body)); i += 1
            elif _is_map_line(body):
                # `- 键: 值` plus its continuation lines are one map at indent + 2
                seq.append(_block([(indent + 2, body)] + inner, 0, indent + 2)[0]); i = j
            elif body == '':
                seq.append(_block(inner, 0, inner[0][0])[0] if inner else None); i = j
            else:
                seq.append(_scalar(body)); i += 1
        return seq, i
    mapping = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith('- '):
        key, rest = _split_key(lines[i][1])
        j = i + 1
        while j < len(lines) and lines[j][0] > indent:
            j += 1
        inner = lines[i + 1:j]
        if rest.startswith(('[', '{')):
            mapping[key] = _flow(rest)
            i += 1
        elif rest == '':
            mapping[key] = _block(inner, 0, inner[0][0])[0] if inner else None
            i = j
        else:
            mapping[key] = _scalar(rest)
            i += 1
    return mapping, i


def _quote(s):
    return '"%s"' % str(s).replace('\\', '\\\\').replace('"', '\\"')


def _plain(v):
    return v is None or isinstance(v, (bool, int))


def _flat(v):
    """A container whose members are all scalars goes on one line as flow style."""
    if isinstance(v, dict):
        return all(_scalarish(x) for x in v.values())
    if isinstance(v, list):
        return all(_scalarish(x) for x in v)
    return False


def _scalarish(v):
    return not isinstance(v, (dict, list))


def _flow_line(v):
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_scalar_out(x) for x in v) + ']'
    return '{' + ', '.join('%s: %s' % (_key_out(k), _scalar_out(val)) for k, val in v.items()) + '}'


def _scalar_out(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return str(v) if isinstance(v, int) else _quote(v)


def _key_out(k):
    if isinstance(k, bool):
        return 'true' if k else 'false'
    if isinstance(k, int):
        return str(k)
    return k if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', str(k)) else _quote(k)


def _emit(v, indent, out):
    pad = ' ' * indent
    if isinstance(v, dict):
        for k, sub in v.items():
            if _flat(sub):
                out.append('%s%s: %s' % (pad, _key_out(k), _flow_line(sub)))
            elif isinstance(sub, (dict, list)):
                out.append('%s%s:' % (pad, _key_out(k)))
                _emit(sub, indent + 2, out)
            else:
                out.append('%s%s: %s' % (pad, _key_out(k), _scalar_out(sub)))
    elif isinstance(v, list):
        for sub in v:
            if _flat(sub) and isinstance(sub, (dict, list)):
                out.append('%s- %s' % (pad, _flow_line(sub)))
            elif isinstance(sub, (dict, list)) and sub:
                body = []
                _emit(sub, indent + 2, body)
                out.append('%s- %s' % (pad, body[0].lstrip(' ')))
                out.extend(body[1:])
            else:
                out.append('%s- %s' % (pad, _scalar_out(sub)))


def yaml_dump(obj, header=()):
    lines = ['# ' + h for h in header]
    _emit(obj, 0, lines)
    return '\n'.join(lines) + '\n'


def yaml_load(text):
    lines = _lines(text)
    if not lines:
        raise ValueError('空的导出文件')
    return _block(lines, 0, lines[0][0])[0]


# ---------------------------------------------------------------- reading

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
    return ''.join(c for c, _ in cells), [idx for _, idx in cells]


class Image:
    """The image the saves were written by, plus the original one glyph diff needs."""

    def __init__(self, rom_path, orig_path=None):
        self.path = rom_path
        self.build, self.probe, self.caps, self.pair, self.localized = \
            '未判定（没有镜像可读）', -1, {}, None, False
        if not (rom_path and os.path.exists(rom_path)):
            return
        rom = T.Rom(rom_path)
        kind, self.probe = which_build(rom)
        self.build = '日文原版' if kind == 'original' else '中文镜像'
        self.localized = kind == 'localized'
        if self.localized:
            # only this build redraws the two kana keycap pages
            self.caps = keycaps(rom.data)
            if orig_path and os.path.exists(orig_path):
                self.pair = (T.Rom(orig_path).data, rom.data)


def read_slot(b, img):
    """Model dict for one slot -- what the report prints and --export writes."""
    if not b[:FIELD_END].strip(b'\x00'):
        return {'untouched': True}
    copy = words(b, DATE2, 2)
    out = {'untouched': False,
           'date': {'month': b[DATE + 1] + 1, 'day': b[DATE] + 1},
           'date_copy': {'month': copy[0] + 1, 'day': copy[1] + 1},
           'attributes': dict(zip(ATTR[1], words(b, ATTR[0], len(ATTR[1]))))}
    names = {}
    for label, off, ncell in NAMES:
        text, cells = name(b, off, img.caps, ncell, img.pair)
        if text:
            names[label] = text
    out['names'] = names
    out['affinity'] = words(b, AFFINITY, N_REC)
    out['visibility'] = [b[PHONE + 2 * i] for i in range(N_REC)]
    out['appointments'] = [{'at': '%03x' % o, 'month': b[o + 1] + 1, 'day': b[o] + 1,
                            'girl': b[o + 2], 'place': b[o + 3]}
                           for o in range(APPT, APPT + 4 * N_APPT, 4)
                           if (b[o], b[o + 1]) != (0xFF, 0xFF)]
    out['unconfirmed'] = {
        'w': dict(('%03x' % off, words(b, off, cnt)) for off, cnt, k in UNCONFIRMED if k == 'w'),
        'b': dict(('%03x' % off, bytes(b[off:off + cnt]).hex(' '))
                  for off, cnt, k in UNCONFIRMED if k == 'b')}
    return out


def print_slot(n, s):
    print('\n-- 槽位 %d（文件 0x%x）--' % (n + 1, n * STRIDE))
    if s['untouched']:
        print('  没存过：0x000–0x%03x 全零，约会表连 ff 都没写过' % FIELD_END)
        return
    d, c = s['date'], s['date_copy']
    print('  日期       %d/%d（%s：0x1cc 日,月 / 0x038·0x03a 月,日，都是 0 基）'
          % (d['month'], d['day'],
             '两份一致' if (c['month'], c['day']) == (d['month'], d['day'])
             else '两份不一致！0x038 那份是 %d/%d' % (c['month'], c['day'])))
    print('  属性       ' + '  '.join('%s%d' % (k, v) for k, v in s['attributes'].items()))
    for label in ('姓', '名', '昵称', '姓·副本', '名·副本'):
        if s['names'].get(label):
            print('  %-9s %s' % (label, s['names'][label]))
    aff, vis = s['affinity'], s['visibility']
    print('  好感度     ' + '  '.join('%s=%d' % (g, aff[i]) for i, g in enumerate(GIRLS)))
    print('             第 11/12 条（身份未确认）= %d / %d' % (aff[10], aff[11]))
    print('  登场       ' + ('  '.join('%s=%s' % (g, PHONE_TIER.get(t) or '%02x' % t)
                                       for g, t in zip(GIRLS, vis) if t)
                            or '十个女生都未登场（0x142 起全是 00）'))
    print('             第 11/12 条（身份未确认）= %02x / %02x' % (vis[10], vis[11]))
    booked = s['appointments']
    print('  约会       ' + ('  '.join('%d/%d %s 地点?%02x[%s]'
                                       % (a['month'], a['day'], girl(a['girl']), a['place'], a['at'])
                                       for a in booked)
                             or '无（0x16e 起 16 条记录的日、月都是 ff）'))
    u = s['unconfirmed']
    print('  身份未确认 ' + '  '.join('%s [%s]' % ('0x' + k, ' '.join(str(x) for x in v))
                                      for k, v in u['w'].items()))
    print('             ' + '  '.join('0x%s %s' % (k, v) for k, v in u['b'].items()))


def report(path, img):
    blob = open(path, 'rb').read()
    md5 = hashlib.md5(blob).hexdigest()
    print('=' * 78)
    print('%s\n  %d bytes  md5 %s  %d 个槽位' % (path, len(blob), md5, len(blob) // STRIDE))
    print('  来源镜像 %s' % (img.path or '（没找到，名字只能按原镜像的字表读）'))
    if img.probe < 0:
        print('  镜像版本 %s' % img.build)
    else:
        print('  镜像版本 %s（两处文本区假名 %d 个）' % (img.build, img.probe))
    if img.path and ('Chinese Localized' in path) != ('Chinese Localized' in img.path):
        print('  警告 存档和镜像不是一对（一个带 (Chinese Localized) 而另一个没有），名字会读错。')
    if img.localized:
        print('  名字注：假名两页的格存的是键号，已按本镜像的中文键帽读；汉字页的格存的是字库槽号，'
              + ('该格点阵与原镜像不同则只印「¤」加槽号。' if img.pair
                 else '没有 --orig 原镜像，所以重画过的格只能印成原镜像该槽的字。'))
    slots = []
    for n in range(len(blob) // STRIDE):
        s = read_slot(blob[n * STRIDE:(n + 1) * STRIDE], img)
        s = dict([('slot', n + 1)] + list(s.items()))
        slots.append(s)
        print_slot(n, s)
    readable = img.path if (img.path and os.path.exists(img.path)) else None
    return {'file': os.path.abspath(path), 'md5': md5, 'bytes': len(blob),
            'rom': os.path.abspath(readable) if readable else None,
            'build': img.build, 'slots': slots}


# ---------------------------------------------------------------- writing

def girl_ref(value, allow_unknown=False):
    if isinstance(value, int):
        if not 0 <= value < N_REC:
            raise ValueError('下标要在 0–%d（给了 %d）' % (N_REC - 1, value))
        return value
    text = str(value).strip()
    if text in GIRLS:
        return GIRLS.index(text)
    if allow_unknown:
        raise ValueError('第 11/12 条身份未确认，只能写下标 10 或 11（给了「%s」）' % text)
    raise ValueError('不认识的名字「%s」，可写：' % text + '、'.join(GIRLS)
                     + '，或者下标 0–%d' % (N_REC - 1))


def _byte_at(b, off, value, label, changes, lo=0, hi=255):
    v = int(value)
    if not lo <= v <= hi:
        raise ValueError('%s 要在 %d–%d 之间（给了 %s）' % (label, lo, hi, value))
    if b[off] != v:
        changes.append('0x%03x  %02x→%02x  %s' % (off, b[off], v, label))
        b[off] = v


def _word_at(b, off, value, label, changes, hi=0xFFFF):
    v = int(value)
    if not 0 <= v <= hi:
        raise ValueError('%s 要在 0–%d 之间（给了 %s）' % (label, hi, value))
    now = int.from_bytes(b[off:off + 2], 'little')
    if now != v:
        changes.append('0x%03x  %d→%d  %s' % (off, now, v, label))
        b[off:off + 2] = v.to_bytes(2, 'little')


# ---------------------------------------------------------------- calendar

def candidates(m, d, year=None):
    """Every day in the school term that this month/day could be, oldest first."""
    out = []
    for y in range(TERM[0].year, TERM[1].year + 1):
        try:
            dt = datetime.date(y, m, d)
        except ValueError:                 # 2/29 in a common year
            continue
        if TERM[0] <= dt <= TERM[1] and (year is None or y == year):
            out.append(dt)
    return out


def slot_date(s, b):
    """The 1-based (month, day) this slot will carry after the import: the YAML's if it
    gives a date, otherwise the one already in the file."""
    date = s.get('date')
    if date:
        return int(date['month']), int(date['day'])
    mo, da = b[DATE + 1], b[DATE]
    return (mo + 1, da + 1) if mo <= 11 and da <= 30 else None


def slot_appts(s, b):
    """The appointment dates the import leaves behind, as 1-based (month, day, label)."""
    listed = s.get('appointments')
    if listed is not None:
        return [(int(a['month']), int(a['day']), '约会%d' % (i + 1)) for i, a in enumerate(listed)]
    out = []
    for i, o in enumerate(range(APPT, APPT + 4 * N_APPT, 4)):
        if (b[o], b[o + 1]) == (0xFF, 0xFF):
            continue
        mo, da = b[o + 1] + 1, b[o] + 1
        if 1 <= mo <= 12 and 1 <= da <= 31:
            out.append((mo, da, '约会%d（文件里原有）' % (i + 1)))
    return out


def resolve_now(m, d, year):
    """Which day of the term a slot's month/day stands for -> (date, 错误, 提醒)."""
    cands = candidates(m, d, year)
    if not cands:
        where = ('--year %d 那年' % year) if year else ('学制 %s' % span_text())
        return None, ['当前日期 %d/%d 不在 %s 之内（开学前、毕业后，或者这个年份里没有这一天）'
                      % (m, d, where)], []
    sundays = [c for c in cands if c.weekday() == SUNDAY]
    if (m, d) == (TERM[0].month, TERM[0].day):
        sundays.append(TERM[0])            # 开学第一天，真实公历上是周四——玩家指定的例外
    if year:
        now = cands[0]
        if now not in sundays:
            # Name the years that DO put this month/day on a Sunday; --year said one of them.
            ok = [c for c in candidates(m, d) if c.weekday() == SUNDAY or c == TERM[0]]
            return now, ['当前日期 %s＝星期%s，不是周日（学制里 %d/%d 是周日的年份：%s）；'
                         '要么改日期，要么 --year 指到那一年'
                         % (now, WEEK[now.weekday()], m, d,
                            '、'.join(str(c.year) for c in ok) or '根本没有')], []
        return now, [], ['当前日期 %d/%d 按 %s（星期%s）算' % (m, d, now, WEEK[now.weekday()])]
    if not sundays:
        days = '、'.join('%d 年星期%s' % (c.year, WEEK[c.weekday()]) for c in cands)
        return None, ['当前日期 %d/%d 在学制里没有对应的周日（%s）；'
                      '要么改日期，要么 --year 指定年份' % (m, d, days)], []
    now = sundays[0]
    return now, [], ['当前日期 %d/%d 落在 %s 这年（星期%s）' % (m, d, now, WEEK[now.weekday()])]


def check_appt(now, m, d, label):
    """One diary entry against the current date: it has to be booked, not already past."""
    hits = [c for c in candidates(m, d)
            if now <= c <= now + datetime.timedelta(days=APPT_WINDOW)]
    if not hits:
        far = '、'.join('%s（%+d 天）' % (c, (c - now).days) for c in candidates(m, d))
        return (['%s %d/%d 不在当前日期 %s 之后 %d 天之内（学制里的 %d/%d：%s）'
                 % (label, m, d, now, APPT_WINDOW, m, d, far or '这一天根本不在学制内')], [])
    dt = hits[0]
    note = [] if dt.weekday() == SUNDAY else \
        ['%s %s（星期%s）不是周日' % (label, dt, WEEK[dt.weekday()])]
    return [], note


def check_calendar(s, b, year):
    """Prove every date this slot ends up with.  Runs on the in-memory copy before a byte
    is committed, and covers dates the YAML never mentions -- a new 当前日期 can push a
    booking that is already in the file out of its 28-day window."""
    day, appts = slot_date(s, b), slot_appts(s, b)
    if day is None and not appts:
        return [], []
    problems, notes = [], []
    now = None
    if day:
        now, p, n = resolve_now(day[0], day[1], year)
        problems += p
        notes += n
    elif appts:
        notes.append('0x1cc 读不出合法的月/日，约会窗口没法定，这一项跳过了')
    for m, d, label in appts:
        if now is None:
            if day:
                problems.append('%s %d/%d 没校验：当前日期先不合法' % (label, m, d))
            break
        p, n = check_appt(now, m, d, label)
        problems += p
        notes += n
    return problems, notes


def apply_slot(b, s, changes, year=None, force=False, notes=None):
    """Write the importable fields of one slot into `b`; `changes` collects the byte log.

    Calendar lines go to `notes` instead: a slot that ends up unchanged has no byte log to
    print, and 'this date is not a Sunday' is worth saying even then.
    """
    if notes is None:
        notes = changes
    if s.get('untouched'):
        return '这个槽位没存过，不写——半个档案不如不动'
    problems, found = check_calendar(s, b, year)
    notes.extend(found)
    if problems and not force:
        raise ValueError('日历校验没过：\n      ' + '\n      '.join(problems)
                         + '\n      （存档只存月/日，年份靠 --year 或按周日推；确认要照写加 --force）'
                         + ('\n      ' + '\n      '.join(notes) if notes else ''))
    for line in problems:
        notes.append('提醒（--force 放行）%s' % line)
    date = s.get('date')
    if date:
        m, d = int(date['month']) - 1, int(date['day']) - 1
        if not (0 <= m <= 11 and 0 <= d <= 30):
            raise ValueError('日期要在 1/1–12/31（给了 %d/%d）' % (m + 1, d + 1))
        _byte_at(b, DATE, d, '日期 0x1cc 日', changes)
        _byte_at(b, DATE + 1, m, '日期 0x1cc 月', changes)
        for off, value, label in ((DATE2, m, '日期 0x038 月'), (DATE2 + 2, d, '日期 0x03a 日')):
            if b[off + 1]:
                changes.append('0x%03x  跳过 %s：那一字高位不是 0（%02x %02x），照写会挪位'
                               % (off, label, b[off], b[off + 1]))
                continue
            _word_at(b, off, value, label, changes, hi=255)
    if s.get('affinity') is not None:
        if len(s['affinity']) != N_REC:
            raise ValueError('好感度要 %d 条（给了 %d 条）' % (N_REC, len(s['affinity'])))
        # Storage is a 16-bit word.  Every value on a real save is 0–255 and the game's own
        # ceiling is not proved, so a bigger number is written but called out.
        for i, value in enumerate(s['affinity']):
            if int(value) > 255:
                changes.append('      提醒 好感度 %s＝%s，超过观测到的 0–255' % (girl(i), value))
            _word_at(b, AFFINITY + 2 * i, value, '好感度 %s' % girl(i), changes)
    if s.get('visibility') is not None:
        if len(s['visibility']) != N_REC:
            raise ValueError('登场状态要 %d 条（给了 %d 条）' % (N_REC, len(s['visibility'])))
        for i, value in enumerate(s['visibility']):
            _byte_at(b, PHONE + 2 * i, value, '登场 %s' % girl(i), changes)
    if s.get('appointments') is not None:
        listed = s['appointments']
        if len(listed) > N_APPT:
            raise ValueError('约会记录最多 %d 条（给了 %d 条）' % (N_APPT, len(listed)))
        live = [o for o in range(APPT, APPT + 4 * N_APPT, 4)
                if (b[o], b[o + 1]) != (0xFF, 0xFF)]
        for i, a in enumerate(listed):
            o = APPT + 4 * i
            m, d = int(a['month']) - 1, int(a['day']) - 1
            if not (0 <= m <= 11 and 0 <= d <= 30):
                raise ValueError('约会%d 的日期要在 1/1–12/31（给了 %d/%d）'
                                 % (i + 1, m + 1, d + 1))
            _byte_at(b, o, d, '约会%d 日 0x%03x' % (i + 1, o), changes)
            _byte_at(b, o + 1, m, '约会%d 月 0x%03x' % (i + 1, o), changes)
            _byte_at(b, o + 2, girl_ref(a['girl']), '约会%d 对象 0x%03x' % (i + 1, o), changes,
                     0, N_REC - 1)
            _byte_at(b, o + 3, a.get('place', b[o + 3]),
                     '约会%d 地点?（未证实）0x%03x' % (i + 1, o), changes)
        for i in range(len(listed), N_APPT):
            o = APPT + 4 * i
            if (b[o], b[o + 1]) == (0xFF, 0xFF):
                continue      # already empty: leave its stale 对象 bytes exactly as they are
            for k in range(4):
                if b[o + k] != 0xFF:
                    changes.append('0x%03x  %02x→ff  清空约会记录第 %d 条' % (o + k, b[o + k], i + 1))
                    b[o + k] = 0xFF
        if len(live) > len(listed):
            changes.append('      约会表原有 %d 条，导入只列 %d 条，其余已清空'
                           '（取消的预约会留下对象字节，留着就是幽灵预约）' % (len(live), len(listed)))
    return None


def stage_save(path, slots, year=None, force=False):
    """Apply the YAML's fields to an in-memory copy; return (blob, original, log lines).

    Nothing is written here, so a bad value in the third slot cannot leave the first
    file half-edited -- run_import stages every save, then commits.  The calendar checks
    ride along for the same reason: they fail before the first byte moves.
    """
    blob = bytearray(open(path, 'rb').read())
    original = bytes(blob)
    log = ['=' * 78,
           '%s\n  md5 %s  导入 %d 个槽位' % (path, hashlib.md5(original).hexdigest(), len(slots))]
    for n, s in slots:
        if n * STRIDE + STRIDE > len(blob):
            log.append('  槽位 %d：文件里没这么多槽位，跳过' % (n + 1))
            continue
        b = blob[n * STRIDE:(n + 1) * STRIDE]
        before = bytes(b)
        changes = []
        notes = []
        note = apply_slot(b, s, changes, year, force, notes)
        blob[n * STRIDE:(n + 1) * STRIDE] = b
        log.append('\n-- 槽位 %d（文件 0x%x）--' % (n + 1, n * STRIDE))
        if note:
            log.append('  ' + note)
        elif bytes(b) == before:
            log.append('  没有变化')
        else:
            log.extend('  ' + line for line in changes)
        log.extend('  ' + line for line in notes)
    return blob, original, log


def commit_save(path, blob, original):
    if bytes(blob) == original:
        return path + '\n  整个文件没有变化，没写。'
    bak = path + '.bak'
    with open(bak, 'wb') as f:
        f.write(original)
    with open(path, 'wb') as f:
        f.write(bytes(blob))
    return '原文备份 %s\n已写 %s（新 md5 %s）' % (bak, path, hashlib.md5(bytes(blob)).hexdigest())


def run_import(dump, paths, dry_run, year=None, force=False):
    saves = dump.get('saves')
    if not isinstance(saves, list):
        raise ValueError('导出文件里没有一个 saves 列表')
    entries = {}
    for entry in saves:
        if not isinstance(entry, dict) or not entry.get('file'):
            continue
        slots = [(int(s['slot']) - 1, dict(s, untouched=False))
                 for s in (entry.get('slots') or [])
                 if isinstance(s, dict) and not s.get('untouched')]
        entries[os.path.abspath(entry['file'])] = (entry, slots)
    picked = []
    if paths:
        for p in paths:
            ap = os.path.abspath(p)
            hit = ap if ap in entries else next(
                (k for k in entries if os.path.basename(k) == os.path.basename(ap)), None)
            if hit:
                picked.append((ap, entries[hit]))
            else:
                print('%s: 导出文件里没有这个存档的条目，跳过' % p)
    else:
        picked = list(entries.items())
    staged = []
    for ap, (entry, slots) in picked:
        if not slots:
            print('%s: 导出里这个存档没有存过的槽位，跳过' % ap)
            continue
        if not os.path.exists(ap):
            print('%s: 没有这个存档文件，跳过' % ap)
            continue
        now = hashlib.md5(open(ap, 'rb').read()).hexdigest()
        if entry.get('md5') and now != entry['md5']:
            print('  提醒 %s 的 md5 与导出时不同（导出 %s，现在 %s）——字段位置没变，照写；'
                  '确认这是你要改的那个存档。' % (ap, entry['md5'], now))
        staged.append((ap,) + stage_save(ap, slots, year, force))   # 校验在这里做完，一个字节都还没写
    for ap, blob, original, log in staged:
        print('\n'.join(log))
        if dry_run:
            print('\n  --dry-run：没写文件。')
            continue
        print(commit_save(ap, blob, original))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='tokimeki_srm_util.py', formatter_class=argparse.RawDescriptionHelpFormatter,
        description='读／导出／写回心跳回忆的 .srm 存档槽（字段含义见本文件 docstring）。')
    ap.add_argument('srm', nargs='*', help='.srm 存档，可以一次给两个（日文版＋中文版）')
    ap.add_argument('--rom', help='这些存档写出来的镜像；不给就用每个存档同名的 .sfc')
    ap.add_argument('--orig', help='原镜像，只用来把重画过的字库格标成「¤」')
    ap.add_argument('--export', action='store_true', help='把读到的字段写成一份 YAML')
    ap.add_argument('--out', help='YAML 落点，默认第一个存档旁的 ' + EXPORT_DEFAULT)
    ap.add_argument('--import', dest='do_import', metavar='YAML',
                    help='照 YAML 写回日期／好感度／登场／约会')
    ap.add_argument('--dry-run', action='store_true', help='配合 --import：只打字节差异')
    ap.add_argument('--year', type=int, metavar='96',
                    help='配合 --import：把存档里的月/日定在哪一年（写 96 或 1996 都行）；'
                         '不给就按「这一年的这一天是不是周日」推')
    ap.add_argument('--force', action='store_true',
                    help='配合 --import：日历校验只提醒，照样写')
    a = ap.parse_args(argv)
    if a.do_import and a.export:
        ap.error('--import 和 --export 各管一头，不要一起给')
    if a.year is not None:
        a.year += 1900 if a.year < 100 else 0
        if not TERM[0].year <= a.year <= TERM[1].year:
            ap.error('--year 要在学制里（%d–%d，给了 %d）' % (TERM[0].year, TERM[1].year, a.year))
    try:
        return _run(a, ap)
    except (ValueError, KeyError, OSError) as e:
        # 一个坏值不该甩 traceback，更不该写半个存档出去（写在 stage 之后）
        print('%s: %s' % (type(e).__name__, e))
        return 1


def _run(a, ap):
    if a.do_import:
        with open(a.do_import, encoding='utf-8') as f:
            dump = yaml_load(f.read())
        run_import(dump, a.srm, a.dry_run, a.year, a.force)
        return 0
    if not a.srm:
        ap.error('要给至少一个 .srm 存档（--help 看用法）')

    images, dumps = {}, []
    for p in a.srm:
        if not os.path.exists(p):
            print('%s: 没有这个存档文件' % p)
            continue
        rom = os.path.abspath(a.rom or os.path.splitext(p)[0] + '.sfc')
        if rom not in images:
            images[rom] = Image(rom, a.orig)
        dumps.append(report(p, images[rom]))
    if a.export:
        if not dumps:
            print('没有可导出的存档。')
            return 1
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.srm[0])), EXPORT_DEFAULT)
        with open(out, 'w', encoding='utf-8') as f:
            f.write(yaml_dump({'export': 'tokimeki-srm', 'version': 1, 'saves': dumps}, HEADER))
        print('\n导出 %s（%d 个存档）' % (out, len(dumps)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
