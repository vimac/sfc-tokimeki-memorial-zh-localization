"""Every field a .srm save slot says, read out of the bytes: the date, the nine
attributes, affinity per record, who has been met and who has a phone number, and every
appointment in the diary.  It can also write back the fields whose offset is proven.

Nothing here needs a path baked in: the saves come from argv, the image they were written
by comes from --rom (or each save's own sibling .sfc), and the original image used only for
the "this glyph was redrawn" diff comes from --orig.  Without an image the names still
read, just through the original image's index->character table.

  python3 tools/tokimeki_srm_util.py [--rom 镜像.sfc] [--orig 原镜像.sfc] 存档.srm [存档.srm ...]
  python3 tools/tokimeki_srm_util.py --export [--out 导出.yaml] 存档.srm [存档.srm ...]
  python3 tools/tokimeki_srm_util.py --import 导出.yaml [存档.srm ...] [--dry-run] [--force]
  python3 tools/tokimeki_srm_util.py --import 存档.srm [--dry-run]   # 读它旁边的 存档.srm.yaml

--export writes ONE file for every save named on the command line, next to the first save and
under its own name plus a `.yaml` suffix (`存档.srm` -> `存档.srm.yaml`); each save is keyed by
its path plus md5, so the Japanese-version and the localized save of the same slot number stay
distinguishable.  The YAML is a hand-rolled subset: mappings are block style one key per line
(so 属性 and 姓名 are directly editable), a list of scalars stays on one line, quoted strings,
ints, true/false/null.  No pyyaml is needed either way -- --import reads the same subset back.
Comment lines are safe to add, tabs are not.

--import writes only these six keys, and only into slots that were actually saved into --
any key you leave out of the file stays untouched, which is what makes export→import a no-op:
  date          年-月-日, one line in the file.  The save keeps the same day twice and both get
                written: 0x1cc (日, and 月|年序 packed into one byte) plus 0x036/0x038/0x03a as
                words.  The second copy is report-only -- it is there to be compared, not edited.
  attributes    the nine status words at 0x00..0x11 (体力／文科／理科／艺术／运动／杂学／容姿／
                毅力／压力), one 属性名: 数值 per line -- edit 容姿 alone and the other eight stay
                as they are.  No ceiling is enforced: a played slot reads 容姿141 and the user's
                own edited slot reads 体力314.
  affinity      the 11 words at 0x100, one 人名: 数值 per line (same subset rule)
  visibility    the 11 status bytes at 0x142, one 人名: 档位 per line.  00 means she has not
                shown up yet (her affinity is always 0 there); 01 and 0f both mean she is in
                play, and what separates those two tiers has never been proved.  This is NOT the
                phone book: measured 2026-09-27, a slot with all eleven heroines at 0f still
                showed none of the new names in 通讯录.
  phone_book    who is listed in 通讯录, from the 24-bit field at 0x8e5.  This IS the gate:
                clearing those three bytes leaves only 诗织/好雄/丽 on screen, FF FF FF fills
                the book with all thirteen entries.  Written as `人名: true／false`, one girl
                per line, so flipping someone in is one character and never a bit number --
                the three raw bytes are report-only and are not exported at all.  Import moves
                only the bits the lines you wrote name, so the fourteen bits of unknown
                purpose stay as they are.
  appointments  up to 16 records for 0x16e: {at, date, girl, place}.  `girl` is a name or an index
                0-10.  `place` is the 约会地点 pool index -- an index into build_zh.PLACE_TABLE,
                the 21 names `$E802` selects between, which is also the order the player picks in
                (user's control 2026-09-28: the 1st and 2nd entries, 附近的公园 and 光辉中央公园,
                landed as 00 and 01).  Each record goes back at the `at` offset the export read it
                from -- the table routinely has empty records in the middle, and packing the list
                from record 1 would shift every booking after such a hole.  Records the list does
                not mention are cleared, because a cancelled booking keeps its 对象 byte and the
                game still counts it.
Everything else in the file (names, unconfirmed) is dumped for reference only.
Every write is followed by a re-sign of the slot's tag at 0xfda (see TAG below).  This is
insurance, not a fix for something observed here: snes9x loads a slot whose tag is stale
(proved 2026-09-27 by injecting one and continuing from it), while the emulator the user
plays on zeroed an edited slot on the next cold boot.  export→import of an unedited file is
still a byte-exact no-op, because an untouched slot already carries the tag its content asks
for; a slot saved by any other editor gets the right one written in.
Before a byte is written the slot's dates are proved against the calendar: 当前日期 must be a
Sunday between 1996-04-04 and 1999-03-01 (4/4 itself passes -- it is 开学第一天, a Thursday in
the real calendar), and every appointment must fall within 28 days AFTER that date.  The year of
当前日期 is in the save (0x1cd's high nibble, and the word at 0x036), so what the export prints is
what the bytes say; only a diary record's year is resolved, and the 28-day window pins it.  Dates
the YAML does not mention are checked too, because changing 当前日期 can push a booking that is
already in the file out of the window.
--force turns every complaint into a warning.
Writes make `<存档>.srm.bak` from the pre-write bytes; --dry-run shows the byte diff only.

Slots are 4 KB apart.  The name lives twice (0x2b0/0x2b8 and 0x300/0x308) and so does the
date.  A slot whose field area is still all zero was never saved into and says nothing; so
does one whose 0xfda tag is zero, which is the shape a slot takes after an emulator wiped it.
The 01 00 02 00 … 0f 00 run at 0xfe2 is in every slot, saved or not, so it is
not the 没存过 marker.
Only fields whose identity is established get a name; the offsets that move between saves
without a proven meaning are dumped once, raw, under 身份未确认.
"""
import sys, os, re, hashlib, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import build_zh as B

STRIDE = 0x1000
ATTR = (0x00, ('体力', '文科', '理科', '艺术', '运动', '杂学', '容姿', '毅力', '压力'))
# The heroines in the order the engine numbers them.  0-9 proven from data: the four
# nonzero entries of a played slot are the same four indices as that slot's status bytes,
# and three of those four match the names read off that save's in-game phone book.
# 10 是早乙女优美——用户 2026-09-27 给的「女生对你的评价」表就是这 11 行（左列 0-4、右列
# 5-10），优美固定第 11 行。
GIRLS = ('藤崎诗织', '如月未绪', '纽绪结奈', '片桐彩子', '虹野沙希',
         '古式由加利', '清川望', '镜魅罗', '朝日奈夕子', '美树原爱',
         '早乙女优美')
N_REC = 11                           # the per-girl tables are ELEVEN records, not twelve:
                                     # the loops over $0C00/$0C16/$0C2C/$0C42 run `INX INX …
                                     # CPX #$0016`, and 0x16/2 = 11.  Five such arrays (好感度
                                     # 0x100, 0x116, 伤心度 0x12C, 登场 0x142, 约会次数 0x158)
                                     # end at 0x16d, which is exactly where the 约会 table
                                     # starts -- a twelfth record would overlap it.
                                     # 伊集院丽 therefore has no row here; index 11 used to be
                                     # labelled 丽 and was reading 0x158's first word instead.
                                     # 0x158 = the per-girl cumulative date count, now proved
                                     # (docs §十七.3): slot1 carries 诗织 2 / 虹野 2 and those are
                                     # exactly the two she-named girls that slot1 had met, the two
                                     # broken slot2s grow 诗织1 -> 诗织1+古式1, and the third-party
                                     # cheat table's `7E0C58` (= $0B00 + 0x158) entry is
                                     # 「与藤崎诗织的约会次数」.  Reported nowhere and written by
                                     # nothing -- it is read-only evidence, like 0x8e3.
AFFINITY = 0x100
PHONE = 0x142                        # (status, 0x80) per record; a real save carries four
                                     # statuses so far -- 00 (affinity is always 0 there), 01,
                                     # 09, 0f (and 03 in one 2026-09-27 probe save).
                                     # 「01 认识但没号码 / 0f 有号码」 was the reading before
                                     # 0x8e5 was found; it is falsified, so only 未登场 is
                                     # claimed and every other tier prints its byte.
                                     # 2026-09-28 watched one 01 -> 0f step in real play, in the
                                     # same fortnight she got her 通讯录 bit; the same day a
                                     # second girl appeared at 09 and is NOT in the book, while
                                     # 诗织 (affinity 51) stayed at 01.  So these are not one
                                     # shared progress ladder, and no rung means "has a number".
                                     # !! 这一格跟登场同步涨，但**不驱动通讯录**：实测把
                                     # slot2 的 index 1-10 全改成 0f，游戏里通讯录还是没有人。
                                     # 真正的闸门是下面 BOOK 那三字节（2026-09-27 找到）。
                                     # !! 引擎自己还另记一份「真登场」（0x8e3-0x8e4 那族比特，
                                     # 编号跟 BOOK 不同：片桐在簿上是比特 15、在这里是 0x8e4 的
                                     # 比特 6）。写 0x142 造不出那一格，
                                     # 详见 docs/research/phone-book.md §十二、§十三。
PHONE_TIER = {0x00: '未登场'}        # everything above it prints its own byte
BOOK = 0x8e5                         # 3 bytes / 24 bits -- who is listed in 通讯录.  Found via
                                     # docs/research/cheats-wikiwiki-snes007.md (`7E13E5-7E13E7
                                     # 写 FF ＝全员电话号码`; the save mirrors 1:1 into WRAM at
                                     # $0B00, so that cheat is save 0x8e5) and then measured bit
                                     # by bit: one probe value per run on a save that reaches
                                     # the book, names read off the screenshot.  Clearing these
                                     # bytes empties the book down to the three below; FF FF FF
                                     # fills it with all thirteen entries.
BOOK_BIT = {'如月未绪': 4, '纽绪结奈': 1, '片桐彩子': 15, '虹野沙希': 10,
            '古式由加利': 12, '清川望': 9, '镜魅罗': 8, '朝日奈夕子': 23,
            '美树原爱': 22, '早乙女优美': 6}          # bit 0 = low bit of byte 0x8e5
BOOK_UNGATED = ('藤崎诗织', '早乙女好雄', '伊集院丽')   # in the book with BOOK cleared
# The other 14 bits (0,2,3,5,7,11,13,14,16,17,18,19,20,21) do nothing to the book -- a played
# slot carries bits 5 and 21 set with no extra name, so they hold something else.  --import
# therefore only ever touches the ten bits above and leaves the rest of the field alone.
MET = 0x8e3                          # 2 bytes -- the engine's OWN 「真的遇见过谁」 list, which only
                                     # real play can set.  Two falsification controls: the
                                     # 1996-04-14 slot where we wrote 0x142 = 0f for 如月 by hand
                                     # reads 0x8e3 = 00, and the 1996-05-06 probe with 片桐／虹野／
                                     # 清川 all written 0f reads 0x8e4 = 00.  如月 getting her phone
                                     # number leaves this block untouched while 0x8e5 moves, so it
                                     # records meetings, not numbers.
MET_BIT = {'如月未绪': (0x8e3, 1),   # 42 slots agree (docs/research/phone-book.md §十二)
           '片桐彩子': (0x8e4, 6),   # two unrelated saves agree (§十三)
           '纽绪结奈': (0x8e4, 7),   # met on 1996-06-30 with no phone number (positive), and slot1
                                     # -- where she was never met -- reads 0x8e4 = 51, bit 7 clear
                                     # (negative).  §十五.
           '虹野沙希': (0x8e4, 4),   # met on the 古式／虹野 play line at 1996-05-26: 0x8e4 went
                                     # 06 -> 1e, so her bits are that new pair {3,4}.  The 4 is her
                                     # own, not the 3: slot1 carries 51 with 虹野 met and has 4 not 3.
                                     # §十六.
           '清川望': (0x8e4, 0)}     # first OBSERVED on 2026-09-28 (docs §十七): the 游泳部 sample took
                                     # 0x8e4 1e -> 1f, exactly bit 0 -- which is also what slot1's
                                     # arithmetic predicted (its three bits 0/4/6 over 片桐/虹野/清川).
                                     # Numbering is NOT the book's (片桐: book bit 15, here bit 6).
                                     # 古式 and 虹野 each lit TWO bits on their first appearance (古式
                                     # {1,2} on 1996-04-28, 虹野 {3,4} on 1996-05-26) while 如月/片桐/
                                     # 纽绪/清川 each lit one.  The reading 「a girl in the player's own
                                     # club lights an extra bit」 is DEAD: the user confirmed on
                                     # 2026-09-28 that all three of 古式/虹野/清川 showed up only after
                                     # he had joined their club and run it for two-three weeks, yet
                                     # 清川 lit one bit -- and slot1's 片桐 (player 美术部, her canon
                                     # club) likewise shows one, so that save is no longer a counter-
                                     # example either.  The extra bit now has NO explanation.  虹野's
                                     # own bit is settled (3 is not hers: slot1's 51 and the broken
                                     # 11-17 slot's 10 both carry 4 without 3); which of 1/2 is 古式's
                                     # still needs the subtraction test -- clear one of them on a /tmp
                                     # copy, cold-boot, and ask 好雄 about her (docs §十七).
                                     # (报告把这类对不上人的比特单列出来。)
                                     # Quitting does not clear it (1996-05-05: 0x0062 moved 7 -> 6 and
                                     # 0x8e4 stayed 06).  The former club number is NOT in 0x0062's
                                     # neighbourhood but does survive, in the quit mask at 0x066 below.
                                     # --import still does not write this block: a written bit has
                                     # never been shown to produce a real 登场.
CLUB = 0x062                         # 玩家社团的编号字；`ffff` = 还没入部（旧 slot2 那份就是）
QUIT_CLUBS = 0x066                   # 「退过的部」比特掩码，一个 16 位字，比特号＝下面 CLUBS 的行号。
                                     # 这就是 §十六 那句「存档里没留退过的部」的反例（2026-09-28 用户
                                     # 冷启动重读档，退出游泳部后发现网球／足球／游泳三个部都再也加不进去
                                     # ——那份历史一定在档里）。三族独立命中，外加三族恒 0 的对照：
                                     #   网球→足球（05-05）＝ 80（比特 7 网球），游泳线（06-30）＝ c0（6+7），
                                     #   篮球→戏剧（06-16）＝ 200（比特 9 篮球），
                                     #   在部里没退（04-28 网球、如月线 篮球）、slot1 美术一年没退、
                                     #   全新档和坏档那两份 ffff 全 0。
                                     # 退掉才置位，还在部里时那一位是 0，所以「被拒绝再加入」＝这一位
                                     # 加当前 0x0062 一起判。全档扫过：这一个字没有第二份（日期那种复制
                                     # 在这里不成立）。
                                     # 一年之后会不会自己清掉，四份样本都还在同一年里，没证。
CLUBS = ('文艺部', '戏剧部', '科学部', '美术部', '轻音乐部',
         '棒球部', '足球部', '网球部', '游泳部', '篮球部')
                                     # Order = the club-name pool in bank-$83 (build_zh.py's UI rows
                                     # 0x18831–0x18878, top to bottom = 编号 0–9).  Pinned by the
                                     # user's two changes on 2026-09-28: joining 篮球部 (last row of
                                     # that pool) wrote 9 into 0x0062, switching to 戏剧部 (second
                                     # row) wrote 1 -- same word, two independent points.
                                     # Only this word moves; what the game does with a written club
                                     # (schedule, attribute growth) has not been tested.
APPT, N_APPT = 0x16e, 16             # 16 x 4-byte records (day-1, month-1, 对象, 地点)
PLACE_NAMES = tuple(zh for _, _, zh in B.PLACE_TABLE)   # the record's 4th byte indexes this
                                     # 21-name 地点池 (the same table `$E802` selects from, in
                                     # that order).  Head pinned by the user's control on
                                     # 2026-09-28: 约了列表第 1、第 2 个地点 → 记录里是 00 和 01,
                                     # 而 PLACE_TABLE 头两项正是 附近的公园／光辉中央公园。
DATE = 0x1cc                         # 日-1, then 月-1 装在低半个字节、年序（年-1996）装在高半个
DATE2 = 0x036                        # 字节；同一个日子还另有第二份，三个 16 位字 (年序, 月-1, 日-1)。
                                     # 年序这一档是 2026-09-28 拿用户亲手玩到 1997 年的那份存档定的：
                                     # 盘中六个槽逐一看过，0x1cd 的高半个字节恒等于 0x036 那个字，
                                     # 1997-01-05 那一份两边都是 1；而 01-05 在真实公历上正是周日，
                                     # 跟「游戏用真历、存档日全是周日」那条独立观测对上了。
FIELD_END = 0x340                    # the diary/name fields above live under this; an
                                     # untouched slot is zero all the way to it.  BOOK (0x8e5)
                                     # is the one named field outside it -- 空槽在那儿也是零，
                                     # 所以判空只看这一段照样成立。
TAG = 0xfda                          # 槽位标记：在用的槽是 01 00 ＋两个字（0xfdc／0xfde），
                                     # 空槽这六字节全零。两个字是 [0,0xfdc) 这段 16 位字的
                                     # 两种求和（见 tag_words）：全求和、以及每第 4 个字求和。
                                     # 4 份存档 7 个槽（含一个全零的空槽）逐字节吻合，无一例外。
                                     # 但 snes9x 这条走查路径不校验它——2026-09-27 实测：把改过
                                     # 内容、校验字仍属旧内容的槽注入 SRA，加载画面照出数据，
                                     # 「请选择要开始的相册」照选中，SRAM 一个字节都没被清。
                                     # 用户那边的模拟器确实在冷启动后把改动过的 slot2 整槽清零
                                     # （0x000 起 537 字节归零，只剩 0xfe2 那串 01..0f），所以
                                     # 校验字按结构不变量对待：写回后照新内容重签，代价为零，
                                     # 防的是校验更严的那类模拟器，不是 snes9x。
                                     # 0xfe2 起那串 01 00 02 00 … 0f 00 每槽都有、存过没存过都一样，
                                     # 所以它不是「没存过」的记号；判空只看 0xfda。

NAMES = (('姓', 0x2b0, 4), ('名', 0x2b8, 4), ('姓·副本', 0x300, 4),
         ('名·副本', 0x308, 4), ('昵称', 0x310, 6))
# Offsets that move between saves but whose meaning is not established: raw values, printed
# as such and never written by --import.
# 0x118（0x116 那 11 个字里除第一格之外的那十格）在 1996-06-30 那份游泳部档里**十个同时** 0→3，
# 而那份只登场过三个人——所以这一族在没登场的女生身上不是她自己的进度，别当每人事件数读；
# slot1 那份是 14–20 各不同，坏档 11-17 是 3,1,1,1 挂在古式/清川/镜/朝日奈上。三种读法
# （她的兴趣／她对你的评价／某种全员初始化）都还没有判据。0x22e 在同一窗口里也一起变 3，
# 但那条不跟着社团走（如月线换了两个部它一直 0），所以也不是「入过几个部」。
UNCONFIRMED = ((0x042, 3, 'w'), (0x118, 10, 'w'), (0x1ae, 1, 'w'), (0x1ba, 9, 'w'),
               (0x22e, 1, 'w'), (0x370, 6, 'w'),
               (0x15a, 1, 'b'), (0x160, 1, 'b'), (0x264, 1, 'b'))
# Regions whose text the localization rewrote: the preset-name pool and block 144.
VERSION_PROBE = ((0x1F890, 0x1FA40), (0x22F000, 0x22F2D4))
# The calendar the writes are proved against.  当前日期 carries its year (see DATE), but a diary
# record only carries day and month, so a booking's year is still resolved -- trivially now,
# because it has to fall in the 28 days after 当前日期.  The game uses the real Gregorian week:
# every played day and every booked day on disk (96/4/7, 96/10/13, 96/12/29 / 4/14, 10/20,
# 10/27, 11/3, and 97/1/5) is a real Sunday.
TERM = (datetime.date(1996, 4, 4), datetime.date(1999, 3, 1))    # 开学第一天 – 毕业典礼
WEEK = '一二三四五六日'
SUNDAY = 6
APPT_WINDOW = 28


def tag_words(b):
    """The two words a slot carries at 0xfdc/0xfde, computed over the words that precede them.

    Proven against 7 slots from 4 saves (two images, plus one slot an emulator had wiped):
    `0xfdc` is the 16-bit sum of all little-endian words in [0x000, 0xfdc), and `0xfde` is
    the same sum taking every fourth word.  The range already covers the `01 00` in-use flag.
    It is a structural invariant, not a proven load gate: snes9x shows a slot whose words are
    stale.  See TAG.
    """
    w = [int.from_bytes(b[i:i + 2], 'little') for i in range(0, TAG + 2, 2)]
    return sum(w) & 0xffff, sum(w[::4]) & 0xffff


def span_text():
    return '%04d-%02d-%02d–%04d-%02d-%02d' % (
        TERM[0].year, TERM[0].month, TERM[0].day, TERM[1].year, TERM[1].month, TERM[1].day)


HEADER = (
    '心跳回忆 .srm 存档导出 -- tools/tokimeki_srm_util.py --export（本文件与存档同名，加 .yaml 后缀）',
    '--import 后面给这份 YAML 或者给存档本身都行：给存档就读它旁边这份，同一个规则不用写两遍路径。',
    '导入只认 date／attributes／club／affinity／visibility／phone_book／appointments 这七个键，'
    '没写的键不动；后五张表都是「一行一个键」，只写你要改的那几行就行，没写的原样留着。',
    '三张女生表的键就是屏幕上那十一个名字，行序也跟引擎下标一致（好感度／登场／通讯录共用同一个顺序，'
    '约会记录里的 girl 也用它）：' + '／'.join(GIRLS) + '。'
    '（伊集院丽不在这些表里——那几张表每条只有 11 项，第五条正好停在约会表 0x16e 上。）',
    'date 写成 年-月-日（比如 1997-02-12）；这一格在存档里存了两份，年份两份都带着：'
    '0x1cc（日）＋一个字节把月放在低半个字节、年序放在高半个字节，以及 0x036·0x038·0x03a '
    '三个字（年序, 月−1, 日−1；年序＝年份减 1996）。两份都是导入自己写、报告自己比，'
    '文件里只留 date 这一行。导出照字节印年份，不再按周日推；约会记录自己没有年，'
    '它的年按当前日期那 28 天窗口定。',
    'attributes＝0x00 起九个状态字（体力／文科／理科／艺术／运动／杂学／容姿／毅力／压力），'
    '一项一行。观测到过 容姿141、体力314，所以面板那个 100 不是这一格的上下限。',
    'club＝玩家社团，直接写部名（%s），或者写那张十项池的行号（0–%d），或者「还没入部」（字节 ffff）。'
    '这一格是 0x0062 那个编号字，编号＝社团名单池的行号：用户 2026-09-28 两次变更把它钉死了——'
    '参加篮球部（名单最后一项）时它是 9，换到戏剧部（第二项）时它是 1。'
    '导入只写这一格，入部带来的日程和属性成长它管不着，所以日志会明说「游戏认不认还没实测」。'
    % ('／'.join(CLUBS), len(CLUBS) - 1),
    '另外 0x066 那个字是**退过的部**（比特号＝上面同一张池子的行号，三族独立命中：'
    '网球→足球＝80、再加退到游泳＝c0、篮球→戏剧＝200；从没退过部的档全是 0，slot1 玩满一年也还是 0）。'
    '这就是「一年内不能重新加入退过的部」那一条的数据来源，所以导日志会在你写一个退过的部时点名提醒。'
    '工具只读不写它——清掉一位能不能真把那个部放开，没在游戏里试过。',
    'affinity＝0x100 起十一个 16 位字，一行一个人（上限按用户口径 999，超了照写但提醒）。',
    'visibility＝0x142 起十一个状态字节，一行一个人（0 未登场；1／3／9／15 都算已登场）。'
    '这一档**不是所有女生共用的一条进度梯**：同一份 1996-06-09 的档里诗织是 1（好感度已经 51）、'
    '片桐 9、如月 15，每一档到底管什么都还没证，报告因此把字节原样带着印。'
    '注意：实测这一格**不驱动通讯录**——全填 15 之后游戏里还是查不到人，要谁上簿子写 phone_book；'
    '自然玩出来的那份也一样，9 那一档的女生登场了却没上簿子。'
    '它管的是**出现在不出现**：用户 2026-09-28 说「没有登场，好雄那里是看不见的，所以无法选择问」，'
    '而坏档那一份十一条全能选，正是因为这一格被我们全写了 15。'
    '至于她到底算不算「真登场」，引擎另有一格，见下面那条。',
    'phone_book＝通讯录：一行一个人、值写 true／false。'
    '闸门是 0x8e5 起那三字节的 24 个比特，一个人名一个比特，'
    '但比特号跟引擎下标不成顺序，照 BOOK_BIT 那张实测表走——'
    '所以这一列才是编辑入口，那三个原始字节只在报告里印、不进这份文件。'
    '导入只动你写进来的那几行对应的比特，其余（存档里常看到比特 5 和 21 挂着）来路不明，原样留着。'
    '藤崎诗织没有比特可写（她和好雄／丽一样不看这三字节），给她 false 不产生字节、只会提示一句。',
    '真登场＝引擎自己另记的那份「遇见过谁」（0x8e3–0x8e4 两字节 16 个比特）。'
    '只在报告里印，不进这份文件、导入也不写：现在有五个人的比特号对得上——'
    '如月（0x8e3 比特 1）、片桐（0x8e4 比特 6）、纽绪（0x8e4 比特 7，'
    '1996-06-30 她登场那一刻亮的，slot1 里没登场所以这一位是 0）、'
    '虹野（0x8e4 比特 4，1996-05-26 她登场那一刻亮的）、'
    '清川（0x8e4 比特 0，1996-06-30 她登场把那格从 1e 推到 1f，只亮了这一位——'
    '这也正是 slot1 那三个比特减出来的预测，prediction 兑现了），'
    '剩下六个还没解。'
    '**0x8e4 的比特 0 和 4 已经分开了**：虹野 1996-05-26 登场把那格从 06 推到 1e（新亮比特 3 和 4），'
    '而 slot1 那份 51 里有 4 没 3、且虹野在那份里登场过——所以 4 是虹野的本位，剩下的 0 就是清川'
    '（清川这一位 2026-09-28 已经被她本人的登场直接证过）。'
    '旧的「比特 4 是古式」读法作废了：它靠的是「簿子没动所以是古式」，而纽绪这次登场簿子同样没动。'
    '**「一次登场点亮一位」这条在古式和虹野身上都没成立**：她俩各自登场时亮了**两位**'
    '（古式比特 1＋2、虹野比特 3＋4），而如月／片桐／纽绪／清川各只亮一位。'
    '当时那条「登场那一刻跟玩家同一个部就多亮一位」的解释，**已经被用户 2026-09-28 的证词否掉**：'
    '清川同样是入游泳部、跑了两三周社团指令之后登场的，却只亮一位——'
    'slot1 的片桐（玩家美术部＝她的设定部）也一样只有一位，从此不算反例，'
    '「入美术部 vs 遇片桐 谁在先」这个问题跟着作废。'
    '于是「多出来那一位」**目前没有任何解释**：虹野那一位已经拆开（比特 3 不是她的——'
    'slot1 的 51 和坏档 11-17 的 10 都是有 4 没 3），古式的 1 和 2 哪个是本位仍然没判据，'
    '清法是副本上分别清掉一位、再去好雄那里打听她（docs §十七）。'
    '退出社团不会把这两位清掉（1996-05-05 玩家换成足球部，古式那两位照挂）；'
    '而「退过哪个部」这件事**确实另有一格记着**：0x066 那个 bitmask（见上面 club 那段）。'
    '两组比特不重叠，所以这不是一个公用的开关。'
    '报告会把这类「挂着但没对上人」的比特单独列出来。'
    '而且**写上去算不算数从没实测过**。它跟 visibility 打架时导入会提醒一句——'
    '那份「打听谁都是如月」的坏档就是这一格只剩如月造成的。'
    '详见 docs/research/phone-book.md §十二–§十七。',
    '约会的 place 是记录第 4 字节＝约会地点在那张 21 项地点池里的下标（池子顺序照 build_zh.PLACE_TABLE，'
    '也就是 `⟦E802⟧` 挑名字用的同一张表）：0＝附近的公园、1＝光辉中央公园——用户 2026-09-28 就约了'
    '列表头两个地点，存档里正是 00 和 01。导入把你写的数原样写回，不写这个键就留着文件里那个字节。',
    '约会按导出里的 at 偏移写回原位，没列出来的记录清空；'
    '取消过的预约会留下对象字节，留着就是幽灵预约。',
    'names／unconfirmed／真登场那两字节是给人看的，一条一行摊开写，导入不碰。'
    '通讯录那三字节的十六进制连这份文件都不进：那是给机器的数，'
    '改它等于绕过人名这一列去猜比特。',
    'tag 是 0xfda 那六个字节（在用标记＋两个求和字）：只给人看，导入不读它——'
    '写回之后仪表按新内容自己重签。这两个字是槽位的结构不变量（7 个槽全吻合），'
    '但 snes9x 读档不校验它：拿旧标记的槽注入照样进游戏。重签是防校验严的模拟器。',
    '写之前过日历：date 要是 %s 之间的周日，%s 开学第一天例外（真实公历上是周四）；'
    '每条约会要落在 date 之后 %d 天之内（当天算，超一天就拒）。'
    % (span_text(), '1996-04-04', APPT_WINDOW),
)


# Slots carry a few fields the report shows and the YAML must not: hex bytes are evidence for a
# human comparing against a cheat code, and date_copy is the save's second copy of the same day --
# the tool writes both and the report compares them, but an editor only ever wants one date.
# --export drops these; --import never looked at them.
EYE_ONLY = ('phone_book_raw', 'date_copy', 'met', 'met_raw', 'quit_mask',
            'quit_clubs')            # quit_clubs 是只读的一栏：清掉一位能不能真把那个部放开，
                                     # 没在游戏里试过，所以 --import 不碰它（跟 0x8e3 那一族同一条规矩）


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
    """Only a container of scalars that is *empty or a list* goes on one line.

    Every mapping is expanded, one key per line, because that is what a player edits: 属性／
    好感度／登场／通讯录／姓名 all read as rows of `键: 值`.  A bare list of numbers is what is
    left over -- the 身份未确认 groups -- and those stay on one line because nobody edits them.
    """
    if isinstance(v, dict):
        return not v
    if isinstance(v, list):
        return all(_scalarish(x) for x in v)
    return False


def _scalarish(v):
    return not isinstance(v, (dict, list))


def _flow_line(v):
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(_scalar_out(x) for x in v) + ']'
    return '{' + ', '.join('%s: %s' % (_key_out(k), _scalar_out(val)) for k, val in v.items()) + '}'


DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
KEY_RE = re.compile(r'^(?!\d+$)[^\W]\w*$')   # 一个词：中日韩字或字母数字下划线，且不能全是数字
                                             # （0x042 那种偏移键一旦裸写，回读就成了整数 42）


def _scalar_out(v):
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    text = str(v)
    return text if DATE_RE.match(text) else _quote(text)


def _key_out(k):
    if isinstance(k, bool):
        return 'true' if k else 'false'
    if isinstance(k, int):
        return str(k)
    return str(k) if KEY_RE.match(str(k)) else _quote(k)


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


def place(i):
    """The 约会地点 a record's 4th byte selects -- the byte is this list's index."""
    return PLACE_NAMES[i] if i < len(PLACE_NAMES) else '第%d号' % (i + 1)


def club(i):
    """The player's club as an editable value -- 0x0062's word is that menu pool's row index.

    Names round-trip into --import, so an index the pool does not cover comes back as the number
    itself rather than a sentence the importer would choke on.
    """
    if i == 0xffff:
        return '还没入部'
    return CLUBS[i] if i < len(CLUBS) else i


def diary_rec(r):
    """One 4-byte diary record the way the player reads it: 月-日 对象 地点.  A record carries no
    year -- that lives with 当前日期 -- so this is month-day, unlike the exported 年-月-日."""
    if (r[0], r[1]) == (0xFF, 0xFF):
        return '空档'
    if not (1 <= r[1] + 1 <= 12 and 1 <= r[0] + 1 <= 31):
        return '月/日字节不对 %02x %02x' % (r[0], r[1])
    return '%02d-%02d %s %s' % (r[1] + 1, r[0] + 1, girl(r[2]), place(r[3]))


def words(b, off, n):
    return [int.from_bytes(b[off + 2 * i:off + 2 * i + 2], 'little') for i in range(n)]


def book_bits(b):
    """The 24 通讯录 bits at 0x8e5 as one integer (bit 0 = bit 0 of byte 0x8e5)."""
    return b[BOOK] | (b[BOOK + 1] << 8) | (b[BOOK + 2] << 16)


def book_flags(b):
    """Who is listed in 通讯录, as `人名: true／false` in engine order.

    One line per girl, keyed by the name the player reads on screen -- the shape that makes
    flipping someone into the book a single character.  The key order is the engine index order,
    which is also how affinity and visibility are keyed, so the three tables are the same list.
    诗织's line is always true: she has no bit, so that line is the export reporting she is
    there, not a knob.
    """
    v = book_bits(b)
    return {g: bool(g in BOOK_UNGATED or (g in BOOK_BIT and v >> BOOK_BIT[g] & 1))
            for g in GIRLS}


def met_flags(b):
    """The engine's own 「真的遇见过谁」 list, as far as its bits are decoded.

    Only the names in MET_BIT have a bit number that survives cross-checking, so this reports
    those and says nothing about the rest -- see MET_BIT above for why the block is read but
    never written.
    """
    return {g: bool(b[MET_BIT[g][0]] >> MET_BIT[g][1] & 1)
            for g in GIRLS if g in MET_BIT}


def book_dangling(raw):
    """Bits 0x8e5–0x8e7 carries that no name owns, from the report's own 「%02x %02x %02x」.

    A played slot routinely carries such bits (5, 21, and on the 游泳部 line 7), and they change
    nothing on the 通讯录 screen, so the report names them instead of letting the raw hex look like
    an undecoded name.
    """
    v = [int(x, 16) for x in raw.split()]
    known = set(BOOK_BIT.values())
    return ['比特 %d' % (8 * i + bit)
            for i, byte in enumerate(v) for bit in range(8)
            if byte >> bit & 1 and 8 * i + bit not in known]


def met_dangling(raw):
    """Bits the engine has lit that no decoded name owns, from the report's own 「%02x %02x」.

    The next bit number always comes out of a fresh sample's *unnamed* bits, so the report prints
    them rather than leaving every round to re-derive them from the raw hex by hand.
    """
    out = []
    for off, byte in zip((MET, MET + 1), (int(x, 16) for x in raw.split())):
        named = {bit for _, (o, bit) in MET_BIT.items() if o == off}
        out += ['0x%03x 比特 %d' % (off, bit) for bit in range(8) if byte >> bit & 1 and bit not in named]
    return out


def girl_lists(b):
    """The four per-girl views of one buffer, in the shape the report and the warnings read.

    read_slot publishes them; apply_slot re-derives them from the buffer it has just written, so
    the 「假登场」 check on the write side is the same computation as the one on the read side
    rather than a second copy that can drift.
    """
    return {'affinity': dict(zip(GIRLS, words(b, AFFINITY, N_REC))),
            'visibility': dict(zip(GIRLS, [b[PHONE + 2 * i] for i in range(N_REC)])),
            'phone_book': book_flags(b),
            'met': met_flags(b)}


def ghost_names(state):
    """Girls `0x142` lists as 登场 while the engine's own mask (0x8e3–0x8e4) has no bit for them.

    Every real meeting observed so far lights a bit in that mask (纽绪 on 1996-06-30 is the third
    such case), so a name that is 登场 here and absent there was put there by an editor.  That is
    the state the broken slot2 was left in, and 好雄's 打听 degrades on it: the menu offers whoever
    `0x142` lists, while the answer comes off the mask.  Girls whose bit number is still unknown
    cannot be judged either way, so they are never called ghosts.
    """
    return [g for g, on in state['met'].items() if state['visibility'].get(g) and not on]


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
    """Model dict for one slot -- what the report prints and --export writes.

    当前日期 comes straight out of the bytes, year included; only a diary record's year is
    resolved, against the slot's own date (see diary_date).
    """
    stored, calc = b[TAG:TAG + 6], tag_words(b)
    ok = list(calc) == [int.from_bytes(stored[2:4], 'little'),
                        int.from_bytes(stored[4:6], 'little')]
    if not b[:FIELD_END].strip(b'\x00'):
        return {'untouched': True}
    # A byte pair the calendar can't place (0x0d 月, 2/30) reads as None, not a crash:
    # this tool has to survive an odd save, and the report says where it came out blank.
    fmt = lambda dt: iso(dt) if dt else None
    now = dated(*day_bytes(b))
    copy = words(b, DATE2, 3)
    out = {'untouched': False,
           'tag': stored.hex(' ') + ('（校验一致）' if ok else
                                     '（标记还是旧内容的：按现在内容应为 %04x %04x）' % calc),
           'date': fmt(now),
           'date_copy': fmt(dated(copy[0], copy[1], copy[2])),
           'attributes': dict(zip(ATTR[1], words(b, ATTR[0], len(ATTR[1])))),
           'club': club(words(b, CLUB, 1)[0]),
           'quit_mask': words(b, QUIT_CLUBS, 1)[0],
           'quit_clubs': [CLUBS[i] for i in range(len(CLUBS))
                          if words(b, QUIT_CLUBS, 1)[0] >> i & 1]}
    names = {}
    for label, off, ncell in NAMES:
        text, cells = name(b, off, img.caps, ncell, img.pair)
        if text:
            names[label] = text
    out['names'] = names
    out.update(girl_lists(b))
    out['phone_book_raw'] = '%02x %02x %02x' % (b[BOOK], b[BOOK + 1], b[BOOK + 2])
    out['met_raw'] = '%02x %02x' % (b[MET], b[MET + 1])
    out['appointments'] = [{'at': '%03x' % o,
                            'date': fmt(diary_date(b[o + 1] + 1, b[o] + 1, now)),
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
    print('  槽位标记   0xfda %s%s' % (s['tag'],
          '' if '一致' in s['tag'] else '——snes9x 不校验这个，照样能读进来；校验严的模拟器会清槽'))
    if not d:
        print('  日期       0x1cc 那两个字节（日／月＋年序）拼不出一份真日期（0x036 那份是 %s）' % c)
    else:
        dt = datetime.date.fromisoformat(d)
        print('  日期       %s（星期%s%s，%s：0x1cc 日／月＋年序，0x036·0x038·0x03a 年·月·日，'
              '都是 0 基，年份＝年序＋1996）'
              % (d, WEEK[dt.weekday()],
                 '' if TERM[0] <= dt <= TERM[1] else '，超出学制 ' + span_text(),
                 '两份一致' if c == d else '两份不一致！0x036 那份是 %s' % c))
    print('  属性       ' + '  '.join('%s%d' % (k, v) for k, v in s['attributes'].items()))
    print('  社团       %s（0x0062 那个编号字＝那张十项池的行号）' % s['club'])
    extra = s['quit_mask'] >> len(CLUBS)
    print('  退过的部   %s（0x066＝%04x，比特号跟上面那张池子同号；退掉才置位，还在部的那一年里'
          '加不回去，所以这一位加上当前那个部＝被拒绝重入的那一批%s）'
          % ('、'.join(s['quit_clubs']) or '无（这份一次都没退过部）', s['quit_mask'],
             '；比特 10 以上还有 %04x，没解' % extra if extra else ''))
    for label in ('姓', '名', '昵称', '姓·副本', '名·副本'):
        if s['names'].get(label):
            print('  %-9s %s' % (label, s['names'][label]))
    print('  好感度     ' + '  '.join('%s=%d' % (g, v) for g, v in s['affinity'].items()))
    print('  登场       %s（这格只说登场到哪一档；簿子上有没有她看守下面的通讯录）'
          % ('  '.join('%s=%s' % (g, PHONE_TIER.get(t) or '已登场·%02x' % t)
                       for g, t in s['visibility'].items() if t)
             or '十一个女生都未登场（0x142 起全是 00）'))
    print('  通讯录     %s（0x8e5 %s；诗织／好雄／丽 不受这三字节管）'
          % ('、'.join(g for g, on in s['phone_book'].items() if on) or '空的',
             s['phone_book_raw']))
    bd = book_dangling(s['phone_book_raw'])
    if bd:
        print('             这一族还挂着对不上人名的比特：%s——簿子上没有多出来的人，'
              '它们管的是别的事，导入一律不碰（实测 5、21，游泳部那份另有 7）'
              % '、'.join(bd))
    met = [g for g, on in s['met'].items() if on]
    n = len(MET_BIT)
    print('  真登场     %s（0x8e3 0x8e4＝%s；这一族只有 %d 个人的比特号对得上，'
          '剩下 %d 个还没解，工具不写它）'
          % ('、'.join(met) or '一个都不在（%s 比特全 0）' % '/'.join(MET_BIT.keys()),
             s['met_raw'], n, len(GIRLS) - n))
    dang = met_dangling(s['met_raw'])
    if dang:
        print('             另外挂着没对上人的比特：%s——她第一次登场时新亮的那一位就是她的号；'
              '一次登场亮两位的事古式和虹野都出现过，可「跟玩家同部就多亮一位」那条解释已经被证词否掉'
              '（清川同部登场只亮一位），所以多出来那一位现在没有解释（§十六、§十七）'
              % '、'.join(dang))
    ghost = ghost_names(s)
    if ghost:
        print('             注意 登场里有 %s，可引擎自己那份「真登场」没登记——这种「假登场」'
              '多半是写出来的，好雄打听会退化' % '、'.join(ghost))
    booked = s['appointments']
    print('  约会       ' + ('  '.join('%s %s 地点 %s[%s]'
                                       % (a['date'] or '日期推不出', girl(a['girl']),
                                          place(a['place']), a['at'])
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

def girl_ref(value):
    if isinstance(value, int):
        if not 0 <= value < N_REC:
            raise ValueError('下标要在 0–%d（给了 %d）' % (N_REC - 1, value))
        return value
    text = str(value).strip()
    if text in GIRLS:
        return GIRLS.index(text)
    raise ValueError('不认识的名字「%s」，可写：' % text + '、'.join(GIRLS)
                     + '，或者下标 0–%d' % (N_REC - 1))


def _as_int(value, label):
    """int() with the field's name in the complaint, so `压力: 七` says which line is wrong."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError('%s 要的是数字（给了「%s」）' % (label, value))


def _byte_at(b, off, value, label, changes, lo=0, hi=255):
    v = _as_int(value, label)
    if not lo <= v <= hi:
        raise ValueError('%s 要在 %d–%d 之间（给了 %s）' % (label, lo, hi, value))
    if b[off] != v:
        changes.append('0x%03x  %02x→%02x  %s' % (off, b[off], v, label))
        b[off] = v


def _word_at(b, off, value, label, changes, hi=0xFFFF):
    v = _as_int(value, label)
    if not 0 <= v <= hi:
        raise ValueError('%s 要在 0–%d 之间（给了 %s）' % (label, hi, value))
    now = int.from_bytes(b[off:off + 2], 'little')
    if now != v:
        changes.append('0x%03x  %d→%d  %s' % (off, now, v, label))
        b[off:off + 2] = v.to_bytes(2, 'little')


# ---------------------------------------------------------------- calendar

def iso(dt):
    return '%04d-%02d-%02d' % (dt.year, dt.month, dt.day)


def parse_date(value, label):
    """`1997-02-12` -> a date.  One format on both sides, so a typo says so plainly."""
    hit = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', str(value).strip().strip('"'))
    if not hit:
        raise ValueError('%s要写成 年-月-日（比如 1997-02-12），给了「%s」' % (label, value))
    y, mo, da = (int(hit.group(i)) for i in (1, 2, 3))
    try:
        return datetime.date(y, mo, da)
    except ValueError:
        raise ValueError('%s %s 没有这么一天' % (label, value))


def candidates(m, d):
    """Every day in the school term that this month/day could be, oldest first."""
    out = []
    for y in range(TERM[0].year, TERM[1].year + 1):
        try:
            dt = datetime.date(y, m, d)
        except ValueError:                 # 2/29 in a common year
            continue
        if TERM[0] <= dt <= TERM[1]:
            out.append(dt)
    return out


def dated(yo, mo, da):
    """The 年-月-日 behind the save's 0-based triple (年序, 月-1, 日-1), or None on a bad byte.
    年序 counts years from 1996 -- see DATE for the control that fixed it."""
    if not 0 <= yo <= 0x0F or not 1 <= mo + 1 <= 12 or not 1 <= da + 1 <= 31:
        return None
    try:
        return datetime.date(1996 + yo, mo + 1, da + 1)
    except ValueError:                     # 2/30 -- the game never writes one, an edited file might
        return None


def day_bytes(b):
    """The slot's own (年序, 月-1, 日-1), unpacked from 0x1cc/0x1cd."""
    return b[DATE + 1] >> 4, b[DATE + 1] & 0x0F, b[DATE]


def guess_date(m, d, after):
    """What year a bare month/day means, by the Sunday rule: the same month/day lands on a
    different weekday in each of 1996/1997/1998, so the term usually holds one Sunday for it.

    Only a diary record needs this -- 当前日期 carries its year in the save -- and only when the
    28-day window leaves no answer, which is a save that already reads as broken.  `after` is the
    slot's own date: a booking means something only relative to the day it was made on.
    """
    cands = candidates(m, d)
    if not cands:
        return None
    sundays = [c for c in cands if c.weekday() == SUNDAY]
    if (m, d) == (TERM[0].month, TERM[0].day):
        sundays.append(TERM[0])            # 开学第一天，真实公历上是周四——玩家指定的例外
    pool = sundays or cands
    ahead = [c for c in pool if c >= after]
    return min(ahead or pool, key=lambda c: abs((c - after).days))


def diary_date(mo, da, now):
    """The 年-月-日 a diary record means.  A record carries only day and month, so the year comes
    from 当前日期 -- and a booking is by definition in the 28 days after it, which pins the year
    (the user's 1997 control: 当前日期 1997-01-05 上约的日子读成 1997 年, 不是 1996 年)."""
    if now is None or not (1 <= mo <= 12 and 1 <= da <= 31):
        return None
    ahead = [c for c in candidates(mo, da) if now <= c <= now + datetime.timedelta(days=APPT_WINDOW)]
    return min(ahead) if ahead else guess_date(mo, da, after=now)


def slot_date(s, b):
    """The 当前日期 this slot ends up with: the YAML's if it gives one, else what the file holds."""
    if s.get('date'):
        return parse_date(s['date'], '当前日期')
    return dated(*day_bytes(b))


def slot_appts(s, b, now=None):
    """The diary dates the import leaves behind, as (标签, date) -- the YAML's list if it
    gives one (then the year is written out), otherwise what the file holds now."""
    listed = s.get('appointments')
    if listed is not None:
        return [('约会%d' % (i + 1), parse_date(a['date'], '约会%d' % (i + 1)))
                for i, a in enumerate(listed)]
    out = []
    for i, o in enumerate(range(APPT, APPT + 4 * N_APPT, 4)):
        if (b[o], b[o + 1]) == (0xFF, 0xFF):
            continue
        dt = diary_date(b[o + 1] + 1, b[o] + 1, now)
        if dt:
            out.append(('约会%d（文件里原有）' % (i + 1), dt))
    return out


def check_calendar(s, b):
    """Prove every date this slot ends up with.  Runs on the in-memory copy before a byte
    is committed, and covers dates the YAML never mentions -- a new 当前日期 can push a
    booking that is already in the file out of its 28-day window."""
    now = slot_date(s, b)
    notes = []
    if now is None:
        return (['当前日期（0x1cc 或 YAML 的 date）读不出合法的一天'], [])
    problems = []
    if now < TERM[0] or now > TERM[1]:
        problems.append('当前日期 %s 不在学制 %s 之内（开学前、毕业后）' % (iso(now), span_text()))
    elif now.weekday() != SUNDAY and now != TERM[0]:
        problems.append('当前日期 %s＝星期%s，不是周日（%d/%d 在学制里的周日是 %s）'
                        % (iso(now), WEEK[now.weekday()], now.month, now.day,
                           '、'.join(str(c.year) for c in candidates(now.month, now.day)
                                     if c.weekday() == SUNDAY) or '根本没有'))
    for label, dt in slot_appts(s, b, now):
        if not now <= dt <= now + datetime.timedelta(days=APPT_WINDOW):
            problems.append('%s %s 不在当前日期 %s 之后 %d 天之内（差 %+d 天）'
                            % (label, iso(dt), iso(now), APPT_WINDOW, (dt - now).days))
        elif dt.weekday() != SUNDAY:
            notes.append('%s %s（星期%s）不是周日' % (label, iso(dt), WEEK[dt.weekday()]))
    return problems, notes


def _by_name(given, keys, field, example='人名: 值'):
    """The one shape every per-row table uses: one `键: 值` line per row, and only the lines you
    write move a byte.

    Lists are not accepted -- the export writes this shape, a player edits one line at a time,
    and demanding all eleven rows would only make them count entries.  Rows come back in the
    table's own order, so the byte log reads the same however the file is ordered.
    """
    if not isinstance(given, dict):
        raise ValueError('%s按「%s」一行一个给（导出就是这个形状）' % (field, example))
    for name in given:
        if name not in keys:
            raise ValueError('%s没有「%s」这一行（可写：%s）' % (field, name, '／'.join(keys)))
    items = [(name, given[name]) for name in keys if name in given]
    if not items:
        raise ValueError('%s这一列什么都没写——要整项不碰就别写这个键' % field)
    return items


def _apply_book(b, given, changes):
    """Write 通讯录 from `人名: true／false`, one girl per line.

    Only the lines you write move a bit, so flipping someone into the book costs one character
    and leaves the rest of the roster -- and the fourteen unmeasured bits -- exactly as the save
    had them.  诗织 has no bit at all (she is listed whatever these bytes say), so her line gets
    a reminder rather than a silent no-op.
    """
    hit = known = 0
    for name, on in _by_name(given, GIRLS, '通讯录', '人名: true／false'):
        if not isinstance(on, bool):
            raise ValueError('通讯录 %s 要的是 true／false（给了「%s」；0／1／15 是登场那一格的档位，'
                             '不是通讯录）' % (name, on))
        bit = BOOK_BIT.get(name)
        if bit is None:
            if not on:
                changes.append('      提醒 %s 不在通讯录闸门里（她不靠这一格上簿子），'
                               'true／false 都不产生字节' % name)
        else:
            known |= 1 << bit
            if on:
                hit |= 1 << bit
    if not known:
        raise ValueError('通讯录这一列没有一个能落进闸门的行——藤崎诗织／早乙女好雄／伊集院丽'
                         '不靠这三字节上簿子，给她们 true／false 都不产生字节')
    new = (book_bits(b) & ~known) | hit
    for k in range(3):
        _byte_at(b, BOOK + k, (new >> (8 * k)) & 0xFF, '通讯录 0x%03x' % (BOOK + k), changes)


def _apply_attributes(b, given, changes):
    """Write the nine status words at 0x00..0x11 from `属性名: 数值`, one per line.

    No ceiling is asserted: a played slot reads 容姿141 and the user's own edited slot reads
    体力314, so 100 is at best a display convention, not the field's bound.
    """
    for label, value in _by_name(given, ATTR[1], '属性', '属性名: 数值'):
        _word_at(b, ATTR[0] + 2 * ATTR[1].index(label), value, '属性 %s' % label, changes)


def _apply_club(b, given, changes):
    """Write 玩家社团 as a club name (or its row number); `ffff` means 还没入部.

    The word is the row index of that ten-name pool, so a name is the honest key.  Only this word
    moves: what the game makes of a written club (its schedule, its attribute growth) has never
    been tested, so the log says so instead of claiming an入部.
    """
    want = given
    if isinstance(want, str) and want.strip() in ('还没入部', '未入部', '退出社团'):
        value = 0xffff
    elif isinstance(want, str) and want.strip() in CLUBS:
        value = CLUBS.index(want.strip())
    else:
        value = _as_int(want, '社团')
        if value != 0xffff and not 0 <= value < len(CLUBS):
            raise ValueError('社团编号 %d 不在那张十项池里（0–%d，或 65535＝还没入部；也可以直接写部名）'
                             % (value, len(CLUBS) - 1))
    before = len(changes)
    _word_at(b, CLUB, value, '社团 %s' % club(value), changes)
    if len(changes) > before:  # an unchanged club in the file is not a change we should comment on
        changes.append('      提醒 只写了 0x0062 这一格：入部带来的日程／属性成长都没动，'
                       '游戏里认不认这个部还没实测')
        if value != 0xffff and words(b, QUIT_CLUBS, 1)[0] >> value & 1:
            changes.append('      注意 这一位（%s）在 0x066 那张「退过的部」名单里，'
                           '游戏照理会拒绝重新加入；工具不清那一个字（清了能不能真加回去没实测过），'
                           '要试的话自己把 0x066 的比特 %d 抹掉' % (club(value), value))


def apply_slot(b, s, changes, force=False, notes=None):
    """Write the importable fields of one slot into `b`; `changes` collects the byte log.

    Calendar lines go to `notes` instead: a slot that ends up unchanged has no byte log to
    print, and 'this date is not a Sunday' is worth saying even then.
    """
    if notes is None:
        notes = changes
    if s.get('untouched'):
        return '这个槽位没存过，不写——半个档案不如不动'
    problems, found = check_calendar(s, b)
    notes.extend(found)
    if problems and not force:
        raise ValueError('日历校验没过：\n      ' + '\n      '.join(problems)
                         + '\n      （当前日期要的是学制 %s 之间的周日，4/4 开学第一天例外；'
                           '约会只能在它之后 %d 天内。确认要照写加 --force）'
                         % (span_text(), APPT_WINDOW)
                         + ('\n      ' + '\n      '.join(notes) if notes else ''))
    for line in problems:
        notes.append('提醒（--force 放行）%s' % line)
    date = s.get('date')
    if date:
        now = parse_date(date, '当前日期')
        m, d, yo = now.month - 1, now.day - 1, now.year - 1996
        if d > 30:
            raise ValueError('当前日期 %s 的日超过了存档里观测到的 1–31' % iso(now))
        if not 0 <= yo <= 0x0F:
            raise ValueError('当前日期 %s 离 1996 太远，装不进 0x1cd 那半个年序字节（0–%d，给了 %d）'
                             % (iso(now), 0x0F, yo))
        _byte_at(b, DATE, d, '日期 0x1cc 日', changes)
        _byte_at(b, DATE + 1, yo * 16 + m, '日期 0x1cc 月＋年序 %d' % yo, changes)
        for off, value, label in ((DATE2, yo, '日期 0x036 年序'),
                                  (DATE2 + 2, m, '日期 0x038 月'),
                                  (DATE2 + 4, d, '日期 0x03a 日')):
            if b[off + 1]:
                changes.append('0x%03x  跳过 %s：那一字高位不是 0（%02x %02x），照写会挪位'
                               % (off, label, b[off], b[off + 1]))
                continue
            _word_at(b, off, value, label, changes, hi=255)
    if s.get('attributes') is not None:
        _apply_attributes(b, s['attributes'], changes)
    if s.get('club') is not None:
        _apply_club(b, s['club'], changes)
    if s.get('affinity') is not None:
        # Storage is a 16-bit word, so the field is not capped at 255: the user played 700
        # without trouble and rules the ceiling at 999 (at 200 the girl still does not blush,
        # so 255 cannot be the game's max).  Values over 999 are written but called out.
        for name, value in _by_name(s['affinity'], GIRLS, '好感度'):
            if _as_int(value, '好感度 %s' % name) > 999:
                changes.append('      提醒 好感度 %s＝%s，超过用户给的上限 999' % (name, value))
            _word_at(b, AFFINITY + 2 * GIRLS.index(name), value, '好感度 %s' % name, changes)
    if s.get('visibility') is not None:
        rows = _by_name(s['visibility'], GIRLS, '登场', '人名: 档位')
        for name, value in rows:
            _byte_at(b, PHONE + 2 * GIRLS.index(name), value, '登场 %s' % name, changes)
        # Same predicate as ghost_names, scoped to the names this file actually wrote: the report
        # already shows the slot's pre-existing mismatches, a write log should name its own.
        ghost = [name for name, value in rows
                 if value and name in MET_BIT and not b[MET_BIT[name][0]] >> MET_BIT[name][1] & 1]
        if ghost:
            changes.append('      提醒 登场写了 %s，可引擎自己那份「真登场」（0x8e3–0x8e4）里'
                           '没登记，好雄的打听会退化。那一族的比特工具不写——'
                           '写上去算不算真登场还没实测' % '、'.join(ghost))
    if s.get('phone_book') is not None:
        _apply_book(b, s['phone_book'], changes)
    if s.get('appointments') is not None:
        listed = s['appointments']
        if len(listed) > N_APPT:
            raise ValueError('约会记录最多 %d 条（给了 %d 条）' % (N_APPT, len(listed)))
        live = [o for o in range(APPT, APPT + 4 * N_APPT, 4)
                if (b[o], b[o + 1]) != (0xFF, 0xFF)]
        keep = set()
        for i, a in enumerate(listed):
            # Write each record back where the export found it.  A table with an empty record
            # in the middle is normal, and packing the list from record 1 shifts every booking
            # after that hole forward -- which is not what the player's diary says.
            o = APPT + 4 * i
            if a.get('at'):
                try:
                    o = int(str(a['at']), 16)
                except ValueError:
                    raise ValueError('约会%d 的 at=%r 不是个偏移' % (i + 1, a['at']))
            if (o - APPT) % 4 or not APPT <= o < APPT + 4 * N_APPT:
                raise ValueError('约会%d 的 at=%r 不是记录起点（0x%x 起、每条 4 字节）'
                                 % (i + 1, a.get('at'), APPT))
            if o in keep:
                raise ValueError('约会%d 的 at=0x%03x 跟前面某条撞了' % (i + 1, o))
            keep.add(o)
            dt = parse_date(a['date'], '约会%d' % (i + 1))
            m, d = dt.month - 1, dt.day - 1
            if d > 30:
                raise ValueError('约会%d 的 %s：日超过了存档里观测到的 1–31' % (i + 1, iso(dt)))
            old = bytes(b[o:o + 4])
            mine = []                          # 一条记录＝玩家眼里的一次约会，所以按记录报，
            _byte_at(b, o, d, '约会%d 日 0x%03x' % (i + 1, o), mine)
            _byte_at(b, o + 1, m, '约会%d 月 0x%03x' % (i + 1, o + 1), mine)
            _byte_at(b, o + 2, girl_ref(a['girl']), '约会%d 对象 0x%03x' % (i + 1, o + 2), mine,
                     0, N_REC - 1)
            _byte_at(b, o + 3, a.get('place', b[o + 3]),
                     '约会%d 地点 0x%03x' % (i + 1, o + 3), mine, 0, len(PLACE_NAMES) - 1)
            if mine:
                new = bytes(b[o:o + 4])
                changes.append('约会%d 0x%03x  %s → %s（%s）'
                               % (i + 1, o, diary_rec(old), diary_rec(new),
                                  '、'.join('0x%03x %02x→%02x' % (o + k, old[k], new[k])
                                            for k in range(4) if old[k] != new[k])))
        for o in [x for x in range(APPT, APPT + 4 * N_APPT, 4) if x not in keep]:
            if (b[o], b[o + 1]) == (0xFF, 0xFF):
                continue      # already empty: leave its stale 对象 bytes exactly as they are
            old = bytes(b[o:o + 4])
            changes.append('清空 0x%03x  %s → 空档（%s）'
                           % (o, diary_rec(old),
                              '、'.join('0x%03x %02x→ff' % (o + k, old[k])
                                        for k in range(4) if old[k] != 0xFF)))
            for k in range(4):
                b[o + k] = 0xFF
        if len(live) > len(keep):
            changes.append('      约会表原有 %d 条，导入只列 %d 条，其余已清空'
                           '（取消的预约会留下对象字节，留着就是幽灵预约）' % (len(live), len(keep)))
    return None


def resign(b, changes):
    """Re-sign the 0xfda tag after the fields moved.

    The two tag words cover [0x000, 0xfdc), so any write to a date, a 好感度, a 登场 byte or
    the 约会 table invalidates them.  Keeping them consistent costs nothing and an unchanged
    slot re-signs to itself, so this can ride along with every write.  It is NOT known to be
    required here: a slot injected with a stale tag loaded fine on snes9x (see TAG).  The one
    wipe we saw -- an edited slot zeroed on the next cold boot -- happened on the emulator
    the user plays on, which this trace environment cannot stand in for.
    """
    if not any(b[:FIELD_END]) and not b[TAG:TAG + 6].strip(b'\x00'):
        return                                   # 空槽：全零就是「没存过」的样子，别给它造标记
    old = bytes(b[TAG:TAG + 6])
    if not int.from_bytes(old[:2], 'little'):
        b[TAG:TAG + 2] = b'\x01\x00'             # 标记得先落下，它在校验区间里
    w1, w2 = tag_words(b)
    b[TAG + 2:TAG + 6] = bytes([w1 & 0xFF, w1 >> 8, w2 & 0xFF, w2 >> 8])
    if bytes(b[TAG:TAG + 6]) != old:
        changes.append('0x%03x  %s→%s  槽位标记重签（内容改了标记就得跟着改；snes9x 不校验它，'
                       '校验严的模拟器会清槽）'
                       % (TAG, old.hex(' '), bytes(b[TAG:TAG + 6]).hex(' ')))


def stage_save(path, slots, force=False):
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
        note = apply_slot(b, s, changes, force, notes)
        if not note:
            resign(b, changes)
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


def import_target(arg, paths):
    """What `--import` names: the export YAML, or the save itself.

    The save case is the same rule --export writes by, so `--import 存档.srm` means
    「把存档旁边那份 `存档.srm.yaml` 写回这个存档」 and only needs the YAML spelled out when it
    lives somewhere else.  Decided by what is on disk, not by guessing at the bytes: an existing
    `<arg>.yaml` sibling makes `arg` the save, otherwise `arg` is the dump."""
    if arg.endswith('.yaml'):
        return arg, paths
    sibling = arg + '.yaml'
    if arg.endswith('.srm') or os.path.exists(sibling):
        if not os.path.exists(arg):
            raise ValueError('%s: 没有这个文件（--import 要给存档，或者给一份 YAML）' % arg)
        if not os.path.exists(sibling):
            raise ValueError('%s 旁边没有 %s：先导出。\n'
                             '  python3 tools/tokimeki_srm_util.py --export %s\n'
                             '（几个存档一起 --export 时，那一份只落在第一个旁边，'
                             '这种就把 YAML 的路径显式写给 --import）'
                             % (arg, os.path.basename(sibling), arg))
        return sibling, [arg] + list(paths)
    return arg, paths


def load_dump(path):
    """Read the export back.  A save reaches here only when it has no sibling export --
    import_target would have taken that one -- so all this can advise is: export it first."""
    with open(path, 'rb') as f:
        blob = f.read()
    try:
        return yaml_load(blob.decode('utf-8'))
    except UnicodeDecodeError as e:
        # 存档就是 4 KB 槽位的整数倍，导出文件不会是——光凭这一点就够认出递过来的是存档
        if not (len(blob) >= STRIDE and len(blob) % STRIDE == 0):
            raise ValueError('%s 不是 UTF-8 文本（第 %d 字节 %02x 读不出字符）'
                             % (path, e.start + 1, blob[e.start]))
        raise ValueError(
            '%s 是一份 .srm 存档（%d 字节＝%d 个 4 KB 槽位，第一个非文本字节在第 %d 个），'
            '它旁边也没有导出的 YAML。先跑：\n'
            '  python3 tools/tokimeki_srm_util.py --export %s'
            % (path, len(blob), len(blob) // STRIDE, e.start + 1, path))


def run_import(dump, paths, dry_run, force=False):
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
        staged.append((ap,) + stage_save(ap, slots, force))   # 校验在这里做完，一个字节都还没写
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
    ap.add_argument('--out', help='YAML 落点，默认就写在第一个存档旁边，同名加 .yaml 后缀')
    ap.add_argument('--import', dest='do_import', metavar='YAML|存档.srm',
                    help='照 YAML 写回日期／属性／好感度／登场／通讯录／约会；也可以直接给存档，'
                         '那就照导出的规则读它旁边同名加 .yaml 后缀的那份')
    ap.add_argument('--dry-run', action='store_true', help='配合 --import：只打字节差异')
    ap.add_argument('--force', action='store_true',
                    help='配合 --import：日历校验只提醒，照样写')
    a = ap.parse_args(argv)
    if a.do_import and a.export:
        ap.error('--import 和 --export 各管一头，不要一起给')
    try:
        return _run(a, ap)
    except ValueError as e:
        # 一个坏值不该甩 traceback，更不该写半个存档出去（写在 stage 之后）
        print('%s: %s' % (type(e).__name__, e) if type(e) is not ValueError else e)
        return 1
    except (KeyError, OSError) as e:
        print('%s: %s' % (type(e).__name__, e))
        return 1


def _run(a, ap):
    if a.do_import:
        dump_path, saves = import_target(a.do_import, a.srm)
        if dump_path != a.do_import:
            print('--import 给的是存档，照导出的规则读它旁边的 %s' % os.path.basename(dump_path))
        run_import(load_dump(dump_path), saves, a.dry_run, a.force)
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
        out = a.out or os.path.abspath(a.srm[0]) + '.yaml'
        for entry in dumps:
            for s in entry['slots']:
                for k in EYE_ONLY:
                    s.pop(k, None)
        with open(out, 'w', encoding='utf-8') as f:
            f.write(yaml_dump({'export': 'tokimeki-srm', 'version': 1, 'saves': dumps}, HEADER))
        print('\n导出 %s（%d 个存档）' % (out, len(dumps)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
