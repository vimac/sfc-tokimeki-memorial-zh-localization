"""Build the Chinese prologue patch (block 144) of rom_original_japanese.sfc.

Model -- every part of it is proven by the byte-exact reconstruction assert in
Codec.walk() and by the disassembly documented in docs/research/glyph-addressing.md:

  * The block is a linear stream of atoms: glyph codes (1 byte SB table code or
    2 byte K2 code), control bytes, name markers ($12 surname / $13 given name),
    opaque variable codes and phrase/sub macros.
  * Each macro body is parsed over its exact byte span (up to the next offset in
    the same table), so its whole text and every layout code it emits are known.
  * Macro bodies are terminated by $0A, whose handler at $80:CC2B is
    `PLA / BNE+1 / RTL / STA $B4 / PLA / STA $B6 / JMP $CA6D`: it pulls back the
    cursor the call pushed at $80:CAA6 (phrase) or $80:CAC6 (sub-text).  The
    dispatcher pre-empts every top-level parse with `PEA #$0000` at $80:CA6A, so
    a top-level $0A pulls that zero word and RTLs instead.  Body-internal $0A
    bytes therefore must NOT be copied into the main stream -- writing them
    inline pops a level that was never pushed and re-points the reader, which is
    how an earlier attempt drifted into the endless loop over one Japanese word.
  * Re-encoding preserves the control stream byte-for-byte: the Chinese text
    replaces the Japanese text, every control byte is copied at its own position.
  * Space.  Block 144 owns file 0x22f1ab..0x22fa1f (2164 bytes) and the next
    block starts immediately after it, so the Chinese stream has to fit those
    bytes: the whole 4 MB image is mapped (every bank $80-$FF holds data) and
    the longest constant run in it is 1270 bytes, so there is nowhere to move
    to.  Measured, a fully literal Chinese encoding needs 2547 bytes, because a
    hanzi costs two bytes through the $F0 band while Japanese spends one byte on
    each kana.  Two levers close the gap, and both are size-neutral for
    Japanese:
      - the $40-$9F band becomes a Chinese *code page*.  Its 96 table entries at
        file 0x18000 are 0xF000|glyph-index words: 71 kana, 15 frequent kanji
        and 10 punctuation marks.  The 71 kana entries are retargeted at the
        WenQuanYi slots of the 71 most frequent Chinese characters, which makes
        each of their ~700 writes 1 byte instead of 2.  The kanji and
        punctuation entries stay exactly as they are, so every folded Japanese
        macro still draws what it drew before;
      - the folded Japanese macros, reused only when the Chinese characters
        there map onto the very slots the Japanese body reads.
    What is NOT used any more: new $E8-$EF sub-macro calls.  The band looks
    like it has 699 spare indexes and 11 KB of unread macro body in bank $C3,
    but neither is free -- the sub pointer table really ends at index 0x578
    (everything above it is another structure, and the 0x21de00 area the earlier
    build filled is live data), and indexes the 145 blocks never mention are
    still reached dynamically by the variable/format codes ⟦E806⟧/⟦ECA5⟧.  The
    first build to write those table entries is what garbled the prologue and
    put it in an endless loop.  This patch therefore never writes the sub or
    phrase tables and never emits a macro call it invented.
  * Chinese glyphs are real WenQuanYi 14x14 records written into font slots that
    no text block, no name block and the kana-variant remap list reach, so the
    Japanese font is never rewritten and the rest of the game still renders.

usage: python3 tools/build_prologue.py [--dump|--stats|--patch]
"""
import sys, os, re, json, collections, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tmtext as T
import wqyfont as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROM = os.path.join(ROOT, 'rom_original_japanese.sfc')
OUT_ROM = os.path.join(ROOT, 'rom_prologue_zh.sfc')
BLOCK = 144
NEIGHBOR = 71                        # the block that follows in address order
END = 0x22FA1F                       # text_ptr(71): first byte past the block
# The new-game prompt that gates the prologue: the first two boxes of TEXT_PTRS
# block 0 (file 0x268000).  They are `$0A`-terminated script steps on the same
# kind of fixed grid, so only the content between the leading `$2E` pad and the
# terminator may change -- growing it pushes the second option's terminator off
# its offset and the engine rewinds into the first line.  The SB code page is
# global, so leaving them Japanese draws 乱码 here, and a player who cannot read
# this screen never reaches the translated prologue at all.
# (file offset, content bytes, Chinese text)
PROMPT = ((0x268001, 16, '从序章开始'), (0x268012, 14, '跳过序章'))
# The day-1 morning monologue 「明日から何をしようかな」 used to be patched here as a
# three-run overlay, because its middle is a `$EBBE` sub-text call whose body lives in
# bank $C3.  Block 8 is now translated as a whole, and its lines have enough room to
# drop that call instead of keeping it -- which is better, since the call would draw
# Japanese kana in the middle of a Chinese sentence.
CAPTION = ()
OVERLAY = PROMPT + CAPTION
# Every TEXT_PTRS block this patch rewrites, with the file offset one past its
# last translatable byte and the translation table it reads.  The SB code page is
# global, so all blocks are allocated, packed and written by one build: a block
# translated later would silently take back the one-byte codes an earlier one
# depends on.
#   8: the morning-monologue pool the day-start caption is drawn from, plus the
#      random telephone scenes.  It ends at 0x1E5E90 rather than at the next block
#      pointer because from there the stream is a `$01` branch table: those bytes
#      are runtime distance tables, not text (docs/research/control-codes.md).
#  144: the 序章.
#   0: the daily system / hint pool, and the two `$0A`-terminated script steps the
#      new-game prompt is drawn from.  Its 726 boxes tile all 14,778 bytes, so the
#      extent end is just the next block pointer; boxes 0 and 1 get written twice on
#      purpose -- once by this block, once by PROMPT below -- and both encode the
#      same two strings, so the later write only replaces bytes with bytes.
BLOCKS = ((0, 'block0_zh.txt', 0x26B9BA), (2, 'block2_zh.txt', 0x25FE05),
          (8, 'block8_zh.txt', 0x1E5E90), (32, 'block32_zh.txt', 0x27AC58),
          (35, 'block35_zh.txt', 0x1CAD18), (38, 'block38_zh.txt', 0x26D5E2),
          (18, 'block18_zh.txt', 0x25010F), (44, 'block44_zh.txt', 0x240A8A),
          (95, 'block95_zh.txt', 0x27A999), (107, 'block107_zh.txt', 0x1E82BB),
          (126, 'block126_zh.txt', 0x230527), (131, 'block131_zh.txt', 0x26D139),
          (132, 'block132_zh.txt', 0x23F2B4),
          (96, 'block96_zh.txt', 0x267494), (97, 'block97_zh.txt', 0x2303F4),
          (99, 'block99_zh.txt', 0x1C848B), (108, 'block108_zh.txt', 0x1E817B),
          (68, 'block68_zh.txt', 0x22F1AB), (21, 'block21_zh.txt', 0x25C385),
          (70, 'block70_zh.txt', 0x1E5171), (27, 'block27_zh.txt', 0x2071CE),
          (49, 'block49_zh.txt', 0x1DC337), (9, 'block9_zh.txt', 0x276A95),
          (14, 'block14_zh.txt', 0x2188b6),
          (6, 'block6_zh.txt', 0x1F6A32), (7, 'block7_zh.txt', 0x1DFAC1),
          (12, 'block12_zh.txt', 0x2506D8), (66, 'block66_zh.txt', 0x1F29B2),
          (72, 'block72_zh.txt', 0x223D7F), (83, 'block83_zh.txt', 0x24F769),
          (103, 'block103_zh.txt', 0x245C5D), (112, 'block112_zh.txt', 0x1D9A45),
          (137, 'block137_zh.txt', 0x2251E6), (92, 'block92_zh.txt', 0x1FF461),
          (46, 'block46_zh.txt', 0x27C4C9), (22, 'block22_zh.txt', 0x22BB97),
          (84, 'block84_zh.txt', 0x259740), (85, 'block85_zh.txt', 0x1D926C),
          (79, 'block79_zh.txt', 0x20B4E2), (67, 'block67_zh.txt', 0x21748D),
          (28, 'block28_zh.txt', 0x26CED4), (36, 'block36_zh.txt', 0x1D5325),
          (61, 'block61_zh.txt', 0x23899E), (57, 'block57_zh.txt', 0x1F23CB),
          (77, 'block77_zh.txt', 0x23AC35),
          (93, 'block93_zh.txt', 0x27D449), (54, 'block54_zh.txt', 0x27A87F),
          (76, 'block76_zh.txt', 0x2588F8), (139, 'block139_zh.txt', 0x230E38),
          (120, 'block120_zh.txt', 0x25A040), (51, 'block51_zh.txt', 0x27C8A2),
          (55, 'block55_zh.txt', 0x20BBC8), (109, 'block109_zh.txt', 0x27B68B),
          (116, 'block116_zh.txt', 0x218CC8), (62, 'block62_zh.txt', 0x1CDD3B),
          (122, 'block122_zh.txt', 0x207333), (123, 'block123_zh.txt', 0x1FF605),
          (125, 'block125_zh.txt', 0x26D298), (129, 'block129_zh.txt', 0x25FB95),
          (115, 'block115_zh.txt', 0x1D95B4), (113, 'block113_zh.txt', 0x1D5632),
          (111, 'block111_zh.txt', 0x1E8585), (50, 'block50_zh.txt', 0x23104F),
          (101, 'block101_zh.txt', 0x239E24), (104, 'block104_zh.txt', 0x218390),
          (114, 'block114_zh.txt', 0x26BD04), (15, 'block15_zh.txt', 0x250A51),
          (24, 'block24_zh.txt', 0x1E7B36),
          (71, 'block71_zh.txt', 0x22FFE2), (135, 'block135_zh.txt', 0x26EC90),
          (141, 'block141_zh.txt', 0x239FCE),
          (65, 'block65_zh.txt', 0x1CCAA5),
          (64, 'block64_zh.txt', 0x1FFFC5), (31, 'block31_zh.txt', 0x277D09),
          (42, 'block42_zh.txt', 0x207FD7), (134, 'block134_zh.txt', 0x26D6DC),
          (130, 'block130_zh.txt', 0x208184),
          (16, 'block16_zh.txt', 0x2157B7), (127, 'block127_zh.txt', 0x1D38C2),
          (128, 'block128_zh.txt', 0x27019D),
          (23, 'block23_zh.txt', 0x1F6C0A), (26, 'block26_zh.txt', 0x1D0008),
          (29, 'block29_zh.txt', 0x245E9B), (41, 'block41_zh.txt', 0x238C21),
          (47, 'block47_zh.txt', 0x1D7A88), (110, 'block110_zh.txt', 0x27AEA4),
          (3, 'block3_zh.txt', 0x1D58DC), (17, 'block17_zh.txt', 0x23F66A),
          (19, 'block19_zh.txt', 0x1EFA64), (74, 'block74_zh.txt', 0x257FBB),
          (5, 'block5_zh.txt', 0x1CA6D1), (69, 'block69_zh.txt', 0x23C95A),
          (4, 'block4_zh.txt', 0x27EF59), (30, 'block30_zh.txt', 0x211467),
          (37, 'block37_zh.txt', 0x22772D), (25, 'block25_zh.txt', 0x22A5B2),
          (40, 'block40_zh.txt', 0x1CF251), (20, 'block20_zh.txt', 0x275E9F),
          (33, 'block33_zh.txt', 0x1F3BD1), (34, 'block34_zh.txt', 0x233FE7),
          (10, 'block10_zh.txt', 0x1E970C), (39, 'block39_zh.txt', 0x261547),
          (43, 'block43_zh.txt', 0x1F93A3), (45, 'block45_zh.txt', 0x278F29),
          (88, 'block88_zh.txt', 0x1EB357),
          (60, 'block60_zh.txt', 0x1D2534), (48, 'block48_zh.txt', 0x251A55),
          (81, 'block81_zh.txt', 0x20CA2B), (80, 'block80_zh.txt', 0x24179D),
          (121, 'block121_zh.txt', 0x265E57), (78, 'block78_zh.txt', 0x267F0F),
          (75, 'block75_zh.txt', 0x24FFD8), (138, 'block138_zh.txt', 0x23DC39),
          (86, 'block86_zh.txt', 0x1CB46B), (63, 'block63_zh.txt', 0x2196A8),
          (89, 'block89_zh.txt', 0x1D10C2), (106, 'block106_zh.txt', 0x2723B8),
          (82, 'block82_zh.txt', 0x2091D9), (94, 'block94_zh.txt', 0x21E234),
          (53, 'block53_zh.txt', 0x272D41), (56, 'block56_zh.txt', 0x25CA5E),
          (100, 'block100_zh.txt', 0x2178D5), (52, 'block52_zh.txt', 0x1DA01B),
          (87, 'block87_zh.txt', 0x20E6A7), (140, 'block140_zh.txt', 0x279DD1),
          (105, 'block105_zh.txt', 0x24323D), (58, 'block58_zh.txt', 0x24BBE8),
          (73, 'block73_zh.txt', 0x22858C), (11, 'block11_zh.txt', 0x26E726),
          (143, 'block143_zh.txt', 0x247F7A),
          (102, 'block102_zh.txt', 0x2256C0),
          (136, 'block136_zh.txt', 0x1ED1A2),
          # block 133 dropped: its grid hit resolved lo/hi = 0x194ef/0x19e92, inside the
          # settings draw-script bank (BANK_TEXT_REGION).  Every real dialog block sits
          # >= 0x1c8000; 133 was the lone grid-scan false positive, and packing Chinese
          # over the panel's interleaved placement opcodes clobbered the save/options
          # screens (black-screen boot).  Those labels are owned by UI_TEXT_ROWS instead.
          (118, 'block118_zh.txt', 0x2644D1), (117, 'block117_zh.txt', 0x1E7FAB),
          (98, 'block98_zh.txt', 0x20032E), (119, 'block119_zh.txt', 0x22BEB1),
          (13, 'block13_zh.txt', 0x1DFFFD), (142, 'block142_zh.txt', 0x1DC865),
          (90, 'block90_zh.txt', 0x1EB7BD), (124, 'block124_zh.txt', 0x25FFD6),
          (91, 'block91_zh.txt', 0x27188B),
          (144, 'prologue_zh.txt', END))
# Which phrase ($B9) and sub-text ($C3) dictionary entries have a Chinese reading.
# Rows are key/cap/refs/japanese/chinese/bytes/fit; only key and chinese are read
# here, the rest is `tools/phrasedict.py` output kept for eyeballing.
PHRASE_GLOSSARY = os.path.join(ROOT, 'translations', 'phrase_glossary.tsv')

# The default player name.  The prologue's 〔姓〕/〔名〕 markers draw the WRAM buffers at
# $0E00 and $0E08.  Stock fills them two ways: `LDA #$xxxx` boot sites whose operands are
# the 2-byte text encodings themselves, and the preset-name table, from which the given
# name is drawn at random -- across cold boots the prologue introduced the player as
# 铃木一路 and once as 铃木ジョン.  Left alone both point at the *Japanese* font's
# records, which would leave the protagonist's name as kanji inside the translated
# prologue that WenQuanYi does not draw; and the three kana entries (さと / めも / ジョン)
# have no Chinese reading at all, so the whole pool is renamed, not just repaged.
# 一路 and friends keep their characters and only change font; 鈴 becomes 铃.
# Each pool record is 3 glyph slots plus the `$0A` end-of-step control, so a replacement
# name may be at most 3 characters and short names pad with the null glyph as stock does.
# (file offset, characters stock draws there, characters we want)
NAME_IMM = ((0x48f1, '鈴', '铃'), (0x48f9, '木', '木'), (0x28b54, '鈴', '铃'),
            (0x28b5c, '木', '木'), (0x28b74, '弦', '弦'))
# The pool is 32 records, not 24: sixteen surnames from $1F890 and sixteen given names
# from $1F900, and the boot draw is random over both.  Stopping the table at $1F8C8 left
# eight surnames on the Japanese font -- harmless-looking for the kanji ones, but the
# first is the game's own joke name ときめ (kana, so it has no Chinese reading at all and
# no WenQuanYi record), and it shows up on roughly one cold boot in sixteen as
# 「我叫ときめ英幸。」.  佟心 keeps the pun: 佟 sounds like とき and 心 is the 心跳 of
# 心跳回忆.
NAME_POOL = ((0x1f890, '青山', '青山'), (0x1f897, '安田', '安田'),
             (0x1f89e, '石原', '石原'), (0x1f8a5, '市原', '市原'),
             (0x1f8ac, '吉岡', '吉冈'), (0x1f8b3, '長谷川', '长谷川'),
             (0x1f8ba, '藤井', '藤井'), (0x1f8c1, 'ときめ', '佟心'),
             (0x1f8c8, '高上', '高上'), (0x1f8cf, '原田', '原田'),
             (0x1f8d6, '佐々木', '佐佐木'), (0x1f8dd, '鈴木', '铃木'),
             (0x1f8e4, '衛藤', '卫藤'), (0x1f8eb, '井上', '井上'),
             (0x1f8f2, '高橋', '高桥'), (0x1f8f9, '黒田', '黑田'),
             (0x1f900, '和浩', '和浩'), (0x1f907, '宣之', '宣之'),
             (0x1f90e, '一路', '一路'), (0x1f915, '景虎', '景虎'),
             (0x1f91c, 'さとし', '思远'), (0x1f923, '淳', '淳'),
             (0x1f92a, '秀徳', '秀德'), (0x1f931, 'めもる', '美玲'),
             (0x1f938, '浩一', '浩一'), (0x1f93f, '栄次郎', '荣次郎'),
             (0x1f946, 'ジョン', '建华'), (0x1f94d, '弦', '弦'),
             (0x1f954, '英幸', '英幸'), (0x1f95b, '秀登', '秀登'),
             (0x1f962, '紀三', '纪三'), (0x1f969, '信勝', '信胜'))
NAME_ROWS = NAME_IMM + NAME_POOL
NAME_SLOTS = 3
# The heroine name pool the `$E803`/`$E804`/`$E805` calls address.  All three opcodes
# carry their own 14-entry offset table (`01 <opcode> 0C <offsets>`, at file
# 0x21A2A6/0x21A2B7/0x21A2C8) and all three resolve to the *same* 14 records, so one
# edit per record fixes every call site.  Only the records' *starts* are load-bearing --
# each is a `$0A`-terminated run of 2-byte glyph codes, so a shorter Chinese name just
# leaves `$0A` behind itself and every later offset still lands.  詩織/紐緒/鏡/美樹原/
# 優美/館林 differ from the simplified forms and さん/ちゃん are kana with no Chinese
# reading at all, so those records cannot be fixed by a font swap.  さん/ちゃん/くん are
# rendered 同学/酱/君 (2026-09-20 ruling said 桑; user playtested and reverted to 同学 on
# 2026-09-21).  酱/君 cost one cell; 同学 costs the same two cells as the kana -- the
# records below are all *starts only*, so equal length means the table needs no offsets.
# The names themselves follow `reference/`: 紐緒=Himou->纽绪, 鏡=Kagami->镜,
# 美樹原=Mikihara->美树原, 優美=Yumi-chan->优美, as the Chinese fan translations have
# them.
NAME_POOL_TABLE = (
    (0x21A2D9, '詩織', '诗织'),          (0x21A2DE, '如月さん', '如月同学'),
    (0x21A2E7, '紐緒さん', '纽绪同学'),    (0x21A2F0, '片桐さん', '片桐同学'),
    (0x21A2F9, '虹野さん', '虹野同学'),    (0x21A302, '古式さん', '古式同学'),
    (0x21A30B, '清川さん', '清川同学'),    (0x21A314, '鏡さん', '镜同学'),
    (0x21A31B, '朝日奈さん', '朝日奈同学'), (0x21A326, '美樹原さん', '美树原同学'),
    (0x21A331, '優美ちゃん', '优美酱'),  (0x21A33C, '館林さん', '馆林同学'),
    (0x21A345, '伊集院', '伊集院'),      (0x21A34C, '良雄', '良雄'),
    (0x21A351, '外井', '外井'),
)
# The surnames the speaker nameplate actually draws come from this `$0A`-terminated
# list, which starts at file 0x180C0 -- the first byte free after the 96-word SB code
# table at 0x18000.  Re-pointing it is what lets the plate draw WenQuanYi without
# editing a single Japanese sentence: it holds names, not text.
SURNAME_TABLE = (
    (0x180C0, '藤崎', '藤崎'),    (0x180C5, '如月', '如月'),
    (0x180CA, '紐緒', '纽绪'),    (0x180CF, '片桐', '片桐'),
    (0x180D4, '虹野', '虹野'),    (0x180D9, '古式', '古式'),
    (0x180DE, '清川', '清川'),    (0x180E3, '鏡', '镜'),
    (0x180E6, '朝日奈', '朝日奈'), (0x180ED, '美樹原', '美树原'),
    (0x180F4, '早乙女', '早乙女'), (0x180FB, '伊集院', '伊集院'),
    (0x18102, '好雄', '好雄'),
)
# The 21 date locations the `$E802` call selects between at runtime -- the place the
# player just picked, spliced into sentences like 「⟦E800⟧に ⟦E802⟧へ 行かない？」.  Same
# shape as the heroine pool: `01 <wram-lo> <21 distances>` at file 0x21A1BF, with the
# distance for selector value V read at head+3+V and the record starting at head+dist,
# `$0A`-terminated (the byte before the first distance, 0x0B here, is never addressed --
# `$01` jumps from head+3).  So again only the starts are load-bearing.  The 22nd byte
# after the distances is `f4`, the lead of 近所の公園's first glyph, which is why a naive
# walk of this entry reads garbage: the records run to 0x21A2A6, well past the 53-byte
# "span" the pointer table reports for $E802.
# Wording is fixed by the location menu in the draw-script bank (`0X1A2EC`-`0X1A44D`),
# which is already translated: 电玩城/歌厅/泳池/溜冰场, so this pool must not invent a
# second name for the same place.  海 has room for one glyph only, and 月/日/年 in the
# date macros need no translation at all -- they are kanji we redraw in place.
PLACE_TABLE = (
    (0x21A1D7, '近所の公園', '附近的公园'),   (0x21A1E2, 'きらめき中央公園', '光辉中央公园'),
    (0x21A1F3, 'ショッピング街', '商业街'),   (0x21A202, '水族館', '水族馆'),
    (0x21A209, '動物園', '动物园'),           (0x21A210, '植物園', '植物园'),
    (0x21A217, 'プラネタリウム', '天文馆'),   (0x21A226, '美術館', '美术馆'),
    (0x21A22D, '図書館', '图书馆'),           (0x21A234, 'ゲームセンター', '电玩城'),
    (0x21A243, 'ボーリング場', '保龄球场'),   (0x21A250, 'カラオケ屋', '歌厅'),
    (0x21A25B, '遊園地', '游乐园'),           (0x21A262, 'スタジアム', '体育场'),
    (0x21A26D, '映画館', '电影院'),           (0x21A274, 'コンサート会場', '演唱会会场'),
    (0x21A283, 'プール', '泳池'),             (0x21A28A, '海', '海'),
    (0x21A28D, '神社', '神社'),               (0x21A292, 'スケート場', '溜冰场'),
    (0x21A29D, 'スキー場', '滑雪场'),
)
NAME_TABLE_ROWS = NAME_POOL_TABLE + SURNAME_TABLE + PLACE_TABLE
# ------------------------------------------------------------------ name entry
# The pre-prologue question/label strings.  They are not TEXT_PTRS blocks: they are
# short draw scripts -- a run of 2-byte glyph codes followed by the engine's own
# placement opcodes (`$02/$03/$07/$08/$0B`, not just `$0A`), which is why the text
# blocks' walk never reaches them.  Two consequences make this surface the cheapest
# one left:
#   * every character here is already a 2-byte glyph code, so localising it costs no
#     code-page byte at all (the $40-$9F band is 86/86 spent), only glyph records; and
#   * no offset table addresses them, so a run only has to keep its own code count --
#     the field's blank padding (index `$000`, `$F0 $00`) does that for a short line.
# Each row is (address, code count, stock text, Chinese text, pad side).  `ui_refs`
# showed the 80-code prompt box is right-aligned, so it is padded on the left.
UI_TEXT_REGION = (0x1F000, 0x1F2D4)
NICK_POOL = (0x1F970, 0x1FA40)      # 16 default nicknames, right after the preset names
# The album (save-file) menu, reached one screen *before* the name entry: 続き/初め and
# 写す/消す are the two option rows the boot walk answers, and アルバム titles its panel.
MENU_TEXT_REGION = (0x18560, 0x18800)
# The nine fortune slips the New-Year おみくじ draws (年の運勢は / 大吉だ！！ / …) sit in
# the same script bank, one row above that menu, and are drawn the same way.
# The status panel's eight affinity labels are the *same* strings in two tables: the
# panel itself (each label followed by the 0x155 mark glyph) and the list screen's tabs.
PANEL_TEXT_REGION = (0x18340, 0x183DC)
TAB_TEXT_REGION = (0x1AF80, 0x1B040)
# The label tables this bank still holds in Japanese (club list, date-spot map, event
# titles, the profile screens).
BANK_TEXT_REGION = (0x18800, 0x1A460)
# The school-festival arcade: nine mini-game cards and their instruction boxes, the
# stall keepers' lines and the 勇者マジラ play-within-the-game script.
FESTIVAL_TEXT_REGION = (0x1B040, 0x1C020)
# The date-planning and club prompts: what to do with a club, why a chosen day is no
# good, and the banners that open each term, holiday and school event.  They sit right
# behind the surname table, so they are the system messages a player reads most.
SYSTEM_TEXT_REGION = (0x18107, 0x18340)
# The sports-day / festival mini-games: the sub-game selector list and the rule screen of
# each of the four athletic events.
MINIGAME_TEXT_REGION = (0x1AB60, 0x1AF80)
# The sports-club show at the festival: each club's secret move and the lines the
# stall keepers shout around them.
CLUB_TEXT_REGION = (0x1C01A, 0x1C1D0)
# The culture-festival program selector (the stall-sketch list screen): it fills
# the gap between the club show and the play pool.
SELECTOR_TEXT_REGION = (0x1C1D0, 0x1C6E8)
# The sound-test menu the title screen hides behind it (sub-game, scenario, BGM and
# background selectors).  Its labels sit in the one gap the panel and album windows
# leave between $183DC and $18560.
SOUND_TEST_REGION = (0x18460, 0x18570)
# The calendar's month table: twelve 3-code entries between the panel and the sound
# test menu.  Note that a bank batch can only *spend* glyph slots: `allocate` reserves
# every index the STOCK image references, so re-pointing a label away never frees the
# Japanese index it used -- those letters were already pinned by the block text anyway.
MONTH_TABLE_REGION = (0x183E8, 0x18461)
# The festival script band: the light-music club's song card, the literature display's
# essays, the four classroom plays and the ending credits.  One window because it is one
# contiguous run of draw scripts; every row still checks its own stock decode.
PLAY_TEXT_REGION = (0x1C6E8, 0x1F000)
KEYBOARD_TEXT_REGION = (0x1F000, 0x1F890)   # name-entry keyboard pools
# Name cards, role labels and the credit roll of the two festival plays.  These
# windows are deliberately narrow -- the prose around them is still Japanese, and a wide
# window would let a stray edit there through the territory audit.
PLAY_LABEL_REGIONS = [(0x1C970, 0x1C97A), (0x1CB1B, 0x1CB25), (0x1D40A, 0x1D418),
                      (0x1D956, 0x1D960), (0x1E990, 0x1E9A0), (0x1EBF0, 0x1F000)]
# Reservation is over the *whole* bank, not just the window this batch translated: a
# label we have not touched yet still draws its own code, and if that code were also a
# Chinese slot the label would print the Chinese bitmap -- the 干字 defect again, one
# screen at a time.  Costs 113 slots and keeps `verify_bank_slots` provable.
BANK_ALL = (0x180C0, 0x20000)         # the whole draw-script bank, for the slot audit
UI_TEXT_REGIONS = (UI_TEXT_REGION, NICK_POOL, MENU_TEXT_REGION,
                   PANEL_TEXT_REGION, TAB_TEXT_REGION) + (BANK_ALL,)
# A row's text may hold this in place of a code that is not a character -- the panel's
# 0x155 affinity mark, for instance.  The stock code is then copied through untouched.
UI_KEEP = '\ue000'
K = UI_KEEP


def card(n, what):
    """A `〜ときめき★X〜` title card, redrawn from our own font cell by cell.

    The nine festival titles all open with `〜ときめき★` and close with `〜`; both marks
    are characters the patch already draws (the culture-festival cards use them), so the
    line writes them literally and the star lands on the same WenQuanYi record the
    Saotome lines use, instead of a second, Japanese-font star on the same screen.
    The Chinese label goes in the remaining cell, blank-padded, so the card keeps its
    width.
    """
    pad = n - 7 - len(what)
    assert pad >= 0, '%s does not fit a %d-code card' % (what, n)
    return '〜心跳  ★' + what + ' ' * pad + '〜'


UI_TEXT_ROWS = (
    (0x1F010, 80, 'あなたの名字を教えてくれる？', '可以告诉我你姓什么吗？', 'L'),
    (0x1F0B1, 4, '名前は？', '名字是？', 'R'),
    (0x1F0BA, 10, 'それじゃ、あだ名は？', '那么你的昵称叫什么呢', 'R'),
    (0x1F0CF, 13, '誕生日と血液型も教えてね？', '请告诉我你的生日和血型', 'R'),
    (0x1F0EA, 18, '藤崎詩織の誕生日と血液型は覚えてる？',
     '藤崎诗织的生日和血型你都还记得吗？', 'R'),
    (0x1F110, 6, 'これでいい？', '这样可以吗？', 'R'),
    (0x1F11E, 2, 'はい', '好的', 'R'),
    (0x1F124, 3, 'いいえ', '不太好', 'R'),
    (0x1F12B, 3, '名前：', '姓名：', 'R'),
    (0x1F13B, 4, 'あだ名：', '昵称：', 'R'),
    (0x1F14A, 2, '前頁', '上页', 'R'),
    (0x1F150, 2, '次頁', '下页', 'R'),
    (0x1F157, 2, 'かな', '平假', 'R'),
    (0x1F15D, 2, 'カナ', '片假', 'R'),
    (0x1F163, 2, '記号', '符号', 'R'),
    (0x1F16D, 2, '終了', '结束', 'R'),
    (0x1F172, 2, '漢字', '汉字', 'R'),
    (0x1F178, 4, '誕生日：', '生日：', 'R'),
    (0x1F190, 4, '血液型：', '血型：', 'R'),
    (0x1F1C6, 3, '誕生月', '出生月', 'R'),
    (0x1F217, 3, '誕生日', '生日', 'R'),
    (0x1F21E, 3, '血液型', '血型', 'R'),
    (0x1F23E, 2, '終了', '结束', 'R'),
    (0x1F244, 2, '名前', '姓名', 'R'),
    # the summary page that follows
    (0x1F254, 3, 'あだ名', '昵称', 'R'),
    (0x1F261, 3, '誕生日', '生日', 'R'),
    (0x1F277, 3, '血液型', '血型', 'R'),
    # (これでいい？ moved to UI_LINE_ROWS: its answer line ⟦0B⟧/いいえ is one record.)
    (0x1F29F, 2, '名前', '姓名', 'R'),
    (0x1F2A5, 2, '藤崎', '藤崎', 'R'),
    (0x1F2AB, 2, '詩織', '诗织', 'R'),
    (0x1F2B1, 3, '誕生日', '生日', 'R'),
    (0x1F2C7, 3, '血液型', '血型', 'R'),
    # The default-nickname choices the summary page draws: 16 x (6 codes + `$0A`) at
    # 0x1F970, i.e. a second preset-name pool right after the first, which is why the
    # summary read `昵称ツヨシさん` under a Chinese 昵称 label.  Kana honorifics have no
    # Chinese reading, so these are re-worded rather than re-pointed; the Chinese forms
    # follow `reference/`'s romanisations the same way the heroine pool does.
    (0x1F970, 6, 'シナモン博士', '肉桂博士', 'R'),
    (0x1F97D, 6, 'ツヨシさん', '阿强同学', 'R'),
    (0x1F98A, 6, 'Ｕジロー', '小次郎', 'R'),
    (0x1F997, 6, 'なかぢー', '阿中同学', 'R'),
    (0x1F9A4, 6, 'ヨッチ', '小耀同学', 'R'),
    (0x1F9B1, 6, '長作', '长作同学', 'R'),
    (0x1F9BE, 6, 'しゅうちゃん', '小秀酱', 'R'),
    (0x1F9CB, 6, '慎さん', '慎同学', 'R'),
    (0x1F9D8, 6, 'がみちゃん', '阿神酱', 'R'),
    (0x1F9E5, 6, '寅次郎', '阿寅同学', 'R'),
    (0x1F9F2, 6, 'ダーリン', '亲爱的', 'R'),
    (0x1F9FF, 6, 'げんさん', '阿元同学', 'R'),
    (0x1FA0C, 6, 'えとちゃん', '小江酱', 'R'),
    (0x1FA19, 6, 'テロリン', '小特同学', 'R'),
    (0x1FA26, 6, 'のりーん', '小诺同学', 'R'),
    (0x1FA33, 6, '兄貴', '大哥', 'R'),
    # The album / save menu one screen earlier.  写す and 消す each appear twice because
    # the copy and delete flows draw the same two options from two scripts.
    (0x18662, 2, '続き', '继续', 'R'),
    (0x18668, 2, '初め', '重来', 'R'),
    (0x1866E, 2, '写す', '复制', 'R'),
    (0x18674, 2, '消す', '删除', 'R'),
    (0x18679, 16, '始めるアルバムを選択して下さい。', '请选择要开始的相册。', 'R'),
    (0x1869A, 2, '写す', '复制', 'R'),
    (0x186A2, 2, '消す', '删除', 'R'),
    (0x186AA, 19, 'クリアー人数そのままで、初めからする。',
     '保持通关人数，从头开始玩。', 'R'),
    (0x186D2, 15, 'コピー側にデータが存在します。', '目标存档已经有数据了。', 'R'),
    (0x186F2, 13, '消去してもよろしいですか？', '确定要删除这个存档吗？', 'R'),
    (0x18716, 3, 'いいえ', '不复制', 'R'),
    (0x1871E, 17, 'このアルバムを消してもいいですか？', '真的要删掉这个存档吗？', 'R'),
    (0x1874A, 3, 'いいえ', '先不删', 'R'),
    (0x18751, 4, 'アルバム', '相册存档', 'R'),
    (0x1875F, 9, 'データがありません', '暂无数据', 'R'),
    (0x18772, 4, 'アルバム', '相册存档', 'R'),
    (0x187A9, 4, 'アルバム', '相册存档', 'R'),
    (0x187B7, 10, 'プロローグから始める', '从序章开始玩', 'R'),
    (0x187DB, 2, '名前', '姓名', 'R'),
    (0x187F4, 3, 'クラブ', '社团', 'R'),
    # the nine New-Year fortune slips, each a run ended by the script's own opcode
    (0x18576, 13, '（さて、今年の運勢は…。）', '（今年的运势是……）', 'R'),
    (0x18592, 10, 'おみくじを引きます。', '来抽运势签吧。', 'R'),
    (0x185AD, 9, 'うおりゃあああーー', '嘿呀呀呀———', 'R'),
    (0x185C1, 3, '「こ、', '「这，', 'R'),
    (0x185C8, 5, 'これは！！', '这是！！', 'R'),
    (0x185D4, 6, '「ラッキー！', '「好运来！', 'R'),
    (0x185E1, 5, '大吉だ！！', '大吉！！', 'R'),
    (0x185ED, 6, '「ラッキー！', '「好运来！', 'R'),
    (0x185FA, 5, '中吉だ！！', '中吉！！', 'R'),
    (0x18606, 6, '「ラッキー！', '「好运来！', 'R'),
    (0x18613, 4, '吉だ！！', '吉！！', 'R'),
    (0x1861D, 7, '「小吉だった。', '「小吉啦。', 'R'),
    (0x1862C, 7, '「末吉だった。', '「末吉啦。', 'R'),
    (0x1863C, 6, '「凶だ‥‥。', '「凶兆…。', 'R'),
    (0x1864A, 5, '「げげっ！', '「啊呀！', 'R'),
    (0x18655, 5, '大凶だ…。', '大凶…。', 'R'),
    # the status panel's nine affinity labels, each followed by the 0x155 mark glyph.
    # The ninth is ストレス, spelled with the half-width pair cells 0x153 (スト) and
    # 0x154 (レス) -- two codes, not four, and no kana character maps to them, so
    # `UI_KEEP` stands in for both on the Japanese side.
    (0x1835A, 3, '体調' + K, '体力' + K, 'R'),
    (0x18362, 3, '文系' + K, '文科' + K, 'R'),
    (0x1836A, 3, '理系' + K, '理科' + K, 'R'),
    (0x18372, 3, '芸術' + K, '艺术' + K, 'R'),
    (0x1837A, 3, '運動' + K, '运动' + K, 'R'),
    (0x18382, 3, '雑学' + K, '杂学' + K, 'R'),
    (0x1838A, 3, '容姿' + K, '容姿' + K, 'R'),
    (0x18392, 3, '根性' + K, '毅力' + K, 'R'),
    (0x1839A, 3, K + K + K, '压力' + K, 'R'),
    # the same nine as the list screen's tabs, without the mark
    (0x1AFB8, 2, '体調', '体力', 'R'),
    (0x1AFC2, 2, '文系', '文科', 'R'),
    (0x1AFCC, 2, '理系', '理科', 'R'),
    (0x1AFD5, 2, '芸術', '艺术', 'R'),
    (0x1AFDF, 2, '運動', '运动', 'R'),
    (0x1AFE9, 2, '雑学', '杂学', 'R'),
    (0x1AFF3, 2, '容姿', '容姿', 'R'),
    (0x1AFFD, 2, '根性', '毅力', 'R'),
    (0x1B007, 2, K + K, '压力', 'R'),
    # ---- the rest of the draw-script bank: the profiles, club list, date-spot map,
    # save-file menu, options page and event titles ($18800-$1A460).  Generated from
    # the ROM itself (tools/../uispec + a stock decode) so the Japanese column can not
    # be mis-transcribed, and width-checked against each field's own code count.
    # A row padded with literal spaces keeps the stock field's column geometry -- the
    # options page draws 速い/普通/遅い at fixed positions, so its labels need blanks
    # between them rather than a left-packed string.
    (0X18800, 2, '中島', '中岛', 'R'),
    (0X18808, 1, '勝', '胜', 'R'),
    (0X18810, 4, 'なかぢー', '    ', 'R'),
    (0X1882A, 3, '無所属', '无社团', 'R'),
    (0X18831, 3, '文芸部', '文艺部', 'R'),
    (0X18838, 3, '演劇部', '戏剧部', 'R'),
    (0X1883F, 3, '科学部', '科学部', 'R'),
    (0X18846, 3, '美術部', '美术部', 'R'),
    (0X1884D, 4, '軽音楽部', '轻音乐部', 'R'),
    (0X18856, 3, '野球部', '棒球部', 'R'),
    (0X1885D, 5, 'サッカー部', '足球部  ', 'R'),
    (0X18868, 4, 'テニス部', '网球部 ', 'R'),
    (0X18871, 3, '水泳部', '游泳部', 'R'),
    (0X18878, 6, 'バスケット部', '篮球部   ', 'R'),
    (0X18885, 6, '＜電話番号＞', '＜电话号码＞', 'R'),
    (0X18892, 4, '藤崎詩織', '藤崎诗织', 'R'),
    (0X1889B, 15, '趣味は音楽鑑賞、特にクラシック', '兴趣是听音乐，尤其是古典乐', 'R'),
    (0X188BA, 12, '成績優秀、スポーツ万能。', '成绩优秀，运动全能。', 'R'),
    (0X188D3, 15, 'クラシックと恋愛物の映画が好み', '喜欢古典乐和爱情电影    ', 'R'),
    (0X188F2, 15, 'アクセサリーを集めてるらしい。', '好像喜欢收集装饰品。   ', 'R'),
    (0X18911, 14, 'ヘアバンドを集めてるらしい。', '好像喜欢收集发带。  ', 'R'),
    (0X1892E, 14, '公園に行くのが好きなようだ。', '好像喜欢去公园玩。  ', 'R'),
    (0X1894B, 5, '早乙女好雄', '早乙女好雄', 'R'),
    (0X18956, 5, '早乙女優美', '早乙女优美', 'R'),
    (0X18961, 11, '俺の妹。スポーツは得意', '我的妹妹，擅长运动', 'R'),
    (0X18978, 13, 'アニメと、プロレスが好み。', '喜欢动漫和摔角。   ', 'R'),
    (0X18993, 15, 'ゲームとかガキっぽいものが好み', '喜欢游戏之类小孩子的东西', 'R'),
    (0X189B2, 12, 'もっと女らしくなれよな。', '有点女孩子的样子吧。', 'R'),
    (0X189CB, 5, '伊集院レイ', '伊集院丽 ', 'R'),
    (0X189D7, 4, 'ＢＷＨ：', '三围：', 'R'),
    (0X189F7, 14, '嫌い嫌い嫌い嫌い嫌い嫌い嫌い', '讨厌讨厌讨厌讨厌讨厌    ', 'R'),
    (0X18A14, 14, '嫌い嫌い嫌い嫌い嫌い嫌い嫌い', '讨厌讨厌讨厌讨厌讨厌    ', 'R'),
    (0X18A31, 14, 'きざきざきざきざきざきざきざ', '装腔作势          ', 'R'),
    (0X18A4E, 14, 'きざきざきざきざきざきざきざ', '装腔作势          ', 'R'),
    (0X18A6B, 14, 'きざで、嫌味で、冷徹で嫌な奴', '装腔作势、刻薄又冷血', 'R'),
    (0X18A88, 15, '全男子生徒の敵。でも、金持ち。', '全校男生的公敌。不过他家有钱', 'R'),
    (0X18AA7, 3, '清川望', '清川望', 'R'),
    (0X18AAE, 15, 'スポーツ万能、水泳は国体レベル', '运动全能，游泳国家级    ', 'R'),
    (0X18ACD, 10, '優柔不断な男は嫌い。', '讨厌优柔寡断的人', 'R'),
    (0X18AE2, 13, '身体を動かすことが大好き。', '非常喜欢体育活动。  ', 'R'),
    (0X18AFD, 16, 'ロックをよく聴く。軟弱者は嫌い。', '常听摇滚乐。讨厌软弱的人。 ', 'R'),
    (0X18B1E, 13, '男っぽいことを気にしてる。', '在意自己不够男人味。', 'R'),
    (0X18B39, 10, '恋愛物の映画が好み。', '喜欢爱情电影。 ', 'R'),
    (0X18B4E, 4, '虹野沙希', '虹野沙希', 'R'),
    (0X18B57, 15, '運動部のアイドルで、趣味は料理', '运动社团的偶像，爱好是做饭', 'R'),
    (0X18B76, 14, '運動はやるより、見るタイプ。', '运动方面更爱看不爱练。', 'R'),
    (0X18B93, 15, 'アクション映画、ロックが好み。', '喜欢动作片和摇滚乐。   ', 'R'),
    (0X18BB2, 14, '趣味は料理。誰にでも優しい。', '爱好是做饭。对谁都温柔。', 'R'),
    (0X18BCF, 15, '何事にも頑張る人が好きらしい。', '好像喜欢什么事都努力的人', 'R'),
    (0X18BEE, 11, '誰からも慕われている。', '大家都仰慕她。  ', 'R'),
    (0X18C05, 5, '朝日奈夕子', '朝日奈夕子', 'R'),
    (0X18C10, 12, '流行に敏感で、遊び歩く。', '对流行敏感，爱到处玩。', 'R'),
    (0X18C29, 12, '勉強は苦手で、うるさい。', '不擅长学习，很吵。', 'R'),
    (0X18C42, 12, '流行に敏感で、うるさい。', '对流行敏感，很吵。', 'R'),
    (0X18C5B, 11, 'アクション映画が好み。', '喜欢动作片。   ', 'R'),
    (0X18C72, 10, '豆豆クラブのファン。', '豆豆社团的粉丝。', 'R'),
    (0X18C87, 15, '古臭いものは嫌いで、うるさい。', '讨厌老土的东西，很吵。  ', 'R'),
    (0X18CA6, 5, '古式ゆかり', '古式由加利', 'R'),
    (0X18CB1, 12, 'ボーッとしてて、のんき。', '总是在发呆，很悠闲。', 'R'),
    (0X18CCA, 7, '趣味は編み物。', '爱好是编织。', 'R'),
    (0X18CD9, 14, 'テニス以外のスポーツは苦手。', '除网球外不擅长运动。  ', 'R'),
    (0X18CF6, 13, 'うるさいものは嫌いらしい。', '好像讨厌吵闹的东西。', 'R'),
    (0X18D11, 13, 'ボーッとできるものが好き。', '喜欢能让人发呆的东西。', 'R'),
    (0X18D2C, 13, 'うるさいものは嫌いらしい。', '好像讨厌吵闹的东西。', 'R'),
    (0X18D47, 4, '美樹原愛', '美树原爱', 'R'),
    (0X18D50, 12, '動物好きで、おとなしい。', '喜欢动物，很文静。', 'R'),
    (0X18D69, 15, '赤面症で、男子の友達は少ない。', '容易脸红，男同学不多。  ', 'R'),
    (0X18D88, 14, '動物のぬいぐるみを集めてる。', '喜欢收集动物玩偶。  ', 'R'),
    (0X18DA5, 15, '赤面症で、男子の友達は少ない。', '容易脸红，男同学不多。  ', 'R'),
    (0X18DC4, 14, '幽霊話とかの話が好きらしい。', '好像喜欢听鬼故事。  ', 'R'),
    (0X18DE1, 14, 'うるさい音楽は、嫌いらしい。', '好像讨厌吵闹的音乐。', 'R'),
    (0X18DFE, 3, '鏡魅羅', '镜魅罗', 'R'),
    (0X18E05, 7, '美人で俺好み。', '漂亮又合口味', 'R'),
    (0X18E14, 15, '趣味はウィンドウショッピング。', '爱好是逛商店。       ', 'R'),
    (0X18E33, 9, '高価なものを好む。', '喜欢贵重的东西。', 'R'),
    (0X18E46, 15, '美的ものにしか興味を持たない。', '只对美的东西有兴趣。   ', 'R'),
    (0X18E65, 12, '家庭の事を誰も知らない。', '家里的事没人知道。', 'R'),
    (0X18E7E, 15, '美的で高価なものしか愛さない。', '只爱美丽又贵的东西。   ', 'R'),
    (0X18E9D, 4, '紐緒結奈', '纽绪结奈', 'R'),
    (0X18EA6, 14, '怪しげな研究をしてるらしい。', '好像在做可疑的研究。', 'R'),
    (0X18EC3, 13, 'その他、詳しいことは不明。', '其他详情不明。     ', 'R'),
    (0X18EDE, 13, '頭はきれるが、運動は駄目。', '头脑聪明，运动不行。', 'R'),
    (0X18EF9, 13, '破壊的なものが好きらしい。', '好像喜欢破坏性的东西。', 'R'),
    (0X18F14, 14, 'きらめき高校の＊＊＊科学者。', '光辉高校的＊＊＊科学家。', 'R'),
    (0X18F31, 15, '頭脳のためにクラシックを聴く。', '为了头脑而听古典乐。   ', 'R'),
    (0X18F50, 4, '片桐彩子', '片桐彩子', 'R'),
    (0X18F59, 10, '趣味は絵を描くこと。', '爱好是画画。   ', 'R'),
    (0X18F6E, 15, '明るく友達が多い。運動は駄目。', '开朗，朋友很多。运动不行。', 'R'),
    (0X18F8D, 15, 'グロテスクな絵、ポップスが好み', '喜欢怪诞的画和流行乐   ', 'R'),
    (0X18FAC, 10, '静かなところは苦手。', '怕安静的地方。  ', 'R'),
    (0X18FC1, 13, '水泳の授業の日は休みがち。', '上游泳课的日子常请假。', 'R'),
    (0X18FDC, 15, 'グロテスクな絵、ポップスが好み', '喜欢怪诞的画和流行乐   ', 'R'),
    (0X18FFB, 4, '如月未緒', '如月未绪', 'R'),
    (0X19004, 16, '身体が弱いことを、気にしている。', '很在意自己身体不好。     ', 'R'),
    (0X19025, 15, '趣味は読書で、文学作品を好む。', '爱好是读书，喜欢文学作品', 'R'),
    (0X19044, 12, '激しいスポーツはしない。', '不做激烈的运动。', 'R'),
    (0X1905D, 11, '落ち着ける音楽が好み。', '喜欢宁静的音乐。', 'R'),
    (0X19074, 12, '激しいスポーツはしない。', '不做激烈的运动。', 'R'),
    (0X1908D, 13, 'ゲーテの詩集がお気に入り。', '最爱歌德的诗集。   ', 'R'),
    (0X190A8, 2, '館林', '馆林', 'R'),
    (0X190AD, 4, '取り消し', '取消', 'R'),
    (0X190B6, 10, '＜女の子からの評価＞', '＜女生对你的评价＞', 'R'),
    (0X190E7, 4, '誕生日：', '生日：', 'R'),
    (0X19100, 3, '星座：', '星座：', 'R'),
    (0X19118, 3, '牡羊座', '白羊座', 'R'),
    (0X1911F, 3, '牡牛座', '金牛座', 'R'),
    (0X19126, 3, '双子座', '双子座', 'R'),
    (0X1912D, 2, '蟹座', '巨蟹', 'R'),
    (0X19132, 3, '獅子座', '狮子座', 'R'),
    (0X19139, 3, '乙女座', '处女座', 'R'),
    (0X19140, 3, '天秤座', '天秤座', 'R'),
    (0X19147, 4, 'さそり座', '天蝎座', 'R'),
    (0X19150, 3, '射手座', '射手座', 'R'),
    (0X19157, 3, '山羊座', '摩羯座', 'R'),
    (0X1915E, 3, '水瓶座', '水瓶座', 'R'),
    (0X19165, 2, '魚座', '双鱼', 'R'),
    (0X1916B, 4, '血液型：', '血型：', 'R'),
    (0X19194, 4, 'ＢＷＨ：', '三围：', 'R'),
    (0X191B0, 2, '神社', '神社', 'R'),
    (0X191B5, 4, 'スケート', '溜冰  ', 'R'),
    (0X191BE, 3, 'スキー', '滑雪 ', 'R'),
    (0X191C5, 6, '＜部活一覧＞', '＜社团一览＞', 'R'),
    (0X191D2, 2, '文芸', '文艺', 'R'),
    (0X191D7, 2, '演劇', '戏剧', 'R'),
    (0X191DC, 2, '科学', '科学', 'R'),
    (0X191E1, 2, '美術', '美术', 'R'),
    (0X191E6, 3, '軽音楽', '轻音乐', 'R'),
    (0X191ED, 4, 'サッカー', '足球  ', 'R'),
    (0X191F6, 2, '野球', '棒球', 'R'),
    (0X191FB, 3, 'テニス', '网球 ', 'R'),
    (0X19202, 2, '水泳', '游泳', 'R'),
    (0X19207, 3, 'バスケ', '篮球 ', 'R'),
    (0X1920E, 2, '私設', '私设', 'R'),
    (0X19213, 3, '無所属', '无社团', 'R'),
    (0X1921A, 1, '部', '部', 'R'),
    (0X1921D, 9, '部に入部しました。', '部，我加入了社团。', 'R'),
    (0X19231, 5, 'クラブ：', '社团：  ', 'R'),
    (0X19245, 5, '備考：', '备注：  ', 'R'),
    (0X19252, 3, '電話：', '电话：', 'R'),
    (0X19334, 9, '＜デートスポット＞', '＜约会地点＞', 'R'),
    (0X19347, 6, '次のページへ', '下一页   ', 'R'),
    (0X19354, 6, '前のページへ', '上一页   ', 'R'),
    (0X19362, 10, '＜期末試験結果発表＞', '＜期末考试成绩公布＞', 'R'),
    (0X19386, 4, '館林見晴', '馆林见晴', 'R'),
    (0X193E2, 16, '・マウス決定ボタン   左 ・右', '・鼠标确认键      左 ・右', 'R'),
    (0X19403, 20, '・カーソル移動速度   速い・普通・遅い', '・光标移动速度     快 ・中 ・慢 ', 'R'),
    (0X1942C, 20, '・文章出力速度     速い・普通・遅い', '・文字输出速度     快 ・中 ・慢 ', 'R'),
    (0X19455, 21, '・サウンド出力     ステレオ・モノラル', '・音频输出       立体声 ・单声道 ', 'R'),
    (0X19480, 2, '終了', '结束', 'R'),
    (0X1949C, 14, '今のゲームをセーブしますか？', '要保存当前的游戏吗？', 'R'),
    (0X194BC, 3, 'は い', '是  ', 'R'),
    (0X194C5, 3, 'いいえ', '否  ', 'R'),
    (0X194CC, 3, '伊集院', '伊集院', 'R'),
    (0X194D3, 2, '館林', '馆林', 'R'),
    (0X194D8, 4, '・おまけ', '・附加', 'R'),
    (0X194E1, 3, '如月２', '如月２', 'R'),
    (0X194E8, 3, '清川２', '清川２', 'R'),
    (0X1A164, 4, 'バスケ部', '篮球部', 'R'),
    (0X1A16D, 3, '演劇部', '戏剧部', 'R'),
    (0X1A174, 3, '文芸部', '文艺部', 'R'),
    (0X1A17B, 3, '実験室', '实验室', 'R'),
    (0X1A182, 3, '美術部', '美术部', 'R'),
    (0X1A189, 4, '軽音楽部', '轻音乐部', 'R'),
    (0X1A192, 2, '校庭', '操场', 'R'),
    (0X1A197, 3, '科学部', '科学部', 'R'),
    (0X1A19E, 2, '教室', '教室', 'R'),
    (0X1A1A3, 3, '学校前', '校门前', 'R'),
    (0X1A1AA, 3, '校門前', '校门前', 'R'),
    (0X1A1B1, 2, '屋上', '天台', 'R'),
    (0X1A1B6, 3, '職員室', '职员室', 'R'),
    (0X1A1BD, 3, '図書室', '图书室', 'R'),
    (0X1A1C4, 3, '文化祭', '文化祭', 'R'),
    (0X1A1CB, 4, '文集展示', '文集展示', 'R'),
    (0X1A1D4, 3, '舞台裏', '幕后 ', 'R'),
    (0X1A1DB, 4, '油絵展示', '油画展示', 'R'),
    (0X1A1E4, 3, '似顔絵', '肖像画', 'R'),
    (0X1A1EB, 6, '公開デッサン', '公开写生  ', 'R'),
    (0X1A1F8, 5, '占いマシン', '占卜机  ', 'R'),
    (0X1A203, 5, '実験ショー', '实验表演 ', 'R'),
    (0X1A20E, 3, '体育祭', '体育祭', 'R'),
    (0X1A215, 2, '玄関', '玄关', 'R'),
    (0X1A21A, 3, '自宅前', '家门口', 'R'),
    (0X1A221, 4, '練習試合', '练习比赛', 'R'),
    (0X1A22A, 6, 'インターハイ', '全国大赛  ', 'R'),
    (0X1A242, 4, '伊集院邸', '伊集院家', 'R'),
    (0X1A24B, 7, 'パーティー会場', '派对会场 ', 'R'),
    (0X1A25A, 4, '廃工場前', '废工厂前', 'R'),
    (0X1A263, 2, '初詣', '参拜', 'R'),
    (0X1A268, 2, '元旦', '元旦', 'R'),
    (0X1A26D, 4, '修学旅行', '修学旅行', 'R'),
    (0X1A276, 7, 'ホテル・ロビー', '饭店大堂 ', 'R'),
    (0X1A285, 6, 'オペラハウス', '歌剧院  ', 'R'),
    (0X1A292, 7, 'エアーズロック', '艾尔斯岩 ', 'R'),
    (0X1A2A1, 5, '天安門広場', '天安门广场', 'R'),
    (0X1A2AC, 5, '万里の長城', '万里长城 ', 'R'),
    (0X1A2B7, 3, '移動中', '旅途中', 'R'),
    (0X1A2BE, 3, '合宿所', '集训地', 'R'),
    (0X1A2C5, 4, 'グランド', '操场  ', 'R'),
    (0X1A2CE, 3, 'ロビー', '大堂 ', 'R'),
    (0X1A2D5, 3, '肝試し', '试胆 ', 'R'),
    (0X1A2DC, 2, '縁日', '庙会', 'R'),
    (0X1A2E1, 5, '近所の公園', '附近公园 ', 'R'),
    (0X1A2EC, 8, 'きらめき中央公園', '光辉中央公园', 'R'),
    (0X1A2FD, 1, '池', '湖', 'R'),
    (0X1A300, 3, '並木道', '林荫道', 'R'),
    (0X1A307, 3, '桜並木', '樱花道', 'R'),
    (0X1A30E, 3, '遊園地', '游乐园', 'R'),
    (0X1A315, 2, '園内', '园内', 'R'),
    (0X1A31A, 3, '映画館', '电影院', 'R'),
    (0X1A321, 2, '館内', '馆内', 'R'),
    (0X1A326, 7, 'コンサート会場', '演唱会会场 ', 'R'),
    (0X1A335, 3, '会場内', '会场内', 'R'),
    (0X1A33C, 7, 'ゲームセンター', '电玩城   ', 'R'),
    (0X1A34B, 6, 'ビデオゲーム', '电子游戏 ', 'R'),
    (0X1A358, 6, 'メダルゲーム', '推币机  ', 'R'),
    (0X1A365, 3, '美術館', '美术馆', 'R'),
    (0X1A377, 3, '彫刻展', '雕塑展', 'R'),
    (0X1A37E, 7, 'ショッピング街', '商业街   ', 'R'),
    (0X1A38D, 5, 'ブティック', '时装店 ', 'R'),
    (0X1A398, 9, 'ファンシーショップ', '精品店     ', 'R'),
    (0X1A3AB, 8, 'ジャンクショップ', '旧货店     ', 'R'),
    (0X1A3BC, 3, '図書館', '图书馆', 'R'),
    (0X1A3C3, 4, 'スキー場', '滑雪场 ', 'R'),
    (0X1A3CC, 4, 'ゲレンデ', '雪场  ', 'R'),
    (0X1A3D5, 5, 'スケート場', '溜冰场 ', 'R'),
    (0X1A3E0, 4, 'リンク内', '冰场内 ', 'R'),
    (0X1A3E9, 3, '動物園', '动物园', 'R'),
    (0X1A3F0, 3, '水族館', '水族馆', 'R'),
    (0X1A3F7, 3, '海水浴', '海水浴', 'R'),
    (0X1A3FE, 2, '浜辺', '海滩', 'R'),
    (0X1A403, 3, '無人島', '无人岛', 'R'),
    (0X1A40A, 3, 'プール', '泳池 ', 'R'),
    (0X1A411, 4, 'プール内', '泳池内 ', 'R'),
    (0X1A41A, 3, '植物園', '植物园', 'R'),
    (0X1A421, 7, 'プラネタリウム', '天文馆   ', 'R'),
    (0X1A430, 5, 'スタジアム', '体育场 ', 'R'),
    (0X1A43B, 4, 'カラオケ', '歌厅  ', 'R'),
    (0X1A44D, 6, 'ボーリング場', '保龄球场 ', 'R'),
    (0X1A13F, 5, '校門（桜）', '校门（樱）', 'R'),
    (0X1A14A, 4, '伝説の樹', '传说之树', 'R'),
    (0X1A153, 2, '廊下', '走廊', 'R'),
    (0X1A158, 2, '中庭', '庭院', 'R'),
    (0X1A15D, 3, '水泳部', '游泳部', 'R'),
    (0X1A237, 5, '甲子園大会', '甲子园大会', 'R'),
    (0X1A36C, 5, 'ガーギー展', '怪物雕塑展', 'R'),
    # ---- the school-festival arcade, `$1B000-$1C000`: the nine mini-game title
    # cards, their instruction boxes, the stall keeper and 早乙女 lines, and the
    # 勇者マジラ play-within-the-game script.  These runs are complete sentences
    # already stored as 2-byte glyph codes, so a row costs no code-page byte and no
    # offset table addresses them -- only each run's own code count is fixed.  Where
    # one Japanese sentence is split across runs by a placement opcode, the Chinese
    # is written to flow across the same seams.
    (0X1B010, 10, 'たいむましーんにのる', '坐时光机', 'R'),
    (0X1B025, 12, 'Ｒ＞次Ｌ＞前ＲＵＮ＞終了', 'Ｒ＞次Ｌ＞前ＲＵＮ＞结束', 'R'),
    (0X1B05C, 19, 'きもちをあやつる神様もーど！ゆうこうど', '操纵心情的神模式！有效度', 'R'),
    (0X1B083, 12, 'Ｒ＞次Ｌ＞前ＲＵＮ＞終了', 'Ｒ＞次Ｌ＞前ＲＵＮ＞结束', 'R'),
    (0X1B09F, 19, 'きもちをあやつる神様もーど！ときめきど', '操纵心情的神模式！心动度', 'R'),
    (0X1B0C6, 12, 'Ｒ＞次Ｌ＞前ＲＵＮ＞終了', 'Ｒ＞次Ｌ＞前ＲＵＮ＞结束', 'R'),
    (0X1B0E2, 20, 'きもちをあやつる神様もーど！しょうしんど', '操纵心情的神模式！上升度', 'R'),
    (0X1B10B, 12, 'Ｌ＞前ぺーじＲＵＮ＞終了', 'Ｌ＞前页ＲＵＮ＞结束', 'R'),
    (0X1B182, 3, '朝日奈', '朝日奈', 'R'),
    (0X1B18F, 3, '美樹原', '美树原', 'R'),
    (0X1B19B, 3, '早乙女', '早乙女', 'R'),
    (0X1B1AA, 13, 'プレゼント交換の時間です。', '交换礼物的时间到啦。', 'R'),
    (0X1B1C9, 10, '「どれにしようかな。', '「选哪个好呢。', 'R'),
    (0X1B1DF, 7, '二人三脚の説明', '二人三足说明', 'R'),
    (0X1B1EE, 7, '（いっち）でＡ', '（左脚）按Ａ', 'R'),
    (0X1B1FD, 10, '（にい）でＢボタン。', '（右脚）按Ｂ键。', 'R'),
    (0X1B212, 13, 'タイミングよく押して下さい', '请按准时机按键', 'R'),
    (0X1B230, 8, '玉入れ競技の説明', '投球比赛说明', 'R'),
    (0X1B243, 14, '左側のかごの中へ、玉を入れる', '请把球投进左边的那个大筐里，', 'R'),
    (0X1B262, 14, '競技です。かご上にある矢印に', '这就是投球比赛啦。筐子上方', 'R'),
    (0X1B281, 4, '向かって', '的箭头', 'R'),
    (0X1B290, 4, '（左右）', '（左右）', 'R'),
    (0X1B299, 4, 'ボタンで', '按键', 'R'),
    (0X1B2A5, 14, '玉を投げます。たくさん、玉を', '来投球。投得多的那一方', 'R'),
    (0X1B2C5, 9, '入れた方が、勝ち。', '就获胜。', 'R'),
    (0X1B2DA, 13, '〜ときめき★占いマシーン〜', card(13, '占卜机'), 'R'),
    (0X1B2F8, 9, 'ボタンを押してね' + K, '请按按键', 'R'),
    (0X1B30D, 22, '相手の事を強く想いながら ボタンを押してね' + K, '心里想着对方，再按下按键', 'R'),
    (0X1B33A, 12, '（どの薬を貰おうかな？）', '（要哪瓶药呢？）', 'R'),
    (0X1B353, 21, '（よし、俺は「情熱に燃える赤」を貰おう。）',
     '（好，我要「热情燃烧的红色」。）', 'R'),
    (0X1B37E, 23, '（よし、俺は「太陽の様に激しい黄」を貰おう。）',
     '（好，我要「像太阳般炽烈的黄色」。）', 'R'),
    (0X1B3AD, 23, '（よし、俺は「海の様に心静かな青」を貰おう。）',
     '（好，我要「像大海般沉静的蓝色」。）', 'R'),
    (0X1B3DE, 11, '〜ときめき★危機一髪〜', card(11, '千钧一发'), 'R'),
    (0X1B3F6, 23, 'コアラに当たらない様、２本の剣を刺して下さい。',
     '别刺中树袋熊，请把两把剑插进去。', 'R'),
    (0X1B429, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1B44A, 14, '（どの穴に刀を刺そうかな？）', '（往哪个洞里插刀呢？）', 'R'),
    (0X1B467, 13, '（次はどこに刺そうかな？）', '（下一个插哪里呢？）', 'R'),
    (0X1B482, 21, '片桐 「ナイスチョイス。やるじゃないの。」',
     '片桐 「选得好。真有两下子。」', 'R'),
    (0X1B4AD, 20, '片桐 「オー、イッツグレイト！見事ね。」', '片桐 「哦，太棒了！真漂亮。」', 'R'),
    (0X1B4D8, 14, '〜ときめき★福引ルーレット〜', card(14, '幸运大转盘'), 'R'),
    (0X1B4F6, 17, '当たれば極楽、ハズれりゃガックリ。', '中了就极乐，不中就泄气。', 'R'),
    (0X1B51B, 24, 'ルーレットをうまく止めて、幸運を射止めましょう。',
     '请把转盘停得准准的，赢得好运吧。', 'R'),
    (0X1B54C, 22, '１等賞・・・星マーク  ２等賞・・・丸マーク', '一等奖 星星    二等奖 圆圈', 'R'),
    (0X1B57A, 10, 'ハズレ・・・小ランプ', '未中奖 小灯', 'R'),
    (0X1B593, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1B5B4, 24, '（うまく狙いを定めて、ストップボタンを押すぞ。）',
     '（看准目标，然后按下停止键。）', 'R'),
    (0X1B5E5, 23, '商店街の人「お、お、お、おおあたりいーーーー！',
     '商业街的人「中啦，中啦，大大中奖啦！', 'R'),
    (0X1B615, 22, 'ついに出ました、１等賞だあ！！」', '终于出来了，是一等奖啊！！」', 'R'),
    (0X1B642, 18, '商店街の人「やったでました、２等賞！', '商业街的人「太好了，二等奖！', 'R'),
    (0X1B668, 22, 'なかなかやるねえ、兄ちゃん！！」', '挺有两下子嘛，小哥！！」', 'R'),
    (0X1B695, 20, '商店街の人「残念、兄ちゃんハズレだねえ。', '商业街的人「可惜，小哥没中。', 'R'),
    (0X1B6BF, 23, '・・・はい、残念賞のティッシュ。」', '来，安慰奖是纸巾一包。」', 'R'),
    (0X1B6F0, 13, '〜ときめき★はにわゲーム〜', card(13, '陶俑游戏'), 'R'),
    (0X1B70C, 24, 'どのハニワにボールがあるか、を当てるゲームです。',
     '猜猜小球藏在哪个陶俑里的游戏。', 'R'),
    (0X1B741, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1B762, 22, '芸人 「いいアルか？よーく見ているアルよ。」', '艺人 「听好了，要看仔细哟。」', 'R'),
    (0X1B78F, 21, '（ボールが入ってるのは、どのハニワかな？）', '（小球装在哪个陶俑里呢？）', 'R'),
    (0X1B7BA, 19, '芸人 「アイヤー、よく判ったアルねー！', '艺人 「哎呀，猜得真准呀！', 'R'),
    (0X1B7E2, 23, '当たったから、このハニワあげるアル。」', '既然猜中了，这个陶俑送给你。」', 'R'),
    (0X1B811, 14, '芸人 「残念、はずれアルね。', '艺人 「可惜，没中。', 'R'),
    (0X1B82F, 22, 'もっと目を鍛えて、また来るヨロシ。」', '再练练眼力，下次再来哟。」', 'R'),
    (0X1B85E, 12, '〜ときめき★スイカ割り〜', card(12, '打西瓜'), 'R'),
    (0X1B878, 23, '狙いを定めて、見事にスイカを割ってみましょう。', '看准目标，把西瓜漂亮地敲开吧。', 'R'),
    (0X1B8AB, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1B8CC, 22, '（心を静めて、スイカに狙いを定めよう・・・）', '（静下心来，对准那个西瓜吧）', 'R'),
    (0X1B8FB, 14, '〜ときめき★スロットゲーム〜', card(14, '老虎机'), 'R'),
    (0X1B919, 23, 'スロットマシーンです。回転している３つのドラム', '这是老虎机。三个转动的滚筒', 'R'),
    (0X1B94A, 23, 'を次々に止めて、ドラムの絵を完成させて下さい。', '要依次把它们停下，排齐图案。', 'R'),
    (0X1B979, 22, '１回ごとに任意のドラムのホールドが出来ます。', '每一轮都可以按住你想要的滚筒。', 'R'),
    (0X1B9A7, 23, '３回のプレイで揃わないと、ゲームオーバーです。', '三次还排不齐，就游戏结束了。', 'R'),
    (0X1B9DA, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1B9FB, 20, '（回したくないドラムをホールド出来るぞ。', '（能按住不想转的滚筒。', 'R'),
    (0X1BA25, 22, 'パッドの上下でドラムスイッチを選び、ボタン', '用手柄上下选滚筒的开关，再用按键', 'R'),
    (0X1BA54, 18, 'でホールドを切替えればよいのか。）', '来切换要不要按住，明白了。）', 'R'),
    (0X1BA7B, 11, '〜ときめき★クエスト〜', card(11, '大冒险'), 'R'),
    (0X1BA93, 7, 'きらめき王国。', '心跳王国。', 'R'),
    (0X1BAA4, 23, 'ときめきと幸せにあふれた、のどかな国であった。',
     '那是一个充满心跳与幸福的宁静国度。', 'R'),
    (0X1BAD4, 24, 'だが、魔王ラアーコの魔の手が伸びてきたのである。',
     '然而，魔王拉阿科的魔爪伸了过来。', 'R'),
    (0X1BB05, 22, '魔王は王国のプリンセスをさらい、洞窟に幽閉。',
     '魔王掳走了王国的公主，把她幽禁在洞窟。', 'R'),
    (0X1BB33, 20, '平和だった王国は暗黒の闇に包まれた・・・', '和平的王国被黑暗的阴影笼罩了。', 'R'),
    (0X1BB5C, 23, '失意に沈む王国・・・だが、そこに一人の勇者が現', '沉入绝望的王国。可就在此时，一位勇者', 'R'),
    (0X1BB8C, 23, 'われた。王から魔王の話を聞いた勇者は、姫君の救',
     '出现了。听国王讲完魔王之事，勇者向王', 'R'),
    (0X1BBBD, 9, '出を王に約束する。', '保证救出公主。', 'R'),
    (0X1BBD0, 23, 'そして危険を承知で勇者は単身、魔王の潜むダンジ',
     '于是勇者明知凶险，只身朝魔王藏身的洞', 'R'),
    (0X1BC00, 21, 'ョンへと向かった。姫を救出するために・・・', '窟出发了，只为救出公主。', 'R'),
    (0X1BC2B, 10, '・・・凶悪なワナが！', '凶恶的陷阱！', 'R'),
    (0X1BC41, 15, '・・・おそるべきモンスターが！', '可怕的怪物出现了！', 'R'),
    (0X1BC62, 22, '多くの難関がダンジョンで勇者を待ちうける！！', '无数难关在洞窟中等着勇者！！', 'R'),
    (0X1BC8F, 23, 'あなたは「伝説の勇者」となり、ダンジョンで捕わ',
     '你将化身为「传说中的勇者」，去寻找', 'R'),
    (0X1BCBF, 23, 'れの身となっている姫を探し出すコトが出来るか？',
     '被囚禁在洞窟里的公主，你能救她吗？', 'R'),
    (0X1BCF2, 15, '［ボタンを押すと冒険開始です］', '［按下按键就开始冒险］', 'R'),
    (0X1BD11, 22, '（パッドの上下で冒険のコースを選ぶんだな。）',
     '（用手柄的上下来选择冒险路线吧。）', 'R'),
    (0X1BD40, 12, '〜ときめき★競馬ゲーム〜', card(12, '赛马游戏'), 'R'),
    (0X1BD5A, 23, 'どの馬がレースに勝つか、を予想して当ててね★', '猜猜哪匹马会赢得这场比赛吧', 'R'),
    (0X1BD8D, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1BDAE, 16, '（どの馬に賭けようかな・・・？）', '（押哪一匹好呢？）', 'R'),
    (0X1BDD1, 13, '〜ときめき★カードゲーム〜', card(13, '纸牌游戏'), 'R'),
    (0X1BDED, 23, 'このゲームはいわゆる「神経衰弱」。お手つき３回',
     '这就是所谓的记忆翻牌。失误三次以', 'R'),
    (0X1BE1E, 22, '以内に３組の女の子カードを揃えると勝ちです。', '内集齐三组女孩卡就算获胜。', 'R'),
    (0X1BE4B, 23, '伊集院カード・・１回ミス。カードをシャッフル。', '伊集院卡 失误一次。牌面重新洗过。', 'R'),
    (0X1BE7B, 20, 'コアラカード・・お手つきが１回減ります。', '树袋熊卡 失误次数减少一次。', 'R'),
    (0X1BEA8, 16, '［ボタンを押すとプレイ開始です］', '［按下按键就开始游戏］', 'R'),
    (0X1BEC9, 16, '早乙女「すごーい、あたったあ。」', '早乙女「好厉害，猜中啦。」', 'R'),
    (0X1BEEA, 18, '早乙女「よし、残るはあと一組だっ！」', '早乙女「好，只剩最后一组！」', 'R'),
    (0X1BF0F, 17, '早乙女「さすが先輩。冴えてるう★」', '早乙女「不愧是前辈，真灵光啊★」', 'R'),
    (0X1BF32, 20, '早乙女「ま、一回くらいは仕方ないよね。」', '早乙女「嘛，错一次也没办法。」', 'R'),
    (0X1BF5B, 21, '早乙女「惜しいっ！お手つきは後１回だよ。」', '早乙女「可惜！只剩一次机会了。」', 'R'),
    (0X1BF86, 17, '早乙女「ちがう、ちがうってばあ！」', '早乙女「不对，我说不对啦！」', 'R'),
    (0X1BFA9, 19, '早乙女「コアラカードだあ★ラッキー。」', '早乙女「是树袋熊卡，真幸运。」', 'R'),
    (0X1BFD0, 19, '早乙女「あーあ、シャッフルカードだ。」', '早乙女「唉，是洗牌卡呀。」', 'R'),
    (0X1BFF7, 17, '早乙女「お見事！やったね、先輩\ue000」', '早乙女「真漂亮！太好了，前辈」', 'R'),
    # The date-planning and club system messages, one `$0A`-terminated draw script per
    # line.  `その日は、クリスマス` / `パーティーの日だ。` are one sentence the engine
    # breaks with a `$14` line control, so the two Chinese rows are written to read
    # across that seam rather than as two halves.
    (0X18107,  4, '誘わない', '不邀请', 'R'),
    (0X18110, 11, 'クラブをどうしますか？', '社团活动怎么办呢？', 'R'),
    (0X18129,  2, '実行', '加入', 'R'),
    (0X1812F,  2, '退部', '退出', 'R'),
    (0X18137,  8, '「文芸部に行く」', '「去文艺部」', 'R'),
    (0X18149,  8, '「美術部に行く」', '「去美术部」', 'R'),
    (0X1815A,  8, '「演劇部に行く」', '「去戏剧部」', 'R'),
    (0X1816C,  9, '「軽音楽部に行く」', '「去轻音乐部」', 'R'),
    (0X1817F,  8, '「科学部に行く」', '「去科学部」', 'R'),
    (0X18190, 15, 'デートする日を指定して下さい。', '请指定外出约会的日子。', 'R'),
    (0X181AF, 15, 'その日は４週間より先の日です。', '那天太远了，只能在４周内。', 'R'),
    (0X181CE, 16, 'その日は他の予定が入っています。', '那一天已经有别的安排了呢。', 'R'),
    (0X181EF, 11, 'その日は、修学旅行だ。', '那天是修学旅行。', 'R'),
    (0X18206, 10, 'その日は、クリスマス', '那天是圣诞', 'R'),
    (0X1821B,  9, 'パーティーの日だ。', '派对的日子。', 'R'),
    (0X1822E, 12, 'その日は、初詣だったな。', '啊，那天是新年的参拜。', 'R'),
    (0X18247, 17, 'あっ、今月はもう予定がいっぱいだ！', '啊，这个月的安排已经全满啦！', 'R'),
    (0X1826D, 10, '「今日から夏休みだ」', '「今天开始放暑假」', 'R'),
    (0X18285, 10, '「今日から２学期だ」', '「今天开始第二学期」', 'R'),
    (0X1829D, 10, '「今日から冬休みだ」', '「今天开始放寒假」', 'R'),
    (0X182B5, 10, '「今日から３学期だ」', '「今天开始第三学期」', 'R'),
    (0X182CD, 10, '「今日から春休みだ」', '「今天开始放春假」', 'R'),
    (0X182E5, 11, '「今日から期末試験だ」', '「今天开始期末考试」', 'R'),
    (0X182FF,  9, '「今日は体育祭だ」', '「今天是体育节」', 'R'),
    # The sports-day and festival mini-games: the selector list and the four rule
    # screens.  Their sentences are broken by the engine's own placement controls, so
    # several rows are one sentence read across the same seams -- `你是靠前的那位` +
    # `选手。`, `一开始` + `（左）` + `按键` + `，先出左脚。`.
    (0X1AB91, 15, 'サブゲームを選択してください。', '请选择一个小游戏。', 'R'),
    (0X1ABB0,  5, '金魚すくい', '捞金鱼', 'R'),
    (0X1ABBC,  4, 'ひもくじ', '抽个签', 'R'),
    (0X1ABC5,  4, '花火デモ', '烟花表演', 'R'),
    (0X1ABCF,  5, 'クリスマス', '圣诞节', 'R'),
    (0X1ABDA,  6, '正月おみくじ', '新年的运势签', 'R'),
    (0X1ABE8,  5, '１００Ｍ走', '百米赛跑', 'R'),
    (0X1ABF3,  4, '二人三脚', '二人三足', 'R'),
    (0X1ABFD,  3, '玉入れ', '投球', 'R'),
    (0X1AC04,  4, '大玉運び', '运大球', 'R'),
    (0X1AC1A,  3, 'ひみつ', '秘密', 'R'),
    (0X1AC22,  5, '戦闘★豪州', '战斗★澳洲', 'R'),
    (0X1AC2D,  5, '戦闘☆中国', '战斗☆中国', 'R'),
    (0X1AC39,  4, '不良戦闘', '街头斗殴', 'R'),
    (0X1AC42,  3, '番長戦', '头目战', 'R'),
    (0X1AC4A,  4, '紐緒ロボ', '纽绪机甲', 'R'),
    (0X1AC54,  8, '金魚すくいの説明', '捞金鱼的说明', 'R'),
    (0X1AC66,  4, '十字キー', '方向键', 'R'),
    (0X1AC6F,  5, '（マウス）', '（鼠标）', 'R'),
    (0X1AC7A,  5, 'の上下左右', '的上下左右', 'R'),
    (0X1AC85, 11, 'で、アミが移動します。', '来移动渔网吧。', 'R'),
    (0X1ACA3,  4, '（左右）', '（左右）', 'R'),
    (0X1ACAC,  8, 'ボタンを押す事で', '按下按键的话', 'R'),
    (0X1ACBD, 12, 'アミは水の中に入ります。', '渔网就会沉进水里。', 'R'),
    (0X1ACDD,  4, '（左右）', '（左右）', 'R'),
    (0X1ACE6,  3, 'ボタン', '按键', 'R'),
    (0X1ACED,  4, 'を離すと', '松开以后', 'R'),
    (0X1ACF6, 14, '水の中から、すくいあげます。', '就把鱼从水里捞上来。', 'R'),
    (0X1AD17,  5, '本日の結果', '今日的结果', 'R'),
    (0X1AD36,  9, '１００Ｍ競走の説明', '百米赛跑的说明', 'R'),
    (0X1AD4B, 13, 'あなたは、手前のプレイヤー', '你是靠前的那位', 'R'),
    (0X1AD68,  3, 'です。', '选手。', 'R'),
    (0X1AD75,  4, '（左右）', '（左右）', 'R'),
    (0X1AD7E,  4, 'ボタンを', '按键，', 'R'),
    (0X1AD89, 13, '交互に連打すると走ります。', '交替连按就能跑起来。', 'R'),
    (0X1ADA6, 13, '早く、ゴールした方が勝ち。', '先跑到终点的一方获胜。', 'R'),
    (0X1ADC2,  4, 'よーうい', '各就位', 'R'),
    (0X1ADCC,  4, 'すたーと', '开始跑', 'R'),
    (0X1ADE2,  5, 'ふらいんぐ', '抢跑', 'R'),
    (0X1ADEF, 11, 'ボタンを押してください', '请按按键起跑', 'R'),
    (0X1AE07,  4, 'ごおーる', '终点', 'R'),
    (0X1AE12,  7, '２人３脚の説明', '二人三足说明', 'R'),
    (0X1AE23,  6, '声に合わせて', '配合口令，', 'R'),
    (0X1AE36,  4, '（左右）', '（左右）', 'R'),
    (0X1AE46, 13, 'ンを交互に押してください。', '把按键交替按下就好。', 'R'),
    (0X1AE63,  4, '最初は、', '一开始', 'R'),
    (0X1AE6F,  3, '（左）', '（左）', 'R'),
    (0X1AE76,  3, 'ボタン', '按键', 'R'),
    (0X1AE84,  7, 'スタートです。', '，先出左脚。', 'R'),
    (0X1AE95, 13, '早く、ゴールした方が勝ち。', '先跑到终点的一方获胜。', 'R'),
    (0X1AEB2,  7, '大玉運びの説明', '运大球的说明', 'R'),
    (0X1AEC6,  3, '（左）', '（左）', 'R'),
    (0X1AECD,  3, 'ボタン', '按键', 'R'),
    (0X1AED4,  3, 'または', '或是', 'R'),
    (0X1AEDE,  3, '（右）', '（右）', 'R'),
    (0X1AEE8, 14, 'ボタンを押すとメーターの方向', '按键，球就会朝着仪表', 'R'),
    (0X1AF07, 14, 'に合わせて大玉が転がります。', '指示的方向滚动起来。', 'R'),
    (0X1AF26,  8, 'メーターの色が、', '仪表的颜色', 'R'),
    (0X1AF51, 10, 'に転がり、早く大玉を', '滚到那边时，快把', 'R'),
    (0X1AF68, 12, 'ゴールに運んだ方が勝ち。', '球运到终点的一方获胜。', 'R'),
    (0X1AF83, 16, '努力は無駄だ！すーぱーまんもーど', '努力才是白费！超人模式', 'R'),
    (0X1AFA4,  9, 'Ｒ＞次ＲＵＮ＞終了', 'Ｒ＞次ＲＵＮ＞结束', 'R'),
    # The drama club's show: the two lines the audience shouts and each club's
    # secret move, which the event announces as `「绝技名」绝技到手。` -- the three
    # rows per club are one sentence split by placement controls, so they are written
    # to read in that order.
    (0X1C01A, 17, '早乙女「ざーんねーんでーしたっ。」', '早乙女「真——可——惜——呀。」', 'R'),
    (0X1C03F, 15, '「うおおおおおおーーーー！！」', '「哇啊啊啊啊啊————！！」', 'R'),
    (0X1C05E,  5, '文芸部奥義', '文艺部奥义', 'R'),
    (0X1C06D,  7, '「熱意の説得」', '「热情的说服」', 'R'),
    (0X1C081,  6, 'を獲得した。', '绝技到手。', 'R'),
    (0X1C08E,  5, '演劇部奥義', '戏剧部奥义', 'R'),
    (0X1C09D,  6, '「暗黒舞踏」', '「黑暗舞踏」', 'R'),
    (0X1C0AA,  5, '科学部奥義', '科学部奥义', 'R'),
    (0X1C0B9, 11, '「戦闘衛星ハッキング」', '「入侵战斗卫星」', 'R'),
    (0X1C0D0,  5, '美術部奥義', '美术部奥义', 'R'),
    (0X1C0DF,  6, '「呪いの絵」', '「诅咒之画」', 'R'),
    (0X1C0EC,  6, '軽音楽部奥義', '轻音乐部奥义', 'R'),
    (0X1C0FD,  7, '「誘惑の音色」', '「诱惑的音色」', 'R'),
    (0X1C10C,  5, '野球部奥義', '棒球部奥义', 'R'),
    (0X1C11B, 10, '「１０００本ノック」', '「１０００次挥棒」', 'R'),
    (0X1C130,  7, 'サッカー部奥義', '足球部奥义', 'R'),
    (0X1C143, 13, '「オーバーヘッド空竹割り」', '「凌空抽射劈竹筒」', 'R'),
    (0X1C15E,  6, 'テニス部奥義', '网球部奥义', 'R'),
    (0X1C16F, 14, '「ブラックホールスマッシュ」', '「黑洞扣杀球」', 'R'),
    (0X1C18C,  5, '水泳部奥義', '游泳部奥义', 'R'),
    (0X1C19B,  5, '「大海衝」', '「大海冲」', 'R'),
    (0X1C1A6,  6, 'バスケ部奥義', '篮球部奥义', 'R'),
    (0X1C1B7, 12, '「ＵＦＯダンクシュート」', '「ＵＦＯ灌篮球」', 'R'),
    # The mouse/keyboard setup help panel and the save-slot list, then the names the
    # calendar shows for each fixed date -- holiday and heroine birthday.  Every row is
    # 1-8 codes because the panel interleaves a placement opcode between its words, and
    # six of them spell one label across that seam.  (The date prompts and the whole
    # mouse/pad settings screen moved to UI_LINE_ROWS: their SB seams garble.)
    (0X19553,  4, '設定終了', '设置结束', 'R'),
    # (The holiday chatter pool's cell-by-cell rows -- 建国記念/緑 and the five
    # ゴールデンウィーク fragments -- retired to UI_LINE_ROWS whole lines.)

    # (The album panel's title, the sound-output help strings and the prologue save
    # slots moved to UI_LINE_ROWS: the R rows could not reach their SB bytes, which
    # left める/オ live on screen.)

    # The sound-test menu reached off the title screen, the theatre plays'
    # role and credit headings, and two heroine names that were still spelled with
    # the Japanese glyph forms (詩織/未緒).  Eight new characters pay for all 23 rows.
    (0X184A5,  4, 'シナリオ', '剧本', 'R'),
    (0X184B5,  5, 'サブゲーム', '小游戏', 'R'),
    (0X184C0,  4, '告白デモ', '告白演示', 'R'),
    (0X184C9,  6, '画面切り替え', '画面切换', 'R'),
    (0X184D6,  5, '背景テスト', '背景测试', 'R'),
    (0X184E1,  7, 'サウンドテスト', '音效测试', 'R'),
    (0X184F0,  5, 'オプション', '选项', 'R'),
    (0X18531,  4, '効果音', '效果音', 'R'),
    (0X18569,  4, '背景番号', '背景编号', 'R'),
    (0X1C970,  5, '藤崎 詩織', '藤崎 诗织', 'R'),
    (0X1CB1B,  5, '如月 未緒', '如月 未绪', 'R'),
    (0X1D40A,  6, 'ナレーター', ' 旁白', 'R'),
    (0X1D956,  5, '魔法使い', ' 魔法师', 'R'),
    (0X1E991,  6, '＜シナリオ＞', '＜剧本＞', 'R'),
    (0X1EBF4,  6, '〜体育祭〜', '〜体育节〜', 'R'),
    (0X1EC54,  6, '〜文化祭〜', '〜文化节〜', 'R'),
    (0X1EC9B,  5, '〜戦闘〜', '〜战斗〜', 'R'),
    (0X1EE2B,  5, '＜効果音＞', '＜效果音＞', 'R'),
    (0X1EFEA,  7, '＜著作・配給＞', '＜著作・发行＞', 'R'),
    # The calendar's month table: each entry is exactly as wide as the rom's own
    # three-letter abbreviation.
    (0X1840E,  3, 'Ｊａｎ', '一月 ', 'R'),
    (0X18415,  3, 'Ｆｅｂ', '二月 ', 'R'),
    (0X1841C,  3, 'Ｍａｒ', '三月 ', 'R'),
    (0X18423,  3, 'Ａｐｒ', '四月 ', 'R'),
    (0X1842A,  3, 'Ｍａｙ', '五月 ', 'R'),
    (0X18431,  3, 'Ｊｕｎ', '六月 ', 'R'),
    (0X18438,  3, 'Ｊｕｌ', '七月 ', 'R'),
    (0X1843F,  3, 'Ａｕｇ', '八月 ', 'R'),
    (0X18446,  3, 'Ｓｅｐ', '九月 ', 'R'),
    (0X1844D,  3, 'Ｏｃｔ', '十月 ', 'R'),
    (0X18454,  3, 'Ｎｏｖ', '十一月', 'R'),
    (0X1845B,  3, 'Ｄｅｃ', '十二月', 'R'),
    (0X184AE,  3, '文化祭', '文化节', 'R'),
    (0X1853E,  4, 'ステレオ', '立体声 ', 'R'),
    (0X1855E,  3, '奥技', '绝技 ', 'R'),
    # (0x19A4D 遊園地 moved to UI_LINE_ROWS: the park line is one SB-mixed entry.)
    (0X19A68,  2, '休館', '休馆', 'R'),
    (0X19AF4,  4, '矢沢米吉', '矢泽米吉', 'R'),
    # The culture-festival literature display: a song card, four essays by
    # the heroines and the player, and the first two classroom plays.  Each line
    # is its own placement run, so a sentence that wraps mid-way keeps its break.
    (0X1C6E8, 12, '〜女々しい野郎どもの詩〜', '〜描写阴柔男子的诗歌〜', 'R'),
    (0X1C701,  9, '窓に映る景色は', '窗前映出的景色', 'R'),
    (0X1C714,  9, '偽りに 溢れて', '尽是虚伪', 'R'),
    (0X1C727,  9, '僕の胸を冷たい', '让我心头冰凉', 'R'),
    (0X1C73A,  9, '暗闇が閉ざすよ', '黑暗紧闭心门', 'R'),
    (0X1C74D, 11, 'Ａｈ 君がいるならば', '啊〜 有你在身边', 'R'),
    (0X1C764, 10, '抱きしめたいのに', '想紧紧抱住你', 'R'),
    (0X1C779, 12, 'Ａｈ 時を戻せるならば', '啊〜 若能回到当年', 'R'),
    (0X1C792,  9, '帰りたい今すぐ', '现在就想要回去', 'R'),
    (0X1C7B2, 13, '題名  「僕の高校生活」', '题目 「我的高中生活」', 'R'),
    (0X1C7CE, 14, '「入学してからあっという間に', '「入学以来转眼间', 'R'),
    (0X1C7EB, 20, '３年という月日が流れようとしています。', '三年时光已经悄悄流去。', 'R'),
    (0X1C815, 17, '女の子に振り向いてもらうために、', '为了能让女孩子回头看我，', 'R'),
    (0X1C838, 22, '勉強にスポーツ、おしゃれ、情報誌チェック、', '读书、运动、打扮、翻时尚杂志，', 'R'),
    (0X1C865, 22, '努力をおしみなく、色々なことをやりました。', '我毫不吝惜力气，什么都试过。', 'R'),
    (0X1C893, 19, 'しかし、最後の目的を成就するまでは、', '但在达成最后那个目标之前，', 'R'),
    (0X1C8BA, 14, '僕は決してあきらめません。', '我绝不会放弃。', 'R'),
    (0X1C8D8, 24, '何度でも、何度でも、チャレンジするつもりです。', '无论多少次，我都要一次又一次地挑战。', 'R'),
    (0X1C90A, 19, 'そして、必ずやすべてのエンディングを', '然后，我一定要亲眼看到全部的结局', 'R'),
    (0X1C931, 11, '見ることでしょう。」', '会看到的。」', 'R'),
    (0X1C94A, 17, '題名  「高校生活を振り返って」', '题目 「高中生活回忆」', 'R'),
    (0X1C97C, 22, '「入学してからはやいもので、もう３年の月日が', '「入学以来光阴似箭，三年的时光', 'R'),
    (0X1C9A9, 12, '流れようとしています。', '已然将要流去。', 'R'),
    (0X1C9C3, 23, '勉強にスポーツ、クラブ活動等、とても充実した', '读书、运动、社团活动，一切都很充实', 'R'),
    (0X1C9F2, 14, '日々を私は送ってきました。', '我就这样走过了每天。', 'R'),
    (0X1CA10, 21, 'しかし、一つだけ心残りなことがあります。', '然而，只有一件事让我耿耿于怀。', 'R'),
    (0X1CA3C, 23, 'それは、素敵な男性に巡り合えなかった事です。', '那就是，我没能遇见一位出色的男生。', 'R'),
    (0X1CA6C, 22, 'でも、卒業まであとわずか、きっと素敵な人が', '不过，离毕业只差一点点，一定会有优秀的人', 'R'),
    (0X1CA99, 16, '私の前に現れると信じています。', '出现在我面前，我相信。', 'R'),
    (0X1CABB, 19, 'そして、この学校に伝わる伝説を、私も', '还有，这所学校流传的那个传说，我也想', 'R'),
    (0X1CAE2, 14, '成し遂げようと思います。」', '亲手实现它。」', 'R'),
    (0X1CB01, 11, '題名  「貧血と私」', '题目  「贫血与我」', 'R'),
    (0X1CB27, 23, '「私は小さい頃から身体が弱く、激しい運動をした', '「我从小就身体虚弱，一做剧烈的', 'R'),
    (0X1CB56, 22, 'りすると、すぐに貧血で倒れてしまうのです。', '运动，马上就会贫血晕倒。', 'R'),
    (0X1CB84, 20, 'ですから、友達もあまり多くありません。', '所以，我的朋友并不算多。', 'R'),
    (0X1CBAE, 23, '読書をする事が私にとっての唯一の趣味でした。', '读书对我来说是唯一的爱好。', 'R'),
    (0X1CBDE, 21, 'しかし、これからもこれに負けることなく、', '但是，今后我也不会向它低头，', 'R'),
    (0X1CC09, 21, '貧血と共に歩んで行こうと思っています。」', '我要和贫血一起走下去。」', 'R'),
    (0X1CC36, 11, '題名  「僕の存在」', '题目  「我的存在」', 'R'),
    (0X1CC50,  4, '男子生徒', '男学生', 'R'),
    (0X1CC5A, 19, '「僕は名前ももらえない、悲しい役です。', '「我连一个名字都没有，是个悲哀的', 'R'),
    (0X1CC82, 18, 'こんなところにしか登場できません。', '角色。只能在这种地方登场。', 'R'),
    (0X1CCA8, 17, 'でも、僕はこれからも清く正しく、', '不过，今后我也会清清白白、', 'R'),
    (0X1CCCB, 17, '明るく生きていこうと思います。」', '开朗地活下去。」', 'R'),
    (0X1CCF0, 13, '題名  「届け私の想い」', '题目 「传达我的心意」', 'R'),
    (0X1CD0E,  3, '女生徒', '女学生', 'R'),
    (0X1CD16, 22, '「私は、いつも隠れてある男の子を見ています。', '「我一直在暗处，偷偷注视着一个男生。', 'R'),
    (0X1CD44, 23, 'きっといつか、その男の子が私の方を振り向いて', '总有一天，那个男孩会朝我转过头来', 'R'),
    # The classroom plays: the 严流岛 duel interrupted by a runaway animal,
    # then the tokusatsu hero with a mahjong tile on his head.  Sentences that
    # the rom wraps across two placement runs keep the same break in Chinese.
    (0X1CD73, 12, 'くれると信じています。', '我相信的。', 'R'),
    (0X1CD8D, 15, '何処かにいる私を探してね。」', '快来寻找躲在某处的我吧。」', 'R'),
    (0X1CDAE,  3, '武蔵', '武藏', 'R'),
    (0X1CDB5,  4, '小次郎', '小次郎', 'R'),
    (0X1CDC6, 19, '「潮騒のさざめく、ここ厳流アイランド。', '「潮声阵阵，这里就是严流岛。', 'R'),
    (0X1CDEF, 23, '今、２人の天才剣士が雌雄を決せんとしていた。', '此刻，两位天才剑士正要一决胜负。', 'R'),
    (0X1CE20, 23, '荒磯の波打ち際に立つは、厳流・佐々木小次郎！', '立于乱礁激浪之间的，正是严流佐佐木小次郎！', 'R'),
    (0X1CE51, 20, 'その眼は沖の果てに鋭く向けられていた。', '他的双眼锐利地望向海的尽头。', 'R'),
    (0X1CE7C, 21, '宿敵・宮本武蔵の舟が見えてくるのを待つ。', '等待着宿敌宫本武藏的船影出现。', 'R'),
    (0X1CEA9, 23, '・・・だが、約束の時が過ぎても、決闘の場所に', '……可是，约定的时辰已过，决斗的场地', 'R'),
    (0X1CED8, 12, '武蔵は現われない・・・', '武藏并未现身……', 'R'),
    (0X1CEF9, 10, '「・・・遅い・・・」', '「……好慢……」', 'R'),
    (0X1CF16, 16, '「武蔵、臆したか！それとも策か！', '「武藏，胆怯了吗！还是另有诡计！', 'R'),
    (0X1CF39, 19, '・・・いずれにせよ、卑怯とみたり！！', '……无论如何，都算卑怯！！', 'R'),
    (0X1CF62, 23, '約束の時を違えて、敵の平常心を乱す作戦と思わ', '故意误了约定的时辰，以为这样就能扰乱敌', 'R'),
    (0X1CF91, 22, 'れるが、その様な策に乗る小次郎ではないわ！', '手的平常心，可惜我小次郎不上这种当！', 'R'),
    (0X1CFC0, 19, 'この、物干し刀のサビにしてくれる。」', '定叫你的晾衣刀锈成一堆废铁。」', 'R'),
    (0X1CFEF, 17, '「・・・それにしても、遅い・・・」', '「……话说回来，也真是慢……」', 'R'),
    (0X1D016, 18, '（・・・キャー！なによ、この動物！）', '（……呀！这是什么动物啊！）', 'R'),
    (0X1D03D, 21, '（どこから楽屋に入り込んだんだ、コイツ！）', '（这家伙是从哪里钻进后台的！）', 'R'),
    (0X1D06A, 17, '（うわっ！大道具をかじるなあっ！）', '（哇！别啃布景道具啊！）', 'R'),
    (0X1D095, 13, '「（な、なんだなんだ？）」', '「（什、什么情况？）」', 'R'),
    (0X1D0B8, 18, '「・・・遅いったら遅いったら遅い！」', '「……太慢了，实在是太慢了！」', 'R'),
    (0X1D0E5, 20, '「おのれ、武蔵！さては出番を忘れたか！？', '「可恶，武藏！你莫非忘了自己该登场！？', 'R'),
    (0X1D110, 23, '来ぬば、不戦勝として笑い者にしてくれよう！」', '若是不来，我便以不战而胜看你笑话！', 'R'),
    (0X1D147, 23, '「（・・・本当に遅い。台本と違うぞ・・・！）」', '「（……真的好慢，和剧本说得不一样啊……！）', 'R'),
    (0X1D17A, 19, '（ダメー！その仕掛けをいじっちゃ！！）', '（不行！别碰那个机关啊！！）', 'R'),
    (0X1D1A3, 23, '（・・・早く捕まえろ！舞台が続けられない！！）', '（……快抓住它！戏都演不下去了！！）', 'R'),
    (0X1D1D4, 20, '（それ！この・・・だめだ、よけられた！）', '（看招！这……不行，被躲开了！）', 'R'),
    (0X1D1FF, 15, '（あっちに逃げたぞ、追え！！）', '（往那边逃了，追！！）', 'R'),
    (0X1D220, 16, '（キャー！そっちは舞台よっ！！）', '（呀！那边是舞台啊！！）', 'R'),
    (0X1D249, 20, '「・・・うわわっ！なんだ、コイツは！！」', '「……哇哇！这家伙是什么啊！！」', 'R'),
    (0X1D276, 22, '（まずい！仕掛けのヒモがかじり切られてる！）', '（糟了！布景的绳子被啃断啦！）', 'R'),
    (0X1D2A5, 23, '（・・・え？というコトは、船の仕掛けが・・・）', '（……咦？这么说，船的机关也……）', 'R'),
    (0X1D2D6, 21, '（キャー！船が勝手に動いてるうーーー！！）', '（呀！船自己动起来了——！！）', 'R'),
    (0X1D30B, 12, '「待たせたな、小次郎！！', '「久等了，小次郎！！', 'R'),
    (0X1D325, 11, '・・・ん、小次郎！？」', '……嗯，小次郎！？」', 'R'),
    (0X1D344, 21, '「・・・この勝負、すでに汝の負けと見たり。', '「……这一战，你已经输了。', 'R'),
    (0X1D371, 22, '惜しや小次郎、戦わずして、散るを急いだか。', '可叹小次郎，未战便先赴了死。', 'R'),
    (0X1D3A0, 23, '・・・さらば、小次郎。我が宿命のライバル。」', '……永别了，小次郎，我宿命的对手。', 'R'),
    (0X1D3D7, 13, '「（こんな負け方って・・・', '「（哪有这样的输法……', 'R'),
    (0X1D3F3, 10, 'ありかよぉ・・・）」', '哪有啊……）」', 'R'),
    (0X1D417,  4, 'マジラ', '马吉拉', 'R'),
    (0X1D420,  7, 'ウラドラマン', '乌拉德拉曼', 'R'),
    (0X1D437, 12, '「平和な街に、怪獣出現！', '「和平的街上，怪兽出现！', 'R'),
    (0X1D451, 11, '街を恐怖のどん底に叩き', '将城市彻底推入恐惧', 'R'),
    (0X1D468, 10, '落としています。」', '的深渊。」', 'R'),
    (0X1D485, 14, '「ギャオギャガオガーーー！」', '「嗷嗷嘎嘎——！」', 'R'),
    (0X1D4AA, 18, '「ああ、このままでは街が危ない・・・', '「啊，再这样下去城市就危险了……', 'R'),
    (0X1D4D1,  5, 'おおっ！', '哇！', 'R'),
    (0X1D4DD,  8, 'あ、あれは！！」', '那、那是！！」', 'R'),
    (0X1D4F6, 14, '「頭に付けてるマークは字牌。', '「头上戴的记号是麻将牌。', 'R'),
    (0X1D515, 13, '自慢のリーチで敵を討つ！', '用得意的立直一击克敌！', 'R'),
# The rest of the two classroom plays and the third one: the mahjong hero finishes his
# attack, the 山吹姬 cast list (its full-width latin letters are written out so they get
# their own records -- Ａ/Ｂ were already redrawn for the blood types, the rest were still
# the Japanese font's), then the fairy tale itself.  The dwarf/witch lines are Snow White
# told badly on purpose, so the Chinese keeps the stage-ham delivery rather than tidying it.
    (0X1D533, 22, 'ヤクマンの国から僕らの為に、きたぞ、我等の', '从役满之国来到我们身边，我们的', 'R'),
    (0X1D560, 10, 'ウラドラマン！！」', '乌拉德拉曼！！」', 'R'),
    (0X1D57D,  8, '「テンパイ！！」', '「听牌！！」', 'R'),
    (0X1D596, 11, '「さあ、ウラドラマン！', '「来吧，乌拉德拉曼！', 'R'),
    (0X1D5AE, 12, 'キミのファイティング・ス', '让我们见识一下你的', 'R'),
    (0X1D5C7, 12, 'ピリッツを見せてくれ！', '战斗之魂吧！', 'R'),
    (0X1D5E2, 19, 'マジラ・ファイト、レディ・ゴー！！」', '马吉拉之战，准备——出发！！」', 'R'),
    (0X1D611, 11, '「ギガゴグガオガー！」', '「叽嘎咕噜嘎嗷——！」', 'R'),
    (0X1D630, 15, '「ギャオギャギゲオガーーー！」', '「呀嗷呀叽咯嗷嘎———！」', 'R'),
    (0X1D657, 18, '「ゴアギゴガギグギギャオガゴガー！」', '「嘎啊叽咕嘎叽咕叽嘎呀嘎咕啊——！」', 'R'),
    (0X1D684, 19, '「ハッハッハッ、無駄無駄無駄無駄ァ！」', '「哈哈哈，没用没用没用没用啊！」', 'R'),
    (0X1D6B3, 21, '「リーチ一発ツモドラウラドラ満貫ビーム！」', '「立直一发、自摸、宝牌、里宝、满贯光线！」', 'R'),
    (0X1D6E6, 18, '「ギャオアオアーーーーーーーー！！」', '「呀嗷嗷嗷———！！」', 'R'),
    (0X1D713,  9, '「ハンチャンッ！」', '「和牌——！」', 'R'),
    (0X1D72A, 17, '（・・・おい、何やってるんだよ！）', '（……喂，你们在干什么啊！）', 'R'),
    (0X1D74F, 19, '（ロープが何かに引っ掛かったみたい。）', '（绳子好像被什么东西挂住了。）', 'R'),
    (0X1D778, 20, '（どうするんだよ！？前に進めないぞっ！）', '（怎么办啊！？船往前开不动了！）', 'R'),
    (0X1D7A5, 21, '（えい！えい！・・・だめだ、動かないぞ。）', '（嘿！呀！……不行，推不动啊。）', 'R'),
    (0X1D7D2, 22, '（早く！タイマー仕掛けの電池が持たないわ！）', '（快点！机关里的计时电池要撑不住啦！）', 'R'),
    (0X1D801, 17, '（そ、そんなコト言ったって・・・）', '（这、这么说也没办法啊……）', 'R'),
    (0X1D82C, 24, '「マジラの活躍によりウラドラマンの野望はついえ、', '「在马吉拉的英勇奋战下，乌拉德拉曼的野心破灭了，', 'R'),
    (0X1D85D, 14, '地球には再び平和が戻った。', '地球又重新恢复了和平。', 'R'),
    (0X1D87C, 22, 'しかし、第２、第３のウラドラマンの魔の手が', '然而，第二个、第三个乌拉德拉曼的魔掌', 'R'),
    (0X1D8A9, 14, '襲い来るかも知れないのだ。', '也许还会袭来。', 'R'),
    (0X1D8C8, 23, 'だが、本当の平和な日が来るその日まで、マジラ', '但是，在真正的和平之日到来之前，马吉拉', 'R'),
    (0X1D8F7, 18, 'は私達のために戦ってくれるだろう！', '会继续为我们战斗下去！', 'R'),
    (0X1D91E, 22, 'ありがとう！ありがとう、僕らのマジラ！！」', '谢谢你！谢谢你，我们的马吉拉！！」', 'R'),
    (0X1D94D,  4, '山吹姫', ' 山吹姬', 'R'),
    (0X1D961,  3, '王子', ' 王子', 'R'),
    (0X1D968,  5, '小人 Ａ', ' 矮人 Ａ', 'R'),
    (0X1D973,  5, '小人 Ｂ', ' 矮人 Ｂ', 'R'),
    (0X1D97E,  5, '小人 Ｃ', ' 矮人 Ｃ', 'R'),
    (0X1D989,  5, '小人 Ｄ', ' 矮人 Ｄ', 'R'),
    (0X1D994,  5, '小人 Ｅ', ' 矮人 Ｅ', 'R'),
    (0X1D99F,  5, '小人 Ｆ', ' 矮人 Ｆ', 'R'),
    (0X1D9AA,  5, '小人 Ｇ', ' 矮人 Ｇ', 'R'),
    (0X1D9BB, 15, '「むかしむかしの、そのむかし。', '「从前从前，很久以前。', 'R'),
    (0X1D9DC, 21, '森の中に一人の女の子が暮らしていました。', '在森林深处，住着一个女孩子。', 'R'),
    (0X1DA09, 23, 'その女の子の名前は「山吹姫」といい、森に映え', '那个女孩的名字叫「山吹公主」，她就像', 'R'),
    (0X1DA38, 16, 'る山吹のように美しい娘でした。', '映照林间的山吹花一样美丽的姑娘。', 'R'),
    (0X1DA5A,  7, '森に住む小人達', '林中矮人们', 'R'),
    (0X1DA69, 20, 'と一緒に、仲良く毎日を過ごしています。', '和它们一起，快快乐乐地过着每一天。', 'R'),
    (0X1DA94, 22, '・・・しかし、姫の美しさをねたむ魔法使いが', '……可是，有一位嫉妒公主美貌的', 'R'),
    (0X1DAC1,  7, 'いたのです。', '魔法师。', 'R'),
    (0X1DAD2, 23, '姫がこの世からいなくなれば、自分が世界中で一', '只要公主从这个世上消失，我就是全世界第', 'R'),
    (0X1DB01,  8, '番美しいはず。', '一美人。', 'R'),
    (0X1DB13, 15, 'そう考えた魔法使いは毒リンゴを', '这样想着的魔法师带着毒苹果', 'R'),
    (0X1DB32, 23, 'たずさえ、姫の住む森へ出かけたのです・・・」', '，动身前往公主住的森林去了……」', 'R'),
    (0X1DB69, 15, '「ヒエッ、ヒエッ、ヒエッ・・・', '「嘿嘿、嘿嘿、嘿嘿……', 'R'),
    (0X1DB8A, 11, 'お嬢さん、掃除かい？', '小姑娘，在打扫吗？', 'R'),
    (0X1DBA2,  7, '感心じゃのう。', '真乖呀。', 'R'),
    (0X1DBB3, 24, 'どれ、感心な娘には良いものをあげようかのう。」', '来来，给这么乖的孩子该送点好东西呀。」', 'R'),
    (0X1DBEC,  9, '「わあ、うれしい。', '「哇，好开心。', 'R'),
    (0X1DC01, 14, 'なにかしら、おばあさん。」', '是什么呢，老奶奶。」', 'R'),
    (0X1DC26, 16, '「ヒエッ、ヒエッ・・・よしよし。', '「嘿嘿、嘿嘿……真好真好。', 'R'),
    (0X1DC49, 19, 'ほれ、真っ赤に実ったリンゴじゃよ。」', '来，这是红彤彤的大苹果呀。」', 'R'),
    (0X1DC74, 23, '（・・・クックックッ、このリンゴには毒が入って', '（……咕咕咕咕，这颗苹果里可', 'R'),
    (0X1DCA3,  7, 'おるんじゃ。', '是下了毒的呀。', 'R'),
    (0X1DCB3, 16, 'これを食べればたちまち深ーい深い', '吃了它，马上就会陷入好深好深的', 'R'),
    (0X1DCD4, 18, '眠りに落ちていってしまうのじゃ。）', '睡眠中沉下去呀。）', 'R'),
    (0X1DD01, 21, '「まあ、なんておいしそうなリンゴでしょう。', '「哇，多么诱人的苹果呀。', 'R'),
    (0X1DD2E, 14, 'ありがとう、おばあさん。」', '谢谢你，老奶奶。」', 'R'),
    (0X1DD53, 10, '「・・・ううーーむ。', '……唔——嗯。', 'R'),
    (0X1DD69, 13, 'ワシが手を下さずとも勝手に', '不用老身动手，她自己', 'R'),
    (0X1DD84, 15, '眠りこけてしまいよったわい。', '就呼呼睡过去了。', 'R'),
    (0X1DDA5,  8, 'まあ、良いわ。', '罢了，挺好。', 'R'),
    (0X1DDB7, 15, '一応、目的は達したようじゃし。', '目的总算是达到了。', 'R'),
    (0X1DDD8, 22, '・・・しかし、ワシはなーーーんの為に老体に', '……可是，老身究竟是为了什么，拖着这把', 'R'),
    (0X1DE05, 22, 'ムチ打って、ここまで来たんじゃろうか・・・', '老骨头拼命赶到这里来的呢……', 'R'),
    (0X1DE34, 21, '・・・いててて、ギ、ギックリ腰が・・・」', '……哎哟哟，闪、闪了腰了……」', 'R'),
    (0X1DE67, 15, '「ああ、なんという事でしょう。', '「啊，怎么会这样。', 'R'),
    (0X1DE88, 23, '山吹姫は悪い魔法使いのリンゴのワナによって、', '山吹公主被坏魔法师那颗毒苹果骗了，', 'R'),
    (0X1DEB7, 19, '長い長い眠りに落ちてしまったのです。', '陷入了好长好长的沉睡。', 'R'),
    (0X1DEE0, 19, 'その寝顔は神々しいほどに美しい・・・', '她的睡脸美得近乎神圣……', 'R'),
    (0X1DF08,  4, 'しかし、', '然而，', 'R'),
    (0X1DF11, 23, '仲良しの森の小人達の手当ても空しく、姫は目を', '好朋友森林矮人们的治疗都白费了，公主始', 'R'),
    (0X1DF40, 15, 'さますことはなかったのです。', '终没有醒来。', 'R'),
    (0X1DF67, 10, '「えーん、えーん。」', '「呜呜，呜呜。」', 'R'),
    (0X1DF84, 20, '「・・・んーー・・・むにゃむにゃ・・・」', '……嗯——…嘟嘟囔囔……', 'R'),
    (0X1DFB5, 14, '「えーん、えーん、えーん。」', '「呜呜，呜呜，呜呜。」', 'R'),
    (0X1DFDA, 22, '「・・・むにゃ・・・もう食べれなあい・・・」', '……嘟嘟…再也吃不下去啦……', 'R'),
    (0X1E03E, 21, '（・・・そんなコトはないと思うけど・・・）', '（……倒也不是没有那种可能啦……）', 'R'),
    (0X1E09A, 19, '「そこに通りかかったのは隣の国の王子。', '「这时恰好路过的是邻国的王子。', 'R'),
    (0X1E0FA, 21, '「小人さん、何をそんなに悲しんでいるの？」', '「矮人们，你们为什么这样悲伤？', 'R'),
    (0X1E162, 23, '「悪い魔法使いのリンゴによって、頭部負傷、全身', '「被坏魔法师的毒苹果所害，头部负伤，全身', 'R'),
    (0X1E1C2,  6, '「どれ・・・', '「让我瞧瞧…', 'R'),
    (0X1E1D0, 17, 'おお、なんと美しい娘であろうか。」', '啊，世上竟有这样美丽的姑娘。」', 'R'),
    (0X1E226, 23, '寝顔に優しくキスをしようと顔を近付けます。」', '他温柔地凑近她的睡脸，想要亲上一口。」', 'R'),
    (0X1E28E, 16, 'よりて、目ざめんことを・・・」', '才醒得过来吧……」', 'R'),
    (0X1E2D2,  7, '「え・・・？」', '「咦…？', 'R'),
    (0X1E320, 18, '「うわわわわわあああーーーー！！！」', '「哇啊啊啊啊———！！！', 'R'),
    (0X1E372, 16, 'これで、これで金メダルよ！！！', '这样、这样就能拿金牌啦！！！', 'R'),
    (0X1E3C2,  9, '・・・て、あれ？', '……诶，那是啥？', 'R'),
    (0X1E3D6,  7, 'ここはどこ？」', '这里是哪儿？」', 'R'),
    (0X1E414, 18, '「あーあ、姫様、寝ぼけてたんだあ。」', '「唉—，公主殿下刚才还在犯迷糊呢。', 'R'),
    (0X1E47A, 20, '「そうそう、嫁の貰い手がなくなるぞお。」', '「就是就是，再这样下去就要嫁不出去啦。', 'R'),
    (0X1E4D8, 16, '「・・・ううう・・・（ガクッ）」', '「……呜呜呜……（瘫倒）', 'R'),
# The ending theme, sung over the credit roll ($1E4FE-$1E8A0).  This band was parked for
# two rounds on the strength of a HANDOFF figure that put the song ~150 characters away
# from affordability -- but that counted every character in the lyrics, while a batch only
# pays for the ones the font does not already hold, and the prologue had already injected
# 1142 of them.  Measured against glyph_alloc.json these 26 rows add 12 records (代伴句吓
# 季恋惯懂渐越踩迟), so the song goes in.  Each line is capped by its own run's code count
# and the halves keep the stock mid-line space, so the meter of the roll is unchanged.
        (0X1E4FE, 11, 'デートの下見の 水族館', '约会踩点的 水族馆', 'R'),
        (0X1E518, 13, '彼女のかわりに 付き合う私', '我代替她 和他约会', 'R'),
        (0X1E536, 13, '待ち合わせに 遅れてきても', '约定的时间 就算迟到', 'R'),
        (0X1E554, 12, '謝る素振りは 一つないの', '丝毫没有 要道歉的样子', 'R'),
        (0X1E570, 11, '髪の毛 触ってるときは', '头发 被摸到的时候', 'R'),
        (0X1E58A, 10, '彼女思い出してるのね', '是在想着她吧', 'R'),
        (0X1E5A2, 12, 'サカナの様に 言葉なしで', '就像鱼儿一样 没有言语', 'R'),
        (0X1E5BE, 11, 'わかるのが つらいのよ', '懂得越多 越难受', 'R'),
        (0X1E5D8, 11, '誰が見ても 二人は恋人', '谁都看得出 我们是恋人', 'R'),
        (0X1E5F2,  8, '同士なのに・・・', '明明是同伴…', 'R'),
        (0X1E61C, 11, 'あなたには お似合いの', '与你倒是 很相配', 'R'),
        (0X1E650,  5, 'わかってる', '我知道', 'R'),
        (0X1E65E, 13, '私より かわいいと思えない', '不觉得 她比我可爱', 'R'),
        (0X1E69E,  8, '釣り合わないのよ', '配不上啦', 'R'),
        (0X1E6CC,  9, '優しい言葉かけられ', '一句温柔的话', 'R'),
        (0X1E702,  5, 'ひかれた私', '我被吓到', 'R'),
        (0X1E728, 10, 'だんだん 目が慣れて', '渐渐 看习惯了', 'R'),
        (0X1E740, 10, 'じわじわ 好きになる', '慢慢 喜欢上你', 'R'),
        (0X1E772, 11, 'ぜんぜん 理想じゃない', '完全 不是理想型', 'R'),
        (0X1E78C, 10, 'さんざん わかってる', '早就 明白了', 'R'),
        (0X1E7BC,  4, '季節には', '季节里', 'R'),
        (0X1E7DA, 11, '上手になってしまうけど', '可是已经 很擅长了', 'R'),
        (0X1E808,  9, '風船は 知らぬ間に', '气球在 不知不觉', 'R'),
        (0X1E834, 12, '割れるショックも 大きい', '破掉的冲击 也很大', 'R'),
        (0X1E868, 14, '通用しない 聖書（バイブル）', '派不上用场 的圣经', 'R'),
        (0X1E8A0,  8, '割と 難しい宿題', '相当 难的作业', 'R'),
# The ending credits that roll after a clear: the role labels and the staff lines whose
# names the preset pool has already renamed (青山 和浩, 吉冈 思远).  The romaji nicknames
# stay as they are because they are handles, not words.
        (0X1E8B4, 10, 'ときめきメモリアル', ' 心跳回忆', 'R'),
        (0X1E8E4, 12, '＜＜開発スタッフ＞＞', '  ＜＜制作班底＞＞', 'R'),
        (0X1E9EC,  6, '＜背景原画＞', '＜背景原画＞', 'R'),
        (0X1EA10,  9, '＜背景圧縮・管理＞', '＜背景压缩、管理＞', 'R'),
        (0X1EA3A,  6, '＜背景ＣＧ＞', '＜背景美术＞', 'R'),
        (0X1EB14,  8, '＜エンディング＞', '＜片尾画面＞', 'R'),
        (0X1ED56, 13, '〜ＳＦＣゲームイベント〜', '〜游戏活动〜', 'R'),
        (0X1EDC8, 11, '＜サウンドプログラム＞', '＜音响程序＞', 'R'),
        (0X1EDF8,  4, '＜音楽＞', '＜音乐＞', 'R'),
        (0X1EE7A, 12, '＜プロダクト・デザイン＞', '＜产品设计＞', 'R'),
        (0X1EEA4,  4, '＜協力＞', '＜协力＞', 'R'),
        (0X1EF94, 15, '＜ときめも統括プロデューサー＞', '＜心跳回忆总监督＞', 'R'),
        (0X1EFC4,  9, '＜プロデューサー＞', '＜制片人＞', 'R'),
        (0X1EAD0,  9, 'プログラム・・・', '  程序', 'R'),
        (0X1E97E,  9, '吉岡 さとし', '吉冈 思远', 'R'),
        (0X1E9C4,  8, '青山 和浩', '青山 和浩', 'R'),
        (0X1EAA6,  8, '青山 和浩', '青山 和浩', 'R'),
        (0X1EC18, 14, '青山 和浩', '青山 和浩', 'R'),
        (0X1EC7C, 15, 'ＣＧ・・・・・吉岡 さとし', '美术・・・・・吉冈 思远', 'R'),
        (0X1ED18, 15, 'ＣＧ・・・・・吉岡 さとし', '美术・・・・・吉冈 思远', 'R'),
        (0X1ED8C, 15, 'ＣＧ・・・・・吉岡 さとし', '美术・・・・・吉冈 思远', 'R'),
        (0X1EBBE, 14, 'データ作成・・・青山 和浩', '资料制作・・青山 和浩', 'R'),
        (0X1EB84, 14, 'エピローグ・・・田安 剛士', '尾声・・・・・田安 刚士', 'R'),
# The credit roll's second half lists the staff by name, and these are real Chinese
# names whose stock forms are the Japanese ones (剛 橋 紀 衛 館 聖 達).  Per the
# no-JIS-substitution rule those must be redrawn; 上原 和彦 and 梶尾助一 are left
# alone because their kanji already *are* the Chinese codepoints, so a row would
# spend a slot to re-point an identical glyph.  10 new records: 函 史 司 夜 庄 昌 村 椋 雅
# (plus 达's, in place); the last row keeps its kana handle on stock codes with UI_KEEP,
# because a kana in a Chinese row would otherwise buy a fresh WenQuanYi slot that has no
# kana bitmap behind it.
        (0X1E99E,  8, '田安 剛士', '   田安 刚士', 'R'),
        (0X1EE1A,  8, '高橋 紀子', '   高桥 纪子', 'R'),
        (0X1EE36,  8, '衛藤 英幸', '   卫藤 英幸', 'R'),
        (0X1EECA, 14, '函館 次郎    小椋 雅史', '函馆 次郎    小椋 雅史', 'R'),
        (0X1EEF4, 13, '村井 聖夜    荘 司朗', '村井 圣夜    庄 司朗', 'R'),
        (0X1EF60, 13, 'いもほれいまい  安達昌宣',
         '为心动所迷的我  安达昌宣', 'R'),
    # （0x1E6xx）、职员表标签与 kana 昵称（0x1E8xx-0x1EFxx、0x185xx、0x1ACxx）、
    # 文化祭节目单选择器（0x1C1D0-0x1C6DE）。jp 全部是 ui_run 的原样回读；
    # 0X1EA49/0X1EB65 的尾格是半长音 UI_KEEP 格，注册进 run 内、随重编消失。
(0X1E00B, 24, '（おい、まさか本当に寝てるんじゃないだろうな？）', '（喂，不会真睡着了吧？）', 'R'),
(0X1E06B, 19, '（そうだな・・・よし、王子様、ＧＯ！）', '（说得对…好，王子，上！）', 'R'),
(0X1E0C3, 23, '泣いている小人達に気がついて、近づきます。」', '注意到哭泣的矮人们，走近。」', 'R'),
(0X1E12D,  5, '「えーん。', '「呜呜。', 'R'),
(0X1E139, 16, '姫様が、姫様が死んじゃったー。」', '公主、公主死掉啦。」', 'R'),
(0X1E191, 20, '打僕、意識不明、焼肉定食なんですー。」', '浑身淤青，不省人事。」', 'R'),
(0X1E1FB, 20, '「姫のあまりの美しさに、心惹かれる王子。', '「公主美得令王子心动。', 'R'),
(0X1E25D,  7, '「美しい娘よ。', '「好美的姑娘', 'R'),
(0X1E26D, 16, '我が願いが叶うなら、この口づけに', '「若这一吻能遂我心愿', 'R'),
(0X1E2B7,  9, '「・・・そ・・・」', '「…呀…', 'R'),
(0X1E2E9, 23, '「そりゃああ！！必殺・横巴投げえーーー！！！」', '「呀啊啊！！必杀横巴投——！」', 'R'),
(0X1E34D,  9, '「やったーーーー！', '「赢啦——！', 'R'),
(0X1E361,  7, '見事な一本！！', '精彩的一本！', 'R'),
(0X1E395,  5, 'コーチ！', '「教练', 'R'),
(0X1E3A1,  5, 'コーチ！！', '「教练', 'R'),
(0X1E3AD,  8, '見てくれました？', '看到我了吗？', 'R'),
(0X1E3ED, 15, '「・・・い、いだだだだ・・・」', '「痛死我了……」', 'R'),
(0X1E441, 24, '「まったく、寝相の悪さもたいがいにしてよねえ。」', '「真是的，睡相差也太夸张了啦。」', 'R'),
(0X1E4AB, 18, '「うるさいわね、あなたたちは・・・」', '「好吵哦，你们这些家伙…', 'R'),
(0X1E605, 10, '「あきらめた・・・」', '「放弃了…」', 'R'),
(0X1E635, 12, '付き合ってる人がいること', '已有交往对象', 'R'),
(0X1E67B, 16, 'あんな娘（こ）選ぶ センスだから', '竟选 那样的女孩', 'R'),
(0X1E6B1, 12, '落ち込んでたとき 不意に', '低落时 突然', 'R'),
(0X1E6E1, 15, '芝居じみてて わざとらしいけど', '像演戏 挺做作', 'R'),
(0X1E70F, 11, 'たまたま そばにいたら', '刚好在身边', 'R'),
(0X1E757, 12, 'もともと タイプじゃない', '本来没来电', 'R'),
(0X1E7A3, 11, '黒板の文字が 速すぎる', '板书 太快了', 'R'),
(0X1E7C7,  8, '傷つける事ばかり', '只会伤人', 'R'),
(0X1E7F3,  9, 'ときめきという名の', '名叫心跳', 'R'),
(0X1E81D, 10, 'ふくらんでしまうから', '就会鼓起来', 'R'),
(0X1E84F, 11, '恋は 神様の常識なんか', '神不懂恋爱', 'R'),
(0X1E887, 11, '夢は 平凡な幸せだけど', '梦虽平凡', 'R'),
(0X1E8C9, 13, '〜伝説の樹の下で〜', '〜传说树下〜', 'R'),
(0X1E8FD,  8, '＜ディレクター＞', '＜监督＞', 'R'),
(0X1E90E,  8, '青山 和浩', '青山 和浩', 'R'),
(0X1E91F,  9, '＜ゲームシステム＞', '＜游戏系统＞', 'R'),
(0X1E932,  7, 'Ｇｅｎ．', 'Ｇｅｎ．', 'R'),
(0X1E941, 13, '＜バストアップキャラＣＧ＞', '＜半身角色美术＞', 'R'),
(0X1E95C,  7, 'かづみＴ', '和实Ｔ', 'R'),
(0X1E96B,  9, '＜ＳＤキャラＣＧ＞', '＜迷你角色美术＞', 'R'),
(0X1E9AF, 10, '＜シナリオデコード＞', '＜剧本解码＞', 'R'),
(0X1E9D7,  9, 'とらじろー★', '虎次郎★', 'R'),
(0X18505, 14, '＊＊サウンドテストモード＊＊', '＊＊音效测试模式＊＊', 'R'),
(0X18524,  4, 'ＢＧＭ', 'ＢＧＭ', 'R'),
(0X18553,  3, '女の子', '女孩子', 'R'),
(0X1A444,  4, 'ＢＯＸ内', 'ＢＯＸ内', 'R'),
(0X1AC0E,  5, '流れ★でも', '流淌★但是', 'R'),
(0X1E9F9, 11, 'スタジオグリーン', '格林工作室', 'R'),
(0X1EA25,  9, 'とらじろー★', '虎次郎★', 'R'),
(0X1EA49,  8, 'なかぢー', '阿二', 'R'),
(0X1EA5C,  9, 'とろとろ藤井', '迷迷糊糊藤井', 'R'),
(0X1EA6F, 11, '＜イベントプログラム＞', '＜活动程序＞', 'R'),
(0X1EA91, 10, '＜メインプログラム＞', '＜主程序＞', 'R'),
(0X1EAB9, 11, '＜データ登録システム＞', '＜数据登录系统＞', 'R'),
(0X1EAE4,  6, 'とらじろー★', '虎次郎★', 'R'),
(0X1EAF3, 15, 'ＣＧ・・・・・・吉岡 さとし', '美术・・・・・・吉冈 思远', 'R'),
(0X1EB25,  9, 'プログラム・・・', '  程序', 'R'),
(0X1EB39,  6, 'とらじろー★', '虎次郎★', 'R'),
(0X1EB48, 13, 'ＣＧ・・・・・・かづみＴ', '美术・・・・・・和实Ｔ', 'R'),
(0X1EB65, 14, 'なかぢー', '阿二', 'R'),
(0X1EBA1, 13, 'スタッフロール・Ｇｅｎ．', '职员表・Ｇｅｎ．', 'R'),
(0X1EBDB, 12, '＜サブゲーム＆イベント＞', '＜迷你游戏＆活动＞', 'R'),
(0X1EC01, 11, 'プログラム・・がみ', '程序・・加见', 'R'),
(0X1EC35, 15, 'ＣＧ・・・・・吉岡 さとし', '美术・・・・・吉冈 思远', 'R'),
(0X1EC61, 13, 'プログラム・・Ｇｅｎ．', '程序・・Ｇｅｎ．', 'R'),
(0X1ECA6, 11, 'プログラム・・がみ', '程序・・加见', 'R'),
(0X1ECBD, 14, '青山 和浩', '青山 和浩', 'R'),
(0X1ECDA, 13, 'Ｇｅｎ．', 'Ｇｅｎ．', 'R'),
(0X1ECF7, 15, 'とらじろー★', '虎次郎★', 'R'),
(0X1ED37, 15, 'とろとろ藤井', '迷迷糊糊藤井', 'R'),
(0X1ED71, 13, 'プログラム・・Ｇｅｎ．', '程序・・Ｇｅｎ．', 'R'),
(0X1EDAB, 14, '会話構成・・・田安 剛士', '对白构成・・・田安 刚士', 'R'),
(0X1EDDF, 12, 'けろっぴ いのうえ', '青蛙君 井上', 'R'),
(0X1EE01, 12, 'けろっぴ いのうえ', '青蛙君 井上', 'R'),
(0X1EE47,  8, '＜ミニＣＤ制作＞', '＜迷你ＣＤ制作＞', 'R'),
(0X1EE58,  8, '上原 和彦', '上原 和彦', 'R'),
(0X1EE69,  8, '流石野 孝', '流石野 孝', 'R'),
(0X1EE93,  8, '難波 和宏', '难波 和宏', 'R'),
(0X1EEAD, 14, 'ＩＧＡ      茅ヶ崎 京', 'ＩＧＡ      茅崎 京', 'R'),
(0X1EEE7,  6, 'メタルユーキ', '金属勇树', 'R'),
(0X1EF0F, 14, '東野美紀     地獄車中村', '东野美纪     地狱车中村', 'R'),
(0X1EF2C, 13, 'ＡＫＴ      梶尾助一', 'ＡＫＴ      梶尾助一', 'R'),
(0X1EF47, 12, '立石孝      ＮＯＲ', '立石孝      ＮＯＲ', 'R'),
(0X1EF7B, 12, '力竜太      Ｈ．Ｍ', '力龙太      Ｈ．Ｍ', 'R'),
(0X1EFB3,  8, '福武 茂', '福武 茂', 'R'),
(0X1EFD7,  9, '長江 勝也', '长江 胜也', 'R'),
(0X1EFF9, 11, 'コナミ株式会社', '科乐美公司', 'R'),
(0X1C1D0, 17, '〜 文化祭セレクター  Ｇｅｎ．〜', '〜　文化节选择器　Ｇｅｎ．〜', 'R'),
(0X1C1F3, 11, '０：弁論（プレイヤー）', '０：演讲（玩家）', 'R'),
(0X1C20A,  8, '０：弁論（藤崎）', '０：演讲（藤崎）', 'R'),
(0X1C21B,  8, '０：弁論（如月）', '０：演讲（如月）', 'R'),
(0X1C22C,  9, '０：弁論（ＮＰＣ）', '０：演讲（ＮＰＣ）', 'R'),
(0X1C23F,  8, '０：弁論（館林）', '０：演讲（馆林）', 'R'),
(0X1C250, 13, '１：ロボット（プレイヤー）', '１：机器人（玩家）', 'R'),
(0X1C26B, 10, '１：ロボット（藤崎）', '１：机器人（藤崎）', 'R'),
(0X1C280, 10, '１：ロボット（紐緒）', '１：机器人（纽绪）', 'R'),
(0X1C295, 11, '１：ロボット（ＮＰＣ）', '１：机器人（ＮＰＣ）', 'R'),
(0X1C2AC, 13, '２：レーザー（プレイヤー）', '２：激光束（玩家）', 'R'),
(0X1C2C7, 10, '２：レーザー（藤崎）', '２：激光束（藤崎）', 'R'),
(0X1C2DC, 10, '２：レーザー（紐緒）', '２：激光束（纽绪）', 'R'),
(0X1C2F1, 11, '２：レーザー（ＮＰＣ）', '２：激光束（ＮＰＣ）', 'R'),
(0X1C308,  9, '３：演劇（巌流島）', '３：演剧（岩流岛）', 'R'),
(0X1C31B, 12, '３：演劇（ウラドラマン）', '３：演剧（乌拉德拉曼）', 'R'),
(0X1C334,  9, '３：演劇（白雪姫）', '３：演剧（白雪）', 'R'),
(0X1C347, 16, '４：演奏会（１年：主人公＆藤崎）', '４：演奏会（１年：主角＆藤崎）', 'R'),
(0X1C368, 16, '４：演奏会（１年：主人公＆片桐）', '４：演奏会（１年：主角＆片桐）', 'R'),
(0X1C389, 17, '４：演奏会（１年：主人公＆ＮＰＣ）', '４：演奏会（１年：主角＆ＮＰＣ）', 'R'),
(0X1C3AC, 16, '４：演奏会（１年：ＮＰＣ＆藤崎）', '４：演奏会（１年：ＮＰＣ＆藤崎）', 'R'),
(0X1C3CD, 16, '４：演奏会（１年：ＮＰＣ＆片桐）', '４：演奏会（１年：ＮＰＣ＆片桐）', 'R'),
(0X1C3EE, 17, '４：演奏会（１年：ＮＰＣ＆ＮＰＣ）', '４：演奏会（１年：ＮＰＣ＆ＮＰＣ）', 'R'),
(0X1C411, 16, '５：演奏会（２年：主人公＆藤崎）', '５：演奏会（２年：主角＆藤崎）', 'R'),
(0X1C432, 16, '５：演奏会（２年：主人公＆片桐）', '５：演奏会（２年：主角＆片桐）', 'R'),
(0X1C453, 17, '５：演奏会（２年：主人公＆ＮＰＣ）', '５：演奏会（２年：主角＆ＮＰＣ）', 'R'),
(0X1C476, 16, '５：演奏会（２年：ＮＰＣ＆藤崎）', '５：演奏会（２年：ＮＰＣ＆藤崎）', 'R'),
(0X1C497, 16, '５：演奏会（２年：ＮＰＣ＆片桐）', '５：演奏会（２年：ＮＰＣ＆片桐）', 'R'),
(0X1C4B8, 17, '５：演奏会（２年：ＮＰＣ＆ＮＰＣ）', '５：演奏会（２年：ＮＰＣ＆ＮＰＣ）', 'R'),
(0X1C4DB, 16, '６：演奏会（３年：主人公＆藤崎）', '６：演奏会（３年：主角＆藤崎）', 'R'),
(0X1C4FC, 16, '６：演奏会（３年：主人公＆片桐）', '６：演奏会（３年：主角＆片桐）', 'R'),
(0X1C51D, 17, '６：演奏会（３年：主人公＆ＮＰＣ）', '６：演奏会（３年：主角＆ＮＰＣ）', 'R'),
(0X1C540, 16, '６：演奏会（３年：ＮＰＣ＆藤崎）', '６：演奏会（３年：ＮＰＣ＆藤崎）', 'R'),
(0X1C561, 16, '６：演奏会（３年：ＮＰＣ＆片桐）', '６：演奏会（３年：ＮＰＣ＆片桐）', 'R'),
(0X1C582, 17, '６：演奏会（３年：ＮＰＣ＆ＮＰＣ）', '６：演奏会（３年：ＮＰＣ＆ＮＰＣ）', 'R'),
(0X1C5A5, 12, '７：ときめき占い（如月）', '７：心跳占卜机（如月）', 'R'),
(0X1C5BE, 10, '７：怪しい薬（紐緒）', '７：可疑药（纽绪）', 'R'),
(0X1C5D3, 14, '７：ときめき危機一髪（片桐）', '７：心跳千钧一发（片桐）', 'R'),
(0X1C5F0, 12, '７：ときめき福引（虹野）', '７：心跳大转盘（虹野）', 'R'),
(0X1C609, 13, '７：ときめきハニワ（古式）', '７：心跳陶俑游戏（古式）', 'R'),
(0X1C624, 15, '７：ときめきスイカ割り（清川）', '７：心跳打西瓜（清川）', 'R'),
(0X1C643, 13, '７：ときめきスロット（鏡）', '７：心跳老虎机（镜）', 'R'),
(0X1C65E, 15, '７：ときめきクエスト（朝比奈）', '７：心跳大冒险（朝日奈）', 'R'),
(0X1C67D, 13, '７：ときめき競馬（美樹原）', '７：心跳赛马游戏（美树原）', 'R'),
(0X1C698, 16, '７：ときめきカードゲーム（優美）', '７：心跳纸牌游戏（优美）', 'R'),
(0X1C6B9,  7, '８：おまけ １', '８：附加　１', 'R'),
(0X1C6C8,  7, '８：おまけ ２', '８：附加　２', 'R'),
(0X1C6D7,  8, '８：奥技獲得デモ', '８：奥义获得演示', 'R'),
    # The band-final sweep: every maximal glyph run the enumeration left outside
    # registered spans and the keyboard band (task #17's 0x1F2D4-0x1F88D stays
    # untouched, and 0x1FB50 turned out to be an address-vector table, not text).
    # Almost all are same-form bookkeeping -- the affinity grid's ●×▲―, the
    # elision rows ‥, １９９/ＡＢ型, 早乙女, the calendar columns' 月 header --
    # registered so the zero-Japanese audit can call the band clean; only 野球
    # actually re-reads.  The 月 columns carry one KEEP + blank per weekday cell.
    (0X19B3F,  2, '野球', '棒球', 'R'),
    (0X19268,  8, '●×▲―×●▲●', '●×▲―×●▲●', 'R'),
    (0X19279,  8, '××▲―●▲●×', '××▲―●▲●×', 'R'),
    (0X1928A,  8, '▲▲▲―●●×●', '▲▲▲―●●×●', 'R'),
    (0X1929B,  8, '▲×●―×●×●', '▲×●―×●×●', 'R'),
    (0X192AC,  8, '▲×●―▲▲××', '▲×●―▲▲××', 'R'),
    (0X192BD,  8, '●●●―×▲▲×', '●●●―×▲▲×', 'R'),
    (0X192CE,  8, '▲××―●×▲×', '▲××―●×▲×', 'R'),
    (0X192DF,  8, '▲▲×―●××▲', '▲▲×―●××▲', 'R'),
    (0X192F0,  8, '●▲●―×▲●▲', '●▲●―×▲●▲', 'R'),
    (0X19301,  8, '●×▲―▲×●●', '●×▲―▲×●●', 'R'),
    (0X19312,  8, '●●●―▲▲××', '●●●―▲▲××', 'R'),
    (0X19323,  8, '●▲×―●▲×●', '●▲×―●▲×●', 'R'),
    (0X190CB,  4, '‥‥‥‥', '‥‥‥‥', 'R'),
    (0X190D4,  5, '‥‥‥‥‥', '‥‥‥‥‥', 'R'),
    (0X18342,  3, '‥‥‥', '‥‥‥', 'R'),
    (0X190DF,  3, '‥‥‥', '‥‥‥', 'R'),
    (0X19B49,  4, '−−−−', '−−−−', 'R'),
    (0X180F4,  3, '早乙女', '早乙女', 'R'),
    (0X183E8,  3, '１９９', '１９９', 'R'),
    (0X18780,  3, '１９９', '１９９', 'R'),
    (0X19187,  3, 'ＡＢ型', 'ＡＢ型', 'R'),
    (0X1F1B0,  3, 'ＡＢ型', 'ＡＢ型', 'R'),
    (0X1F1CF, 17, (K + '月 ') * 5 + K + '月', (K + '月 ') * 5 + K + '月', 'R'),
    (0X1F1F4, 17, (K + '月 ') * 5 + K + '月', (K + '月 ') * 5 + K + '月', 'R'),
    # task #35: the prologue SFX label cluster (collision 「ドン」 + the
    # ringtone's per-cell kana pieces + the magazine banner fragments).
    (0X193C1,  2, 'ドン', '咚', 'R'),
    (0X193CD,  1, 'ト', '嘟', 'R'),
    (0X193D0,  1, 'ゥ', '嘟', 'R'),
    (0X193D3,  1, 'ル', '噜', 'R'),
    (0X193D6,  1, 'ぷ', '嘟', 'R'),
    (0X193D9,  1, 'る', '噜', 'R'),
    (0X19382,  1, '点', '点', 'R'),
    (0X19398,  2, '創刊', '创刊', 'R'),
    (0X193AD,  2, '月号', '月号', 'R'),
    # The name-entry keyboard pools ($1F2D4-$1F88D) must NOT be re-encoded:
    # the engine derives the character a key inputs from the glyph index it
    # stores there, so Chinese indices make the screen-init jump off a cliff
    # (black-screen hang, 批次U bisect).  The keys already read as Chinese:
    # backfill_records() redraws each kana band record with its homophone
    # bitmap, so the stock pool displays 啊衣呜... while still inputting kana.
)

# A label whose bytes alternate glyph codes with $40-$9F code-page bytes and
# dictionary calls cannot be fixed cell by cell: every surviving kana SB byte
# draws whatever the *Chinese* page now says (ッ→慨, ー→我), and every hijacked
# glyph index draws our fresh pool.  These rows re-encode a whole line inside its
# original span: text becomes pure 2-byte glyph cells, the leftover bytes become
# $0A (the engine stops at the first one, so padding never draws), and the line's
# delimiters ($2E joins, $0A/A0 ends) stay outside the span.  A span may hold
# glyph cells, SB bytes, «A0-E7» phrase calls and ⟦E8-EF xx⟧ sub-text calls --
# the swallowed calls are simply no longer emitted -- but never an
# operand-eating control byte (<$40 outside a call), which is how the date-print
# slot labels (⟦E801⟧) stay untouched.  `jp` is the span decoded through the
# Japanese page, an assertion that the row names the string actually there.
UI_LINE_ROWS = (
    # Date scheduling prompts (the phone-call flow) and the mouse/pad settings
    # screen -- the garble the user screenshotted (鼠标与手柄慨 / 东西行力速度 /
    # デ我タSAVE / 快这慢这).
    (0X194F0, 18, 'デートする日を指定してください', '请指定约会的日子'),
    (0X19504, 19, 'デート場所を指定してください', '请指定约会的地点'),
    (0X19519, 17, 'マウス・パッド設定', '鼠标与手柄的设定'),
    (0X1952C, 13, '⟦ECE8⟧出力速度設定', '文字输出速度'),
    (0X1953B,  7, 'データ⟦EC15⟧', '存储'),
    (0X19544, 13, 'データＬＯＡＤ', '读取进度'),
    (0X1955D, 19, 'カーソル移動速度設定', '光标移动速度设定'),
    (0X19572, 19, 'マウス決定ボタン設定', '鼠标确认键设定'),
    (0X19587,  5, '⟦E966⟧速い', '快'),
    (0X1958E,  6, '⟦E966⟧普通', '中'),
    (0X19596,  5, '⟦E966⟧遅い', '慢'),
    (0X1959D, 23, 'マウスでの決定を右ボタンにする', '用右键确认'),
    (0X195B6, 23, 'マウスでの決定を左ボタンにする', '用左键确认'),
    (0X195CF,  5, '⟦EA61⟧速い', '快'),
    (0X195D6,  6, '⟦EA61⟧普通', '中'),
    (0X195DE,  5, '⟦EA61⟧遅い', '慢'),
    # The file menu.  The prompt line opens right after the slot-number splice
    # (１．〔ctrl〕２．〔ctrl〕...), so it carries the `loose` flag; the rest are
    # whole pool entries.  A trailing «A0» stays outside the span and draws the
    # 。 for free.  0x1968D keeps its two ⟦0B newlines -- the only control byte
    # the walk admits -- so the three-line layout survives.
    (0X195FD, 14, 'ファイルを⟦ED4F⟧して⟦EC7E⟧', '请选择存储进度', True),
    (0X1960D, 10, '３．⟦EC15⟧中止', '３．取消'),
    (0X19619, 11, '⟦EC15⟧を中止します', '取消存储'),
    (0X19626, 12, '⟦EC16⟧１に⟦EC15⟧しました', '已存入进度１'),
    (0X19634, 12, '⟦EC16⟧２に⟦EC15⟧しました', '已存入进度２'),
    (0X19642, 16, '３．ＬＯＡＤ中止', '３．取消读取'),
    (0X19654, 17, 'ＬＯＡＤを中止します', '已取消读取'),
    (0X19667, 17, '⟦EC16⟧１をＬＯＡＤします', '开始读取进度１'),
    (0X1967A, 17, '⟦EC16⟧２をＬＯＡＤします', '开始读取进度２'),
    (0X1968D, 42, '⟦EC15⟧とＬＯＡＤは⟦0B⟧平日コマンド入力時でしか⟦0B⟧実行できません',
     '存储与读取只能⟦0B⟧在工作日的指令输入⟦0B⟧时进行'),
    (0X196B9, 10, '１．未使用', '存储进度１'),
    (0X196C5, 10, '２．未使用', '存储进度２'),
    (0X196D1, 16, '１．記録されていません', '进度１暂无存档'),
    (0X196E3, 16, '２．記録されていません', '进度２暂无存档'),
    (0X196F5, 19, '⟦EC16⟧１はＬＯＡＤできません', '无法读取进度１'),
    (0X1970A, 19, '⟦EC16⟧２はＬＯＡＤできません', '无法读取进度２'),
    # The schedule panel's holiday chatter + announcement pool -- the lines the user
    # read as 「么嗯上、诗织约会。」: the SB bytes 今日は、 now spell 么嗯上 through
    # the Chinese page, so every entry needs whole-line re-encoding.  Spans here
    # swallow the trailing «A0» (it is a token, and keeping it inside buys the 。
    # even when the padding lands a $0A first); lines whose JP ends on $0A keep
    # that byte outside the span -- $0A inside a span is what froze the pool walk
    # (bug #36), and the padding already terminates.  ⟦EB3F⟧ (约会), ⟦EAC7⟧ (补休),
    # ⟦ED0F⟧ (体育), ⟦ECDA⟧ (儿童), ⟦ED72⟧ (专题)... stay as calls: their bodies
    # are Chinese and the spans cannot hold them inline.  The 安田 line 0x1974F is
    # NOT here -- its `12 00 00` speaker prefix is operand bytes the walk rejects.
    (0X1971F,  9, '今日は元旦だ«A0»', '今天元旦«A0»'),
    (0X19729, 10, '今日は成人の日だ«A0»', '成人节«A0»'),
    (0X19734, 14, '今日は建国記念日だ«A0»', '建国纪念日«A0»'),
    (0X19743, 11, '今日は春分の日だ«A0»', '今天春分日«A0»'),
    (0X1975D,  9, '今日は緑の日だ«A0»', '绿化日«A0»'),
    (0X19767, 20, '今日はゴールデンウィークだ«A0»', '今天是黄金周«A0»'),
    (0X1977C, 10, '今日は⟦ECDA⟧の日⟦EAC7⟧«A0»', '儿童节⟦EAC7⟧«A0»'),
    (0X19787,  9, '今日は海の日だ«A0»', '海洋日«A0»'),
    (0X19791, 10, '今日は海の日⟦EAC7⟧«A0»', '海洋日⟦EAC7⟧«A0»'),
    (0X1979C, 11, '今日は敬老の日だ«A0»', '今天敬老日«A0»'),
    (0X197A8, 12, '今日は敬老の日⟦EAC7⟧«A0»', '敬老日⟦EAC7⟧«A0»'),
    (0X197B5, 11, '今日は秋分の日だ«A0»', '今天秋分日«A0»'),
    (0X197C1,  9, '今日は⟦ED0F⟧の日だ«A0»', '今天⟦ED0F⟧日«A0»'),
    (0X197CB, 11, '今日は文化の日だ«A0»', '今天文化日«A0»'),
    (0X197D7, 12, '今日は文化の日⟦EAC7⟧«A0»', '文化日⟦EAC7⟧«A0»'),
    (0X197E4, 13, '今日は勤労⟦ED15⟧の日だ«A0»', '勤劳感谢日«A0»'),
    (0X197F2, 14, '今日は勤労⟦ED15⟧の日⟦EAC7⟧«A0»', '勤劳感谢⟦EAC7⟧«A0»'),
    (0X19801, 14, '今日は天皇誕生日だ«A0»', '天皇诞生日«A0»'),
    (0X19810, 11, '今日は、詩織⟦EB3F⟧«A0»', '⟦EC9A⟧和诗织⟦EB3F⟧«A0»'),
    (0X1981C, 11, '今日は、⟦ECF5⟧さん⟦EB3F⟧«A0»', '今天和⟦ECF5⟧⟦EB3F⟧«A0»'),
    (0X19828, 11, '今日は、⟦ED23⟧さん⟦EB3F⟧«A0»', '今天和⟦ED23⟧⟦EB3F⟧«A0»'),
    (0X19834, 11, '今日は、⟦ED2D⟧さん⟦EB3F⟧«A0»', '今天和⟦ED2D⟧⟦EB3F⟧«A0»'),
    (0X19840, 13, '今日は、虹野さん⟦EB3F⟧«A0»', '今天和虹野⟦EB3F⟧«A0»'),
    (0X1984E, 13, '今日は、古式さん⟦EB3F⟧«A0»', '今天和古式⟦EB3F⟧«A0»'),
    (0X1985C, 13, '今日は、清川さん⟦EB3F⟧«A0»', '今天和清川⟦EB3F⟧«A0»'),
    (0X1986A, 11, '今日は、鏡さん⟦EB3F⟧«A0»', '今天和镜⟦EB3F⟧«A0»'),
    (0X19876,  8, '今日は、«BD»⟦EB3F⟧«A0»', '今日«BD»⟦EB3F⟧«A0»'),
    (0X1987F, 11, '今日は、⟦EC98⟧さん⟦EB3F⟧«A0»', '今天和⟦EC98⟧⟦EB3F⟧«A0»'),
    (0X1988B,  8, '今日は、«B7»⟦EB3F⟧«A0»', '今日«B7»⟦EB3F⟧«A0»'),
    (0X19894,  5, '⟦E9F4⟧日だ«A0»', '⟦E9F4⟧日«A0»'),
    (0X1989A,  8, '⟦E9F4⟧試合だ«A0»', '⟦E9F4⟧比赛«A0»'),
    (0X198A3, 18, '入部する⟦EC8F⟧を⟦ED4F⟧してください«A0»', '请选择要进的社团«A0»'),
    # The magazine spot-news pool: headline lines end on the rom's own $0A, which
    # stays outside the span; the corner notices wrap with ⟦0B⟧ and end in «A0».
    (0X198B6, 35, '次号から、このコーナーで⟦0B⟧最新スポットを教えます«A0»',
     '从下期起，本栏目⟦0B⟧将介绍最新好去处«A0»'),
    (0X198DA, 12, '中央公園紹介', '中央公园介绍'),
    (0X198E8,  4, '⟦EC89⟧⟦ED73⟧', '⟦EC89⟧⟦ED73⟧'),
    (0X198EE,  4, '⟦EC84⟧⟦ED72⟧', '⟦EC84⟧⟦ED72⟧'),
    (0X198F4, 12, 'スタジアム⟦ED73⟧', '体育场⟦ED73⟧'),
    (0X19902,  4, '⟦EC86⟧⟦ED72⟧', '⟦EC86⟧⟦ED72⟧'),
    (0X19908,  4, '⟦EB3E⟧⟦ED72⟧', '⟦EB3E⟧⟦ED72⟧'),
    (0X1990E,  4, '⟦EA05⟧⟦ED72⟧', '⟦EA05⟧⟦ED72⟧'),
    (0X19914, 15, 'カラオケＢＯＸ⟦ED73⟧', '卡拉ＯＫ厅⟦ED73⟧'),
    (0X19925, 29, '今月号は、紹介できる⟦0B⟧スポットがありません«A0»',
     '本期没有⟦0B⟧可以介绍的去处«A0»'),
    (0X19943, 25, '本誌は、今号をもって⟦0B⟧休刊となります«A0»',
     '本刊至本期为止⟦0B⟧正式休刊«A0»'),
    (0X1995D, 53, 'このコーナーでは、次号より⟦0B⟧盛沢山のイベント⟦ED0B⟧を⟦0B⟧提供していきます。おたのしみに«A0»',
     '本栏目从下期起⟦0B⟧将为大家提供⟦0B⟧丰富多彩的⟦ED0B⟧，敬请期待«A0»'),
    (0X19993, 12, '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧４⟦E86F⟧«A0»', '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧４⟦E86F⟧«A0»'),
    (0X199A0, 15, '次号に期待してくれ！', '敬请期待下一期'),
    (0X199B1, 15, '動物園に⟦EC81⟧がやって来る', '⟦EC81⟧来到动物园'),
    (0X199C2, 18, '⟦E976⟧⟦0B⟧⟦EC84⟧でイルカの⟦EC79⟧開催', '⟦E976⟧⟦0B⟧⟦EC84⟧海豚⟦EC79⟧开演'),
    (0X199D6, 34, '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧３⟦E86F⟧。⟦0B⟧⟦EC83⟧にウォータースライダー⟦ED73⟧',
     '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧３⟦E86F⟧。⟦0B⟧⟦EC83⟧新增水上滑梯⟦ED73⟧'),
    (0X199FA, 20, '⟦EA02⟧にメダルコーナー⟦0B⟧登場', '⟦EA02⟧新增⟦0B⟧奖牌兑换区'),
    (0X19A10, 28, '⟦E976⟧⟦0B⟧遊園地に⟦EBA1⟧⟦ED73⟧⟦0B⟧⟦EC89⟧で彫刻展開催',
     '⟦E976⟧⟦0B⟧游乐园过山车⟦ED73⟧⟦0B⟧⟦EC89⟧开雕塑展'),
    (0X19A2E, 12, '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧２⟦E86F⟧«A0»', '⟦ED71⟧⟦E81F⟧⟦0B⟧⟦ED71⟧２⟦E86F⟧«A0»'),
    (0X19A3B, 16, '⟦EC89⟧でガーギー展が開催', '⟦EC89⟧嘎尔吉展开幕'),
    # $0A（那是池遍历的终止符，写在 span 外）。⟦ECC3⟧(バーン)/⟦EB5C⟧(全スターズ)
    # 是本池首次引用的 sub-text 体，词典已补 烈焰/全明星；⟦EBC7⟧ 体改 交响乐团。
    # ＫＯＫＯ 借不到 ⟦ECE0⟧（体=行了，剧情行在折叠它），全角四字又超 6 B span，
    # 故意译「可可」；「の丘」的 span 只有 5 B，「希望丘」按 ⟦ED53⟧丘 落。
(0X19A6E, 12, 'モンキーバイソン', '猴王斗野牛'),
(0X19A7C,  6, '嵐ヶ原', '呼啸原'),
(0X19A84,  9, '⟦ECC3⟧ナックル', '⟦ECC3⟧之拳'),
(0X19A8F, 11, 'ツインビークス', '双峰镇'),
(0X19A9C,  7, 'トラへもん', '虎面丸'),
(0X19AA5,  8, 'アクシア', '阿西亚传'),
(0X19AAF,  5, '⟦ED53⟧の丘', '⟦ED53⟧丘'),
(0X19ABC, 10, '死が微笑むとき', '死亡微笑时'),
(0X19AC8, 14, 'エメラルドムーン', '翡翠之月'),
(0X19AD8,  8, '僕らの青春', '青春群像'),
(0X19AE2,  8, 'ＫＮＭ⟦EBC7⟧', 'ＫＮＭ⟦EBC7⟧'),
(0X19AEC,  6, 'Ｋ⟦ECE0⟧Ｏ', '可可'),
(0X19B07,  8, '甲玉リコ', '甲玉梨子'),
(0X19B17,  8, '３Ｘ３⟦EB5C⟧', '３Ｘ３⟦EB5C⟧'),
(0X19B21,  8, '科学忍者', '科学忍者'),
(0X19B2F, 14, 'ジュウ＆バラズ', '枪与玫瑰'),
    # The save-album prompt, the sound-output help lines and the prologue save
    # slots -- retired from R rows, which could not reach the SB bytes mid-line
    # (出力/から hid there, leaving 慨/这慢/める garble).  The «0000» pins are the
    # cursor-cell placeholders the script interleaves; ⟦E802⟧ is the 21-place
    # date-spot splice and ⟦EB47⟧ its 碰头 body.
    (0X19B53, 23, 'どのアルバムにセーブしますか？', '保存到哪个相册？'),
    (0X19B6C, 14, 'サウンド出力設定', '声音输出设置'),
    (0X19B7C, 19, 'サウンド出力«0000»ステレオ', '声音输出«0000»立体声'),
    (0X19B91, 20, 'サウンド出力«0000»モノラル', '声音输出«0000»单声道'),
    (0X19BA7,  6, '⟦E802⟧で、⟦EB47⟧', '在⟦E802⟧⟦EB47⟧'),
    (0X19BAF, 19, '１．プロローグから始める', '１．从序章开始'),
    (0X19BC4, 19, '２．プロローグから始める', '２．从序章开始'),
    # The two operand-prefixed pool entries the walk could not reach before the
    # pin mechanism: 0x1974F opens with «12 0000» (speaker 〔姓〕 + blank splice),
    # and the park line keeps its «0000»/⟦0B⟧ mid-line.  ⟦E9E1⟧ has no translated
    # body, so the call is dropped and the sentence reads around it.
    (0X1974F, 13, '〔姓〕«0000»「今日は何を⟦EBBE⟧な«A0»', '〔姓〕«0000»去哪玩呢«A0»'),
    (0X19A4D, 25, '遊園地に体感マシーン⟦0B⟧«0000»⟦E9E1⟧が⟦ED73⟧',
     '游乐园体感游艺机⟦0B⟧«0000»已⟦ED73⟧'),
    # The name-entry confirmation.  Three half-width supplement cells (0x158-0x15A,
    # no character of either language) ride through as KEEP; the row is loose
    # because a $06 operand precedes it.
    (0X1F284, 25, 'これでいい？⟦0B⟧' + K * 3 + 'いいえ',
     '就这样好吗？⟦0B⟧' + K * 3 + '不要', True),
    # 「ドン」 with its bracketing control pair pinned verbatim.
    (0X193C6, 6, '«3B»ドン«39»', '«3B»咚«39»'),
    # task #45 (endgame, batch U): the five unregistered scenario streams --
    # Z1 bank-$86 boss event/battle pool, Z2 纽绪 ending, Z3 朝日奈/诗织毕业,
    # Z4 丽/镜/片桐/虹野/见晴 chains, Z5 优美/如月/清川/古式/美树原 endings.
    # Sequential $0A-walked pools: whole-row re-encode, control tokens re-emitted.
    (0X034FD5, 21, '«20»早乙女「えーーんっ«2818»', '«20»早乙女「哇啊啊啊«2818»'),
    (0X034FEB, 29, '«20»早乙女「えーん（うそなき）«2818»', '«20»早乙女「呜呜（骗你的啦）«2818»'),
    (0X035009, 71, '«20»敵「これは、いかん！«2810»«20»敵「女、子供を泣かせては、«2810»«20»敵「男がすたる。«2810»', '«20»敌「这可不行！«2810»«20»敌「让女人小孩哭鼻子，«2810»«20»敌「还算什么男人。«2810»'),
    (0X035051, 19, '«20»美樹原「きゃっ…«2812»', '«20»美树原「呀啊…«2812»'),
    (0X035065, 17, '«20»美樹原「はっ…«2812»', '«20»美树原「咦…«2812»'),
    (0X035077, 25, '«20»朝日奈「ねえ、ねえっ、«2806»', '«20»朝日奈「喂，喂呀，«2806»'),
    (0X035091, 29, '«20»朝日奈「聞いて、聞いてっ！«2806»', '«20»朝日奈「听我说，听我说！«2806»'),
    (0X0350AF, 21, '«20»敵「なんだ、なんだ？', '«20»敌「怎么了，怎么了？'),
    (0X0350C5, 17, '«20»«0708»おやじの怒り«2810»', '«20»«0708»老爹的怒火«2810»'),
    (0X0350D7, 25, '«20»古式「お父様ーーっ！！«2810»', '«20»古式「父亲大人——！！«2810»'),
    (0X0350F1, 21, '«20»虹野「がんばってっ！', '«20»虹野「加油呀！'),
    (0X035107, 15, '«20»«0705»«0705»魅惑の瞳«2810»', '«20»«0705»«0705»魅惑之瞳«2810»'),
    (0X035117, 29, '«20»鏡「また、私のとりこが一人…', '«20»镜「又一个人拜倒在我裙下…'),
    (0X035135, 27, '«20»鏡「でなおしてらっしゃい！', '«20»镜「给我重新振作！'),
    (0X035151, 23, '«20»清川「馬鹿野郎ーっ！«2802»', '«20»清川「混账东西——！«2802»'),
    (0X035169, 25, '«20»清川「フザケンナヨー！«2802»', '«20»清川「得意过头了！«2802»'),
    (0X035183, 44, '«20»清川「あっ！«2803»«20»清川「いや、なんでもない…«2802»', '«20»清川「啊！«2803»«20»清川「不，没什么…«2802»'),
    (0X0351B0, 21, '«20»«0704»ポコポコ乱れ撃ち«2810»', '«20»«0704»咚咚连珠炮«2810»'),
    (0X0351C6, 29, '«20»紐緒「これでもくらいなさい！', '«20»纽绪「接下这一招吧！'),
    (0X0351E4, 17, '«20»藤崎「やめてっ！', '«20»藤崎「不要啊！'),
    (0X0351F6, 27, '«20»如月「ああっ！ めまいが！', '«20»如月「啊呀！我头晕！'),
    (0X035212, 13, '«20»«0709»５％回復«2812»', '«20»«0709»５％回复«2812»'),
    (0X035220, 29, '«20»次元の狭間に吸い込まれた！«2812»', '«20»被吸进了次元夹缝！«2812»'),
    (0X03523E, 25, '«20»次元の狭間でダメージ！«2812»', '«20»次元夹缝造成伤害！«2812»'),
    (0X035258, 23, '«20»効果が無かった‥‥。«2812»', '«20»效果全无‥‥。«2812»'),
    (0X035270, 17, '«20»敵は混乱した！«2810»', '«20»对手混乱了！«2810»'),
    (0X035282, 25, '«20»聖なる響きでダメージ！«2810»', '«20»神圣之音造成伤害！«2810»'),
    (0X03529C, 21, '«20»敵は説得に応じた！«2810»', '«20»对手被说服了！«2810»'),
    (0X0352B2, 29, '«20»番長「わしは感動したぜー！«2810»', '«20»番长「老夫深受感动啊—！«2810»'),
    (0X0352D0, 23, '«20»敵は説得に応じない。«2810»', '«20»对手不吃这一套。«2810»'),
    (0X0352E8, 15, '«20»«0708»熱意の説得«2804»', '«20»«0708»热血说服«2804»'),
    (0X0352F8, 13, '«20»«0709»暗黒舞踏«2810»', '«20»«0709»暗黑舞踏«2810»'),
    (0X035306, 23, '«20»«0704»戦闘衛星ハッキング«2810»', '«20»«0704»卫星劫持«2810»'),
    (0X03531E, 13, '«20»«0709»呪いの絵«2810»', '«20»«0709»诅咒之画«2810»'),
    (0X03532C, 15, '«20»«0708»誘惑の音色«2810»', '«20»«0708»诱惑之音«2810»'),
    (0X03533C, 15, '«20»«0708»破邪の音色«2810»', '«20»«0708»破邪之音«2810»'),
    (0X03534C, 21, '«20»«0705»１０００本ノック«2810»', '«20»«0705»千本棒打«2810»'),
    (0X035362, 27, '«20»«0702»オーバーヘッド空竹割り«2810»', '«20»«0702»天降空竹劈«2810»'),
    (0X03537E, 29, '«20»«0701»ブラックホールスマッシュ«2810»', '«20»«0701»黑洞爆裂杀«2810»'),
    (0X03539C, 13, '«20»«0705»«0705»大海衝«2810»', '«20»«0705»«0705»怒海冲«2810»'),
    (0X0353AA, 25, '«20»«0703»ＵＦＯダンクシュート«2810»', '«20»«0703»飞碟爆扣«2810»'),
    (0X0353C4, 23, '«20»「よせっ！紐緒さん！«2812»', '«20»「住手！纽绪同学！«2812»'),
    (0X0353E5, 25, '«20»«0703»真・世界征服ロボ！！«2812»', '«20»«0703»真·世界征服机神！！«2812»'),
    (0X0353FF, 21, '«20»«0705»服従ドリルパンチ«2810»', '«20»«0705»服从钻拳«2810»'),
    (0X035415, 25, '«20»«0703»独裁ミサイルシャワー«2810»', '«20»«0703»独裁飞弹雨«2810»'),
    (0X03542F, 27, '«20»«0702»世界征服ハイメガビーム«2810»', '«20»«0702»世界征服光炮«2810»'),
    (0X03544B, 23, '«20»ロボ「ガギグ・・・ッ«2806»', '«20»机器人「嘎咕咕…«2806»'),
    (0X0354BA, 25, '«20»不良たちが襲ってきた！«2810»', '«20»不良少年们扑了上来！«2810»'),
    (0X0354D4, 69, '«20»不良「そんな、ヤワな«2808»«20»攻撃では、俺たちの拳とは«2808»«20»かたれないぜっ！«2808»', '«20»不良「这种软绵绵«2808»«20»的攻击，可挡不住«2808»«20»我们的铁拳！«2808»'),
    (0X03551A, 21, '«20»    不良パンチ«2810»', '«20»    不良拳«2810»'),
    (0X035530, 56, '«20»不良「口ほどにもない奴め！«2808»«20»不良「出直してきやがれ！«2808»', '«20»不良「光会动嘴的废物！«2808»«20»不良「滚回去再练练！«2808»'),
    (0X035569, 42, '«20»不良「くっ！«2806»«20»不良「なかなかやるなっ！«2808»', '«20»不良「可恶！«2806»«20»不良「有两下子啊！«2808»'),
    (0X035594, 50, '«20»不良「しょうがねぇっ！«2808»«20»不良「番長様に御報告！«2808»', '«20»不良「真没办法！«2808»«20»不良「快去向番长报告！«2808»'),
    (0X0355C7, 52, '«20»不良「なかなかいい話だ。«2808»«20»よし、番長様に御報告！«2808»', '«20»不良「这话说得不错。«2808»«20»好，向番长报告！«2808»'),
    (0X0355FC, 75, '«20»戦闘に勝った！！«2812»«20»経験値  ２３６０ＥＸＰ«2812»«20»お金   ３６００ゴールド«2812»', '«20»战斗胜利！！«2812»«20»经验值  ２３６０ＥＸＰ«2812»«20»金钱   ３６００金币«2812»'),
    (0X035648, 27, '«20»おたから：ミスリル学ラン«2812»', '«20»宝物：秘银学生服«2812»'),
    (0X035664, 25, '«20»おたから：炎のＴシャツ«2812»', '«20»宝物：炎之T恤«2812»'),
    (0X03567E, 25, '«20»おたから：ダイヤの学帽«2812»', '«20»宝物：钻石学生帽«2812»'),
    (0X035698, 25, '«20»おたから：源氏のかたな«2812»', '«20»宝物：源氏之刀«2812»'),
    (0X0356B2, 19, '«20»番長「超眼力！！«2812»', '«20»番长「超眼力！！«2812»'),
    (0X0356C6, 17, '«20»番長「袖龍！！«2812»', '«20»番长「袖龙！！«2812»'),
    (0X0356E8, 42, '«20»？？「ちょっとまてぇいー！«2810»«20»「誰だっ！«2810»', '«20»？？「给我慢着——！«2810»«20»「是谁！«2810»'),
    (0X035713, 144, '«20»番長「わしは、«2810»«20»この世界の番長や！«2814»«20»わしの子分達が、ずいぶん«2810»«20»世話になったようだなぁ。«2814»«20»だが、茶番は終わりだ。«2814»«20»これでも、くらえーいっ！«2818»', '«20»番长「老夫，«2810»«20»正是这个世界的番长！«2814»«20»老夫的小弟们，«2810»«20»想必让你们费心不少。«2814»«20»不过，闹剧该收场了。«2814»«20»那就尝尝这个——！«2818»'),
    (0X0357A4, 120, '«20»番長「どうだ、«2808»思い知ったか。«2810»«20»俺様に逆らった者の末路は«2810»«20»こういうめにあうのだ。«2818»«20»番長「わー«2804»っはっ«2802»はっ«2802»はっ！«2818»', '«20»番长「怎么样，«2808»尝到苦头了吧。«2810»«20»与老夫作对的人，«2810»«20»最后就是这种下场。«2818»«20»番长「哇«2804»哈哈哈«2802»哈哈哈«2802»哈哈哈！«2818»'),
    (0X03581D, 23, '«20»番長「なにぃいー！？«2812»', '«20»番长「什么——！？«2812»'),
    (0X035835, 123, '«20»番長「こわっぱごときが、«2810»«20»超眼力を見切ったぐらいで«2810»«20»いい気になりおって。«2810»«20»我が秘奥義を見せてくれる。«2810»«20»ゆくぞーーーっ！', '«20»番长「区区黄毛小儿，«2810»«20»看破了老夫的超眼力«2810»«20»就得意成这副样子。«2810»«20»让你见识老夫的秘奥义。«2810»«20»要来了———！'),
    (0X0358B1, 31, '«20»番長「この俺に、敗北は無い！«2812»', '«20»番长「老夫绝没有败北二字！«2812»'),
    (0X0358D1, 23, '«20»番長「ううーむ‥‥。«2812»', '«20»番长「唔——嗯‥‥。«2812»'),
    (0X0358E9, 25, '«20»番長「なかなかやるな。«2812»', '«20»番长「有两下子嘛。«2812»'),
    (0X035903, 31, '«20»番長「少しは、できそうだな。«2812»', '«20»番长「还算有点能耐。«2812»'),
    (0X035923, 31, '«20»番長「貴様の力はこの程度か！«2812»', '«20»番长「你的实力仅此而已！«2812»'),
    (0X035943, 23, '«20»番長「片腹痛いわあ！«2812»', '«20»番长「实在太可笑了！«2812»'),
    (0X03595B, 29, '«20»番長「さあ、かかってこい！«2812»', '«20»番长「来吧，放马过来！«2812»'),
    (0X035979, 95, '«20»番長「ふっ、恐れ入ったぜっ。«2812»«20»俺を倒せるやつが、«2812»«20»この世界にいたとはな…。«2812»«20»〔姓〕「番長‥‥。«2812»', '«20»番长「哈，老夫心服口服。«2812»«20»能打败老夫的家伙，«2812»«20»原来这世上真有…。«2812»«20»〔姓〕「番长‥‥。«2812»'),
    (0X0359D9, 81, '«20»番長「いや、その名は«2812»«20»もう俺にはふさわしくない。«2812»«20»これからは、お前が番長だ。«2812»', '«20»番长「不，那个称呼«2812»«20»已不再适合老夫了。«2812»«20»从今往后，你就是番长。«2812»'),
    (0X035A48, 181, '«20»戦闘に勝った！！«2812»«20»経験値  ３２７６７ＥＸＰ«2812»«20»お金   ６５５３５ゴールド«2812»«20»おたから：ドラゴン学ラン«2812»«20»おたから：不思議な学帽«2812»«20»おたから：エクスカリバー«2812»«20»おたから：番長の証し«2812»', '«20»战斗胜利！！«2812»«20»经验值  ３２７６７ＥＸＰ«2812»«20»金钱   ６５５３５金币«2812»«20»宝物：龙纹学生服«2812»«20»宝物：神奇学生帽«2812»«20»宝物：石中剑«2812»«20»宝物：番长之证«2812»'),
    (0X035AFE, 21, '«20»獲得称号：世界番長«2812»', '«20»获得称号：世界番长«2812»'),
    (0X035B14, 21, '«20»獲得称号：時空番長«2812»', '«20»获得称号：时空番长«2812»'),
    (0X035B2A, 21, '«20»獲得称号：銀河番長«2812»', '«20»获得称号：银河番长«2812»'),
    (0X035B40, 23, '«20»獲得称号：朝焼け番長«2812»', '«20»获得称号：朝霞番长«2812»'),
    (0X035B58, 44, '«20»（どこからともなく«2818»«20»声が聞こえてきた。）«2820»', '«20»（不知从何处«2818»«20»传来了声音。）«2820»'),
    (0X035B85, 82, '«20»天使の声「お願い、«2818»«20»立ちあがって。«2820»«20»あなたには、«2818»«20»まだやるべき事があるのよ。«2820»', '«20»天使之声「拜托你，«2818»«20»站起来。«2820»«20»你还有«2818»«20»该去做完的事呢。«2820»'),
    (0X035C28, 45, '«20»〔姓〕「もう超眼力は«2812»«20»見切ったぜ！«2812»«20»〔姓〕「番長！«2812»', '«20»〔姓〕「超眼力我已经«2812»«20»看破了！«2812»«20»〔姓〕「番长！«2812»'),
    (0X0C6EAC, 99, '«20»«0708»«22»待ってた«23»…。«21»«2820»«20»«0705»«0705»«22»いえ«23»…。«2810»«20»«0702»«22»ご«23»、«2804»«22»ごめんなさい«21»«23»。«2808»⟦0B⟧«0702»«22»こんな所«21»に呼び出して«23»…。«2810»', '«20»«0708»«22»我等你«23»…。«21»«2820»«20»«0705»«0705»«22»不对«23»…。«2810»«20»«0702»«22»很«23»、«2804»«22»对不起«21»«23»。«2808»⟦0B⟧«0702»«22»把你叫到这种地«21»方来«23»…。«2810»'),
    (0X0C6F10, 48, '«20»«0703»ど、どうしたの？«2810»⟦0B⟧«0703»紐緒さんらしくないよ。«2810»', '«20»«0703»你、你怎么了？«2810»⟦0B⟧«0703»这可不像纽绪同学啊。«2810»'),
    (0X0C6F41, 78, '«20»«0707»«22»い«23»、«2808»«22»«21»いいのよ«23»。«2810»«20»«0704»«22»今日から«23»«2802»«22»変わることに⟦0B⟧«0704»決めたんだから«23»…。«2810»', '«20»«0707»«22»没«23»、«2808»«22»«21»没事的«23»。«2810»«20»«0704»«22»从今天开始«23»«2802»«22»我已经下定决心⟦0B⟧«0704»要改变了«23»…。«2810»'),
    (0X0C6F90, 19, '«20»«0708»え？«2810»変わる？«2810»', '«20»«0708»咦？«2810»改变？«2810»'),
    (0X0C6FA4, 996, '«20»«0706»«22»そう«23»、«21»«2808»«22»変わるの«23»。«2810»«20»«0707»«22»今までの私は«23»、«2808»«20»«0703»«22»自分の才能に溺れて«23»«2810»«22»人を⟦0B⟧«0703»見下した態度を«21»取って«23»、«2810»«20»«0705»«22»誰が見ても«21»、すごく⟦0B⟧«0705»嫌な女の子だった«23»。«21»«2810»«20»«0707»«22»普通の女の子が⟦0B⟧«0707»愛だの恋だのと«23»«2810»«20»«0706»«22»騒いでいるの«21»を、⟦0B⟧«0706»馬鹿にしてたわ«23»。«2810»«20»«0702»«22»だけど«21»、いつの頃からか«23»、«21»«2810»«20»«0704»«22»私の中に初めて«21»⟦0B⟧«0704»込み上げる感情が«23»…。«2820»«20»«0703»«22»すぐに«23»、«2808»«22»あなたに⟦0B⟧«0703»恋してると«21»気付いたわ«23»。«2810»«20»«0701»«22»«21»でも«23»、«2808»«22»私は科学という悪魔に⟦0B⟧«0701»魂を売り渡した女«23»。«2810»«20»«0704»«22»そんな浮ついた感情«21»を⟦0B⟧«0704»押さえるために«23»、«2810»«20»«0703»«22»研究だけに没頭したの«23»。«21»«2810»«20»«0706»«22»だけど«23»、«2808»«22»«21»卒業が⟦0B⟧«0706»近づいてくると«23»、«2810»«20»«0701»«22»«21»その想いが強くなってきて«23»、«2810»«20»«0705»«22»自分でも«21»押さえ⟦0B⟧«0705»きれなくなって«23»…。«2810»«20»«0702»«22»だから«23»、«2808»«22»その想いを完全に⟦0B⟧«0702»否定しようとして«23»、«2810»«20»«0702»«22»«21»あなたに戦いを挑んだの«23»。«2810»«20»«0704»«22»結果は«23»、«2808»«22»言わなくても⟦0B⟧«0704»分かる«21»けど«23»…。«2810»«20»«0701»«22»全てにおいて«23»、«2810»«22»私はあなたに⟦0B⟧«0701»負けてしまったの«23»«21»。«2810»«20»«0703»«22»もう、«21»あなたに嫌われる⟦0B⟧«0703»なんて«23»、«2808»«22»考えたくない«23»。«2810»«20»«0701»«22»世界征服の野望も捨てるわ«23»«21»。«2818»«20»«0702»«22»だってもう、私の野望は«23»«21»、«2810»«20»«0703»«22»あなたに好かれることに⟦0B⟧«0703»変わったから«23»«21»…。«2820»', '«20»«0706»«22»对«23»，«21»«2808»«22»我要改变«23»。«2810»«20»«0707»«22»从前的我«23»，«2808»«20»«0703»«22»沉迷在自己的才华里«23»«2810»«22»对别人⟦0B⟧«0703»露出轻蔑«21»的态度«23»，«2810»«20»«0705»«22»不管谁看了«21»，都觉得⟦0B⟧«0705»我是个特别讨厌的女孩«23»。«21»«2810»«20»«0707»«22»普通的女孩子⟦0B⟧«0707»为恋爱吵吵闹闹«23»«2810»«20»«0706»«22»那副样子«21»，⟦0B⟧«0706»我还在背后笑话«23»。«2810»«20»«0702»«22»可是«21»，不知从什么时候起«23»。«21»«2810»«20»«0704»«22»我心里头一回«21»⟦0B⟧«0704»涌起了这样的感情«23»…。«2820»«20»«0703»«22»马上«23»，«2808»«22»我就发觉自己⟦0B⟧«0703»爱上了你«21»«23»。«2810»«20»«0701»«22»«21»可是«23»，«2808»«22»我可是把灵魂卖给⟦0B⟧«0701»科学这个恶魔的女人«23»。«2810»«20»«0704»«22»为了压住«21»这份⟦0B⟧«0704»不安分的感情«23»，«2810»«20»«0703»«22»我一心扑在研究上«23»。«21»«2810»«20»«0706»«22»可是«23»，«2808»«22»«21»眼看就要⟦0B⟧«0706»毕业了«23»，«2810»«20»«0701»«22»«21»那份思念越来越强烈«23»，«2810»«20»«0705»«22»连我自己«21»都⟦0B⟧«0705»快按捺不住了«23»…。«2810»«20»«0702»«22»所以«23»，«2808»«22»我拼了命地想⟦0B⟧«0702»把它否定掉«23»，«2810»«20»«0702»«22»«21»才向你发起挑战的«23»。«2810»«20»«0704»«22»结果«23»，«2808»«22»就算不说⟦0B⟧«0704»你也明白«21»吧«23»…。«2810»«20»«0701»«22»从头到尾«23»，«2810»«22»我输给了你⟦0B⟧«0701»输得一败涂地«23»«21»。«2810»«20»«0703»«22»已经，«21»被你讨厌⟦0B⟧«0703»这种事«23»，«2808»«22»我不想再多想一下«23»。«2810»«20»«0701»«22»征服世界的野心也丢掉了«23»«21»。«2818»«20»«0702»«22»因为现在的我，最大的野望«23»«21»，«2810»«20»«0703»«22»已经变成了要让你⟦0B⟧«0703»喜欢上我«23»«21»…。«2820»'),
    (0X0C7389, 46, '«20»«0703»実を言うと、⟦0B⟧«0703»俺も紐緒さんの«21»事が…。«2810»«21»«2810»', '«20»«0703»说实话，⟦0B⟧«0703»我对纽绪同学也«21»…。«2810»«21»«2810»'),
    (0X0C73B8, 174, '«20»«0707»«22»ほ«23»、«2802»«22»本当に«23»…？«2810»«20»«0705»«22»じゃあ、野望は⟦0B⟧«0705»達成されたのね«23»…。«21»«2810»«20»«0703»«22»嬉しいわ«23»…。«2810»«22»きっと«23»、⟦0B⟧«0703»«2808»«22»世界征服したとしても«23»、«21»«2810»«20»«22»こんなに幸せになれなかっ«21»たと⟦0B⟧思うわ«23»…。«2810»', '«20»«0707»«22»真«23»，«2802»«22»真的吗«23»…？«2810»«20»«0705»«22»那么，我的野心⟦0B⟧«0705»也算达成了呢«23»…。«21»«2810»«20»«0703»«22»我好开心«23»…。«2810»«22»我想«23»，⟦0B⟧«0703»«2808»«22»就算真的征服了世界«23»，«21»«2810»«20»«22»也未必能像现在这样«21»⟦0B⟧幸福«23»…。«2810»'),
    (0X0C7467, 22, '«20»«0706»俺も、幸せだよ。«23»«2810»', '«20»«0706»我也很幸福。«23»«2810»'),
    (0X0C747E, 75, '«20»«0709»«22»私もっと«23»、«2808»«20»«0702»«22»あなたに好かれる女の子に⟦0B⟧«0702»なるために、努力するわ«23»。«2820»', '«20»«0709»«22»我会更加«23»，«2808»«20»«0702»«22»努力变成一个⟦0B⟧«0702»能让你喜欢上的女孩«23»。«2820»'),
    (0X0D6F96, 431, '«20»«0703»«22»こんなとこに呼び出すの«21»⟦0B⟧«0703»何だなと思ったけど«23»。«2815»«20»«0700»«22»卒業する前に«23»、«2805»«22»どうしても⟦0B⟧«0700»言いたいことがあるっていうか、«21»«23»«2807»«20»«0707»«22»何て言うか«23»…。«2815»«20»«0700»«22»いままで«23»«21»、«2805»«22»流行の色々な場所に⟦0B⟧«0700»行って、«23»«2808»«20»«0701»«22»遊ぶのが一番の楽しみだった⟦0B⟧«0701»けど«23»…。«21»«2815»«20»«0702»«22»何て言うか«23»、«2805»«22»最近«23»、«2805»«22»それも⟦0B⟧«0702»飽きちゃったみたいな感じ«23»。«2812»«20»«0709»«22»やっぱ«23»…、«21»«2815»«20»«0700»«22»好きな人と一緒なら«23»、«2805»«22»何処にも⟦0B⟧«0700»行かなくても楽しいと思う«23»。«2812»«20»«0701»«22»こうしてる«21»今も«23»、«2805»«22»そう思う«23»。«2815»', '«20»«0703»«22»把你约到这种地方«21»⟦0B⟧«0703»我还觉得有点怪怪的«23»。«2815»«20»«0700»«22»毕业之前«23»，«2805»«22»我有些事⟦0B⟧«0700»不得不跟你说，该说是«21»«23»«2807»«20»«0707»«22»怎么说呢«23»。«2815»«20»«0700»«22»以前«23»«21»，«2805»«22»我到处去⟦0B⟧«0700»流行的地方，«23»«2808»«20»«0701»«22»觉得痛快玩一场最开心⟦0B⟧«0701»来着«23»«21»«2815»«20»«0702»«22»怎么说呢«23»，«2805»«22»最近«23»，«2805»«22»感觉⟦0B⟧«0702»连这个都玩腻了«23»。«2812»«20»«0709»«22»果然«23»…，«21»«2815»«20»«0700»«22»只要和喜欢的人在一起«23»，«2805»«22»哪儿都不⟦0B⟧«0700»去也会很开心«23»。«2812»«20»«0701»«22»就像现在«21»这样«23»，«2805»«22»我就是这么觉得的«23»。«2815»'),
    (0X0D7146, 30, '«20»«0702»ふーん、«21»飽きちゃったの。«2810»', '«20»«0702»哦？«21»玩腻了啊。«2810»'),
    (0X0D7165, 91, '«20»«0701»«22»もう、ウル馬鹿なんだから«23»！«2812»«20»«0700»«22»私は«23»、«2805»«22»あなたといるのが楽しい⟦0B⟧«0700»って言ってるの«23»！«2815»', '«20»«0701»«22»真是的，你个大笨蛋«23»！«2812»«20»«0700»«22»我是说«23»，«2805»«22»和你待在一起⟦0B⟧«0700»最开心啦«23»！«2815»'),
    (0X0D71C1, 21, '«20»«0706»そ、それって…。«2810»', '«20»«0706»这、这么说…。«2810»'),
    (0X0D71D7, 211, '«20»«0704»«22»超«21»恥ずかしいけど«23»…、«2815»«20»«0703»«22»«21»私«23»、«2805»«22»あなたのこと好きに⟦0B⟧«0703»なっちゃたみたい«23»！«2815»«20»«0700»«22»«21»もう、あなただけいてくれたら、⟦0B⟧«0700»何もいらない«23»！«2812»«20»«0701»«22»流行なんて、どうでもいい«23»！«2812»«20»«0700»«22»…だから«23»、«21»«2805»«22»私と付き合って«23»！！«2815»', '«20»«0704»«22»超级«21»害羞的啦«23»…，«2815»«20»«0703»«22»«21»我«23»，«2805»«22»好像已经喜欢上⟦0B⟧«0703»你了«23»！«2815»«20»«0700»«22»«21»只要有你在身边，⟦0B⟧«0700»我什么都不要了«23»！«2812»«20»«0701»«22»赶不赶流行，都无所谓«23»！«2812»«20»«0700»«22»…所以«23»，«21»«2805»«22»和我交往吧«23»！！«2815»'),
    (0X0D72AB, 41, '«20»«0704»実は«23»、«2805»俺も⟦0B⟧«0704»朝日奈さんの事が…。«2810»', '«20»«0704»其实«23»，«2805»我也⟦0B⟧«0704»一直对朝日奈同学…。«2810»'),
    (0X0D72D5, 125, '«20»«0709»«22»超嬉しい«23»！«2815»«20»«0701»«22»でも…«23»、«21»«2805»«22»やっぱりただ一緒に⟦0B⟧«0701»いるだけよりも«23»…、«2810»«20»«0701»«22»何処かに遊びに行ったほうが⟦0B⟧«0701»楽しいよね？«21»«23»«2815»', '«20»«0709»«22»超级开心«23»！«2815»«20»«0701»«22»不过…«23»，«21»«2805»«22»果然比起只是⟦0B⟧«0701»待在一起«23»…，«2810»«20»«0701»«22»一起出去玩⟦0B⟧«0701»会更开心对吧？«21»«23»«2815»'),
    (0X0D7353, 19, '«20»«0707»そ、そうだね。«2810»', '«20»«0707»是、是啊。«2810»'),
    (0X0D7367, 47, '«20»«0703»«22»卒業したらさ、⟦0B⟧«0703»«21»どっか旅行に行こうよ«23»。«2815»', '«20»«0703»«22»毕业以后，⟦0B⟧«0703»«21»我们一起去旅行吧«23»。«2815»'),
    (0X0D7397, 19, '«20»«0707»あぁ、いいよ。«2810»', '«20»«0707»啊，好呀。«2810»'),
    (0X0D73AB, 56, '«20»«0700»«22»それじゃ«23»、«21»«23»«2805»«22»⟦0B⟧«0700»これから旅行代理店に行こうよ«23»。«2815»', '«20»«0700»«22»那么«23»，«21»«23»«2805»«22»⟦0B⟧«0700»现在就去旅行社吧«23»。«2815»'),
    (0X0D73E4, 53, '«20»«0702»（全然«21»変わらないけど…、⟦0B⟧«0702» ま、いいか。）«2810»«21»«27»«2815»', '«20»«0702»（一点都«21»没变呢…，⟦0B⟧«0702» 嘛，算了。）«2810»«21»«27»«2815»'),
    (0X0D741A, 20, '«20»«0709»«21»«2810»し、詩織…。«2820»', '«20»«0709»«21»«2810»诗、诗织…。«2820»'),
    (0X0D742F, 124, '«20»«0702»«22»ごめんなさい«23»。«21»«2808»«22»こんな所に⟦0B⟧«0702»呼び出したりして«23»、«2810»«20»«0702»«22»今日«23»、«21»«2804»«22»あなたにどうしても«23»«2808»⟦0B⟧«0702»«22»言いたいことがあって«23»…。«2820»', '«20»«0702»«22»对不起«23»。«21»«2808»«22»把你叫到⟦0B⟧«0702»这种地方来«23»，«2810»«20»«0702»«22»今天«23»，«21»«2804»«22»因为我«23»«2808»⟦0B⟧«0702»«22»有无论如何都想对你说的话«23»…。«2820»'),
    (0X0D74AC, 27, '«20»«0703»言いたいことって、何？«2820»', '«20»«0703»想说的话，是什么？«2820»'),
    (0X0D74C8, 296, '«20»«070C»«21»«22»私ね«23»、«2814»«20»«0702»«22»今まで男の子と付き合った«21»⟦0B⟧«0702»ことがないの«23»…。«2810»«20»«070C»«22»でも«23»、«2810»«20»«0707»«22»興味がなかった⟦0B⟧«0707»訳«21»じゃないのよ«23»。«2818»«20»«0705»«0705»«22»私だって«23»、«2810»«20»«0705»«22»男の子と«21»付き合って⟦0B⟧«0705»みたかったし«23»、«2810»«20»«0703»«22»ラブレターだって何通も⟦0B⟧«0703»«21»貰ったこともあるわ«23»。«2810»«20»«070C»«22»でも«23»、«2810»«20»«0705»«21»«22»どうしても付き合う⟦0B⟧«0705»気になれなかったの«23»。«2820»', '«20»«070C»«21»«22»我呢«23»，«2814»«20»«0702»«22»到现在还从来没有和男孩子«21»⟦0B⟧«0702»交往过呢«23»…。«2810»«20»«070C»«22»可是«23»，«2810»«20»«0707»«22»也不是⟦0B⟧«0707»完全不动«21»心啦«23»。«2818»«20»«0705»«0705»«22»我当然也«23»，«2810»«20»«0705»«22»和男孩子«21»交往看看⟦0B⟧«0705»也是想过的«23»，«2810»«20»«0703»«22»情书也收到过⟦0B⟧«0703»«21»好几封呢«23»。«2810»«20»«070C»«22»可是«23»，«2810»«20»«0705»«21»«22»却怎么也没办法⟦0B⟧«0705»下定决心去交往«23»。«2820»'),
    (0X0D75F1, 21, '«20»«0707»ど、どうして？«21»«27»«2820»', '«20»«0707»为、为什么？«21»«27»«2820»'),
    (0X0D7607, 588, '«20»«0709»«22»あなたが«23»…、«21»«2814»«20»«0706»«22»あなたがそばに⟦0B⟧«0706»いてくれたから«23»…。«2814»«21»«2814»«20»«0704»«22»今まで«23»、«2804»«22»あなたの事を«23»、«2810»«20»«0705»«22»ただの幼馴染みだと⟦0B⟧«0705»思ってた«23»…。«2810»«20»«0707»«21»«22»ううん«23»、«2804»«22»きっと«23»«2808»«20»«0705»«22»あなたに私の本心が⟦0B⟧«0705»«21»悟られるのが恐くて«23»、«2810»«20»«0705»«22»そう«23»«2802»«22»思い込んでい«21»た⟦0B⟧«0705»のかもしれない«23»。«2818»«21»«2818»«20»«0705»«22»でも、卒業する«21»今«23»…、«2810»«20»«0703»«22»離れ離れになるかもしれ⟦0B⟧«0703»ない今になってやっと«23»、«2810»«21»«2808»«20»«0708»«21»«22»この気持ちに⟦0B⟧«0708»気付いたの«23»…。«2810»«21»«2808»«20»«0708»«22»恥ずかしくて«23»、«2810»«20»«0709»«22»逃げたい⟦0B⟧«0709»気分だけど«23»«21»«2810»«20»«070C»«22»もう«23»、«2810»«20»«0703»«22»ただの幼馴染みじゃ«23»«2808»«22»嫌«23»…。«21»«27»«2810»«21»«27»«20»«0705»«22»一人の女の子として«23»、«2808»«20»«0706»«22»私だけを«21»見つめて⟦0B⟧«0706»ほしいから«23»、«2810»«20»«0704»«22»勇気を出して言います«23»。«21»«2820»', '«20»«0709»«22»是因为你«23»…，«21»«2814»«20»«0706»«22»你一直陪在⟦0B⟧«0706»我身边«23»…。«2814»«21»«2814»«20»«0704»«22»以前«23»，«2804»«22»我一直把你«23»，«2810»«20»«0705»«22»只当作普通的⟦0B⟧«0705»青梅竹马«23»…。«2810»«20»«0707»«21»«22»不«23»，«2804»«22»一定«23»«2808»«20»«0705»«22»是怕自己的真心⟦0B⟧«0705»«21»被你察觉«23»，«2810»«20»«0705»«22»这样«23»«2802»«22»硬催眠自己«21»⟦0B⟧«0705»也说不定«23»。«2818»«21»«2818»«20»«0705»«22»可是，要到毕业的«21»现在«23»…，«2810»«20»«0703»«22»也许就要天各一方⟦0B⟧«0703»的此刻，我终于«23»，«2810»«21»«2808»«20»«0708»«21»«22»对这份心意⟦0B⟧«0708»有了察觉«23»…。«2810»«21»«2808»«20»«0708»«22»害羞得不得了«23»，«2810»«20»«0709»«22»真想逃走⟦0B⟧«0709»可是«23»«21»«2810»«20»«070C»«22»已经«23»，«2810»«20»«0703»«22»只做普通的青梅竹马«23»«2808»«22»我不愿意«23»…。«21»«27»«2810»«21»«27»«20»«0705»«22»作为一个女孩子«23»，«2808»«20»«0706»«22»我想让你«21»只注视⟦0B⟧«0706»我一个人«23»，«2810»«20»«0704»«22»所以鼓起勇气说出来«23»。«21»«2820»'),
    (0X0D7854, 74, '«20»«0709»«2810»«22»好きです«23»…。«2818»«20»«0702»«22»世界中の誰よりもあなたが«23»、«2810»⟦0B⟧«20»«0709»«22»好きです«23»…。«2820»', '«20»«0709»«2810»«22»我喜欢你«23»。«2818»«20»«0702»«22»这世上谁都比不上你«23»，«2810»⟦0B⟧«20»«0709»«22»最喜欢你«23»。«2820»'),
    (0X0D789F, 40, '«20»«0706»実を言うと…。⟦0B⟧«0706»俺も詩織の事が…。«2814»', '«20»«0706»其实我…。⟦0B⟧«0706»我也一直喜欢诗织…。«2814»'),
    (0X0D794B, 38, '«20»«0707»もちろんだよ。⟦0B⟧«0707»好きだよ、詩織。«2820»', '«20»«0707»那还用说。⟦0B⟧«0707»我喜欢你，诗织。«2820»'),
    (0X0D7972, 73, '«20»«0705»«0705»«22»嬉しい«23»…。«2820»«20»«0705»«22»いつま«21»でも«2804»«22»私の事を、⟦0B⟧«0705»離さないでね«23»…。«2818»«21»«27»«2818»', '«20»«0705»«0705»«22»我好开心«23»…。«2820»«20»«0705»«22»请永«21»远«2804»«22»都不要离开⟦0B⟧«0705»我，好吗«23»…。«2818»«21»«27»«2818»'),
    (0X1B606F, 27, '«20»«0704»«21»何処かで見たような？«23»«2830»', '«20»«0704»«21»好像在哪儿见过？«23»«2830»'),
    (0X1B608B, 39, '«20»«0708»«22»わ、«2802»«21»私«23»…。«2818»⟦0B⟧«0708»«22»伊集院です«23»。«2818»', '«20»«0708»«22»我、«2802»«21»就是«23»…«2818»⟦0B⟧«0708»«22»伊集院啦«23»。«2818»'),
    (0X1B60B3, 35, '«20»«0706»伊集院に妹«21»なんて⟦0B⟧«0706»いたっけ？«2818»', '«20»«0706»伊集院家«21»哪来的⟦0B⟧«0706»妹妹来着？«2818»'),
    (0X1B60D7, 42, '«20»«070B»«22»いえ«23»。⟦0B⟧«2810»«20»«0704»«22»伊集院レイ«21»本人です«23»。«2818»', '«20»«070B»«22»不«23»。⟦0B⟧«2810»«20»«0704»«22»伊集院丽«21»本人哦«23»。«2818»'),
    (0X1B610C, 85, '«20»«0707»ごめんなさい。«21»«2818»«20»«0708»«22»今まで私«23»…。«21»«2818»«20»«0706»«22»男のふりをして、«21»⟦0B⟧«0706»嘘をついてたの«23»…。«2818»', '«20»«0707»对不起。«21»«2818»«20»«0708»«22»一直以来我«23»…。«21»«2818»«20»«0706»«22»装作男孩子，«21»⟦0B⟧«0706»一直在说谎«23»…。«2818»'),
    (0X1B6162, 22, '«20»«0706»す、すごい嘘だ。«21»«2818»', '«20»«0706»好、好大的谎。«21»«2818»'),
    (0X1B6179, 114, '«20»«0703»«22»伊集院家では、女の子は⟦0B⟧«0703»«21»高校を卒業するまで«23»、«2820»«20»«0701»«22»家の外では、男の子として⟦0B⟧«0701»«21»生活しなくてはいけないの«23»。«2820»', '«20»«0703»«22»伊集院家的女孩子，⟦0B⟧«0703»«21»到中学毕业为止«23»，«2820»«20»«0701»«22»在校外都要当作⟦0B⟧«0701»«21»男孩子来生活的«23»。«2820»'),
    (0X1B61EC, 20, '«20»«0707»漫画みたい…。«21»«2818»', '«20»«0707»跟漫画一样…。«21»«2818»'),
    (0X1B6201, 141, '«20»«0708»«22»でも、私«23»…。«21»«2818»⟦0B⟧«20»«0704»«22»あと一日だったけど«23»、«21»«2818»«20»«0707»«22»どうしても我慢が⟦0B⟧«0707»出来なくて«23»…。«21»«2818»«20»«22»こんな所に呼び出したりして«23»«21»、⟦0B⟧«22»ごめんなさい«23»。«2818»', '«20»«0708»«22»可是，我«23»…。«21»«2818»⟦0B⟧«20»«0704»«22»明明只剩最后一天了«23»，«21»«2818»«20»«0707»«22»可我怎么也忍不⟦0B⟧«0707»住了«23»…。«21»«2818»«20»«22»把你约到这种地方«23»«21»，⟦0B⟧«22»对不起«23»。«2818»'),
    (0X1B628F, 29, '«20»«0708»い、«21»いいよ。⟦0B⟧«0708»別に…。«2810»', '«20»«0708»没、«21»没事啦。⟦0B⟧«0708»没事…。«2810»'),
    (0X1B62AD, 369, '«20»«0702»«22»いつも、憎まれ口ばかりで⟦0B⟧«0702»ご«21»めんなさい«23»。«2820»«20»«0703»«22»でも、今まで憎まれ口を⟦0B⟧«0703»たたいて«21»たのは«23»、«2820»«20»«0704»«22»あなたに嫌われようと⟦0B⟧«0704»してたからなの«23»…。«21»«2820»«20»«0705»«22»嫌われてしまえば、⟦0B⟧«0705»«21»«22»あなたの事を«23»«2820»«20»«0701»«22»忘れられると思ったから«23»…。«21»«2820»«20»«0702»«22»でも、いつもあなたは«21»私に⟦0B⟧«0702»電話をしてきてくれて«23»、«21»«2820»«20»«0704»«22»あんなにひどいことを⟦0B⟧«0704»言ったのに«23»、«21»«2820»«20»«0706»«22»何度も何度も«23»…。«2818»«20»«0707»«22»私、嬉しくて«23»«21»、«2818»', '«20»«0702»«22»总是对你讲反话，⟦0B⟧«0702»对«21»不起«23»。«2820»«20»«0703»«22»可是，以前之所以⟦0B⟧«0703»净是逞口舌«21»刺伤你«23»，«2820»«20»«0704»«22»就是想让你讨厌⟦0B⟧«0704»我才那样的«23»…。«21»«2820»«20»«0705»«22»被讨厌了的话，⟦0B⟧«0705»«21»«22»你的事«23»«2820»«20»«0701»«22»我想就能忘掉«23»…。«21»«2820»«20»«0702»«22»可你总是«21»会给我⟦0B⟧«0702»打电话来«23»，«21»«2820»«20»«0704»«22»我明明说了那么⟦0B⟧«0704»难听的话，你却«23»，«21»«2820»«20»«0706»«22»一次又一次«23»…。«2818»«20»«0707»«22»我，好开心«23»«21»，«2818»'),
    (0X1B641F, 49, '«20»«22»«0703»いつも電話の向こう側で⟦0B⟧«0703»泣いてたのよ«23»…。«21»«2820»', '«20»«22»«0703»每次在电话那头⟦0B⟧«0703»我都在哭呢«23»…。«21»«2820»'),
    (0X1B6451, 142, '«20»«0702»«22»後、私が誘拐されたとき«23»、«21»«2818»«20»«0706»«22»廃工場まで来て⟦0B⟧«0706»くれたでしょう«23»。«21»«2820»«20»«0705»«22»こんな私を«21»心配して⟦0B⟧«0705»くれるなんて«23»、«2820»«20»«0705»«22»すごく嬉しかった«23»。«21»«2818»', '«20»«0702»«22»还有，我被绑架那次«23»，«21»«2818»«20»«0706»«22»你一路追到了⟦0B⟧«0706»废工厂，对吧«23»。«21»«2820»«20»«0705»«22»这样的我«21»你居然⟦0B⟧«0705»还会担心«23»，«2820»«20»«0705»«22»我特别高兴«23»。«21»«2818»'),
    (0X1B64E0, 486, '«20»«0706»«22»普段は、気丈に⟦0B⟧«0706»生きてきたけど«23»…。«21»«2820»«20»«0706»«22»«21»でも、私だって、⟦0B⟧«0706»普通の女の子よ«23»。«2820»«20»«22»«21»いつでもみんなと一緒にいて、⟦0B⟧おしゃべりしたり«23»、«21»«2820»«20»«0701»«22»遊びに行ったりしたかった«23»。«2818»«20»«0701»«22»バレンタイン«21»のときだって、⟦0B⟧«0701»あなたに«23»…。«2820»«20»«0701»«22»明日からはそうなれるけど«23»、«2818»«20»«0702»«22»卒業する前に«21»、本当の私を⟦0B⟧«0702»見て欲しかったから«23»…。«21»«2820»«20»«0704»«22»もう伊集院家なんて、⟦0B⟧«0704»どうでもいいの«23»。«21»«2820»«20»«0705»«0705»«22»だから«23»…«2818»«20»«0709»«22»好きです«23»。«2818»«20»«0703»«22»今まで、嘘をついていて⟦0B⟧«0703»ごめんなさい«23»。«21»«2820»«20»«070B»«22»でも«23»«21»、«2810»«20»«0701»«22»私と付き合ってください«23»。«2818»', '«20»«0706»«22»平日里，我总撑着⟦0B⟧«0706»很坚强地活着«23»…。«21»«2820»«20»«0706»«22»«21»可我，也是⟦0B⟧«0706»普通的女孩子呀«23»。«2820»«20»«22»«21»想一直和大家在一起，⟦0B⟧聊聊天«23»，«21»«2820»«20»«0701»«22»一起出去玩«23»。«2818»«20»«0701»«22»情人节«21»那天也是，⟦0B⟧«0701»我本想送给你«23»…。«2820»«20»«0701»«22»明天起就能这样了«23»，«2818»«20»«0702»«22»但毕业之前«21»，想让你看到⟦0B⟧«0702»真正的我«23»…。«21»«2820»«20»«0704»«22»伊集院家什么的，⟦0B⟧«0704»已经无所谓了«23»。«21»«2820»«20»«0705»«0705»«22»所以«23»…«2818»«20»«0709»«22»我喜欢你«23»。«2818»«20»«0703»«22»一直以来，骗了你⟦0B⟧«0703»对不起«23»。«21»«2820»«20»«070B»«22»但是«23»«21»，«2810»«20»«0701»«22»请和我交往吧«23»。«2818»'),
    (0X1B66C7, 39, '«20»«0704»伊集院…。«21»⟦0B⟧«0704»いや、伊集院さん…。«2818»', '«20»«0704»伊集院…。«21»⟦0B⟧«0704»不，伊集院同学…。«2818»'),
    (0X1B66EF, 94, '«20»«0701»«22»«21»迷惑だと思うけど«23»…。⟦0B⟧«2818»«0701»«22»あなたの気持ちを聞かせて«23»。«21»«2818»«20»«0702»«22»それで諦めがつくから«23»…。«21»«2818»', '«20»«0701»«22»«21»也许很冒昧«23»…。⟦0B⟧«2818»«0701»«22»把你的心意告诉我吧«23»。«21»«2818»«20»«0702»«22»那样我才死得了心«23»…。«21»«2818»'),
    (0X1B674E, 55, '«20»«0702»そこまで想ってくれて、⟦0B⟧«0702»断れる訳無いじゃ«21»ないか。«2818»', '«20»«0702»你待我这么认真，⟦0B⟧«0702»我哪有不答应的道«21»理啊。«2818»'),
    (0X1B6786, 24, '«20»«0707»«22»そ、«21»それじゃ«23»…。«2818»', '«20»«0707»«22»那、«21»那么说«23»…。«2818»'),
    (0X1B679F, 30, '«20»«0709»もちろん«23»。⟦0B⟧«0709»ＯＫだよ«23»。«2810»', '«20»«0709»当然«23»。⟦0B⟧«0709»ＯＫ啦«23»。«2810»'),
    (0X1B67BE, 96, '«20»«0702»«22»私«23»…«2802»«22»私«23»…。«2802»⟦0B⟧«0702»«22»何て言ったらいいのか«23»…。«2820»«20»«22»やっと、⟦0B⟧«22»普通の«21»女の子になれたのね«23»…。«2818»', '«20»«0702»«22»我«23»…«2802»«22»我«23»…。«2802»⟦0B⟧«0702»«22»该说什么才好«23»…。«2820»«20»«22»终于，⟦0B⟧«22»我做了回«21»普通的女孩子了«23»…。«2818»'),
    (0X1B681F, 35, '«20»«0706»一つだけ聞い«21»ても⟦0B⟧«0706»いいかな？«2818»', '«20»«0706»有件事想«21»问⟦0B⟧«0706»，可以吗？«2818»'),
    (0X1B6843, 17, '«20»«0709»«22»えっ、何？«23»«2810»', '«20»«0709»«22»诶，什么？«23»«2810»'),
    (0X1B6855, 38, '«20»«0705»好雄が倒れたときの⟦0B⟧«0705»事だけど…。«2818»', '«20»«0705»就是好雄晕倒⟦0B⟧«0705»那件事…。«2818»'),
    (0X1B687C, 121, '«20»«0704»«22»ご、ごめんなさい«23»…。«21»«2818»«20»«0701»«22»好雄君に私が女の子だという⟦0B⟧«0701»事«21»がばれてしまったので«23»、«2818»«20»«0702»«22»記憶を操作したんです«23»…。«21»«2818»', '«20»«0704»«22»对、对不起«23»…。«21»«2818»«20»«0701»«22»因为被好雄君发现了⟦0B⟧«0701»我其实是女孩子«21»这件事«23»，«2818»«20»«0702»«22»我就修改了他的记忆«23»…。«21»«2818»'),
    (0X1B68F6, 35, '«20»«0705»やっぱり«21»⟦0B⟧«0705»そうだったんだ…。«2818»', '«20»«0705»果然«21»⟦0B⟧«0705»是这样啊…。«2818»'),
    (0X1B691A, 28, '«20»«0704»«22»け、軽蔑«21»しますか«23»…。«2818»', '«20»«0704»«22»你会瞧不起«21»我吗«23»…。«2818»'),
    (0X1B6937, 41, '«20»«0702»いや…。⟦0B⟧«0702»その気持ち«21»分かるから…。«2818»', '«20»«0702»不会…。⟦0B⟧«0702»那种心情«21»我能懂…。«2818»'),
    (0X1B6961, 93, '«20»«0707»«22»ありがとう«23»…。⟦0B⟧«21»«2818»«20»«0704»«22»本当に優しいのね«23»…。«2818»«20»«0704»«22»あなたを好きに«21»なって⟦0B⟧«0704»良かった«23»…。«2830»', '«20»«0707»«22»谢谢«23»…。⟦0B⟧«21»«2818»«20»«0704»«22»你真的好温柔«23»…。«2818»«20»«0704»«22»喜欢上你«21»了这件事⟦0B⟧«0704»真好«23»…。«2830»'),
    (0X1B69BF, 22, '«20»«0707»«21»«2810»か、鏡さん…。«2810»', '«20»«0707»«21»«2810»镜、镜同学…。«2810»'),
    (0X1B69D6, 57, '«20»«0700»«22»こんな所に«21»呼び出したりして«23»、«2807»«22»⟦0B⟧«0700»ごめんなさい«23»。«2810»', '«20»«0700»«22»把你约到«21»这种地方«23»，«2807»«22»⟦0B⟧«0700»对不起«23»。«2810»'),
    (0X1B6A10, 45, '«20»«0705»い、«21»いきなり。«2805» ⟦0B⟧«0705»鏡さんが謝った…。«2810»', '«20»«0705»太、太«21»突然了。«2805» ⟦0B⟧«0705»镜同学竟在道歉…。«2810»'),
    (0X1B6A3E, 89, '«20»«0700»«22»そ«23»«21»、«2807»«22»そんなに驚かなくても…«23»。«2810»«20»«0706»«22»でも«23»、«2807»«22»いいの«23»。«2810»⟦0B⟧«0706»«22»私の話を聞いて«23»«21»。«2815»', '«20»«0700»«22»那个«23»«21»，«2807»«22»不用那么惊讶啦…«23»。«2810»«20»«0706»«22»不过«23»，«2807»«22»这样也好«23»。«2810»⟦0B⟧«0706»«22»听我把话说完«23»«21»。«2815»'),
    (0X1B6AA8, 417, '«20»«0701»«22»私«23»、«2807»«22»中学の頃«23»、«2807»«22»⟦0B⟧«0701»この街に引っ越してきたの«23»。«2810»«23»«2810»«20»«0704»«22»その前の街で«23»、«2807»«22»私«23»…。«2810»«20»«0701»«22»男の子に何度も振られて«23»…。«2815»«20»«0701»«22»だから«23»、«2807»«22»この街に来る時に«23»、«2807»⟦0B⟧«0701»«22»生まれ変わろう«23»。«2810»«20»«0701»«22»もっと«23»、«2807»«22»もてる女になって«23»、«2810»«20»«0701»«22»男の子達を見返してやろうと⟦0B⟧«0701»思ったの«23»。«2810»«20»«0700»«22»苦労の甲斐があって«23»、«2807»«22»⟦0B⟧«0700»男の子の目を惹く女になったわ«23»。«2815»«20»«0700»«22»そして«23»、«2807»«22»⟦0B⟧«0700»わざと高慢な態度を取って«23»…、«2810»«22»«20»⟦0B⟧«0701»«22»男の子達に復讐してきたの«23»。«2810»', '«20»«0701»«22»我«23»，«2807»«22»初中的时候«23»，«2807»«22»⟦0B⟧«0701»搬到了这座城市«23»。«2810»«23»«2810»«20»«0704»«22»在之前那座城里«23»，«2807»«22»我«23»…。«2810»«20»«0701»«22»被男孩子一次次甩掉«23»…。«2815»«20»«0701»«22»所以«23»，«2807»«22»来这座城市的时候«23»，«2807»⟦0B⟧«0701»«22»我要重新做人«23»。«2810»«20»«0701»«22»更加«23»，«2807»«22»受欢迎的女人«23»，«2810»«20»«0701»«22»让那些男孩子刮目相看⟦0B⟧«0701»我是这么打算的«23»。«2810»«20»«0700»«22»苦没白吃«23»，«2807»«22»⟦0B⟧«0700»我成了吸引男孩子目光的女人«23»。«2815»«20»«0700»«22»然后«23»，«2807»«22»⟦0B⟧«0700»故意摆出高傲的态度«23»…，«2810»«22»«20»⟦0B⟧«0701»«22»向男孩子们展开复仇«23»。«2810»'),
    (0X1B6C4A, 29, '«20»«0702»…そ、そうだったんだ…。«2810»', '«20»«0702»…原、原来是这样…。«2810»'),
    (0X1B6C68, 806, '«20»«0704»«22»«21»最初は楽しかった«23»…。«2810»«20»«0700»«22»男の子にもてはやされることが⟦0B⟧«0700»嬉しかった«23»…。«2810»«20»«0700»«22»でも«23»«21»、«2807»«22»そんな事じゃ«23»、«2807»«22»⟦0B⟧«0700»私の心は満たされなかったわ«23»。«2815»«20»«0707»«22»当たり前よね«23»。«2810»«20»«0700»«22»自分に嘘をついて生きていて«23»、«2807»«22»⟦0B⟧«0700»«21»心が満たされるはずが無いもの«23»。«2815»«20»«0700»«22»貴方に会わなければ«23»、«2807»«22»こんな事⟦0B⟧«0700»は考えなかったのかも«21»しれない«23»。«2810»«20»«0703»«22»…貴方と知り合って«23»…、«2815»«20»«0702»«22»«21»この人となら«23»、«2807»«22»今の自分を⟦0B⟧«0702»捨てられると思ったわ«23»。«2810»«20»«0700»«22»だけど«21»«23»、«2807»«22»私には«21»その時«23»、«2807»«22»自分を⟦0B⟧«0700»捨てる勇気が無かったの«23»。«2810»«20»«0702»«22»また«23»、«2807»«22»昔の自分に戻りたく⟦0B⟧«0702»なかったから«23»…。«2815»«20»«0702»«22»でも«23»、«2807»«22»今になって«23»、«2807»«22»«21»やっと⟦0B⟧«0702»勇気が出たわ«23»。«2810»«20»«0700»«22»貴方に…«23»、«2807»«22»⟦0B⟧«0700»こんな女だと思われたまま«23»…、«2808»«20»«0700»«22»卒業するなんて耐えられない«23»«21»。«2810»«20»«0703»«22»何十人の男性よりも«23»…、«2808»«20»⟦0B⟧«0700»«22»ただ貴方だけそばにいて欲しい«23»。«2810»«20»«0700»«22»«21»私の心の傷を癒してくれるのは«23»、«2807»«22»⟦0B⟧«0700»貴方だけだから«23»…。«21»«2830»', '«20»«0704»«22»«21»一开始真的很痛快«23»…。«2810»«20»«0700»«22»被男孩子们众星捧月⟦0B⟧«0700»我很得意«23»…。«2810»«20»«0700»«22»可是«23»«21»，«2807»«22»光靠那种事«23»，«2807»«22»⟦0B⟧«0700»填不满我的心«23»。«2815»«20»«0707»«22»也是当然的啦«23»。«2810»«20»«0700»«22»对自己说着谎过日子«23»，«2807»«22»⟦0B⟧«0700»«21»心怎么可能满足呢«23»。«2815»«20»«0700»«22»要不是遇见了你«23»，«2807»«22»这种话⟦0B⟧«0700»我大概根本不会«21»去想吧«23»。«2810»«20»«0703»«22»…认识了你以后«23»…，«2815»«20»«0702»«22»«21»和你在一起的话«23»，«2807»«22»现在的自己⟦0B⟧«0702»我想我可以舍弃«23»。«2810»«20»«0700»«22»可是«21»«23»，«2807»«22»那时的我«21»却«23»，«2807»«22»没有⟦0B⟧«0700»舍弃自己的勇气«23»。«2810»«20»«0702»«22»因为«23»，«2807»«22»回到从前的自己⟦0B⟧«0702»是我不愿的«23»…。«2815»«20»«0702»«22»但是«23»，«2807»«22»到了现在«23»，«2807»«22»«21»终于⟦0B⟧«0702»我鼓起勇气了«23»。«2810»«20»«0700»«22»被你…«23»，«2807»«22»⟦0B⟧«0700»看成这样的女人«23»…，«2808»«20»«0700»«22»就这么毕业我受不了«23»«21»。«2810»«20»«0703»«22»比起几十个男人«23»…，«2808»«20»⟦0B⟧«0700»«22»我只想要你陪在身边«23»。«2810»«20»«0700»«22»«21»能治好我心头伤的«23»，«2807»«22»⟦0B⟧«0700»只有你«23»…。«21»«2830»'),
    (0X1B6F8F, 71, '«20»«0709»…«22»«21»好きよ«23»。«2815»«20»«0700»«22»いつまでも私のそばにいて«23»…。«2815»«20»«0709»«22»お願い«23»…。«21»«2820»', '«20»«0709»…«22»«21»我喜欢你«23»。«2815»«20»«0700»«22»永远陪在我身边吧«23»…。«2815»«20»«0709»«22»拜托了«23»…。«21»«2820»'),
    (0X1B6FD7, 21, '«20»«0706»そうだったんだ。«2810»', '«20»«0706»原来是这样啊。«2810»'),
    (0X1B6FED, 38, '«20»«0701»«22»«21»やっぱり«23»、«2807»«22»私じゃ駄目よね«23»。«2810»', '«20»«0701»«22»«21»果然«23»，«2807»«22»还是我不行呢«23»。«2810»'),
    (0X1B7014, 41, '«20»«0705»い、いや。«2805» ⟦0B⟧«0705»俺でよかったら«23»…。«2810»', '«20»«0705»不、不是的。«2805» ⟦0B⟧«0705»我也可以的话«23»…。«2810»'),
    (0X1B703E, 84, '«20»«0709»…«22»本当に«23»？«2815»«20»«0709»«22»«21»嬉しい«23»…。«2810»«20»«0701»«22»やっと«23»、«2807»«22»⟦0B⟧«0701»«21»本当の自分を取り戻せそう«23»。«2810»', '«20»«0709»…«22»真的«23»？«2815»«20»«0709»«22»«21»我好高兴«23»…。«2810»«20»«0701»«22»终于«23»，«2807»«22»⟦0B⟧«0701»«21»我能找回真正的自己了«23»。«2810»'),
    (0X1B7093, 45, '«20»«0704»でも、他の男子から、⟦0B⟧«0704»怨まれそうだね«23»。«2810»', '«20»«0704»不过，会被其他男生⟦0B⟧«0704»记恨的吧«23»。«2810»'),
    (0X1B70C1, 79, '«20»«0709»«22»«21»大丈夫。«23»«2810»«20»«0700»«22»私が選んだ人だもの«23»«21»、«2807»«22»⟦0B⟧«0700»誰も文句を言うはずがないわ«23»。«2810»', '«20»«0709»«22»«21»没关系。«23»«2810»«20»«0700»«22»你是我选中的人«23»«21»，«2807»«22»⟦0B⟧«0700»谁都不该有意见«23»。«2810»'),
    (0X1B7111, 48, '«20»«0703»そうだといいんだけど。«2810»⟦0B⟧«0703»ちょっと心配…。«2825»', '«20»«0703»但愿是吧。«2810»⟦0B⟧«0703»有点担心…。«2825»'),
    (0X1B7142, 24, '«20»«0706»«21»«2808»か、片桐さん…。«2810»', '«20»«0706»«21»«2808»片、片桐同学…。«2810»'),
    (0X1B715B, 93, '«20»«0703»«22»あ«23»っ、«22»ソーリー«23»。«2808»⟦0B⟧«0703»«22»待った？ごめんなさい«23»。«2810»«20»«0705»«22»こんな所に«21»⟦0B⟧«0705»呼び出したりして«23»。«2810»', '«20»«0703»«22»啊«23»，«22»抱歉«23»。«2808»⟦0B⟧«0703»«22»久等了吧？对不起«23»。«2810»«20»«0705»«22»把你约到«21»⟦0B⟧«0705»这种地方«23»。«2810»'),
    (0X1B71B9, 31, '«20»«0707»別に、い«21»いよ。⟦0B⟧«0707»何の用？«2810»', '«20»«0707»没、没«21»关系啦。⟦0B⟧«0707»什么事？«2810»'),
    (0X1B71D9, 82, '«20»«0705»«0705»«22»あの«23»«21»…。«2810»«20»«22»一つ聞きたいんだ«21»けど«23»…。«2810»⟦0B⟧«22»大雑把な性格の«21»女の子は嫌い«23»？«2810»', '«20»«0705»«0705»«22»那个«23»«21»…。«2810»«20»«22»想问你一件事«21»呢«23»…。«2810»⟦0B⟧«22»大大咧咧的«21»女孩子你会讨厌«23»？«2810»'),
    (0X1B722C, 37, '«20»«0706»いや、好きだけど«21»…⟦0B⟧«0706»それだけ？«2810»', '«20»«0706»不，挺喜欢的«21»…⟦0B⟧«0706»就这些？«2810»'),
    (0X1B7252, 447, '«20»«0706»«22»あっウェイト«23»、⟦0B⟧«0706»«22»«21»ちょっと待って«23»。«2810»«20»«0707»«22»本当の用は、⟦0B⟧«0707»これからなの«23»。«21»«2810»«20»«0702»«22»どうしても«23»、«2804»«22»あなたに⟦0B⟧«0702»言いたいこと«21»があって«23»…。«2810»«20»«0704»«22»私ってね«23»«21»、«2808»«22»誰とでも⟦0B⟧«0704»仲良く話をするから«23»、«2810»«20»«0703»«22»そうは見えなかったかも«21»⟦0B⟧«0703»しれないんだけど«23»、«2810»«20»«0707»«22»«21»あなたと話を⟦0B⟧«0707»してるときが«23»、«2808»«20»«0705»«22»一番«21»リラックスして⟦0B⟧«0705»いられたの«23»。«2810»«20»«0705»«22»今になって«21»、それに⟦0B⟧«0705»やっと気付いて«23»、«2810»«20»«0705»«22»このまま«21»卒業して«23»、«2810»«20»«0702»«22»あなたに会えなく«21»なるかも⟦0B⟧«0702»しれないと思ったら«23»、«2810»', '«20»«0706»«22»哎呀等等«23»，⟦0B⟧«0706»«22»«21»先别走呀«23»。«2810»«20»«0707»«22»真正的正事，⟦0B⟧«0707»从现在才开始«23»。«21»«2810»«20»«0702»«22»无论如何«23»，«2804»«22»我都有⟦0B⟧«0702»话想对你«21»说«23»…。«2810»«20»«0704»«22»我这人呢«23»«21»，«2808»«22»跟谁⟦0B⟧«0704»都聊得来«23»，«2810»«20»«0703»«22»也许看不«21»⟦0B⟧«0703»出来吧«23»，«2810»«20»«0707»«22»«21»但和你⟦0B⟧«0707»说话的时候«23»，«2808»«20»«0705»«22»最«21»放松⟦0B⟧«0705»了«23»。«2810»«20»«0705»«22»到了现在«21»，这才⟦0B⟧«0705»注意到«23»，«2810»«20»«0705»«22»就这样«21»毕业«23»，«2810»«20»«0702»«22»也许就«21»再也⟦0B⟧«0702»见不到你了，想到这«23»，«2810»'),
    (0X1B7412, 85, '«20»«0702»«22»途端に悲しくなってきて«23»、«2820»«20»«0703»«22»私どうしたらいいのか«23»、⟦0B⟧«0703»«22»分からなくなって«23»…。«2820»', '«20»«0702»«22»我一下子难过起来«23»，«2820»«20»«0703»«22»我该怎么办«23»，⟦0B⟧«0703»«22»全都不知道了«23»…。«2820»'),
    (0X1B7468, 251, '«20»«0707»«22»私、いい加減な«21»⟦0B⟧«0707»性格だけど«23»、«2810»⟦0B⟧«20»«0706»«22»この事だけは、⟦0B⟧«0706»真剣に考え«21»たの«23»。«2810»«20»«0704»«22»それで、決心したの«23»«21»。«2810»«20»«0701»«22»女の子から言うのは、すごく⟦0B⟧«0701»恥ずかしい«21»んだけど«23»。«2810»«20»«0705»«22»私の«21»本当の気持ちを«23»«21»«2808»⟦0B⟧«0705»«22»聞いて欲しい«23»…。«2810»⟦0B⟧«20»«0707»«22»聞いてくれる⟦0B⟧«0707»だけでいいの«23»。«2810»', '«20»«0707»«22»我这人，做事«21»⟦0B⟧«0707»是挺马虎的«23»，«2810»⟦0B⟧«20»«0706»«22»可只有这件事⟦0B⟧«0706»我是认真想过«21»的«23»。«2810»«20»«0704»«22»所以，我下定决心了«23»«21»。«2810»«20»«0701»«22»女孩子先开口，虽然⟦0B⟧«0701»难为情«21»得不行«23»。«2810»«20»«0705»«22»我«21»真正的心意«23»«21»«2808»⟦0B⟧«0705»«22»想让你听到«23»…。«2810»⟦0B⟧«20»«0707»«22»你只要肯听⟦0B⟧«0707»就够了«23»。«2810»'),
    (0X1B7574, 102, '«20»«0707»«22»アイミスユー«23»«21»。«2810»«20»«0706»«22»あなたがいないと«21»⟦0B⟧«0706»寂しくて«23»«21»…。«2810»⟦0B⟧«20»«0707»«22»だから«23»…、«2808»⟦0B⟧«0707»«22»だから私と«23»«21»…。«2810»', '«20»«0707»«22»想你啦«23»«21»。«2810»«20»«0706»«22»你不在身边«21»⟦0B⟧«0706»就好寂寞«23»«21»…。«2810»⟦0B⟧«20»«0707»«22»所以«23»…，«2808»⟦0B⟧«0707»«22»所以，跟我«23»«21»…。«2810»'),
    (0X1B75DB, 43, '«20»«0705»さっき、好き«21»だって⟦0B⟧«0705»言ったでしょう。«2810»', '«20»«0705»刚才，你不是«21»说过⟦0B⟧«0705»喜欢我吗。«2810»'),
    (0X1B7607, 36, '«20»«070B»えっ«23»、«2808»«20»«070C»«22»う«23»、«2808»«20»«070B»«22»うん«23»。«2810»', '«20»«070B»诶«23»，«2808»«20»«070C»«22»我«23»，«2808»«20»«070B»«22»嗯«23»。«2810»'),
    (0X1B762C, 44, '«20»«0704»それって実は、«21»⟦0B⟧«0704»片桐さんの事なんだ。«21»«2810»', '«20»«0704»那其实是，«21»⟦0B⟧«0704»就是片桐同学你呀。«21»«2810»'),
    (0X1B7659, 34, '«20»«0709»«22»リアリー«23»、«2810»⟦0B⟧«0709»«22»本当に«23»…？«2810»', '«20»«0709»«22»说真的«23»，«2810»⟦0B⟧«0709»«22»真的«23»…？«2810»'),
    (0X1B767C, 41, '«20»«0704»«21»こんな時に冗談なんて⟦0B⟧«0704»言えないよ。«2810»', '«20»«0704»«21»这种时候，哪说得出⟦0B⟧«0704»玩笑呀。«2810»'),
    (0X1B76A6, 146, '«20»«0705»«22»アンビリーバブル«23»«21»。«2810»«20»«0706»«22»信じられない«23»…。«2810»«20»«0705»«22»生まれてから«21»、⟦0B⟧«0705»今日が一番幸せよ«23»。«2810»«20»«0705»«22»«21»ネバーフォゲット«23»。«2810»⟦0B⟧«0705»«22»私、一生忘れない«23»。«2810»«21»«2820»', '«20»«0705»«22»令人吃惊«23»«21»。«2810»«20»«0706»«22»不敢相信«23»…。«2810»«20»«0705»«22»出生到现在«21»，⟦0B⟧«0705»今天我最幸福«23»。«2810»«20»«0705»«22»«21»绝不忘记«23»。«2810»⟦0B⟧«0705»«22»我一生都不会忘«23»。«2810»«21»«2820»'),
    (0X1B7739, 24, '«20»«0706»«21»«2810»に、虹野さん…。«2820»', '«20»«0706»«21»«2810»虹、虹野同学…。«2820»'),
    (0X1B7752, 83, '«20»«0705»«22»ご«23»、«21»«2802»«22»ごめんなさい«23»。«2810»«20»«0703»«22»忙しいのに、こんな所に⟦0B⟧«0703»呼び出したりして«23»…。«21»«2820»', '«20»«0705»«22»对«23»，«21»«2802»«22»不起«23»。«2810»«20»«0703»«22»明明那么忙，还把你约到⟦0B⟧«0703»这种地方«23»…。«21»«2820»'),
    (0X1B77A6, 42, '«20»«0704»いや、いいよ。⟦0B⟧«0704»別に忙しくないから。«2810»', '«20»«0704»没事，不要紧。⟦0B⟧«0704»我并不忙。«2810»'),
    (0X1B77D1, 192, '«20»«0703»«22»あなたに«21»、どうしても⟦0B⟧«0703»伝えたいことがあって«23»、«21»«2814»«20»«0705»«22»あんな手紙を⟦0B⟧«0705»出してしまったの«23»。«2814»«20»«0703»«22»«21»手紙で、全てを伝えても⟦0B⟧«0703»よかったけど«23»、«2814»«20»«0702»«22»この想いだけは«21»、⟦0B⟧«0702»直接言いたかったから«23»…。«2814»', '«20»«0703»«22»我有话«21»，一定要⟦0B⟧«0703»告诉你«23»，«21»«2814»«20»«0705»«22»才寄出了⟦0B⟧«0705»那样的信«23»。«2814»«20»«0703»«22»«21»其实信里说尽⟦0B⟧«0703»也未尝不可«23»，«2814»«20»«0702»«22»但这份心意«21»，⟦0B⟧«0702»我想亲口告诉你«23»…。«2814»'),
    (0X1B7892, 17, '«20»«0708»そ、そう…。«2810»', '«20»«0708»是、这样…。«2810»'),
    (0X1B78A4, 89, '«20»«0703»«22»あなたは、⟦0B⟧«0703»知らないでしょうけど«23»、«2814»«20»«0702»«22»私は、いつも«21»あなたの事を⟦0B⟧«0702»見ていたわ«23»。«2814»', '«20»«0703»«22»你大概，⟦0B⟧«0703»不知道吧«23»，«2814»«20»«0702»«22»我一直«21»都在⟦0B⟧«0702»注视着你«23»。«2814»'),
    (0X1B78FE, 87, '«20»«0704»«22»そして«21»、何事にも⟦0B⟧«0704»頑張って向かっていく«23»«2818»«20»«0704»«22»その姿に、⟦0B⟧«0704»だんだん惹かれて«23»…。«2810»', '«20»«0704»«22»然后«21»，无论什么事⟦0B⟧«0704»都拼命去面对«23»«2818»«20»«0704»«22»那个样子，⟦0B⟧«0704»让我渐渐心动«23»…。«2810»'),
    (0X1B7956, 149, '«20»«0706»«22»私は«21»、悩んだり、⟦0B⟧«0706»苦しいときには«23»、«2818»«20»«0701»«22»いつもあなたの、ひたむきな⟦0B⟧«0701»頑張りにはげまされて«23»、«21»«2818»«20»«0704»«22»どんなときでも«21»、⟦0B⟧«0704»切り抜けてこれたわ«23»。«2818»', '«20»«0706»«22»我«21»，遇到烦恼、⟦0B⟧«0706»难受的时候«23»，«2818»«20»«0701»«22»总是被你那一心向前的⟦0B⟧«0701»努力推着走«23»，«21»«2818»«20»«0704»«22»不管什么时候«21»，⟦0B⟧«0704»都能挺过来«23»。«2818»'),
    (0X1B79EC, 44, '«20»«0704»«22»だから、今日も⟦0B⟧«0704»勇気を出せると思う«23»。«2818»', '«20»«0704»«22»所以今天，⟦0B⟧«0704»我想我能鼓起勇气«23»。«2818»'),
    (0X1B7A29, 212, '«20»«0706»«22»私«21»、料理ぐらいしか⟦0B⟧«0706»とりえはなくて«23»、«2818»«20»«0701»«22»他には、何も出来ないし«23»…。«21»«2810»«20»«0703»«22»あなたにとって«21»、⟦0B⟧«0703»迷惑かもしれないけど«23»、«2818»«20»«0702»«22»もう、これ以上自分の心に⟦0B⟧«0702»嘘はつ«21»けないから«23»«2818»«20»«22»この場で、はっきり言います«23»。«2818»', '«20»«0706»«22»我«21»，除了做饭⟦0B⟧«0706»没什么长处«23»，«2818»«20»«0701»«22»别的什么也不行«23»…。«21»«2810»«20»«0703»«22»对你来说«21»，⟦0B⟧«0703»也许是种麻烦«23»，«2818»«20»«0702»«22»我已经不能再对⟦0B⟧«0702»自己的心«21»说谎了«23»«2818»«20»«22»我要在这里，当面说清楚«23»。«2818»'),
    (0X1B7AFE, 73, '«20»«0705»«22»あなたが好きです«23»。«2810»«20»«0705»«22»ずっとあなただけを⟦0B⟧«0705»応援していきたい«23»…。«2810»', '«20»«0705»«22»我喜欢你«23»。«2810»«20»«0705»«22»我想永远只为你⟦0B⟧«0705»加油打气«23»…。«2810»'),
    (0X1B7B48, 36, '«20»«0704»実はね。⟦0B⟧«0704»僕も、虹野さんが…。«2818»', '«20»«0704»其实呢。⟦0B⟧«0704»我也是，对虹野同学…«2818»'),
    (0X1B7B6D, 31, '«20»«0702»«22»勇気を出してよかった«23»…。«2810»', '«20»«0702»«22»鼓起勇气真好«23»…。«2810»'),
    (0X1B7B8D, 44, '«20»«0705»«22»やっぱり頑張れば、⟦0B⟧«0705»なんとかなるね«23»。«2818»', '«20»«0705»«22»果然努力了，⟦0B⟧«0705»总会有办法呢«23»。«2818»'),
    (0X1B7BBA, 117, '«20»«0708»«22»そ、そうだ«23»。«21»«2810»«20»«0704»«22»明日«23»…、«21»«2802»«22»二人きりで«23»、«2810»«20»«0703»«22»卒業記念のパーティーを⟦0B⟧«0703»開きたいな«23»…。«2818»«20»«0708»«22»来てくれる？«23»«2810»', '«20»«0708»«22»对、对了«23»。«21»«2810»«20»«0704»«22»明天«23»…，«21»«2802»«22»就我们两个人«23»，«2810»«20»«0703»«22»毕业纪念的派对⟦0B⟧«0703»想办一场呢«23»…。«2818»«20»«0708»«22»你来吗？«23»«2810»'),
    (0X1B7C30, 26, '«20»«0709»もちろん。⟦0B⟧«0709»喜んで。«2818»', '«20»«0709»当然。⟦0B⟧«0709»求之不得。«2818»'),
    (0X1B7C4B, 91, '«20»«0702»«22»それじゃ«21»、あなたの好きな⟦0B⟧«0702»料理教えてね«23»。«2818»«20»«0704»«22»明日«21»、たくさん作って⟦0B⟧«0704»待ってるから。', '«20»«0702»«22»那就«21»，告诉我你⟦0B⟧«0702»爱吃什么菜吧«23»。«2818»«20»«0704»«22»明天«21»，我做一大桌⟦0B⟧«0704»等着你。'),
    (0X1B7CAA, 20, '«20»«0707»«21»あっ、君は…。«2810»', '«20»«0707»«21»啊，你是…。«2810»'),
    (0X1B7CBF, 159, '«20»«0704»«22»今まで«21»、ごめんなさい«23»。«2810»«20»«0702»«22»私、館林見晴って«21»言います«23»。«2810»«20»«0701»«22»こんな所«21»に呼び出したのは«23»、«2810»«20»«0705»«22»あなたにどうしても«21»«23»«2810»«20»«0701»«22»言いたいことがあったから«23»…。«2810»', '«20»«0704»«22»一直以来«21»，对不起«23»。«2810»«20»«0702»«22»我叫«21»馆林见晴«23»。«2810»«20»«0701»«22»把你约到«21»这种地方，是因为«23»，«2810»«20»«0705»«22»我«21»«23»«2810»«20»«0701»«22»一定要对你说的话«23»…。«2810»'),
    (0X1B7D5F, 28, '«20»«0703»言いたいことって、«21»何？«2810»', '«20»«0703»要说的话，«21»是什么？«2810»'),
    (0X1B7D7C, 76, '«20»«0705»«22»私«23»、«21»«2804»«22»今まであなたに⟦0B⟧«0705»ぶつかっていたのは«23»、«2820»«20»«0706»«22»偶然じゃないの«23»。«2810»', '«20»«0705»«22»我«23»，«21»«2804»«22»以前总是来⟦0B⟧«0705»缠着你«23»，«2820»«20»«0706»«22»都不是偶然哦«23»。«2810»'),
    (0X1B7DC9, 36, '«20»«0705»そんなの、⟦0B⟧«0705»誰だってわかるよ。«2818»', '«20»«0705»那种事，⟦0B⟧«0705»谁看得出来啊。«2818»'),
    (0X1B7DEE, 46, '«20»«0704»«22»私«23»、«2804»«22»あなたに一目ぼれ⟦0B⟧«0704»しちゃって«23»、«2820»', '«20»«0704»«22»我«23»，«2804»«22»对你呀一见钟⟦0B⟧«0704»情了«23»，«2820»'),
    (0X1B7E1D, 142, '«20»«0704»«22»いつでも、あなたの事⟦0B⟧«0704»見てたの«23»。«2818»«20»«0702»«22»それで«21»、せめて顔だけでも«23»«2810»«20»«0704»«22»覚えてもらいたくて«23»、«2810»«20»«0707»«22»あんな事を«23»…。«2810»«20»«0707»«22»ごめんな«21»さい«23»。«2810»', '«20»«0704»«22»我一直⟦0B⟧«0704»都在看着你«23»。«2818»«20»«0702»«22»所以«21»，哪怕只记住我的脸«23»«2810»«20»«0704»«22»也好«23»，«2810»«20»«0707»«22»我才做了那些«23»…。«2810»«20»«0707»«22»对不«21»起«23»。«2810»'),
    (0X1B7EAC, 24, '«20»«0705»そうだった«21»のか…。«2810»', '«20»«0705»原来是«21»这样啊…。«2810»'),
    (0X1B7EC5, 45, '«20»«0704»«22»あんな事しておいて«21»、⟦0B⟧«0704»何ですけど«23»…。«2820»', '«20»«0704»«22»那种事之后«21»，⟦0B⟧«0704»虽然这话很厚脸皮«23»…。«2820»'),
    (0X1B7EF3, 71, '«20»«0704»«22»やっぱり、一目ぼれを⟦0B⟧«0704»信じます«23»。«2820»«20»«0702»«22»私と付き合ってください«23»。«2810»', '«20»«0704»«22»我果然还是⟦0B⟧«0704»相信一见钟情«23»。«2820»«20»«0702»«22»请和我交往吧«23»。«2810»'),
    (0X1B7F3B, 47, '«20»«0704»実は俺も館林さんが、⟦0B⟧«0704»気になってたんだ。«23»«2818»', '«20»«0704»其实，我也一直在意⟦0B⟧«0704»馆林同学哦。«23»«2818»'),
    (0X1B7F6B, 29, '«20»«0703»«22»それじゃ、ＯＫなのね«23»。«2810»', '«20»«0703»«22»那就是，答应我了«23»。«2810»'),
    (0X1B7F89, 71, '«20»«0709»«22»嬉しいわ«23»«21»。«2810»«20»«0703»«22»お互いの事は«23»、これから⟦0B⟧«0703»«22»知っていきま«21»しょう«23»。', '«20»«0709»«22»我真开心«23»«21»。«2810»«20»«0703»«22»我们之间的事情«23»，从今天开始⟦0B⟧«0703»«22»一起去«21»了解«23»。'),
    (0X3E6069, 68, '«20»«0707»«22»ごめんなさい«23»。«2818»«20»«0705»«22»«21»こんな所に呼び出し⟦0B⟧«0705»ちゃったりして«23»…。«2820»', '«20»«0707»«22»对不起«23»。«2818»«20»«0705»«22»«21»把前辈约到⟦0B⟧«0705»这种地方«23»…。«2820»'),
    (0X3E60AE, 24, '«20»«0705»«21»いや、別にいいよ。«2818»', '«20»«0705»«21»不，没关系的。«2818»'),
    (0X3E60C7, 193, '«20»«0705»«0705»«22»あのね«23»«21»。⟦0B⟧«2810»«0705»«0705»«22»優美ね«23»«21»。«2820»«20»«0703»«22»ずっと先輩と同じ学年に⟦0B⟧«0703»なりたかったんです«23»«21»。«2820»«20»«0702»«22»同じ学年だったら«21»、高校も⟦0B⟧«0702»３年間一緒にいられたし«23»、«2820»«20»«0704»«22»修学旅行だって⟦0B⟧«0704»一緒に行けたのに«23»…。«21»«2820»', '«20»«0705»«0705»«22»那个嘛«23»«21»。⟦0B⟧«2810»«0705»«0705»«22»优美啊«23»«21»。«2820»«20»«0703»«22»一直都想和前辈⟦0B⟧«0703»同一个年级«23»«21»。«2820»«20»«0702»«22»同年级的话«21»，高中⟦0B⟧«0702»三年都能在一起«23»，«2820»«20»«0704»«22»连修学旅行⟦0B⟧«0704»也能一起去了«23»…。«21»«2820»'),
    (0X3E6189, 207, '«20»«0703»«22»どうして、お兄ちゃんの«21»⟦0B⟧«0703»生まれるときに«23»«21»«2820»«20»«0704»«22»優美が生まれなかった⟦0B⟧«0704»のかなって«23»…。«21»«2820»«20»«0703»«22»何度も、泣いちゃった«23»。«2818»«20»«0705»«22»«21»先輩の学年の⟦0B⟧«0705»女の人と比べたら«23»«21»、«2820»«20»«0705»«22»子供っぽくて«21»、⟦0B⟧«0705»わがままだと思う«23»。«2820»', '«20»«0703»«22»为什么，哥哥«21»⟦0B⟧«0703»出生的时候，«23»«21»«2820»«20»«0704»«22»生下来的不是⟦0B⟧«0704»优美呢«23»。«21»«2820»«20»«0703»«22»我哭了好多次«23»。«2818»«20»«0705»«22»«21»和前辈年级⟦0B⟧«0705»的女孩子比，«23»«21»«2820»«20»«0705»«22»我幼稚«21»，⟦0B⟧«0705»又任性«23»。«2820»'),
    (0X3E6259, 163, '«20»«22»でも«21»、子供っぽいのが嫌なら«23»、«2818»«20»«0702»«22»もっと大人っぽくなるよう⟦0B⟧«0702»努力します«23»«21»。«2820»«20»«0704»«22»«21»わがままも治します«23»。«2818»«20»«0704»«22»だから«21»、«2802»お兄ちゃんの⟦0B⟧«0704»妹としてじゃなくて«23»、«21»«2820»', '«20»«22»可是«21»，要是讨厌幼稚的我«23»，«2818»«20»«0702»«22»我会努力变得⟦0B⟧«0702»更成熟一点«23»«21»。«2820»«20»«0704»«22»«21»任性我也会改«23»。«2818»«20»«0704»«22»所以«21»，«2802»不要只把我当⟦0B⟧«0704»哥哥的妹妹«23»，«21»«2820»'),
    (0X3E62FD, 136, '«20»«0705»«22»一人の女の子として«21»⟦0B⟧«0705»付き合って下さい«23»。«2820»«20»«0706»«22»だって«21»、先輩が⟦0B⟧«0706»世界中の誰より«23»、«2820»«20»«0704»«22»大好きで、大好きで⟦0B⟧«0704»しかたがないから«23»…。«2820»', '«20»«0705»«22»请把我当作«21»⟦0B⟧«0705»一个女孩子，和我交往吧«23»。«2820»«20»«0706»«22»因为«21»，前辈是⟦0B⟧«0706»全世界我«23»，«2820»«20»«0704»«22»最喜欢、最喜欢⟦0B⟧«0704»喜欢到没办法«23»…«2820»'),
    (0X3E6386, 38, '«20»«0703»実はね。⟦0B⟧«0703»俺も、優美ちゃんが…。«2818»', '«20»«0703»其实呢。⟦0B⟧«0703»我也，喜欢优美酱…。«2818»'),
    (0X3E63AD, 21, '«20»«0707»«22»ホントですか？«23»«2818»', '«20»«0707»«22»真的吗？«23»«2818»'),
    (0X3E63C3, 29, '«20»«0703»«22»年下でもいいんですか？«23»«2818»', '«20»«0703»«22»我比你小也可以吗？«23»«2818»'),
    (0X3E63E1, 42, '«20»«0709»当然だよ。«2810»«20»«0703»好きだよ、優美ちゃん。«2818»', '«20»«0709»那是当然。«2810»«20»«0703»我喜欢你，优美酱。«2818»'),
    (0X3E640C, 46, '«20»«0704»«22»それじゃ、制服の⟦0B⟧«0704»第二ボタンを下さい。«23»«2818»', '«20»«0704»«22»那么，请把制服的⟦0B⟧«0704»第二颗纽扣给我。«23»«2818»'),
    (0X3E643B, 27, '«20»«0705»«0705»いいよ。«21»⟦0B⟧«0705»«0705»はい。«2818»', '«20»«0705»«0705»好呀。«21»⟦0B⟧«0705»«0705»给。«2818»'),
    (0X3E6457, 211, '«20»«0705»«0705»«22»ワーイ«23»。«2818»«20»«0704»«22»これをお守りにして«23»、«21»⟦0B⟧«0704»«22»あと一年頑張ります«23»。«2818»«20»«0704»«22»お兄ちゃんにでなく«21»、⟦0B⟧«0704»優美に会うために«23»«2818»«20»«0702»«22»家に遊びに来て下さいね«23»«21»。«2818»«20»«0706»«22»そうじゃないと、⟦0B⟧«0706»優美寂しくて«23»«21»«2818»«20»«0707»«22»泣いちゃうから«23»。«2818»', '«20»«0705»«0705»«22»太好了«23»。«2818»«20»«0704»«22»有这个当护身符«23»，«21»⟦0B⟧«0704»«22»我再努力一年«23»。«2818»«20»«0704»«22»不是为了见哥哥«21»，⟦0B⟧«0704»是为了见优美«23»«2818»«20»«0702»«22»才来我家玩哦«23»«21»。«2818»«20»«0706»«22»要是不来，⟦0B⟧«0706»优美会好寂寞«23»«21»«2818»«20»«0707»«22»会哭出来的«23»。«2818»'),
    (0X3E652B, 26, '«20»«0708»うん。⟦0B⟧«0708»必ず行くよ。«2818»', '«20»«0708»嗯。⟦0B⟧«0708»我一定会去的。«2818»'),
    (0X3E6546, 34, '«20»«0708»うれしい«23»。«21»⟦0B⟧«0708»«22»大好きです«23»。«2818»', '«20»«0708»好高兴«23»。«21»⟦0B⟧«0708»«22»最喜欢你了«23»。«2818»'),
    (0X3E6569, 11, '«20»«070B»先輩。«2818»', '«20»«070B»前辈。«2818»'),
    (0X3E6575, 50, '«20»«0704»（でも、結婚したら、⟦0B⟧«0704»好雄の弟になるか…。）«2828»', '«20»«0704»（不过结了婚的话，⟦0B⟧«0704»不就成好雄的弟弟了…。）«2828»'),
    (0X3E65A8, 59, '«20»«0707»«21»«2810»き、如月さん。«23»«2810»«20»«0705»あれ？«23»«2810»⟦0B⟧«0705»眼鏡はどうしたの？«23»«2810»', '«20»«0707»«21»«2810»如、如月同学。«23»«2810»«20»«0705»咦？«23»«2810»⟦0B⟧«0705»你的眼镜呢？«23»«2810»'),
    (0X3E65E4, 98, '«20»«0704»«22»こっちの方が、«23»«2810»⟦0B⟧«0704»«22»好みにあうと思って、«23»«2810»«20»«0703»«22»思い切ってコンタクトに⟦0B⟧«0703»してしまいました。«23»«2810»', '«20»«0704»«22»我觉得这样«23»«2810»⟦0B⟧«0704»«22»更合我自己的喜好，«23»«2810»«20»«0703»«22»就下定决心换⟦0B⟧«0703»成了隐形眼镜。«23»«2810»'),
    (0X3E6647, 39, '«20»«0706»（もしかして、⟦0B⟧«0707»俺のために…。）«23»«2810»', '«20»«0706»（难道说，⟦0B⟧«0707»是为了我…。）«23»«2810»'),
    (0X3E666F, 24, '«20»«0706»«21»«2810»き、如月さん…。«2810»', '«20»«0706»«21»«2810»如、如月同学…。«2810»'),
    (0X3E6688, 188, '«20»«0703»«22»すみません«23»。«21»«2810»«22»失礼だとは⟦0B⟧«0703»思いましたけど«23»…。«2810»«20»«0708»«22»どうしても«23»、«2804»⟦0B⟧«0708»«22»«21»今日あなたに«23»«2810»«20»«0704»«22»言わなければならない⟦0B⟧«0704»«21»ことがあって«23»、«2810»«20»«0703»«22»こんな所に«23»、«22»呼び出して«21»⟦0B⟧«0703»しまいました«23»。«2810»', '«20»«0703»«22»对不起«23»。«21»«2810»«22»虽然明知⟦0B⟧«0703»这样很失礼«23»…«2810»«20»«0708»«22»可我«23»，«2804»⟦0B⟧«0708»«22»«21»今天一定要对你«23»«2810»«20»«0704»«22»说清楚⟦0B⟧«0704»«21»一件事«23»，«2810»«20»«0703»«22»所以才把你«23»，«22»约到«21»⟦0B⟧«0703»这种地方来«23»。«2810»'),
    (0X3E6745, 47, '«20»«0703»別に、いいよ。«2810»⟦0B⟧«0703»言いたいことって、何？«23»«2810»', '«20»«0703»没关系啦。«2810»⟦0B⟧«0703»你想说什么？«23»«2810»'),
    (0X3E6775, 404, '«20»«22»私は«23»、«2808»«22»身体が弱かった«21»せいか«23»、«2810»⟦0B⟧«22»友達も«21»あまりいなくて«23»、«2810»«20»«0703»«22»趣味は«21»本を読むこと⟦0B⟧«0703»ぐらいしかありません«23»。«2810»«20»«0702»«22»«21»そして«23»、«22»本を読むたびに«23»、⟦0B⟧«0702»«22»その中の恋愛に«21»憧れ«23»、«2810»«20»«0705»«22»少し嫉妬してしまう⟦0B⟧«0705»自分が«21»情けなくて«23»、«2810»«20»«0702»«22»«21»本当の気持ちを打ち明け⟦0B⟧«0702»られないでいる«21»«23»«2810»«20»«0704»«22»臆病な自分が、ずっと⟦0B⟧«0704»腹立たしくて«23»…。«2810»«20»«0706»«22»でも«23»、«2808»«22»«21»今日という⟦0B⟧«0706»日を境に«23»«2810»«20»«0702»«22»«21»今までの自分を変えようと⟦0B⟧«0702»思うんです«23»。«2810»', '«20»«22»我«23»，«2808»«22»也许是因为体质«21»虚弱«23»，«2810»⟦0B⟧«22»朋友«21»也几乎没有«23»，«2810»«20»«0703»«22»爱好«21»也只有读书⟦0B⟧«0703»这一件事而已«23»。«2810»«20»«0702»«22»«21»于是«23»，«22»每次读到书«23»中⟦0B⟧«0702»«22»对里面的恋爱«21»心生向往«23»，«2810»«20»«0705»«22»忍不住嫉妒⟦0B⟧«0705»自己«21»的«23»，«2810»«20»«0702»«22»«21»无法坦白⟦0B⟧«0702»真实的心意«21»«23»«2810»«20»«0704»«22»这样胆小的我，一直⟦0B⟧«0704»让我很气恼«23»…«2810»«20»«0706»«22»可是«23»，«2808»«22»«21»我要以今天⟦0B⟧«0706»这一天为界«23»«2810»«20»«0702»«22»«21»我要改变迄今为止⟦0B⟧«0702»的自己«23»。«2810»'),
    (0X3E690A, 22, '«20»«0707»ど、どうして？«2810»«21»«2810»', '«20»«0707»为、为什么？«2810»«21»«2810»'),
    (0X3E6921, 418, '«20»«0705»«22»今まで«23»、«22»たくさんの⟦0B⟧«0705»本と出会っ«21»て«23»、«2810»«20»«0706»«22»私の思い出の中に⟦0B⟧«0706»残してきました«23»。«2810»«21»«2810»«20»«0702»«22»でも«23»、«22»«21»あなたと知り合った⟦0B⟧«0702»高校生活の全てを«21»«23»«2810»«20»«0705»«22»ただの思い出だけに⟦0B⟧«0705»したくないから«23»…、«2810»«20»«0703»«22»«21»小説のような空想だけの«21»⟦0B⟧«0703»事にしたくないから«23»、«2810»«20»«0705»«22»私の«23»«2808»«22»«21»一生分の勇気を⟦0B⟧«0705»出して言います«23»。«2810»«20»«0705»«0705»«22»好きです«23»«21»«2810»«20»«0703»«22»恋人じゃなく«23»、«22»«21»お友達でも⟦0B⟧«0703»いいんです«23»«21»。«2810»«20»«0703»«22»卒業してからも«23»、«22»«21»ずっと⟦0B⟧«0703»あなたに会えるなら«23»…。«2810»', '«20»«0705»«22»到现在«23»，«22»我已经遇见⟦0B⟧«0705»太多太多的书«21»«23»，«2810»«20»«0706»«22»把它们都留在了⟦0B⟧«0706»我的回忆里«23»。«2810»«21»«2810»«20»«0702»«22»可是«23»，«22»«21»与你相识的⟦0B⟧«0702»整个高中生活«21»«23»«2810»«20»«0705»«22»我不想让它⟦0B⟧«0705»只是回忆«23»…，«2810»«20»«0703»«22»«21»空想般的«21»⟦0B⟧«0703»小说情节«23»，«2810»«20»«0705»«22»我要鼓起«23»«2808»«22»«21»一生的勇气⟦0B⟧«0705»说出来«23»。«2810»«20»«0705»«0705»«22»我喜欢你«23»«21»«2810»«20»«0703»«22»不做恋人«23»，«22»«21»只做朋友⟦0B⟧«0703»也可以«23»«21»。«2810»«20»«0703»«22»毕业以后«23»，«22»«21»只要能⟦0B⟧«0703»一直见到你«23»…«2810»'),
    (0X3E6AC4, 41, '«20»«0703»実を言うと⟦0B⟧«0703»俺も如月«21»さんの事が…。«2810»', '«20»«0703»说实话⟦0B⟧«0703»我也，对如月«21»同学…。«2810»'),
    (0X3E6AEE, 76, '«20»«0705»«22»ほ«23»、«2808»«22»«21»本当ですか«23»…。«2810»«20»«0705»«22»本当に«23»、«22»こんな私で⟦0B⟧«0705»いいんですか«23»…？«2810»', '«20»«0705»«22»真«23»，«2808»«22»«21»真的吗«23»…。«2810»«20»«0705»«22»这样的我«23»，«22»真的⟦0B⟧«0705»可以吗«23»…？«2810»'),
    (0X3E6B3B, 43, '«20»«0704»もちろんだよ、⟦0B⟧«0704»好きだよ«21»、如月さん。«2810»', '«20»«0704»当然啦，⟦0B⟧«0704»我喜欢你«21»，如月同学。«2810»'),
    (0X3E6B67, 21, '«20»«0707»«22»嬉しいです«23»…。«2810»', '«20»«0707»«22»我好高兴«23»…。«2810»'),
    (0X3E6B7D, 34, '«20»«0707»あっ、危ない。«2810»⟦0B⟧«0707»如月さん。«2810»', '«20»«0707»啊，小心。«2810»⟦0B⟧«0707»如月同学。«2810»'),
    (0X3E6BA0, 165, '«20»«0709»うふ‥‥。«2810»«20»«0706»«22»身体が弱いのも⟦0B⟧«0706»いいものですね«23»。«2810»«20»«0701»«22»こうやって、あなたに抱き⟦0B⟧«0701»止めて貰えるんですから«23»…。«2810»«20»«0704»«22»しばらく«23»、«2802»«22»そのままで⟦0B⟧«0704»いてください«23»…。«2820»', '«20»«0709»唔呵呵…。«2810»«20»«0706»«22»身体弱⟦0B⟧«0706»也有好处呢«23»。«2810»«20»«0701»«22»这样能被你⟦0B⟧«0701»抱在怀里«23»…«2810»«20»«0704»«22»请让我«23»，«2802»«22»就这样⟦0B⟧«0704»再待一会儿«23»…«2820»'),
    (0X3E6C46, 22, '«20»«0706»«21»き、清川さん…。«2828»', '«20»«0706»«21»清、清川同学…。«2828»'),
    (0X3E6C5D, 22, '«20»«0707»«22»ごめんなさい«23»。«21»«2818»', '«20»«0707»«22»对不起«23»。«21»«2818»'),
    (0X3E6C74, 45, '«20»«0705»«22»«21»こんな所に«23»、«2804»⟦0B⟧«0705»«22»呼び出したりして«23»。«2820»', '«20»«0705»«22»«21»把你约到«23»，«2804»⟦0B⟧«0705»«22»这种地方«23»。«2820»'),
    (0X3E6CA2, 35, '«20»«0707»別に、いいよ。«21»⟦0B⟧«0707»どうしたの？«2818»', '«20»«0707»没什么啦。«21»⟦0B⟧«0707»怎么了？«2818»'),
    (0X3E6CC6, 123, '«20»«0705»«22»今日で卒業だから«23»、«21»«2820»«20»«0701»«22»あなたに«23»、«2804»«22»«21»どうしても話して⟦0B⟧«0701»おきたいことがあって«23»«21»…。«2820»«20»«0702»«22»聞くだけでもいいから«23»…。«2820»', '«20»«0705»«22»今天是毕业典礼«23»，«21»«2820»«20»«0701»«22»我有«23»，«2804»«22»«21»一定要告诉⟦0B⟧«0701»你的话«23»«21»…。«2820»«20»«0702»«22»你只要听着就好«23»…。«2820»'),
    (0X3E6D42, 29, '«20»«0705»«0705»うん«21»…。⟦0B⟧«0705»«0705»聞くよ。«2818»', '«20»«0705»«0705»嗯«21»…。⟦0B⟧«0705»«0705»我听。«2818»'),
    (0X3E6D60, 266, '«20»«0703»«22»いままで水泳ばかりで、«21»«2820»«20»«0704»«22»愛だの恋だの«23»«2802»«22»言ってる⟦0B⟧«0704»«22»暇もなかったし«23»、«21»«2820»«20»«0702»«22»貧弱な«23»、«2802»«22»«21»男の子ばっかりで«23»、«2818»«20»«0703»«22»私の興味を引く«21»男の子も⟦0B⟧«0703»いなかったから«23»、«2820»«20»«0706»«22»今まで気にもして⟦0B⟧«0706»なかっ«21»たけど«23»…。«2820»«20»«0703»«22»いつごろからかな«23»、«2804»⟦0B⟧«0703»«22»«21»もう覚えてないけど«23»…。«2810»', '«20»«0703»«22»一直以来我只顾着游泳，«21»«2820»«20»«0704»«22»什么情啊爱啊«23»«2802»«22»的⟦0B⟧«0704»«22»根本没空去管«23»，«21»«2820»«20»«0702»«22»队里尽是«23»，«2802»«22»«21»些文弱男生«23»，«2818»«20»«0703»«22»没有能让我«21»感兴趣的⟦0B⟧«0703»男孩子«23»，«2820»«20»«0706»«22»所以以前我从⟦0B⟧«0706»未«21»在意过«23»…«2820»«20»«0703»«22»是从什么时候开始«23»，«2804»⟦0B⟧«0703»«22»«21»已经记不清了«23»…«2810»'),
    (0X3E6E6E, 394, '«20»«0706»«22»あなたの存在が«23»、⟦0B⟧«0706»«21»«22»気になってきて«23»、«2818»«20»«0701»«22»練習にも«21»身が入らなくて«23»…。«21»«2818»«20»«0705»«22»最近では«23»、«2802»«22»夜も⟦0B⟧«0705»眠れないくらいに«23»、«2818»«20»«0704»«22»«21»胸がどきどきして«23»…。«2818»«20»«0704»«22»私、«21»男っぽいって⟦0B⟧«0704»言われ続けてきても«23»、«2818»«20»«0702»«22»«21»気にもならなかったけど«23»、«2818»«20»«0704»«22»あなたにだけは、«21»⟦0B⟧«0704»そう思われたくない。«23»«2820»«20»«0702»«22»だから«23»、«2802»«22»«21»あなたの前では«23»、«2820»«20»«0702»«22»男言葉を話さないように⟦0B⟧«0702»«21»注意してきたつもりだし«23»、«2820»«20»«0707»«22»行動だって«23»…。«2818»', '«20»«0706»«22»你的存在«23»，⟦0B⟧«0706»«21»«22»让我越来越«23»，«2818»«20»«0701»«22»连训练都«21»静不下心«23»…«21»«2818»«20»«0705»«22»最近«23»，«2802»«22»夜里⟦0B⟧«0705»心跳得«23»，«2818»«20»«0704»«22»«21»睡不着«23»…«2818»«20»«0704»«22»我«21»一直被人说⟦0B⟧«0704»像个男孩子«23»，«2818»«20»«0702»«22»«21»我都不在意«23»，«2818»«20»«0704»«22»只有你，«21»⟦0B⟧«0704»我不想让你这样看我。«23»«2820»«20»«0702»«22»所以«23»，«2802»«22»«21»在你面前«23»，«2820»«20»«0702»«22»我一直注意不⟦0B⟧«0702»«21»说男孩子的话«23»，«2820»«20»«0707»«22»连举动也«23»…«2818»'),
    (0X3E6FF9, 44, '«20»«0705»«22»これでも駄目なら、⟦0B⟧«0705»水泳も捨てるわ«23»。«2820»', '«20»«0705»«22»这样都不行的话，⟦0B⟧«0705»我连游泳也不要了«23»。«2820»'),
    (0X3E7026, 69, '«20»«0707»«22»髪の毛だって«23»、«2818»«20»«0703»«22»あなたが望むなら⟦0B⟧«0703»いくらだって伸ばすわ«23»。«2820»', '«20»«0707»«22»头发也是«23»，«2818»«20»«0703»«22»只要你愿意⟦0B⟧«0703»多长我都留«23»。«2820»'),
    (0X3E706C, 42, '«20»«0706»«22»あなたの望む女に⟦0B⟧«0706»変身して見せる«23»。«2820»', '«20»«0706»«22»我会变成⟦0B⟧«0706»你想要的样子«23»。«2820»'),
    (0X3E7097, 180, '«20»«0704»«22»ご、«21»ごめんなさい«23»…。«2818»«20»«0701»«22»勝手なこと言っちゃって«23»…。«2818»«20»«0701»«22»でも、«21»断られたっていいの«23»。«2818»«20»«0704»«22»ただ、«21»こんな気持ちで⟦0B⟧«0704»卒業したくないから«23»。«2820»«20»«22»わたしの気持ちだけ、«21»聞いて«23»。«2818»', '«20»«0704»«22»对、«21»对不起«23»…«2818»«20»«0701»«22»说这种任性话«23»…«2818»«20»«0701»«22»可是，«21»被拒绝也没关系«23»。«2818»«20»«0704»«22»只是，«21»怀着这样的感情⟦0B⟧«0704»我不想就这样毕业«23»。«2820»«20»«22»你只要听听«21»我的心意«23»。«2818»'),
    (0X3E714C, 17, '«20»«0708»う、うん…。«2818»', '«20»«0708»嗯、嗯…。«2818»'),
    (0X3E715E, 45, '«20»«0709»«22»好きよ«23»…。«21»«2820»«20»«0704»«22»夜も眠れないほど«23»…。«2820»', '«20»«0709»«22»我喜欢你«23»…。«21»«2820»«20»«0704»«22»喜欢得睡不着«23»…。«2820»'),
    (0X3E719C, 135, '«20»«0707»«22»そ、そうよね«23»。«21»«2818»«20»«0703»«22»やっぱり、私なんかじゃ⟦0B⟧«0703»駄目ね«23»。«21»«2820»«20»«22»でも、言ってせいせいしたわ«23»。«21»«2818»«20»«0701»«22»ありがとう«23»、«2806»«22»«21»聞いてくれて«23»。«2820»', '«20»«0707»«22»是、是啊«23»。«21»«2818»«20»«0703»«22»果然像我这样的人⟦0B⟧«0703»是不行的吧«23»。«21»«2820»«20»«22»不过说出来痛快多了«23»。«21»«2818»«20»«0701»«22»谢谢你«23»，«2806»«22»«21»愿意听我说«23»。«2820»'),
    (0X3E7224, 31, '«20»«0707»き、清川さん。⟦0B⟧«0707»待って«21»。«2818»', '«20»«0707»清、清川同学。⟦0B⟧«0707»等等«21»。«2818»'),
    (0X3E7244, 136, '«20»«0706»«22»引き止めないで«23»。«21»«2818»«20»«0703»«22»引き止められたら、⟦0B⟧«0703»期待しちゃうじゃない«23»。«2820»«20»«0706»«22»慰めの言葉なんて⟦0B⟧«0706»かけられたら«23»、«21»«2818»«20»«0706»«22»惨めじゃない«23»。«2818»', '«20»«0706»«22»别拦我«23»。«21»«2818»«20»«0703»«22»要被你拦住的话，⟦0B⟧«0703»人家还会抱有希望的«23»。«2820»«20»«0706»«22»要是你说几句⟦0B⟧«0706»安慰我的话«23»，«21»«2818»«20»«0706»«22»那才难看呢«23»。«2818»'),
    (0X3E72CD, 33, '«20»«0707»«21»清川さん。⟦0B⟧«0707»俺も好きだよ。«2818»', '«20»«0707»«21»清川同学。⟦0B⟧«0707»我也喜欢你。«2818»'),
    (0X3E72EF, 26, '«20»«0705»«22»えっ、今なんて«23»…？«21»«2818»', '«20»«0705»«22»诶，你刚才说«23»…？«21»«2818»'),
    (0X3E730A, 55, '«20»«0702»俺も、清川さんの事が、⟦0B⟧«0702»好きだって言ったんだよ«23»。«2818»', '«20»«0702»我说，我也，⟦0B⟧«0702»喜欢清川同学«23»。«2818»'),
    (0X3E7342, 69, '«20»«0707»«22»ホ«23»、«2802»«22»ホントに？«23»«2818»«20»«0704»«22»こんな水泳しか⟦0B⟧«0704»とりえの無い私で«23»…。«2820»', '«20»«0707»«22»真«23»，«2802»«22»真的吗？«23»«2818»«20»«0704»«22»我这个人除了⟦0B⟧«0704»游泳别无长处«23»…。«2820»'),
    (0X3E7388, 20, '«20»«0707»もちろんだよ。«21»«2810»', '«20»«0707»当然是啦。«21»«2810»'),
    (0X3E739D, 17, '«20»«0708»うふ…あっ…«2810»', '«20»«0708»唔…啊…«2810»'),
    (0X3E73AF, 17, '«20»«0709»«22»だ、駄目«23»。«2810»', '«20»«0709»«22»不、不行«23»。«2810»'),
    (0X3E73C1, 31, '«20»«0702»«22»もう、涙が止まらない«23»…。«2818»', '«20»«0702»«22»眼泪怎么都止不住«23»…。«2818»'),
    (0X3E73E1, 54, '«20»«0705»«0705»«22»お願い«23»。«2810»«20»«0701»«22»あなたの胸の中で«23»«2802»«22»泣かせて«23»。«2818»', '«20»«0705»«0705»«22»拜托«23»。«2810»«20»«0701»«22»让我在你的«23»«2802»«22»怀里哭一场«23»。«2818»'),
    (0X3E7418, 15, '«20»«0705»«0705»いいよ。«2810»', '«20»«0705»«0705»好呀。«2810»'),
    (0X3E7428, 41, '«20»«0705»«0705»«22»嬉しい«23»。«2818»«20»«0707»«22»最高に«23»«2802»«22»幸せ…。«2828»', '«20»«0705»«0705»«22»好开心«23»。«2818»«20»«0707»«22»最«23»«2802»«22»幸福了…。«2828»'),
    (0X3E7452, 24, '«20»«0706»«21»«2810»こ、古式さん…。«2810»', '«20»«0706»«21»«2810»古、古式同学…。«2810»'),
    (0X3E746B, 163, '«20»«0703»…«22»失礼な事と«21»存じました⟦0B⟧«0703»けれども«23»、«2810»«20»«0700»«22»どうしても«23»、«2810»«22»お話«21»致したいこと⟦0B⟧«0700»がございまして«23»、«2810»«20»«0702»«22»お呼び出しいたしました«23»。«2815»«20»«0703»…«22»«21»申し訳ございません«23»。«2815»', '«20»«0703»…«22»我知道这事«21»很是失礼⟦0B⟧«0703»可是«23»，«2810»«20»«0700»«22»我有一件«23»，«2810»«22»必须向您«21»说的话⟦0B⟧«0700»，«23»，«2810»«20»«0702»«22»才斗胆请您前来«23»。«2815»«20»«0703»…«22»«21»万望恕罪«23»。«2815»'),
    (0X3E750F, 34, '«20»«0700»そんなに、«21»改まらなくても…。«2810»', '«20»«0700»不用那么，«21»郑重其事的…。«2810»'),
    (0X3E7532, 96, '«20»«0701»«22»いいえ«21»«23»。«2815» ⟦0B⟧«0701»«22»そういう訳には参りません«23»。«2815»«20»«0705»«22»私«21»の一生をかけた⟦0B⟧«0705»大事な用ですから«23»。«2815»', '«20»«0701»«22»不«21»«23»。«2815» ⟦0B⟧«0701»«22»这可是马虎不得的«23»。«2815»«20»«0705»«22»这是我«21»一辈子⟦0B⟧«0705»最重要的事«23»。«2815»'),
    (0X3E7593, 19, '«20»«0707»大事な用って？«2810»', '«20»«0707»最重要的事？«2810»'),
    (0X3E75A7, 158, '«20»«0700»«22»«21»いつも«23»、«2810»«22»私は何も考えないで⟦0B⟧«0700»いるのが好きなのですけれども«23»、«2810»«20»«0701»«22»最近«21»では«23»、«2810»«22»その時間よりも«23»、«2810»«20»«0701»«22»色々と考えてしまう事の方が⟦0B⟧«0701»«21»多いのです«23»。«2815»', '«20»«0700»«22»«21»一直以来«23»，«2810»«22»我都喜欢什么也不⟦0B⟧«0700»想地发呆«23»，«2810»«20»«0701»«22»可最«21»近«23»，«2810»«22»比起那段时光«23»，«2810»«20»«0701»«22»胡思乱想的时候⟦0B⟧«0701»«21»反而更多«23»。«2815»'),
    (0X3E7646, 17, '«20»«0708»考え事って？«2810»', '«20»«0708»想什么事？«2810»'),
    (0X3E7658, 518, '«20»«0700»«22»«21»お恥ずかしいお話ですけれども«23»、«2810»«20»«0704»«22»あなた«21»の姿が«23»、«2810»⟦0B⟧«0704»«22»頭から離れなくて«23»…。«2815»«20»«0702»…«22»家にいても«23»、«2810»⟦0B⟧«0702»«22»あなた«21»の事ばかり考えて«23»、«2810»«20»«0705»«22»時間が経つのも⟦0B⟧«0705»忘れてしまいます«23»«21»。«2815»«20»«0701»«22»いつもよりも«23»、«2810»⟦0B⟧«0701»«22»ボーッとして«21»いましたので«23»、«2810»«20»«0704»«22»お母様に«23»、«2810»⟦0B⟧«0704»«22»理由を聞かれました«23»。«2815»«20»«0701»…«22»«21»その事を正直に話しました⟦0B⟧«0701»ところ«23»、«2810»«20»«0701»«22»それならば«23»、«2810»⟦0B⟧«0701»«22»«21»卒業式の日にこの樹の下で«23»、«2810»«20»«0701»«22»あなたの本心を«23»、«2810»«22»その殿方に⟦0B⟧«0701»話しな«21»さいと申されました«23»。«2815»«20»«0700»«22»ですから«23»、«2810»«22»私の本心を笑わない⟦0B⟧«0700»で聞いていただきたいのです«23»。«21»«2820»', '«20»«0700»«22»«21»说来实在惭愧«23»，«2810»«20»«0704»«22»你的身影«21»却«23»，«2810»⟦0B⟧«0704»«22»从我脑海中挥之不去«23»…«2815»«20»«0702»…«22»即使在家«23»，«2810»⟦0B⟧«0702»«22»也«21»尽想着你的事«23»，«2810»«20»«0705»«22»连时间流逝都⟦0B⟧«0705»浑然不觉«23»«21»。«2815»«20»«0701»«22»因为比平时«23»，«2810»⟦0B⟧«0701»«22»更要发呆«21»一些«23»，«2810»«20»«0704»«22»母亲«23»，«2810»⟦0B⟧«0704»«22»便问我缘由«23»。«2815»«20»«0701»…«22»«21»我把这事如实⟦0B⟧«0701»说了«23»，«2810»«20»«0701»«22»母亲便说«23»«2810»⟦0B⟧«0701»«22»«21»毕业典礼那天，请到这棵树下«23»，«2810»«20»«0701»«22»把你的真心«23»，«2810»«22»对那位男生⟦0B⟧«0701»说«21»出来吧«23»。«2815»«20»«0700»«22»所以«23»，«2810»«22»请你不要笑话我，⟦0B⟧«0700»听一听我的心意«23»。«21»«2820»'),
    (0X3E785F, 15, '«20»«0709»う、うん。«2810»', '«20»«0709»嗯、嗯。«2810»'),
    (0X3E786F, 254, '«20»«0702»«22»いつも«23»、«2810»«22»あなた«21»の事だけを⟦0B⟧«0702»考えてしまいます«23»。«2810»«20»«0700»«22»私が«23»、«2810»«22»落ち着いていられる場所⟦0B⟧«0700»は«23»、«2810»«22»あなた«21»のそばだけです«23»。«2820»«20»«0704»«22»…私でよろしければ«23»、«2810»«22»⟦0B⟧«0704»これからずっと«23»«21»…、«2810»«20»«0705»«22»卒業してからも«23»«21»…、«2810»«20»«0700»«22»お付き合いしていただきたいの⟦0B⟧«0700»です«23»«21»。«2815»', '«20»«0702»«22»我«23»，«2810»«22»止不住地«21»只想着你⟦0B⟧«0702»一个人«23»。«2810»«20»«0700»«22»我«23»，«2810»«22»能安心下来的地方⟦0B⟧«0700»只有«23»，«2810»«22»你的«21»身边而已«23»。«2820»«20»«0704»«22»…如蒙你不嫌弃«23»，«2810»«22»⟦0B⟧«0704»从今往后«23»«21»…，«2810»«20»«0705»«22»毕业以后«23»«21»…，«2810»«20»«0700»«22»也请让我与你⟦0B⟧«0700»交往«23»«21»。«2815»'),
    (0X3E796E, 45, '«20»«0703»実を言うとね、⟦0B⟧«0703»俺も«21»古式さんの事が…。«2810»', '«20»«0703»说实话，⟦0B⟧«0703»我也，对古式«21»同学…。«2810»'),
    (0X3E799C, 133, '«20»«0708»«22»本当ですか«23»？«2815»«20»«0709»«22»良«21»かった«23»。«2810»«20»«0700»«22»お母様の言うとおりにして«23»«21»…。«2815»«20»«0700»«22»それでは«23»«21»、«2810»«22»明日お父様に会って⟦0B⟧«0700»いただけますか«23»«21»？«2815»', '«20»«0708»«22»真的吗«23»？«2815»«20»«0709»«22»太好«21»了«23»。«2810»«20»«0700»«22»照母亲说的去做«23»«21»…。«2815»«20»«0700»«22»那么«23»«21»，«2810»«22»明天您能来我家⟦0B⟧«0700»见一见父亲吗«23»«21»？«2815»'),
    (0X3E7A22, 33, '«20»«0700»えっ、古式さんのお父さんに？«2810»', '«20»«0700»诶，去见古式同学的父亲？«2810»'),
    (0X3E7A44, 127, '«20»«0709» «22»はい«23»。 «2815»«20»«0701»«22»お«21»父様に«23»、«2810»«22»私とお付き合いを⟦0B⟧«0701»する殿方は«23»、«2810»«20»«0702»«22»家の方に連れてくるように⟦0B⟧«0702»言われております«21»ので«23»。«2815»', '«20»«0709» «22»是«23»。 «2815»«20»«0701»«22»父«21»亲大人«23»，«2810»«22»嘱咐过我，与我⟦0B⟧«0701»交往的人«23»，«2810»«20»«0702»«22»一定要带到家里⟦0B⟧«0702»来见他«21»«23»。«2815»'),
    (0X3E7AC4, 39, '«20»«0709»そ、そう。«2810»⟦0B⟧«0705»…じゃあ、«21»行くよ。«2810»', '«20»«0709»这、这样。«2810»⟦0B⟧«0705»…那，«21»我去。«2810»'),
    (0X3E7AEC, 84, '«20»«0708»«22»そうですか«23»。«2815»«20»«0700»«22»きっと«21»«22»、«2810»«22»お父様にも気に入って⟦0B⟧«0700»いただけると思いますよ«23»。', '«20»«0708»«22»是吗«23»。«2815»«20»«0700»«22»父亲«21»«22»，«2810»«22»也一定会⟦0B⟧«0700»喜欢您的«23»。'),
    (0X3E7B65, 26, '«20»«0705»«21»«2810»み、美樹原さん…。«2810»', '«20»«0705»«21»«2810»美、美树原同学…。«2810»'),
    (0X3E7B80, 63, '«20»«0709»«22»あの«23»…。«21»«2812»«20»«0704»«22»こんな所に«23»、«2808»«22»⟦0B⟧«0704»呼び出したりして«23»…。«21»«2812»', '«20»«0709»«22»那个«23»…«21»«2812»«20»«0704»«22»把你约到«23»，«2808»«22»⟦0B⟧«0704»这种地方«23»…«21»«2812»'),
    (0X3E7BC0, 36, '«20»«0707»別にいいよ。«2805»⟦0B⟧«0707»ところで、何？«2810»', '«20»«0707»没关系啦。«2805»⟦0B⟧«0707»对了，什么事？«2810»'),
    (0X3E7BF9, 17, '«20»«0708»どうしたの？«2810»', '«20»«0708»你怎么了？«2810»'),
    (0X3E7C0B, 63, '«20»«0701»«22»だ«23»、«2804»«22»駄目«23»…。«2812» ⟦0B⟧«0701»«21»«22»やっぱり«23»、«2808»«22»恥ずかしくて«23»…。«2810»', '«20»«0701»«22»不«23»，«2804»«22»不行«23»…。«2812» ⟦0B⟧«0701»«21»«22»还是«23»，«2808»«22»太害羞了«23»…。«2810»'),
    (0X3E7C6E, 282, '«20»«0708»«22»は«23»、«2804»«22»はい«23»…。«2812»«20»«0700»«22»で«23»、«2804»«22»«21»でも«23»、«2804»«22»今日«23»、«2804»«22»勇気を出さな⟦0B⟧«0700»いと«23»、«21»«2808»«22»一生後悔するから«23»…。«2812»«20»«0704»«22»い«23»、«2804»«22»«21»言いたいことは«23»、«2808»«22»⟦0B⟧«0704»たくさんあるけど«23»…。«2812»«20»«0701»«22»今言うと«23»、«21»«2808»«22»一番大事なことが⟦0B⟧«0701»言えない気がします«23»…。«2812»«20»«0700»«22»だから…«23»、«2808»«22»⟦0B⟧«0700»«21»一番大事なことだけ言います«23»…。«2820»', '«20»«0708»«22»是«23»，«2804»«22»嗯«23»…。«2812»«20»«0700»«22»那«23»，«2804»«22»«21»可是«23»，«2804»«22»今天«23»，«2804»«22»不鼓起勇气⟦0B⟧«0700»的话«23»，«21»«2808»«22»一辈子都会后悔的«23»…。«2812»«20»«0704»«22»想«23»，«2804»«22»«21»想说的话«23»，«2808»«22»⟦0B⟧«0704»有很多很多«23»…。«2812»«20»«0701»«22»可现在就说«23»，«21»«2808»«22»最重要的话⟦0B⟧«0701»就没机会说了«23»…。«2812»«20»«0700»«22»所以…«23»，«2808»«22»⟦0B⟧«0700»«21»我只说最重要的那句«23»…。«2820»'),
    (0X3E7D89, 95, '«20»«0703»«22»«21»あ«23»、«2804»«22»«21»あなたが«23»…。«2810» ⟦0B⟧«0703»«22»あなたが«23»、«2804»«22»好きです«23»…。«21»«2812»«20»«0705»«22»は«23»、«2804»«22»«21»恥ずかしい«23»…。«2812»', '«20»«0703»«22»«21»你«23»，«2804»«22»«21»我喜欢的是你«23»…。«2810» ⟦0B⟧«0703»«22»你«23»，«2804»«22»我最喜欢了«23»…。«21»«2812»«20»«0705»«22»啊«23»，«2804»«22»«21»好害羞«23»…。«2812»'),
    (0X3E7DE9, 34, '«20»«0701»あっ、待って。«2805»美樹«21»原さん。«2810»', '«20»«0701»啊，等等。«2805»美树«21»原同学。«2810»'),
    (0X3E7E0C, 43, '«20»«0704»«22»駄目«23»。«2812» ⟦0B⟧«0704»«21»«22»ここにいられない«23»…。«2812»', '«20»«0704»«22»不行«23»。«2812» ⟦0B⟧«0704»«21»«22»我待不下去了«23»…。«2812»'),
    (0X3E7E38, 40, '«20»«0703»俺も、美樹原さんの事、⟦0B⟧«0703»好きだよ。«2810»', '«20»«0703»我也，喜欢⟦0B⟧«0703»美树原同学。«2810»'),
    (0X3E7E61, 98, '«20»«0705»«22»えっ«23»…。«21»«2812» ⟦0B⟧«0705»«22»ほ«23»、«2804»«22»本当ですか«23»…？«2815»«20»«0704»…«22»«21»この樹の下で«23»、«2808»⟦0B⟧«0704»«22»告白してよかった«23»…。«2810»', '«20»«0705»«22»诶«23»…。«21»«2812» ⟦0B⟧«0705»«22»真«23»，«2804»«22»真的吗«23»…？«2815»«20»«0704»…«22»«21»能在这棵树下«23»，«2808»⟦0B⟧«0704»«22»告白真好«23»…。«2810»'),
    (0X3E7EC4, 43, '«20»«0704»美樹原さんも、⟦0B⟧«0704»伝«21»説知ってたんだ…。«2810»', '«20»«0704»原来美树原同学⟦0B⟧«0704»也知道传«21»说的呀…。«2810»'),
    (0X3E7EF0, 159, '«20»«0700»«22»はい«23»…。«2810»⟦0B⟧«0700»«22»«21»でも«23»、«2804»«22»嘘でも良かったんです«23»。«2810»«20»«0700»«22»この樹の伝説に頼れば«23»、«21»«2808»«22»きっと«23»、«2808»⟦0B⟧«0700»«22»告白する勇気が出ると思って«23»…。«2810»«20»«0705»«22»本当に良かった«23»…。«2810»', '«20»«0700»«22»是«23»…«2810»⟦0B⟧«0700»«22»«21»可是«23»，«2804»«22»哪怕传说是假的也没关系«23»。«2810»«20»«0700»«22»只要向这棵树的传说求助«23»，«21»«2808»«22»一定«23»，«2808»⟦0B⟧«0700»«22»会有告白勇气的«23»…«2810»«20»«0705»«22»真的太好了«23»…«2810»'),
    (0X3E7F90, 45, '«20»«0704»俺も美樹原さんに⟦0B⟧«0704»告白«21»されて最高だよ。«2810»', '«20»«0704»被美树原同学⟦0B⟧«0704»告白«21»，我也是最开心的。«2810»'),
    (0X3E7FBE, 56, '«20»«0702»«22»«21»これでもう«23»«21»、«2808»«22»⟦0B⟧«0702»二人の愛は永遠ですね«23»…。«2810»«21»«27»«2815»', '«20»«0702»«22»«21»从今往后«23»«21»，«2808»«22»⟦0B⟧«0702»两人的爱将永远在一起«23»…。«2810»«21»«27»«2815»'),
    (0X034F85, 4, '如月', '如月'),
    (0X034F8A, 4, '紐緒', '纽绪'),
    (0X034F8F, 4, '片桐', '片桐'),
    (0X034F94, 4, '虹野', '虹野'),
    (0X034F99, 4, '古式', '古式'),
    (0X034F9E, 4, '清川', '清川'),
    (0X034FA3, 2, '鏡', '镜'),
    (0X034FA6, 6, '朝日奈', '朝日奈'),
    (0X034FAD, 6, '美樹原', '美树原'),
    (0X034FB4, 6, '早乙女', '早乙女'),
    (0X034FBB, 6, '伊集院', '伊集院'),
    (0X034FC2, 4, '好雄', '好雄'),
    (0X034FC8, 12, '攻撃防御奥義', '攻击防御奥义'),
    (0X0353DC, 8, '紐緒ロボ', '纽绪铁人'),
    (0X035463, 12, 'クロコダイル', '鳄鱼'),
    (0X035470, 26, 'クロコダイルが襲ってきた！', '鳄鱼袭击过来了！'),
    (0X03548B, 10, '不良パンダ', '不良熊猫'),
    (0X035496, 26, '凶悪なパンダが襲ってきた！', '凶恶的熊猫袭击过来了！'),
    (0X0354B1, 8, '不良たち', '不良们'),
    (0X0356D8, 8, '元・番長', '前・番长'),
    (0X0356E1, 6, '番長 ', '番长 '),
    (0X035A2B, 28, 'あばよ、彼女と仲良くなっ！«2812»', '永别了，和女朋友和好如初！«2812»'),
    (0X035BD8, 79, '（天使の声と共に«2812»«20»〔姓〕は、蘇った！«2812»«20»なんと、〔姓〕は、«2812»«20»最大ＨＰが２０００増えた！«2812»', '（伴随着天使的声音«2812»«20»〔姓〕，复活了！«2812»«20»没想到，〔姓〕竟«2812»«20»最大HP增加了２０００！«2812»'),
    (0X035C56, 18, '     ５％回復', '     ５%回复'),
    (0X035C69, 11, '〔姓〕「だめだ！', '〔姓〕「不行啊！'),
    (0X035C75, 19, '〔姓〕「このままでは…。', '〔姓〕「再这样下去…。'),
    (0X035C89, 11, '〔姓〕「くそう！', '〔姓〕「可恶！'),
    (0X035C95, 19, '〔姓〕「このままでは…。', '〔姓〕「再这样下去…。'),
    (0X035CA9, 16, '好雄「いくぞっ！', '好雄「看我的！'),
    (0X035CBA, 18, '好雄「良雄闘気拳！', '好雄「良雄斗气拳！'),
    (0X035CCD, 18, '好雄「良雄稲妻脚！', '好雄「良雄闪电脚！'),
    (0X035CE0, 24, '  好雄は逃げようとした', '  好雄想要逃跑'),
    (0X035CF9, 28, '好雄「だめだ！歯がたたねえ！', '好雄「不行啊！根本挡不住！'),
    (0X035D16, 28, '好雄「だめだ！逃げられねえ！', '好雄「不行啊！逃不掉了！'),
    (0X035D33, 28, '伊集院「頼りにならん男だ…。', '伊集院「真是靠不住的家伙…。'),
    (0X035D50, 24, ' 私設軍隊 軍事衛星攻撃', ' 私设军队 军事卫星打击'),
    (0X035D69, 26, '伊集院「ま、こんなものさ。', '伊集院「嘛，就这样吧。'),
    (0X035D84, 20, '    竹槍アタック', '    竹枪突击'),
    (0X035D99, 18, '    熊猫光波斬', '    熊猫光波斩'),
    (0X035DAC, 22, '？？「退散！大熊猫！！', '？？「退散！大熊猫！！'),
    (0X035DC3, 20, '   鶴亀仙人登場！', '   鹤龟仙人登场！'),
    (0X035DD8, 20, '   中国四千年光線', '   中国四千年光线'),
    (0X035DED, 22, '仙人「無事無事。再見！', '仙人「无事无事。再见！'),
    (0X035E04, 20, '   テイルアタック', '   尾巴突袭'),
    (0X035E19, 20, '  ワイルドファング', '  野性獠牙'),
    (0X035E2E, 15, '〔姓〕「・・・おや？', '〔姓〕「…咦？'),
    (0X035E3E, 23, '〔姓〕「何かがやってくる！？', '〔姓〕「有什么东西过来了！？'),
    (0X035E56, 24, ' 正義のカンガルー参上！', ' 正义袋鼠参上！'),
    (0X035E6F, 20, '    南十字星神拳', '    南十字星神拳'),
    (0X035E84, 14, '戦闘に勝った！', '战斗胜利！'),
    (0X035E93, 28, 'ありがとう伊集院家私設軍隊！', '谢谢你们！伊集院家私设军队！'),
    (0X035EB0, 24, '経験値 ：   ０ＥＸＰ', '经验值 ：   ０ＥＸＰ'),
    (0X035EC9, 26, 'お金  ：   ０ゴールド', '金钱  ：   ０金币'),
    (0X035EE4, 22, 'おたから：伊集院バッジ', '宝物：伊集院徽章'),
    (0X035EFB, 28, 'おたから：伊集院キーホルダー', '宝物：伊集院挂件'),
    (0X035F18, 14, '戦闘に勝った！', '战斗胜利！'),
    (0X035F27, 28, 'ありがとう正義のカンガルー！', '谢谢你！正义的袋鼠！'),
    (0X035F44, 24, '経験値 ： ８２０ＥＸＰ', '经验值 ： ８２０ＥＸＰ'),
    (0X035F5D, 26, 'お金  ： ５７３ゴールド', '金钱  ： ５７３金币'),
    (0X035F78, 22, 'おたから：ワニ皮バック', '宝物：鳄鱼皮包'),
    (0X035F8F, 22, 'おたから：ワニ皮ベルト', '宝物：鳄鱼皮带'),
    (0X035FA6, 14, '戦闘に勝った！', '战斗胜利！'),
    (0X035FB5, 20, 'ありがとう謎の仙人！', '谢谢你！神秘的仙人！'),
    (0X035FCA, 24, '経験値 ：４０００ＥＸＰ', '经验值 ：４０００ＥＸＰ'),
    (0X035FE3, 26, 'お金  ：４０００ゴールド', '金钱  ：４０００金币'),
    (0X035FFE, 16, 'おたから：笹の葉', '宝物：竹叶'),
    (0X03600F, 20, 'おたから：竹ほうき ', '宝物：竹扫帚 '),
    (0X0D78C8, 12, '«20»«0708»«22»あ«23»、«2810»«21»', '«20»«0708»«22»啊«23»，«2810»«21»'),
    (0X0D78D5, 117, '«27»«22»あれ«23»…？«2814»«20»«0705»«22»嬉し«21»いはずなのに«23»«2810»⟦0B⟧«0705»«22»涙が出てきちゃった«23»。«2810»«21»«27»«20»«0707»«22»本当に«23»、«280C»«22»本当に«23»、«2806»⟦0B⟧«0707»«22»信じて«21»いいのね«23»。«2820»', '«27»«22»那«23»…？«2814»«20»«0705»«22»高兴«21»明明应该«23»«2810»⟦0B⟧«0705»«22»眼泪却掉下来了«23»。«2810»«21»«27»«20»«0707»«22»真的«23»，«280C»«22»真的«23»，«2806»⟦0B⟧«0707»«22»可以相信«21»了是吧«23»。«2820»'),
    (0X1B6102, 9, '«20»«070C»え？«2810»', '«20»«070C»诶？«2810»'),
    (0X3E7B41, 35, '«2815»«20»«0700»（いきなり、お父さんか…。）«2825»', '«2815»«20»«0700»（突然冒出来的，爸爸…。）«2825»'),
    (0X3E7C4B, 34, '«0700»«20»そんなに«21»恥ずかしいことなの？«2810»', '«0700»«20»那么«21»让人难为情吗？«2810»'),
)
PRESET_NAMES = (0x1F890, 0x1F970)     # the pool itself: 32 x 7-byte preset names
KANA_REMAP_LIST = 0x54E4             # $80:D4E4, zero-terminated source indices
KANA_REMAP_BASE = 0x0D5A             # $80:D4DE: new index = $0D5A + position
# Endgame #43: the whole-band backfill reads each kana cell through this table --
# the same homophone grid the name-entry keyboard was re-encoded to -- and rewrites
# every record the Chinese text does not own in WenQuanYi, so no font cell left on
# the card can draw a Japanese glyph even by a stray reference.
KANA_HOMO = {
 'あ':'啊','い':'衣','う':'呜','え':'哎','お':'哦','か':'卡','き':'基','く':'苦',
 'け':'刻','こ':'科','さ':'撒','し':'诗','す':'斯','せ':'色','そ':'索','た':'他',
 'ち':'吃','つ':'呲','て':'特','と':'托','な':'拿','に':'呢','ぬ':'努','ね':'捏',
 'の':'诺','は':'哈','ひ':'稀','ふ':'福','へ':'黑','ほ':'伙','ま':'妈','み':'米',
 'む':'木','め':'么','も':'摸','や':'呀','ゆ':'鱼','よ':'哟','ら':'拉','り':'日',
 'る':'噜','れ':'勒','ろ':'洛','わ':'娃','を':'我','ん':'恩','が':'嘎','ぎ':'吉',
 'ぐ':'姑','げ':'格','ご':'歌','ざ':'杂','じ':'自','ず':'租','ぜ':'则','ぞ':'作',
 'だ':'大','ぢ':'地','づ':'图','で':'得','ど':'督','ば':'吧','び':'笔','ぶ':'不',
 'べ':'贝','ぼ':'波','ぱ':'怕','ぴ':'屁','ぷ':'噗','ぺ':'呸','ぽ':'坡','ゃ':'压',
 'ゅ':'淤','ょ':'跃','っ':'呃','ぁ':'阿','ぃ':'咿','ぅ':'屋','ぇ':'耶','ぉ':'沃',
 'ゎ':'娃','ゐ':'维','ゑ':'为','ア':'阿','イ':'伊','ウ':'乌','エ':'诶','オ':'奥',
 'カ':'咖','キ':'奇','ク':'库','ケ':'课','コ':'颗','サ':'萨','シ':'西','ス':'苏',
 'セ':'涩','ソ':'所','タ':'塔','チ':'池','ツ':'此','テ':'贴','ト':'吐','ナ':'那',
 'ニ':'泥','ヌ':'怒','ネ':'内','ノ':'乃','ハ':'虾','ヒ':'披','フ':'夫','ヘ':'赫',
 'ホ':'货','マ':'摩','ミ':'迷','ム':'幕','メ':'没','モ':'莫','ヤ':'鸭','ユ':'油',
 'ヨ':'要','ラ':'辣','リ':'李','ル':'鲁','レ':'雷','ロ':'啰','ワ':'蛙','ヲ':'沃',
 'ン':'宁','ガ':'尬','ギ':'旗','グ':'古','ゲ':'戈','ゴ':'过','ザ':'砸','ジ':'字',
 'ズ':'组','ゼ':'泽','ゾ':'昨','ダ':'达','ヂ':'治','ヅ':'土','デ':'第','ド':'都',
 'バ':'巴','ビ':'毕','ブ':'布','ベ':'北','ボ':'拨','パ':'帕','ピ':'匹','プ':'铺',
 'ペ':'泼','ポ':'坡','ャ':'岈','ュ':'育','ョ':'约','ッ':'促','ァ':'哇','ィ':'咿',
 'ゥ':'屋','ェ':'也','ォ':'哟','ヮ':'瓦','ヰ':'伟','ヱ':'未','ヴ':'弗','ヵ':'咔',
 'ヶ':'克','ー':'—','―':'—','゛':'★','゜':'☆',
}
# JP shinjitai (and old-form) codepoints still referenced by shipped data, mapped to
# the Simplified glyph their record must now draw.  Produced by the translation itself
# (glossary single-position alignments + the keyboard wave), not by a converter.
SC_VARIANTS = dict([
 ('亜','亚'),('於','于'),('値','值'),('兎','兔'),('呂','吕'),('務','务'),('浄','净'),
 ('渋','涩'),('製','制'),('蹟','迹'),('絶','绝'),('選','选'),('繕','缮'),('講','讲'),
 ('測','测'),('歳','岁'),('載','载'),('殺','杀'),('柵','栅'),('讃','赞'),('腫','肿'),
 ('純','纯'),('乗','乘'),('讐','售'),('禰','祢'),('鉦','钲'),('羅','罗'),('債','债'),
 ('試','试'),('時','时'),('積','积'),('劇','剧'),('動','动'),('園','园'),('報','报'),
 ('樹','树'),('級','级'),('結','结'),('線','线'),('詩','诗'),('館','馆'),('実','实'),
 ('気','气'),('対','对'),('関','关'),('開','开'),('閉','闭'),('経','经'),('応','应'),
 ('営','营'),('楽','乐'),('変','变'),('検','检'),('録','录'),('蔵','藏'),('視','视'),
 ('覚','觉'),('設','设'),('証','证'),('鉄','铁'),('涙','泪'),('緑','绿'),('銭','钱'),
 ('険','险'),('隠','隐'),('臓','脏'),('竜','龙'),('縁','缘'),('渓','溪'),('挙','举'),
 ('拠','据'),('圏','圈'),('処','处'),('従','从'),('択','择'),('沢','泽'),('焼','烧'),
 ('拝','拜'),('悩','恼'),('専','专'),('態','态'),('囲','围'),('衆','众'),('剣','剑'),
 ('晩','晚'),('曽','曾'),('壊','坏'),('桜','樱'),('獣','兽'),('価','价'),('揺','摇'),
 ('摂','摄'),('暦','历'),('歴','历'),('帰','归'),('毎','每'),('裏','里'),('恵','惠'),
 ('斉','齐'),('斎','斋'),('瞼','睑'),('預','预'),('領','领'),('捜','搜'),
])
# Font slots the pre-prologue UI draws on screen, produced by tools/ui_refs.py from the
# captured name-entry/file-select frames.  They are not text, so `used_slots` cannot see
# them and the allocator would happily hand one out -- which is how the keyboard's 漢字
# tab came to read 干字 in one build.
UI_SLOTS_FILE = 'docs/research/ui_glyph_indices.json'
# Of those, the labels whose JIS form differs from simplified *and* that no text block
# reaches, so redrawing them in WenQuanYi localises the label without changing a single
# Japanese sentence's font: the 漢字 tab becomes 汉字.
UI_GLYPHS = {'汉': 0x35D}
# Same story for the speaker nameplate: it draws 藤崎/伊集院/好雄 from name tables no
# text pointer reaches, so those names sat in the Japanese font while the dialog under
# them was Chinese.  `tools/jisaudit.py` measures the slots off captured frames.
NAME_SLOTS_FILE = 'docs/research/nameplate_glyph_indices.json'
# `$E806` draws the birthday number through the engine's own digit routine, which
# addresses `$6C`+value -- that band runs straight into the Ａ/Ｂ/Ｏ the blood type
# splice uses.  A digit is the same character in both languages, so replacing those
# records changes the font of `５月２７日` without touching any Japanese wording.
DIGIT_GLYPHS = {c: 0x6C + i for i, c in enumerate('０１２３４５６７８９')}
MARK = {0x12: '〔姓〕', 0x13: '〔名〕'}
# $09 used to be listed here as a full-width space.  It is not one: its handler
# $80:CC20 loads a 16-bit operand from cursor+1 into $0A26/$0A28 and the
# dispatcher then eats 3 bytes (docs/research/control-widths.md).  Encoding a
# lone $09 would silently swallow the two bytes after it.
MARK_B = {v: k for k, v in MARK.items()}
# Operand-eating control codes (docs/research/control-codes.md, read off the
# dispatcher's handler table).  A walker that treats $09 as 1 byte swallows the
# tile-cursor operand into the next text run -- the block 47 `09 1a 44` -> `09 1a
# 2e` mangle that froze date entry.  Everything not listed is width 1.
CTRL_WIDTH = {0x00: 2, 0x01: 2, 0x02: 2, 0x03: 4, 0x04: 2, 0x07: 2, 0x08: 2,
              0x09: 3, 0x0F: 5, 0x28: 2,
              **{c: 2 for c in range(0x30, 0x38)}}
LINE_CTRL = (0x14, 0x0C, 0x0A)
# The record draws columns 0..13 of its 16-dot cell and WenQuanYi's 13px strike inks 13
# columns, so dx=2 -- which the old bbox calibration scored best, because a cropped glyph
# matches the stock box exactly -- threw away the right stroke of 88% of the vocabulary.
# dx=1 lands the right edge on column 13 like the Japanese font and drops nothing.
WQY_DX, WQY_DY = 1, 0
# The Japanese font hangs its full-width alnum band three rows above the kanji
# window (ink rows 1..11 vs 0..13), and the birthday echo / blood-type row draw
# the record verbatim -- at WQY_DY the digits sit on rows 4..13 and visibly ride
# low.  Copy the Japanese placement for exactly that band.
def wqy_dy(ch):
    n = unicodedata.normalize('NFKC', ch)
    return WQY_DY - 3 if ch != n and n.isascii() and n.isalnum() else WQY_DY
CTL_RE = re.compile(r'⟦([0-9A-Fa-f]{2,4})⟧')


# ------------------------------------------------------------------- walking

def table_spans(base, count, data):
    offs = []
    for k in range(count):
        lo, hi = data[base + k * 2: base + k * 2 + 2]
        offs.append((hi << 8) | lo)
    ordered = sorted(set(o for o in offs if 0x8000 <= o <= 0xFFFF))
    nxt = dict(zip(ordered, ordered[1:] + [0x10000]))
    return offs, nxt


def kana_remap_slots(data):
    """Glyph slots holding the handwritten kana variant -- live font, not slack.

    $80:D4BD redirects every drawn index in $AB..$FC through the list at file
    0x54E4 to slot $0D5A + position, so those slots look unreferenced to a text
    scan yet are drawn constantly.  The previous build wrote Japanese *text*
    bytes over the first 92 of them, which is the 乱码 the prologue showed.
    """
    n = 0
    while data[KANA_REMAP_LIST + n]:
        n += 1
    return set(range(KANA_REMAP_BASE, KANA_REMAP_BASE + n))


def backfill_records(code, char2idx, written_idx):
    """Endgame #43 (B/C tier): redraw every font record the Chinese text does not own.

    Kana cells take the WenQuanYi bitmap of their homophone -- the keyboard re-encode
    means Chinese text no longer emits kana codes at all, so this only insures stray
    references -- and kanji cells a WQY re-render at their own codepoint, with JP
    variant forms taking the Simplified glyph through SC_VARIANTS.  Anything the
    allocator or this build's in-place set already claimed is skipped, so the pass can
    never stomp an owned record; the $AB..$FC redirect slots are honoured too, since
    that is where the engine actually reads a redirected kana's bitmap from.
    """
    data = code.rom.data
    owned = set(char2idx.values()) | set(written_idx)

    def rec(ch):
        return W.record(ch, WQY_DX,
                        wqy_dy(ch) + (1 if ch in '。、，！？…：；' else 0))

    out = {}
    n = 0
    while data[KANA_REMAP_LIST + n]:
        src, slot = data[KANA_REMAP_LIST + n], KANA_REMAP_BASE + n
        ch = T.idx_to_char(src)
        if slot < T.MAX_INDEX and slot not in owned and ch in KANA_HOMO:
            out[slot] = rec(KANA_HOMO[ch])
        n += 1
    for i in range(T.JIS_HIRA, 0x0153):        # direct kana records (katakana band)
        if i in owned or i in out:
            continue
        ch = T.idx_to_char(i)
        if ch in KANA_HOMO:
            out[i] = rec(KANA_HOMO[ch])
    for i in range(T.JIS_KANJI, T.GLYPH_WRITABLE_MAX):  # kanji band
        if i in owned or i in out:
            continue
        ch = T.idx_to_char(i)
        if ch is None:
            continue
        out[i] = rec(SC_VARIANTS.get(ch, ch))
    return out


def preset_name_slots(data):
    """Glyph slots the preset player-name pool draws.

    It is a fixed table rather than a TEXT_PTRS or name block, so `used_slots`'s text
    walk never sees it.  Its 7-byte entries leave the glyph pairs on odd offsets, so
    this scans every byte -- a false positive only costs the allocator a slot, while a
    miss hands a live name glyph to WenQuanYi (two of this table's slots were claimed
    by the previous build, so two of the 23 preset names drew a Chinese character).
    """
    lo, hi = PRESET_NAMES
    return {((data[i] << 8) | data[i + 1]) & 0x0FFF
            for i in range(lo, hi - 1) if 0xF0 <= data[i] < 0xFF}


def ui_run(data, addr, n):
    """The n 2-byte glyph codes at addr, checked to be one maximal run.

    Maximality is not pedantry: the placement opcodes that follow these strings carry
    operand bytes, and an operand that happens to be >= $F0 would be swallowed as a
    glyph code by a careless edit -- which is exactly the pointer drift the 死循环
    screenshots showed.
    """
    assert addr - 1 >= 0 and data[addr - 1] < 0xF0 and data[addr + 2 * n] < 0xF0, \
        '%#x is not a maximal %d-code glyph run' % (addr, n)
    return [((data[addr + j] << 8) | data[addr + j + 1]) & 0x0FFF
            for j in range(0, 2 * n, 2)]


def ui_text_slots(data):
    """Glyph slots the name-entry scripts draw, translated or not.

    No text pointer addresses this region, so `used_slots` is blind to it and the
    allocator would hand out a label's slot -- the same miss that once made the
    keyboard's 漢字 tab read 干字.
    """
    out = set()
    for lo, hi in UI_TEXT_REGIONS:
        i = lo
        while i < hi - 1:
            if i + 1 < hi and data[i] >= 0xF0:
                out.add(((data[i] << 8) | data[i + 1]) & 0x0FFF)
                i += 2
            else:
                i += 1
    return out


def parse_body(data, start, stop, sb, names=None):
    """Macro byte span -> (text, ctrls, clean, slots, tokens).

    The body ends at its $0A return, which is local to the macro and must not be
    propagated.  $00/$0E/$0F are parameter bytes of the variable/format macros,
    so a body holding them is not plain text.

    ``names`` maps a font index to the character the patch put there, so a body
    we rewrote reads back as its Chinese rather than as whatever the JIS table
    calls that slot.

    ``slots`` and ``text`` parallel each other: the glyph index the body reads a
    character from, or None where it holds a name marker.  A fold may only be
    reused when those indices are the ones the Chinese allocation picked, or the
    engine would draw the old Japanese bitmap instead of the new one.  ``tokens``
    is the same content in stream order as ('g', slot) / ('c', byte) pairs.
    """
    names = names or {}
    name = lambda i: names.get(i) or T.idx_to_char(i)
    i, chars, ctrls, slots, toks = start, [], [], [], []

    def out(clean):
        return ''.join(chars), ctrls, clean, slots, toks
    while i < stop:
        b = data[i]
        if b == 0x0A:
            return out(True)                         # RTL: body over
        if b in (0x00, 0x0E, 0x0F):
            return out(False)
        if b < 0x40:
            if b in MARK:
                chars.append(MARK[b])
                slots.append(None)
                toks.append(('n', b))
            else:
                ctrls.append(b)
                toks.append(('c', b))
            i += 1
        elif b < 0xA0:
            idx = sb[b]
            c = name(idx)
            if not c:
                return out(False)
            chars.append(c)
            slots.append(idx)
            toks.append(('g', idx))
            i += 1
        elif b < 0xF0:
            return out(False)                        # nested macro
        else:
            idx = ((b << 8) | data[i + 1]) & 0x0FFF
            chars.append(name(idx) or '')
            slots.append(idx)
            toks.append(('g', idx))
            i += 2
    return out(True)


class Codec:
    """Everything that only depends on the original ROM's code tables."""

    def __init__(self, rom):
        self.rom = rom
        self.names = {}                      # index -> char, set by the verifier
        d = rom.data
        self.sb = {c: rom.sb_entry(c) for c in range(0x40, 0xA0)}
        self.c2code = {}
        for c, i in self.sb.items():
            ch = T.idx_to_char(i)
            if ch and ch not in self.c2code:
                self.c2code[ch] = c
        self.ph_off, self.ph_next = table_spans(T.PHRASE_TABLE, 0x48, d)
        self.sub_off, self.sub_next = table_spans(T.SUB_TABLE, 2048, d)

    def phrase_span(self, code):
        base = (0xB9 - 0x80) * 0x8000 - 0x8000
        o = self.ph_off[code - 0xA0]
        return base + o, base + self.ph_next.get(o, 0xFFFF)

    def sub_span(self, hi, lo):
        base = (0xC3 - 0x80) * 0x8000 - 0x8000
        o = self.sub_off[(((hi << 8) | lo) & 0x7FF)]
        return base + o, base + self.sub_next.get(o, 0xFFFF)

    def phrase(self, code):
        return parse_body(self.rom.data, *self.phrase_span(code), sb=self.sb,
                          names=self.names)

    def sub(self, hi, lo):
        return parse_body(self.rom.data, *self.sub_span(hi, lo), sb=self.sb,
                          names=self.names)

    def body(self, code_str):
        """The macro bytes a folded atom's 'code' really expands to, minus the $0A.

        Needed because a fold may only be emitted while every code in its body
        still means what it meant in Japanese: retargeting an SB entry would
        silently change what an old body draws.
        """
        codes = [int(x, 16) for x in (code_str[i:i + 2] for i in range(0, len(code_str), 2))]
        if len(codes) == 1:
            lo, hi = self.phrase_span(codes[0])
        else:
            lo, hi = self.sub_span(*codes)
        raw = bytes(self.rom.data[lo:hi])
        return raw[:raw.index(0x0A) + 1] if 0x0A in raw else raw

    def walk(self, addr, end):
        """Byte range -> atom list (asserts a byte-exact reconstruction)."""
        d = self.rom.data
        atoms, i = [], addr
        while i < end:
            b = d[i]
            if b < 0x40:
                mk = MARK.get(b)
                if mk:
                    atoms.append({'k': 'n', 'ch': mk, 'raw': bytes([b]), 'ctrl': []})
                    i += 1
                else:
                    w = CTRL_WIDTH.get(b, 1)
                    ops = d[i + 1:i + w]
                    if (len(ops) == w - 1 and all(x < 0xF0 for x in ops)
                            and i + w <= end - 1):
                        # a pure operand run: inert bytes the dispatcher eats.
                        # $F0-$FF operands stay visible (runtime_glyphs reads the
                        # kept $0F bodies' kanji through this walk), and the last
                        # byte of the range is the block's own terminator, which
                        # group() must still find (block 141's `30 a0`).
                        atoms.append({'k': 'c', 'ch': '', 'raw': bytes(d[i:i + w]),
                                      'ctrl': list(d[i:i + w])})
                        i += w
                    else:
                        atoms.append({'k': 'c', 'ch': '', 'raw': bytes([b]), 'ctrl': [b]})
                        i += 1
            elif b < 0xA0:
                atoms.append({'k': 'g', 'ch': T.idx_to_char(self.sb[b]) or '',
                              'raw': bytes([b]), 'ctrl': []})
                i += 1
            elif b < 0xE8:
                text, ctrl, clean, slots, toks = self.phrase(b)
                if clean:
                    atoms.append({'k': 'm', 'ch': text, 'raw': bytes([b]),
                                  'ctrl': ctrl, 'slots': slots, 'toks': toks,
                                  'code': '%02X' % b, 'body': self.body('%02X' % b)})
                else:
                    atoms.append({'k': 'v', 'ch': '⟦%02X⟧' % b,
                                  'raw': bytes([b]), 'ctrl': []})
                i += 1
            elif b < 0xF0:
                hi, lo = b, d[i + 1]
                text, ctrl, clean, slots, toks = self.sub(hi, lo)
                if clean:
                    atoms.append({'k': 'm', 'ch': text, 'raw': bytes([hi, lo]),
                                  'ctrl': ctrl, 'slots': slots, 'toks': toks,
                                  'code': '%02X%02X' % (hi, lo),
                                  'body': self.body('%02X%02X' % (hi, lo))})
                else:
                    atoms.append({'k': 'v', 'ch': '⟦%02X%02X⟧' % (hi, lo),
                                  'raw': bytes([hi, lo]), 'ctrl': []})
                i += 2
            else:
                idx = ((b << 8) | d[i + 1]) & 0x0FFF
                atoms.append({'k': 'g', 'ch': T.idx_to_char(idx) or '',
                              'raw': bytes([b, d[i + 1]]), 'ctrl': []})
                i += 2
        got = b''.join(a['raw'] for a in atoms)
        assert got == bytes(d[addr:end]), 'atom walk lost bytes: %d vs %d' % (
            len(got), end - addr)
        return atoms


def segmentize(atoms):
    segs, cur = [], []
    for a in atoms:
        cur.append(a)
        if a['ctrl'] and a['ctrl'][-1] in LINE_CTRL:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


TERM = set(range(0xA0, 0xA8)) | {0x0A}
PAD = 0x2E                       # the dispatcher's 1-byte, 0-width no-op


def group(atoms):
    """atoms -> boxes, each with its own segments.

    A box ends where the executed control stream hits $0C (drawn by a $A0-$A7
    macro) or a top-level $0A (end of that script step).  $82:A1D6 computes the
    next box's start as `per-object base + 2*script operand` and uses the text
    only to decide whether to keep it or rewind one byte, so the grid of starts
    is fixed by the object script and a text patch cannot move it: every box has
    to end on the same file offset with the same 1-byte terminator it had in
    Japanese.  Fitting the block as a whole is not enough -- a box one byte too
    long shifts every later box and the reader starts cutting sentences in half,
    which is the drift the prologue screenshots show.
    """
    boxes, cur, n = [], [], 0
    for a in atoms:
        cur.append(a)
        n += len(a['raw'])
        k = a['ctrl'][-1] if a['ctrl'] else None
        if k in (0x0C, 0x0A):
            boxes.append({'bytes': n, 'term': 'STEP' if k == 0x0A else 'BOX',
                          'raw': a['raw'], 'atoms': cur})
            cur, n = [], 0
    if cur:
        boxes.append({'bytes': n, 'term': 'TAIL', 'raw': b'', 'atoms': cur})
    for bx in boxes:
        bx['segs'] = segmentize(bx['atoms'])
    return boxes


def box_spans(boxes):
    """[(first_seg, one_past_last_seg)] into the head-stripped segment list."""
    spans, k = [], 0
    for bx in boxes[1:]:
        spans.append((k, k + len(bx['segs'])))
        k = spans[-1][1]
    return spans


def pack_boxes(boxes, spans, seg_bytes):
    """Per-box exact spans: content, $2E padding, terminator last.

    The grid fixes P_{i+1}, the address the engine probes for box i+1: it keeps
    P_{i+1} when the byte at P_{i+1}-1 is a terminator and otherwise rewinds to
    the terminator before it.  A box *could* therefore stop at P_{i+1}-2 and hand
    its last byte to its successor -- but that successor then starts one cell
    earlier, on the cell where the box-open code draws its own 「, and its first
    glyph is painted over.  So every box ends exactly at P_{i+1}-1, which leaves
    `span_i` bytes for box i and nothing else.

    Returns (bytes, [problems]).
    """
    span = [bx['bytes'] for bx in boxes[1:]]
    term = [bx['raw'] for bx in boxes[1:]]
    cov = len(seg_bytes)
    out, bad = bytearray(b''.join(a['raw'] for a in boxes[0]['atoms'])), []
    for i, bx in enumerate(boxes[1:]):
        lo, hi = spans[i]
        if hi > cov:                              # not translated yet: leave it be
            out += b''.join(a['raw'] for s in bx['segs'] for a in s)
            continue
        sb = seg_bytes[lo:hi]
        cap = span[i]
        used = sum(len(b) for b in sb)
        if sb[-1][-1:] != term[i]:
            bad.append((i, 'terminator', term[i].hex(), sb[-1][-1:].hex(), cap))
            continue
        if used > cap:
            bad.append((i, 'over', used - cap, '', cap))
            continue
        out += b''.join(sb[:-1]) + sb[-1][:-1]
        out += bytes([PAD]) * (cap - used) + term[i]
    return bytes(out), bad


def seg_runs(seg):
    """[(text, [ctrls], [(macro_text, raw, [ctrls], [slots], body)])] in stream order."""
    runs = []
    for a in seg:
        if a['k'] == 'c' and not a['ctrl']:
            continue
        if not runs:
            runs.append(['', [], []])
        if a['ch'] and runs[-1][1]:
            runs.append(['', [], []])
        runs[-1][0] += a['ch']
        if a['k'] == 'm' and a['ch']:
            runs[-1][2].append((a['ch'], a['raw'], a['ctrl'], a['slots'], a['body']))
        runs[-1][1].extend(a['ctrl'])
    return [r for r in runs if r[0] or r[1]]


# ------------------------------------------------------------------- tokens

def zh_tokens(s):
    out, pos = [], 0
    for m in CTL_RE.finditer(s):
        out += list(s[pos:m.start()])
        out.append('⟦%s⟧' % m.group(1))
        pos = m.end()
    out += list(s[pos:])
    toks, k = [], 0
    while k < len(out):
        if out[k] == '〔' and out[k:k + 3] == ['〔', '姓', '〕']:
            toks.append('〔姓〕'); k += 3
        elif out[k] == '〔' and out[k:k + 3] == ['〔', '名', '〕']:
            toks.append('〔名〕'); k += 3
        else:
            toks.append(out[k]); k += 1
    return toks


def k2(idx):
    return bytes((0xF0 | (idx >> 8), idx & 0xFF))


# ------------------------------------------------------------------- encoder

class Encoder:
    """items (chars, '=xx' controls, name markers, variable codes) -> bytes.

    `words` maps an item tuple to the raw bytes of a folded Japanese macro, and
    `page` maps a character to the SB code this patch retargeted onto its
    WenQuanYi slot.  A shortest path over the item list is taken per line, so
    the control skeleton is preserved exactly while the text in between is
    packed as tightly as the bands allow.

    Nothing here ever invents a macro call: the emitted stream contains only
    literal glyph codes, control bytes, name markers, the variable codes the
    Japanese stream already had, and Japanese macros the engine already runs.
    """

    def __init__(self, code, char2idx, folds, page=()):
        self.code = code
        self.char2idx = char2idx
        self.words = dict(folds)
        self.page = dict(page)
        self.win = max([1] + [len(k) for k in folds])
        self.sb_of = {}
        for c, sbc in code.c2code.items():
            if char2idx.get(c) == code.sb[sbc]:
                self.sb_of[c] = sbc

    def single(self, tok):
        if tok.startswith('='):
            return bytes([int(tok[1:], 16)])
        if tok in MARK_B:
            return bytes([MARK_B[tok]])
        if tok.startswith('⟦'):
            return bytes.fromhex(tok[1:-1].lower())
        if tok in self.sb_of:                    # same slot, half the bytes
            return bytes([self.sb_of[tok]])
        if tok in self.page:                     # code page entry, 1 byte
            return bytes([self.page[tok]])
        if tok in self.char2idx:
            return k2(self.char2idx[tok])
        return None

    def encode(self, items):
        """-> (bytes, [item tuples]) shortest packing of one line."""
        best = {0: (b'', [])}
        n = len(items)
        for pos in range(n + 1):
            if pos not in best:
                continue
            cur = best[pos]
            for size in range(min(self.win, n - pos), 0, -1):
                span = tuple(items[pos:pos + size])
                if size == 1:
                    raw = self.single(span[0])
                else:
                    raw = self.words.get(span)
                if raw is None:
                    continue
                np = pos + size
                val = (cur[0] + raw, cur[1] + [span])
                if np not in best or len(val[0]) < len(best[np][0]):
                    best[np] = val
        if n not in best:
            raise SystemExit('cannot encode line starting %r' % list(items[:8]))
        return best[n]


# ------------------------------------------------------------------- glyphs

def used_slots(code, registered=()):
    """Glyph slots any *text* or *name* block can reach, so none may be reused.

    Name blocks (pointer table 0x9872) hold the speaker and menu word lists that
    the prologue draws, so their glyphs are load-bearing too; a false positive
    here merely costs the allocator a slot.
    `registered` is the set of TEXT_PTRS block numbers whose zh file already
    replaces the block in the patched ROM.  Their raw Japanese bytes never
    render again, so they contribute no slots -- that is the runway for every
    later registration wave.  Their dictionary calls are still visited with
    glyph collection on: a phrase body without a Chinese row (the `shorten`
    list) still draws its Japanese from any caller, registered included.
    """
    d = code.rom.data
    rom = code.rom
    used, done = set(), set()

    def visit(start, stop, depth, chain, glyphs=True):
        if (start, stop) in done or depth > 3:
            return
        done.add((start, stop))
        i = start
        while i < stop:
            b = d[i]
            if b < 0x40:
                i += 1
            elif b < 0xA0:
                if glyphs:
                    used.add(code.sb[b])
                i += 1
            elif b < 0xE8:
                if b not in chain:
                    o = code.ph_off[b - 0xA0]
                    if 0x8000 <= o <= 0xFFFE:
                        base = (0xB9 - 0x80) * 0x8000 - 0x8000
                        visit(base + o, base + code.ph_next[o], depth + 1,
                              chain | {b})
                i += 1
            elif b < 0xF0:
                k = ((b << 8) | d[i + 1]) & 0x7FF
                o = code.sub_off[k]
                if k not in chain and 0x8000 <= o <= 0xFFFE:
                    base = (0xC3 - 0x80) * 0x8000 - 0x8000
                    visit(base + o, base + code.sub_next[o], depth + 1,
                          chain | {k})
                i += 2
            else:
                if glyphs:
                    used.add(((b << 8) | d[i + 1]) & 0x0FFF)
                i += 2

    def extents(table):
        starts = sorted(a for a in (table(i) for i in range(T.PTR_COUNT)) if a)
        for a in starts:
            nxt = next((s for s in starts if s > a), None)
            yield a, min(len(d), (nxt if nxt and nxt - a < 0x4000 else a + 0x2000))

    reg = set(registered)
    for i in range(T.PTR_COUNT):
        a = rom.text_ptr(i)
        if not a:
            continue
        for s, stop in extents(rom.text_ptr):
            if s == a:
                visit(a, stop, 0, frozenset(), glyphs=(i not in reg))
                break
    for a, stop in extents(rom.name_ptr):
        visit(a, min(stop, a + 0x200), 0, frozenset())
    return used


SB_SHARE = set('「」（）、。？…‥')

# Always pinned into the 86-code page (see plan(): the `bd` dictionary body
# 朝日奈同学 needs 日 as a 1-byte code or it outgrows its own 8 B span and
# every box that calls it reverts to the 8 B literal).
FORCE_PIN = ('日',)
# The only characters allowed to keep a Japanese slot: shared full-width
# punctuation, not a hanzi.  The SB band also shortcuts 15 high-frequency kanji
# (私 今 行 何 当 思 張 来 日 気 見 出 人 一 言); spare_codes() hands those codes
# to Chinese, each pointing at a fresh WenQuanYi slot, so the simplified form
# is drawn rather than the JIS one.  Every hanzi gets WenQuanYi.
TERM_MACRO = {                                        # punctuation macros, $B9
    ('。', '=0C'): 0xA0, ('？', '=0C'): 0xA1, ('！', '=0C'): 0xA2,
    ('。', '）', '=0C'): 0xA3, ('。', '」', '=0C'): 0xA4,
    ('…', '」', '=0C'): 0xA5, ('？', '」', '=0C'): 0xA6, ('！', '」', '=0C'): 0xA7,
    ('。', '=14'): 0xA8, ('？', '=14'): 0xA9, ('！', '=14'): 0xAA,
    ('…', '=14'): 0xAB, ('、', '=14'): 0xAC, ('…', '。', '=14'): 0xAD,
}


def ui_drawn_slots():
    """Slots tools/ui_refs.py saw on the pre-prologue screens, or none if unscanned."""
    p = os.path.join(ROOT, UI_SLOTS_FILE)
    if not os.path.exists(p):
        return set()
    return {int(k, 16) for k in json.load(open(p))['drawn']}


def nameplate_glyphs(need):
    """{char: stock index} for the speaker nameplate kanji this patch also translates.

    The plate is fed by name tables no text pointer reveals, so its font can only be
    changed in place.  Restricted to characters our own Chinese lines use: that is what
    keeps this from becoming a look-alike swap -- a stock slot is only touched when the
    very character sitting in it is one we must draw in WenQuanYi anyway.  Names whose
    simplified form *differs* (詩織) are excluded, because redrawing them in place would
    rewrite a Japanese word into a Chinese one; those need the table itself re-pointed.
    """
    p = os.path.join(ROOT, NAME_SLOTS_FILE)
    if not os.path.exists(p):
        return {}
    return {c: int(k, 16) for k, c in json.load(open(p))['plate'].items() if c in need}


def stock_binding(need, code):
    """{char: index} for characters the JIS kanji band already addresses by itself.

    The band holds 3,015 kanji and `char_to_idx` says which index draws which of them,
    so a Chinese character that *is* one of those codepoints needs no new slot at all:
    point its codes at the stock index and rewrite that one record.  Zero slot cost, and
    the reason it is safe is the same equality -- every surviving Japanese reference to
    that index (text blocks, the $A0-$EF phrase bodies, the draw-script bank's ~1,700
    labels, the nameplate) keeps naming the very character it meant to name, only now in
    WenQuanYi.  That is the whole-font backfill the user authorised on 2026-09-20; what
    this function refuses is the B-tier version, retargeting an index at an *unrelated*
    hanzi, which would silently rewrite Japanese words into wrong Chinese ones.

    Three characters are held back even when the band has them.  Chars in `code.c2code`
    own a 1-byte SB code, and `Encoder.sb_of` would then shortcut them to that byte at
    the exact moment `build_code_page` hands the same code, repointed, to some other
    char -- 日 would start drawing 执.  A low byte inside `TERM` makes the pair read as a
    box terminator to every raw-byte audit tool, which is how a good build gets reported
    as a broken one.  And the band test is `idx_to_char(idx) == c` rather than a bare
    index lookup, so a one-way map can never bind two characters to one record.
    """
    bound = {}
    # Kana cells are drawn through the $80:D4BD redirect and rewrite into a
    # *different* glyph than their index names, so binding below the kanji band
    # must skip them.  Everything else that round-trips to itself is the same
    # A-tier in-place rewrite -- full-width Latin/symbols included.
    kana_cells = kana_remap_slots(code.rom.data)
    for c in sorted(set(need)):
        if (c in SB_SHARE or c in code.c2code or c in MARK_B
                or c.startswith('⟦')):
            continue
        idx = T.char_to_idx(c)
        if idx is None or not 0 <= idx < T.GLYPH_WRITABLE_MAX:
            continue
        if T.idx_to_char(idx) != c or (idx & 0xFF) in TERM:
            continue
        if idx < T.JIS_KANJI and idx in kana_cells:
            continue
        bound[c] = idx
    return bound


def allocate(need, code, verbose=True):
    """char -> glyph slot.

    Two kinds of slot.  A character the JIS band already draws at our exact codepoint
    keeps that stock index (`stock_binding`), plus shared punctuation that a 1-byte SB
    code renders (。「」、？… （）); everything else -- simplified forms the band has
    under a different codepoint, and characters outside JIS -- gets an unreferenced
    slot.  All of them receive a WenQuanYi record, so no Chinese character is ever
    rendered with a Japanese glyph, and the only Japanese text a stock rewrite touches
    is text that reads the same way afterwards.
    The kana-variant slots are excluded on top: they are drawn through the
    redirect at $80:D4BD and no text pointer reveals them.  So are the UI slots
    and the speaker nameplate's, for the same reason.
    """
    shared = {c for c in need if c in SB_SHARE and c in code.c2code}
    bound = stock_binding(need, code)
    new = sorted(set(c for c in need if c not in shared and c not in bound
                     and c not in MARK_B and not c.startswith('⟦')))
    used = (used_slots(code, registered={b for b, _, _ in BLOCKS})
            | preset_name_slots(code.rom.data) | ui_text_slots(code.rom.data)
            | ui_drawn_slots()
            | set(nameplate_glyphs(need).values()))
    # A bound index may well have been free -- the band is 3,015 wide and `used` only
    # sees what a pointer reaches -- so take the bindings out of the pool before the
    # rest of the characters draw from it.  That is what keeps 耽 from being handed
    # 0x8DD twice over.
    # When the kanji band runs dry the pool extends into the *unused* cells below it
    # (spare ku1/ku2 punctuation variants, geometric marks, free latin, the half-width
    # extras above the redirect window, and the hiragana band).  Those records are
    # plain 28-byte slots at the same addressing; `used` already contains every cell a
    # live pointer reaches plus everything the $AB-$FC kana redirect table points at,
    # so claiming the rest takes no glyph the engine still draws.  The gojūon chart's
    # fidelity was waived (user 2026-09-20), and no intermediate deliverable ships, so
    # this is pool widening, not the B/C-band retargeting reserved for the final pass.
    boundset = set(bound.values())
    pool = [i for i in range(T.JIS_KANJI, T.GLYPH_WRITABLE_MAX)
            if i not in used and i not in boundset]
    pool += [i for i in range(1, T.JIS_KANJI)
             if i not in used and i not in boundset]
    if len(pool) < len(new):
        nojis = [c for c in new if T.char_to_idx(c) is None]
        raise SystemExit('not enough free slots: %d free, %d needed; '
                         'new=%d no-JIS=%s bound-rejected=%s'
                         % (len(pool), len(new), len(new), nojis,
                            [c for c in new if c not in nojis]))
    char2idx = dict(zip(new, pool))
    char2idx.update(bound)
    for c in shared:
        char2idx[c] = code.sb[code.c2code[c]]
    if verbose:
        print('glyphs: %d chars, %d on fresh slots %s..%s of %d usable, '
              '%d at their own stock index, %d shared SB punctuation'
              % (len(char2idx), len(new), hex(pool[0]), hex(pool[-1]),
                 len(pool), len(bound), len(char2idx) - len(new) - len(bound)))
    return char2idx, new


# ------------------------------------------------------------------ code page

def spare_codes(code):
    """The SB codes Chinese may take over: everything but the shared punctuation.

    The $40-$9F band is the codec's single-byte path and the whole 4 MB image
    has no room to grow, so a Chinese patch has to win some of those 96 entries
    or pay two bytes per hanzi.  The 71 kana and 15 frequent-kanji entries are
    fair game (a kanji entry is retargeted at a fresh WenQuanYi slot, so the
    simplified form is drawn rather than the JIS one); only 「」（）、。？…‥
    keep their entries, because Chinese uses the very same glyphs and a folded
    Japanese macro's body reads them.
    """
    out = []
    for c in range(0x40, 0xA0):
        ch = T.idx_to_char(code.sb[c])
        if ch and ch not in SB_SHARE:
            out.append(c)
    return out


def build_code_page(cnt, code, char2idx, extra=(), verbose=True):
    """char -> retargeted SB code, for the most frequent Chinese characters.

    `extra` characters are pinned into the page ahead of the frequency order:
    a per-box byte budget (tools/boxbudget.py) can need a rare character to be
    one byte wide to fit its box's fixed span.
    """
    codes = spare_codes(code)
    pinned = [c for c in extra if c in char2idx and c not in SB_SHARE]
    order = pinned + sorted((c for c in cnt if c in char2idx and c not in SB_SHARE
                             and c not in MARK_B and not c.startswith('⟦')
                             and c not in pinned),
                            key=lambda c: (-cnt[c], c))
    page = {ch: cd for ch, cd in zip(order, codes)}
    hits = sum(cnt[ch] for ch in page)
    if verbose:
        print('code page: %d/%d spare codes -> the most frequent characters, '
              '%d/%d glyph writes become 1 byte'
              % (len(page), len(codes), hits, sum(cnt.values())))
    return page


# ------------------------------------------------------------------- folding

def line_items(code, seg, line, char2idx, repaged=frozenset()):
    """The encoder's item list for one segment: chars then their control bytes.

    A Japanese macro folds into the Chinese stream only when the characters the
    translator put there decode to the very glyph slots the Japanese body reads
    -- in practice the shared full-width punctuation.  Folding anything else
    would draw a Japanese kanji in place of its simplified Chinese form, which
    is the substitution this project refuses.  A body is rejected outright if it
    reads a code the Chinese code page took over, since the patch rewrites that
    table entry and the body would then draw something else.
    """
    runs = seg_runs(seg)
    zruns = line.split('|')
    if len(zruns) != len(runs):
        raise SystemExit('line needs %d "|" (jp runs: %s) for %r'
                         % (len(runs) - 1, [r[0] for r in runs], line))
    items, folds = [], {}
    for (jptext, ctrls, macs), zt in zip(runs, zruns):
        toks = zh_tokens(zt)
        for t in toks:
            if not t.startswith('⟦'):
                continue
            raw = bytes.fromhex(t[1:-1])
            # A cite whose body is plain text is not a citation, it is that text:
            # the engine will draw the body, the round trip will compare the body,
            # and the dictionary fold recompacts the body's own Chinese into the
            # same 1-2 bytes.  Only a variable/format body ($00/$0E/$0F or a nested
            # macro) has to be written as its code, because nothing else can say it.
            if len(raw) == 1 and 0xA0 <= raw[0] < 0xE8:
                text, _, clean, _, _ = code.phrase(raw[0])
            elif len(raw) == 2 and 0xE8 <= raw[0] < 0xF0:
                text, _, clean, _, _ = code.sub(*raw)
            else:
                continue
            if clean:
                raise SystemExit('line cites %s, a plain-text macro that reads %r; '
                                 'write that Chinese instead (the fold recompacts it)'
                                 % (t, text))
        items += toks
        items += [('=%02X' % c) for c in ctrls]
        for ftext, fraw, fctrl, fslots, fbody in macs:
            ftoks = zh_tokens(ftext)
            if len(ftoks) != len(fslots):
                continue                 # body holds something we can't see
            if any(0x40 <= b < 0xA0 and b in repaged for b in fbody):
                continue                 # body reads a retargeted code
            if any(s is not None and char2idx.get(t) != s
                   for t, s in zip(ftoks, fslots)):
                continue                 # would draw the Japanese bitmap
            key = tuple(ftoks + [('=%02X' % c) for c in fctrl])
            if key:
                folds[key] = fraw
    folds.update({k: bytes([v]) for k, v in TERM_MACRO.items()})
    return items, folds


def encode_all(code, segs, zh, char2idx, page, dict_folds=()):
    """(Encoder, [bytes per segment], [items per segment]) for one code page."""
    lines, folds = [], {}
    for k, (seg, line) in enumerate(zip(segs, zh)):
        try:
            it, f = line_items(code, seg, line, char2idx,
                               frozenset(page.values()))
        except SystemExit as e:
            raise SystemExit('%s  [seg %d: %s]' % (
                e, k, b''.join(a['raw'] for a in seg).hex(' ')))
        lines.append(it)
        folds.update(f)
    folds.update(dict_folds)
    enc = Encoder(code, char2idx, folds, page)
    return enc, [enc.encode(it)[0] for it in lines], lines


def macro_span(code, key):
    """(lo, hi) -- the file span one dictionary code owns, up to the next entry."""
    return (code.phrase_span(int(key, 16)) if len(key) == 2
            else code.sub_span(int(key[:2], 16), int(key[2:], 16)))


def phrase_glossary(path=None):
    """{macro code: Chinese} for the dictionary entries a translation exists for."""
    p = path or PHRASE_GLOSSARY
    if not os.path.exists(p):
        return {}
    return {f[0].lower(): f[4].strip() for f in
            (l.rstrip('\n').split('\t') for l in open(p, encoding='utf-8'))
            if len(f) > 4 and re.fullmatch(r'[0-9a-fA-F]{2}([0-9a-fA-F]{2})?', f[0])
            and f[4].strip()}


def macro_bodies(code, char2idx, gloss=(), page=(), verbose=True):
    """([($B9/$C3 rewrite, cap, key, jp, zh)], {fold: call bytes}, [(key, why not)]).

    A 2-3 byte box is not a layout problem when its sentence does not live in the
    box: block 0's 1,370 macro calls draw from 178 shared bodies, so rewriting one
    body localises every box that calls it while the box spends its original call
    bytes.  The body is replaced *inside its own span* -- the phrase and sub-text
    tables are never touched, because an index no text block mentions is still
    reached dynamically by the variable codes (see 'Space' in the module docstring).
    An entry whose Chinese is longer than its span gets no fold either, so its
    boxes report as over budget instead of failing somewhere obscure.  Nothing
    can be relocated: the phrase bank's only gap is a table at its start and the
    sub-text bank's 1,883 spans tile the whole 32 KB, so the fix is to shorten
    that entry's chinese until it fits (2026-09-20, 172 of 178 fit that way).

    This runs on the *settled* code page, because a page entry is what makes
    「我才是」 4 bytes instead of 7.  The price: if a later batch moves a character
    out of the page, that entry's fold disappears and its boxes come up over
    budget in the grid audit -- the same loud, fixable symptom the shared code page
    already has everywhere else (§四: every batch can squeeze an old box).
    """
    enc = Encoder(code, char2idx, (), page)
    slot2ch = {i: c for c, i in char2idx.items()}
    # Read a body back through the code page this build *installs*: a page entry is
    # one byte, and the engine resolves it with the patched table, not the JP one.
    dec = Codec(code.rom)
    dec.sb = dict(code.sb)
    for ch, cd in page.items():
        dec.sb[cd] = char2idx[ch]
    dec.names = slot2ch
    gloss = gloss or phrase_glossary()
    out, folds, late = [], {}, []
    for key in sorted(gloss):
        lo, hi = macro_span(code, key)
        jp, ctrl, clean, slots, _ = parse_body(code.rom.data, lo, hi, sb=code.sb)
        items = zh_tokens(gloss[key])
        if not clean or ctrl or any(s is None for s in slots):
            late.append((key, 'body is not plain text'))
            continue
        if any(not t or t.startswith('⟦') or t in MARK_B for t in items):
            late.append((key, 'chinese is not plain text'))
            continue
        if any(enc.single(t) is None for t in items):
            late.append((key, 'no glyph slot for %r' % gloss[key]))
            continue
        body = enc.encode(items)[0]
        # Read the encoding back the way the engine will, through *our* slot map:
        # a byte below $40 or a $A0-$A7 box code that is the low half of a
        # $F0-$FF glyph pair is an operand and inert, but one the parser reaches
        # on its own would open a box mid-body.  A same-form translation (清川望
        # for 清川望) still has to pass this, because rewriting the body is what
        # moves it off the Japanese font's slots.
        back, c2 = decode_stream(body, 0, len(body), dec, slot2ch)
        if c2 or back != gloss[key]:
            late.append((key, 'body decodes as %r%s'
                         % (back, ' +ctrl %s' % bytes(c2).hex() if c2 else '')))
        elif len(body) + 1 > hi - lo:
            late.append((key, '%d B chinese + $0A > %d B span' % (len(body), hi - lo)))
        else:
            out.append(((lo, body + b'\x0a'), hi - lo, key, jp, gloss[key]))
            raw = (bytes([int(key, 16)]) if len(key) == 2
                   else bytes((int(key[:2], 16), int(key[2:], 16))))
            prev = folds.get(tuple(items))
            # Two entries may carry the same chinese body (e3 and eccf both say
            # 自己): every call draws the same text, so the fold must be the
            # cheaper call bytes, not whichever key sorts last.
            if prev is None or len(raw) < len(prev):
                folds[tuple(items)] = raw
    if verbose:
        span = [t for t in late if 'span' in t[1]]
        print('phrase bodies: %d of %d dictionary entries rewritten in place, '
              '%d whose chinese is longer than their own span (neither bank has a '
              'dead zone to move them, so they can only be shortened), %d refused (%s)'
              % (len(out), len(gloss), len(span), len(late) - len(span),
                 '; '.join('%s %s' % t for t in late if 'span' not in t[1])
                 or 'none'))
        # Which ones, named: the work order for shortening is per entry, and the count
        # alone does not say whose boxes are about to report as over budget.
        for key, why in span:
            print('  shorten %s (%s): %s' % (key, gloss[key], why))
    return out, folds, late


def prompt_bodies(enc):
    """(offset, bytes) for the new-game prompt boxes, padded to the JP span."""
    out = []
    for addr, span, line in PROMPT:
        b, _ = enc.encode(list(line))
        body = bytes([PAD]) + b + bytes([PAD]) * (span - 1 - len(b))
        assert len(body) == span, '%s: %d bytes, box holds %d' % (line, len(body), span)
        out.append((addr, body))
    return out


def name_bodies(char2idx, rom):
    """(offset, bytes) re-pointing the default name's text encodings at our records.

    Every site is checked against what stock puts there, so a wrong offset fails at
    build time instead of scribbling over 65816 code.
    """
    out = []
    for addr, jp, line in NAME_IMM:
        got = bytes(rom.data[addr:addr + 2])
        idx = ((got[0] << 8) | got[1]) & 0x0FFF
        assert T.idx_to_char(idx) == jp and len(line) == 1, \
            '%#x holds %s (%r), not the %r encoding' % (addr, got.hex(' '), jp, line)
        out.append((addr, k2(char2idx[line[0]])))
    for addr, jp, line in NAME_POOL:
        rec = bytes(rom.data[addr:addr + 7])
        idx = [((rec[j] << 8) | rec[j + 1]) & 0x0FFF for j in (0, 2, 4)]
        assert rec[6] == 0x0A and ''.join(T.idx_to_char(x) or '?'
                                          for x in idx if x) == jp, \
            '%#x holds %s, not %r' % (addr, rec.hex(' '), jp)
        assert len(line) <= NAME_SLOTS, '%s overflows a %d-glyph record' % (line, NAME_SLOTS)
        body = b''.join(k2(char2idx[c]) for c in line)
        out.append((addr, body + k2(0) * (NAME_SLOTS - len(line)) + b'\x0a'))
    return out


def name_table_bodies(char2idx, rom):
    """(offset, bytes) re-pointing the name pool and the surname list.

    Stock bytes are checked before anything is written: all three offset tables store
    the *distance* to each record, so a row whose offset is off by one would silently
    rewrite a neighbour's code rather than fail.  A record may not change its start for
    the same reason -- but not its length: the engine reads a record the way it reads a
    text stream (a `$F0-$FF` lead takes its operand, `$0A` ends the run), so a Chinese
    name that is shorter than the kana it replaces just leaves `$0A` dead bytes behind
    it, and the next name keeps the offset its three tables already hold.  The dead
    bytes must be `$0A`, not the blank glyph `$000`: the terminator is where the engine
    stops, so blanks would be *drawn* as a gap after a name that speaks inline.
    """
    out = []
    for addr, jp, line in NAME_TABLE_ROWS:
        rec = bytes(rom.data[addr:addr + 2 * len(jp)])
        got = ''.join(T.idx_to_char(((rec[j] << 8) | rec[j + 1]) & 0x0FFF) or '?'
                      for j in range(0, len(rec), 2))
        assert got == jp, '%#x holds %r, not %r' % (addr, got, jp)
        assert len(line) <= len(jp), \
            '%s -> %s overflows a %d-code record' % (jp, line, len(jp))
        missing = [c for c in line if c not in char2idx]
        assert not missing, '%s: no glyph slot for %s' % (line, ''.join(missing))
        body = b''.join(k2(char2idx[c]) for c in line)
        span = 2 * len(jp) + 1              # codes + the byte that ends the record
        out.append((addr, body + b'\x0a' * (span - len(body))))
    return out


def ui_codes(line, n, side, char2idx, stock):
    """The n glyph indices a row's field must hold, blank-padded on the given side.

    ``UI_KEEP`` in the line copies the stock code at that position through untouched,
    which is how a row keeps a non-character glyph (the panel's affinity mark) while the
    label next to it is translated.  A literal space is the blank glyph itself -- index
    `$000` decodes as ' ' -- so a row can hold a column gap open (the options page lays
    its labels out in fixed columns) instead of shifting everything after it left.
    """
    pad = [None] * (n - len(line))
    cells = pad + list(line) if side == 'L' else list(line) + pad
    return [0 if c is None or c == ' ' else (stock[i] if c == UI_KEEP else char2idx[c])
            for i, c in enumerate(cells)]


def ui_text_bodies(char2idx, rom):
    """(offset, bytes) replacing the name-entry question and label runs.

    Stock bytes are checked the same way the name tables are, and the field keeps its
    code count by padding with the blank glyph the original uses, so the placement
    opcode after each run stays where the script expects it.
    """
    out = []
    seen = {}
    for addr, n, jp, line, side in UI_TEXT_ROWS:
        hit = [c for c in range(addr, addr + 2 * n, 2) if c in seen]
        # Two rows over the same bytes would each pass their own stock decode check and
        # then write over one another -- a sub-run of a longer row still looks maximal
        # to the byte test, so only the disjointness test catches it.
        assert not hit, '%#x overlaps the row at %#x' % (addr, seen[hit[0]])
        for c in range(addr, addr + 2 * n, 2):
            seen[c] = addr
        stock = ui_run(rom.data, addr, n)
        got = ''.join(T.idx_to_char(x) or UI_KEEP for x in stock)
        assert got.strip(' ') == jp, '%#x holds %r, not %r' % (addr, got, jp)
        assert len(line) <= n, '%s needs %d codes, the field has %d' % (line, len(line), n)
        missing = [c for c in line if c not in (UI_KEEP, ' ') and c not in char2idx]
        assert not missing, '%s: no glyph slot for %s' % (line, ''.join(missing))
        out.append((addr, b''.join(k2(x) for x in
                                   ui_codes(line, n, side, char2idx, stock))))
    return out


def jp_sb_page(rom):
    """code -> char for the $40-$9F band as the *Japanese* page holds it."""
    d = rom.data
    return {0x40 + i: T.idx_to_char(((d[T.SB_TABLE + 2 * i] << 8)
                                      | d[T.SB_TABLE + 2 * i + 1]) & 0x0FFF)
            for i in range(96)}


def ui_line_walk(data, addr, n, raw=()):
    """Tokenise a line span: ('g',idx) ('b',code) ('p',code) ('s',hi,lo) ('c',0x0B).

    The contract (see UI_LINE_ROWS) is that the only control byte inside the span
    is $0B -- the zero-operand newline (docs/research/control-codes.md) -- and the
    span ends on a token boundary; either proves the row names a real line pool
    entry rather than a slice of the drawing script.

    `raw` is an order-preserving map of relative offset -> byte length for operand
    runs the script interleaves with its text (placement opcodes like $3B/$08/$12,
    name markers $12/$13, the blank cell $00 00, the row's own $0A/$A0 terminator).
    Those bytes are re-emitted verbatim, so the only freedom inside them is their
    position -- which is exactly what keeps a mid-script line re-encode safe.
    """
    raw = dict(raw)
    toks, i, end = [], addr, addr + n
    while i < end:
        if i - addr in raw:
            k = raw[i - addr]
            toks.append(('r', bytes(data[i:i + k]))); i += k; continue
        b = data[i]
        if b >= 0xF0:
            assert i + 1 < end, '%#x: glyph cell runs off the span end' % i
            toks.append(('g', ((b << 8) | data[i + 1]) & 0x0FFF)); i += 2
        elif b >= 0xE8:
            assert i + 1 < end, '%#x: sub-text call runs off the span end' % i
            toks.append(('s', b, data[i + 1])); i += 2
        elif b >= 0xA0:
            toks.append(('p', b)); i += 1
        elif b >= 0x40:
            toks.append(('b', b)); i += 1
        elif b == 0x0B:
            toks.append(('c', b)); i += 1
        elif b in MARK:
            toks.append(('k', b)); i += 1
        else:
            raise AssertionError('%#x: control byte $%02X inside the span' % (i, b))
    return toks


def raw_ok(bs):
    """Operand bytes a row may pin: controls only, and $0A/$0B/$0C are one byte each."""
    return all(b < 0x40 and (b != 0x0A or len(bs) == 1) for b in bs)


def ui_line_text(toks, sbjp):
    out = []
    for t in toks:
        if t[0] == 'g':
            out.append(T.idx_to_char(t[1]) or UI_KEEP)
        elif t[0] == 'b':
            out.append(sbjp[t[1]] or '??')
        elif t[0] == 'p':
            out.append('«%02X»' % t[1])
        elif t[0] == 'c':
            out.append('⟦0B⟧')
        elif t[0] == 'k':
            out.append(MARK[t[1]])
        elif t[0] == 'r':
            out.append('«%s»' % t[1].hex().upper())
        else:
            out.append('⟦%02X%02X⟧' % (t[1], t[2]))
    return ''.join(out)


def jp_raw_runs(jp, data, addr):
    """Operand runs a row pins, walked over the ROM bytes: (span offset, length).

    The row author writes the interleaved script bytes -- «08 40 06» placement
    operands, «0000» blank cells, the row's own terminator -- exactly where
    ui_line_text renders them, but the *widths* cannot be read off the text:
    Japanese pool lines mix 1-byte SB codes with 2-byte glyph cells, so each
    plain character is measured against the byte at its offset (1 if $40-$9F,
    else 2).  Tokens cost their own byte count, ⟦0B⟧ and 〔姓〕 cost one.
    """
    runs, pos, i = [], 0, 0
    while i < len(jp):
        m = LINE_TOKEN.match(jp, i)
        if m:
            tok = m.group(1)
            bs = bytes.fromhex(tok[1:-1])
            if tok[0] == '«' and raw_ok(bs):
                runs.append((pos, len(bs)))
            pos += len(bs)
            i += len(tok)
        elif jp.startswith(LINE_NL, i):
            pos += 1
            i += len(LINE_NL)
        elif jp[i:i + 3] in MARK.values():
            pos += 1
            i += 3
        else:
            b = data[addr + pos]
            assert b >= 0x40, '%#x+%d: unpinned control byte $%02X under %r' \
                % (addr, pos, b, jp[i])
            pos += 1 if b <= 0x9F else 2
            i += 1
    return runs


def line_raw_runs(line):
    """The same walk over a Chinese line: every plain character is a 2-byte cell."""
    runs, pos, i = [], 0, 0
    while i < len(line):
        m = LINE_TOKEN.match(line, i)
        if m:
            tok = m.group(1)
            bs = bytes.fromhex(tok[1:-1])
            if tok[0] == '«' and raw_ok(bs):
                runs.append((pos, len(bs)))
            pos += len(bs)
            i += len(tok)
        elif line.startswith(LINE_NL, i):
            pos += 1
            i += len(LINE_NL)
        elif line[i:i + 3] in MARK.values():
            pos += 1
            i += 3
        else:
            pos += 2
            i += 1
    return runs


def line_keeps(toks):
    """The raw cell bytes of the glyph tokens no Japanese page names (UI_KEEP)."""
    return [k2(t[1]) for t in toks
            if t[0] == 'g' and T.idx_to_char(t[1]) is None]


LINE_NL = '⟦0B⟧'          # in-line newline, kept at its Japanese offset
# A line may also *keep* a Japanese macro call by writing it: ⟦EB3F⟧ is the two
# sub-text bytes, «BD» the one phrase byte -- both are dictionary calls whose bodies
# earlier batches already translated, so re-emitting the call is how a 7-byte span
# says 今日朝日奈同学约会。
LINE_TOKEN = re.compile(r'(⟦[0-9A-Fa-f]{4}⟧|«(?:[0-9A-Fa-f]{2})+»)')


def line_bytes(char2idx, line, keeps=()):
    """Chinese line text (⟦0B newlines, macro calls, 〔姓〕 markers, pinned «08»
    operands, \ue000 kept cells) -> the span bytes.  A «XX» with XX < $40 is a
    pinned operand byte re-emitted verbatim; the row's $0A/$A0 terminator rides
    along the same way.  Each \ue000 takes the next entry of `keeps` -- the raw
    2-byte code of the unnamed supplement cell the Japanese line held there."""
    body = b''
    klist = list(keeps)
    for si, seg in enumerate(line.split(LINE_NL)):
        if si:
            body += b'\x0b'
        for part in LINE_TOKEN.split(seg):
            if not part:
                continue
            if part[0] in '⟦«':
                body += bytes.fromhex(part[1:-1])
            elif part in MARK.values():
                body += bytes((MARK_B[part],))
            else:
                j = 0
                while j < len(part):
                    mk = next((v for v in MARK.values()
                               if part.startswith(v, j)), None)
                    if mk:
                        body += bytes((MARK_B[mk],)); j += len(mk)
                    elif part[j] == UI_KEEP:
                        assert klist, \
                            '%s: more kept cells than the Japanese line has' % line
                        body += klist.pop(0); j += 1
                    else:
                        body += k2(char2idx[part[j]]); j += 1
    assert not klist, '%s: fewer kept cells than the Japanese line has' % line
    return body


def ui_line_bodies(char2idx, rom):
    """(offset, bytes) re-encoding whole line-pool entries as pure glyph cells.

    Each row writes its span as 2-byte WenQuanYi cells and fills what the line
    leaves unused with blank glyph cells ($F0 $00), keeping the $0A terminator at
    the end of the span -- the shape every Japanese entry has before its $2E.
    $0A padding is forbidden here: this whole region is one pool, and the pool
    walk that builds the schedule's hit targets dies on a $0A the Japanese line
    did not have -- a doubled terminator truncates the table and the cell's press
    handler never dispatches (freeze bug #36).  Blanks draw nothing and are a
    normal 2-byte token for both walks.  An odd leftover byte takes a $0B, which
    the renderer never reaches because it stops at the $0A behind it.
    The delimiters outside the span ($2E joins, $0A/A0 ends) are never touched.
    """
    out, seen = [], {}
    for a2, n2, _, _, _ in UI_TEXT_ROWS:
        for c in range(a2, a2 + 2 * n2):
            seen[c] = ('ui', a2)
    sbjp = jp_sb_page(rom)
    for addr, n, jp, line, loose in (r + (False,) * (5 - len(r))
                                     for r in UI_LINE_ROWS):
        hit = [c for c in range(addr, addr + n) if c in seen]
        assert not hit, '%#x overlaps the %s row at %#x' % (
            addr, seen[hit[0]][0], seen[hit[0]][1])
        for c in range(addr, addr + n):
            seen[c] = ('line', addr)
        raw = jp_raw_runs(jp, rom.data, addr)
        for off, ln in raw:
            assert raw_ok(rom.data[addr + off:addr + off + ln]), \
                '%#x+%d is not a pinnable operand run' % (addr, off)
        if not loose:                       # a splice line starts on control operands
            assert rom.data[addr - 1] in (0x2E, 0x0A), \
                '%#x does not start right after a line delimiter' % addr
        assert rom.data[addr + n] in (0x2E, 0x0A, 0xA0, 0x3C, 0x3B, 0x44, 0x7D), \
            '%#x+%d is %#02X, not a delimiter' % (addr, n, rom.data[addr + n])
        toks = ui_line_walk(rom.data, addr, n, raw)
        got = ui_line_text(toks, sbjp)
        assert got == jp, '%#x holds %r, not %r' % (addr, got, jp)
        keeps = line_keeps(toks)
        assert line.count(UI_KEEP) == len(keeps), \
            '%s: %d kept cells, line has %d' % (line, len(keeps), line.count(UI_KEEP))
        text = LINE_TOKEN.sub('', line.replace(LINE_NL, ''))
        for v in MARK.values():
            text = text.replace(v, '')
        text = text.replace(UI_KEEP, '')
        missing = [c for c in text if c not in char2idx]
        assert not missing, '%s: no glyph slot for %s' % (line, ''.join(missing))
        body = line_bytes(char2idx, line, keeps)
        k = n - len(body)
        assert k >= 0, '%s needs %d B, the span has %d' % (line, len(body), n)
        if k:
            body += (b'\xf0\x00' * ((k - 1) // 2)
                     + (b'' if k % 2 else b'\x0b') + b'\x0a')
        out.append((addr, body))
    return out


def verify_ui_lines(char2idx, path):
    """Re-read the re-encoded lines from the written ROM and decode them back."""
    slot2ch = {i: c for c, i in char2idx.items()}
    src = T.Rom(SRC_ROM)
    exp = ui_line_bodies(char2idx, src)
    d = open(path, 'rb').read()
    ok, good_rows, rows = True, 0, []
    for (addr, n, jp, line), (a2, b2) in zip((r[:4] for r in UI_LINE_ROWS), exp):
        assert a2 == addr
        good = bytes(d[addr:addr + n]) == b2
        toks = ui_line_walk(src.data, addr, n, jp_raw_runs(jp, src.data, addr))
        body = line_bytes(char2idx, line, line_keeps(toks))
        got = ''
        for t in ui_line_walk(d, addr, len(body), line_raw_runs(line)):
            if t[0] == 'g':
                got += slot2ch.get(t[1]) or UI_KEEP
            elif t[0] == 'c':
                got += LINE_NL
            elif t[0] == 's':
                got += '⟦%02X%02X⟧' % (t[1], t[2])
            elif t[0] == 'k':
                got += MARK[t[1]]
            elif t[0] == 'r':
                got += '«%s»' % t[1].hex().upper()
            elif t[0] == 'p':
                got += '«%02X»' % t[1]
            else:
                got += '??'
        good &= got == line
        if not good:
            print('ui line %#x: BROKEN %r -> %r (%s)'
                  % (addr, line, got, b2.hex(' ')))
        ok &= good
        good_rows += good
        rows.append(line)
    print('bank lines: %d/%d -> %s' % (good_rows, len(UI_LINE_ROWS), ' '.join(rows)))
    return ok


def grid_score(ctx, seg_bytes):
    """(over bytes, broken boxes) -- what the code page balancing minimises."""
    over = broken = 0
    for bi, bx in enumerate(ctx['boxes'][1:]):
        lo, hi = ctx['spans'][bi]
        sb = seg_bytes[lo:hi]
        if hi > len(seg_bytes):                   # box not translated yet
            continue
        if sb[-1][-1:] != bx['raw']:
            broken += 1
        over += max(0, sum(len(b) for b in sb) - bx['bytes'])
    return over, broken


def balance_pages(ctxs, code, char2idx, chars, page, dict_folds=(), seeds=()):
    """Grow the shared code page toward the boxes the fixed grids squeeze.

    A 1-byte code page entry is worth one byte to every occurrence of that
    character, in *every* block -- so the page is balanced over all translated
    blocks at once, and a pin that saves block 8 may cost block 144 a byte.
    Greedy: each round adds the character that most reduces the total
    over-budget across all blocks, until nothing helps.  Returns
    (page, pinned, [(over, broken) per block]).
    """
    pinned = [c for c in seeds if c in char2idx and c not in SB_SHARE]
    if pinned:
        page = build_code_page(chars, code, char2idx, pinned, verbose=False)
    for _ in range(24):
        scored = [(ctx, encode_all(code, ctx['segs'], ctx['zh'], char2idx, page,
                                   dict_folds)[1])
                  for ctx in ctxs]
        tot = [grid_score(ctx, sb) for ctx, sb in scored]
        over = sum(o for o, _ in tot)
        if not over:
            return page, pinned, tot
        # A byte saved is a byte saved, whichever box it comes from -- so the
        # tie-break goes to the character that earns its one-byte code most often.
        # A pin is sticky (frequency order alone would evict it again), and one
        # spent on a character no translated line uses yet is one the next batch
        # still needs.  Being folded into a dictionary call elsewhere is not a
        # reason to skip it: the box that spells it out still pays per character.
        big = [(ctx, sb) for (ctx, sb), (o, _) in zip(scored, tot) if o]
        cand = {t for ctx, sb in big
                for bi, bx in enumerate(ctx['boxes'][1:])
                if sum(len(b) for b in sb[ctx['spans'][bi][0]:ctx['spans'][bi][1]])
                > bx['bytes']
                for t in zh_tokens(''.join(ctx['zh'][ctx['spans'][bi][0]:
                                                ctx['spans'][bi][1]]))
                if t in char2idx and t not in page}
        best = None
        for c in sorted(cand, key=lambda c: (-chars.get(c, 0), c))[:40]:
            trial = build_code_page(chars, code, char2idx, pinned + [c],
                                    verbose=False)
            t2 = [grid_score(ctx, encode_all(code, ctx['segs'], ctx['zh'],
                                             char2idx, trial, dict_folds)[1])
                  for ctx in ctxs]
            o = sum(x[0] for x in t2)
            if o < over and (best is None or o < best[0]
                             or (o == best[0] and chars.get(c, 0)
                                 > chars.get(best[1], 0))):
                best = (o, c, trial)
        if best is None:
            return page, pinned, tot
        print('  pin %r (%d occurrence%s, over-budget now %d B)'
              % (best[1], chars.get(best[1], 0),
                 '' if chars.get(best[1], 0) == 1 else 's', best[0]))
        pinned.append(best[1])
        page = best[2]
    return page, pinned, [grid_score(ctx, encode_all(code, ctx['segs'], ctx['zh'],
                                                     char2idx, page,
                                                     dict_folds)[1])
                          for ctx in ctxs]




# ------------------------------------------------------------------- patch

def block_starts(rom):
    return sorted(a for a in (rom.text_ptr(i) for i in range(T.PTR_COUNT)) if a)


def block_extent(rom, i):
    """(start, end) -- end is the start of the next block in address order."""
    starts = block_starts(rom)
    a = rom.text_ptr(i)
    return a, next(s for s in starts if s > a)


def set_ptr(out, i, addr):
    bank = 0x80 + addr // 0x8000
    a = addr - (bank - 0x80) * 0x8000 + 0x8000
    p = T.TEXT_PTRS + i * 3
    out[p:p + 3] = bytes((a & 0xFF, a >> 8, bank))


def wqy_records(char2idx, need, dy_extra='。、，！？…：；'):
    """char -> 28-byte WenQuanYi record, for the slots the patch owns."""
    out = {}
    for ch in need:
        if ch.startswith('⟦') or ch in MARK_B:
            continue
        idx = char2idx.get(ch)
        if idx is None:
            continue
        out[ch] = W.record(ch, WQY_DX, wqy_dy(ch) + (1 if ch in dy_extra else 0))
    return out


# The `$E8-$EF` sub-text calls our translations deliberately keep.  `$E806` splices
# a birthday date and `$E807` a blood type into two prologue lines, and their bodies
# live in bank $C3 -- no text block can re-layout them, so the six glyphs they draw
# are the last characters the translated prologue still shows in the Japanese font.
# `$E800`/`$E801` are the same kind of call (month/day, and year/month/day, printed
# from WRAM by `$0F` around a 月/日/年 glyph) and block 0's phone invitations use them,
# so those three kanji join the in-place set too.  `$E802`'s place names are translated
# as records, not glyphs -- see PLACE_TABLE.
RUNTIME_CALLS = (0xE800, 0xE801, 0xE806, 0xE807)


def runtime_glyphs(code):
    """[(char, font index)] drawn by the kept sub-text calls, kana left out.

    Only 2-byte `$F0-$FF` glyph atoms count: the bodies also hold `$01`/`$0F`
    parameter codes whose operands a naive walk reads as one-byte SB codes, and
    retargeting one of those would corrupt a code the engine still uses.
    """
    out = {}
    for c in RUNTIME_CALLS:
        lo, hi = code.sub_span(c >> 8, c & 0xFF)
        for a in code.walk(lo, hi):
            if a['k'] != 'g' or len(a['raw']) != 2:
                continue
            idx = ((a['raw'][0] << 8) | a['raw'][1]) & 0x0FFF
            ch = T.idx_to_char(idx)
            if ch and not '぀' <= ch <= 'ヿ':
                out[ch] = idx
    return out


def inplace_glyphs(code, need):
    """{char: stock index} for every glyph that has to be drawn where it already sits.

    Four sets, for the same reason: the kept `$E806`/`$E807` sub-text bodies, the UI's
    own labels, the speaker nameplate and the digit band all address fixed slots that no
    text pointer reveals, so the only way to change what they show is to rewrite the
    record in place.  `tools/jisaudit.py` is what looks the others up on real frames.
    """
    digits = {c: i for c, i in DIGIT_GLYPHS.items() if T.idx_to_char(i) == c}
    assert len(digits) == len(DIGIT_GLYPHS), 'the full-width digit band is not at $6C'
    return dict(runtime_glyphs(code), **UI_GLYPHS, **digits, **nameplate_glyphs(need))


def inplace_records(glyphs, char2idx):
    """{index: record}, refusing any index one of our own characters already holds."""
    taken = {i: c for c, i in char2idx.items()}
    for ch, idx in glyphs.items():
        assert idx not in taken or taken[idx] == ch, \
            'in-place glyph %s@%03X collides with %s' % (ch, idx, taken.get(idx))
    return {idx: W.record(ch, WQY_DX, wqy_dy(ch)) for ch, idx in glyphs.items()}


def block_ctx(rom, code, blk, hi, path):
    """Everything one translated block needs: its atoms, boxes, segments, lines."""
    lo, cap = block_extent(rom, blk)
    assert lo < hi <= cap, 'block %d ends at %#x, outside %#x..%#x' % (blk, hi, lo, cap)
    atoms = code.walk(lo, hi)
    segs = segmentize(atoms)
    boxes = group(atoms)
    assert boxes[-1]['term'] != 'TAIL', 'block %d does not end on a terminator' % blk
    head, segs = segs[0], segs[1:]
    spans = box_spans(boxes)
    assert sum(len(b['segs']) for b in boxes) == len(segs) + 1
    zh = open(path, encoding='utf-8').read().rstrip('\n').split('\n')
    assert len(zh) <= len(segs), 'block %d: %d segments, %d translation lines' % (
        blk, len(segs), len(zh))
    # A translation may stop part-way through a block -- that is how a 1600-line
    # block gets shipped in pieces -- but only on a *box* boundary: a half-covered
    # box would pack Chinese into part of a grid span and leave Japanese in the
    # rest, which reads as one mixed sentence.  So coverage trims back to the last
    # box whose lines are all present, and the tail stays byte-identical Japanese.
    cov = len(zh)
    for lo_s, hi_s in spans:
        if hi_s > cov:
            cov = lo_s
            break
    ctx = {'blk': blk, 'lo': lo, 'hi': hi, 'atoms': atoms, 'head': head,
           'segs': segs, 'boxes': boxes, 'spans': spans, 'zh': zh[:cov],
           'cov': cov, 'given': len(zh)}
    ctx['body_len'] = sum(b['bytes'] for b in boxes)
    assert ctx['body_len'] == hi - lo, 'block %d: boxes cover %d of %d bytes' % (
        blk, ctx['body_len'], hi - lo)
    return ctx


def patch(rom, code, written, char2idx, need, page, edits=(), inplace=(),
          bodies=()):
    """written = [(block, file offset, bytes, cap)] for every translated block."""
    out = bytearray(rom.data)
    # TK_SKIP_ADDR="lo-hi,lo-hi" (hex ok) suppresses overlay/pool/dictionary writes
    # by file address, for the same skip-write bisection as TK_SKIP_BLOCKS.
    rngs = [(int(a, 0), int(b, 0)) for a, b in
            (r.split('-') for r in os.environ.get('TK_SKIP_ADDR', '').split(',') if r.strip())]
    skipped = [0]
    def _skip(addr):
        if any(lo <= addr < hi for lo, hi in rngs):
            skipped[0] += 1
            return True
        return False
    for blk, s, body, cap in written:
        if any(lo < s + cap and s < hi for lo, hi in rngs):
            # byte-precise: keep the Chinese but restore JP under the suppressed
            # addresses, so a 3-byte operand run can be bisected inside a block
            mb = bytearray(body)
            for lo, hi in rngs:
                for a in range(max(lo, s), min(hi, s + cap)):
                    mb[a - s] = rom.data[a]
                    skipped[0] += 1
            body = bytes(mb)
        assert len(body) <= cap, 'stream %d bytes does not fit %d' % (len(body), cap)
        out[s:s + len(body)] = body
        for i in range(s + len(body), s + cap):
            out[i] = 0xFF
    for addr, b in edits:
        if _skip(addr):
            continue
        out[addr:addr + len(b)] = b
    for (addr, b), cap, key, jp, zh in bodies:
        assert len(b) <= cap, 'dictionary %s: %d bytes in a %d byte span' % (
            key, len(b), cap)
        if os.environ.get('TK_SKIP_BODIES') or _skip(addr):
            continue
        out[addr:addr + len(b)] = b
    nrec = 0
    if rngs or os.environ.get('TK_SKIP_BODIES'):
        print('SKIP-ADDR: %d write(s) suppressed by %s' % (
            skipped[0], os.environ.get('TK_SKIP_ADDR') or 'TK_SKIP_BODIES'))
    for ch, rec in wqy_records(char2idx, need).items():
        o = T.glyph_offset(char2idx[ch])
        out[o:o + 28] = rec
        nrec += 1
    ip = inplace_records(inplace, char2idx)
    for idx, rec in ip.items():
        o = T.glyph_offset(idx)
        out[o:o + 28] = rec
    bf = backfill_records(code, char2idx, set(ip) | set(char2idx.values()))
    for idx, rec in bf.items():
        o = T.glyph_offset(idx)
        out[o:o + 28] = rec
    print('backfill: %d band records redone in WenQuanYi (kana -> homophone, '
          'JP variant -> simplified)' % len(bf))
    for ch, cd in page.items():
        v = 0xF000 | char2idx[ch]          # all 96 entries carry $F in the flag nibble
        p = T.SB_TABLE + (cd - 0x40) * 2
        out[p:p + 2] = bytes((v >> 8, v & 0xFF))
    open(OUT_ROM, 'wb').write(bytes(out))
    for blk, s, body, cap in written:
        print('block %d written in place at file %#x (%d/%d bytes)'
              % (blk, s, len(body), cap))
    print('%d WenQuanYi records (%d of them in place at stock indices no text reaches: '
          '%s), %d code page entries'
          % (nrec + len(inplace), len(inplace),
             ' '.join(sorted('%s@%03X' % (c, i) for c, i in inplace.items())),
             len(page)))
    for (addr, b), cap, key, jp, zh in bodies[:4]:
        print('  dict %s @%#x: %d/%d bytes  %s -> %s'
              % (key, addr, len(b), cap, jp, zh))
    if len(bodies) > 4:
        print('  ...and %d more dictionary bodies' % (len(bodies) - 4))
    audit(rom.data, out, [(b, s, cap) for b, s, _, cap in written], bodies)
    return written



def audit(orig, out, written=(), bodies=(), quiet=b'\xff'):
    """List every byte range the patch touched, with what it is."""
    # Every block range comes from the build's own table, so a mistyped offset
    # there shows up as UNEXPECTED territory instead of slipping through.
    known = [('sb code table', (T.SB_TABLE, T.SB_TABLE + 0xC0)),
             ('prologue text', (0x22F000, 0x230000)),
             ('new-game prompt', (0x268000, 0x268100)),
             ('default-name code', (0x48f0, 0x4910)),
             ('default-name code', (0x28b50, 0x28b80)),
             ('preset name table', (0x1f890, 0x1f970)),
             ('name pool', (0x21A2D9, 0x21A356)),
             ('place pool', (0x21A1D7, 0x21A2A6)),
             ('surname name table', (0x180C0, 0x18107)),
             ('name-entry ui', UI_TEXT_REGION),
             ('nickname pool', NICK_POOL),
             ('album menu + fortune ui', MENU_TEXT_REGION),
             ('status panel labels', PANEL_TEXT_REGION),
             ('affinity tabs', TAB_TEXT_REGION),
             ('bank label ui', BANK_TEXT_REGION),
             ('festival arcade ui', FESTIVAL_TEXT_REGION),
             ('date + club prompts', SYSTEM_TEXT_REGION),
             ('mini-game rules ui', MINIGAME_TEXT_REGION),
             ('club secret moves', CLUB_TEXT_REGION),
             ('sound test menu', SOUND_TEST_REGION),
             ('month table', MONTH_TABLE_REGION),
             ('festival scripts', PLAY_TEXT_REGION),
             ('festival selector ui', SELECTOR_TEXT_REGION),
             ('name keyboard ui', KEYBOARD_TEXT_REGION),
             ('z1 boss event stream', (0x034F6C, 0x36041)),
             ('z2 hime ending stream', (0x0C6EAC, 0x0C74CA)),
             ('z3 asahina/shiori stream', (0x0D6F96, 0x0D79BC)),
             ('z4 graduation chains', (0x1B605D, 0x1B7FD4)),
             ('z5 date endings', (0x3E6069, 0x3E7FF7)),
             ('font record', (0x3E8000, 0x400000))]
    known += [('block %d text' % blk, (lo, lo + cap))
              for blk, lo, cap in written]
    known += [('play label %d' % i, w) for i, w in enumerate(PLAY_LABEL_REGIONS)]
    # A rewritten dictionary body lives in bank $B9/$C3, outside every text
    # pointer, so without this the audit would call those bytes unknown ground.
    known += [('dictionary body', (lo, lo + len(b)))
              for (lo, b), _cap, _key, _jp, _zh in bodies]

    def label(a):
        for k, v in known:
            if v[0] <= a < v[1]:
                return k
        return 'UNEXPECTED'
    i, rows = 0, []
    while i < len(orig):
        if orig[i] != out[i]:
            j = i
            while j < len(orig) and orig[j] != out[j]:
                j += 1
            rows.append((i, j - i))
            i = j
        else:
            i += 1
    bylabel = collections.Counter()
    for a, n in rows:
        bylabel[label(a)] += n
    print('changed %d bytes in %d runs: %s' % (
        sum(n for _, n in rows), len(rows),
        ', '.join('%s %d' % (k, v) for k, v in bylabel.items())))
    bad = [k for k in bylabel if k == 'UNEXPECTED']
    assert not bad, 'patch touched unknown territory: %s' % [hex(a) for a, n in rows
                                                             if label(a) == 'UNEXPECTED'][:8]


# ------------------------------------------------------------------- verify

def decode_stream(d, start, end, code, slot2ch):
    """Re-read encoded bytes -> (text, executed ctrl stream), macros expanded.

    Runs on bytes alone, so it is an independent check of what patch() wrote.
    """
    text, ctrls, i = [], [], start
    while i < end:
        b = d[i]
        if b < 0x40:
            if b in MARK:
                text.append(MARK[b])
                i += 1
            else:
                w = CTRL_WIDTH.get(b, 1)
                ops = d[i + 1:i + w]
                if (len(ops) == w - 1 and all(x < 0xF0 for x in ops)
                        and i + w <= end - 1):
                    ctrls += list(d[i:i + w])
                    i += w
                else:
                    ctrls.append(b)
                    i += 1
        elif b < 0xA0:
            idx = code.sb[b]
            text.append(slot2ch.get(idx) or T.idx_to_char(idx) or '?')
            i += 1
        elif b < 0xE8:
            t, k, clean, sl, tk = code.phrase(b)
            text.append(t if clean else '⟦%02X⟧' % b)
            if clean:
                ctrls += k
            i += 1
        elif b < 0xF0:
            hi, lo = b, d[i + 1]
            t, k, clean, sl, tk = code.sub(hi, lo)
            text.append(t if clean else '⟦%02X%02X⟧' % (hi, lo))
            if clean:
                ctrls += k
            i += 2
        else:
            idx = ((b << 8) | d[i + 1]) & 0x0FFF
            text.append(slot2ch.get(idx) or T.idx_to_char(idx) or '?')
            i += 2
    return ''.join(text), ctrls


def patched_codec():
    """Codec for the patched ROM, with the phrase/sub-text span tables of the source.

    The offset tables themselves are never rewritten -- dictionary bodies are
    replaced in place -- but the speaker-name pool and the place pool store
    their records inside the sub-text table's dead zone (file 0x21A1D7..), and
    a rewritten record's glyph pair re-parses as a body offset once the tables
    are rebuilt from the patched bytes, hijacking some other entry's span end
    in any reader that does that (this build: 「优美酱」's 美 = F4 AC at an even
    offset read as 0xACF4, collapsing e898's span to 1 byte).  The engine only
    ever reads a body's *start* offset and runs to $0A, so the source tables
    are the correct reference for a re-reader too.
    """
    code = Codec(T.Rom(OUT_ROM))
    ref = Codec(T.Rom(SRC_ROM))
    code.ph_off, code.ph_next = ref.ph_off, ref.ph_next
    code.sub_off, code.sub_next = ref.sub_off, ref.sub_next
    return code


def verify(char2idx, ctx, dst, total):
    """Round-trip the patched ROM against the intended Chinese text.

    The re-read uses a Codec built on the patched bytes, so the code page the
    patch installed is what resolves the single-byte codes -- the same table the
    engine will read.
    """
    slot2ch = {i: c for c, i in char2idx.items()}
    patch_rom = T.Rom(OUT_ROM)
    pcode = patched_codec()
    pcode.names = slot2ch               # a rewritten body reads back as Chinese
    txt, ctrls = decode_stream(patch_rom.data, dst, dst + total,
                               pcode, slot2ch)
    want_txt = ''.join(l.replace('|', '') for l in ctx['zh'])
    jp_ctrl = [c for a in ctx['atoms'] for c in a['ctrl']]
    strip = lambda cs: [c for c in cs if c != PAD]
    ok_ctrl = strip(ctrls) == strip(jp_ctrl)
    print('control stream: %d bytes (+%d $%02X grid pads), %s the Japanese stream'
          % (len(ctrls), len(ctrls) - len(strip(ctrls)), PAD,
             'IDENTICAL to' if ok_ctrl else 'DIFFERS from'))
    if not ok_ctrl:
        for n, (a, b) in enumerate(zip(strip(ctrls), strip(jp_ctrl))):
            if a != b:
                print('   first difference at ctrl #%d: %02X vs %02X' % (n, a, b))
                break
        print('   lengths %d vs %d' % (len(strip(ctrls)), len(strip(jp_ctrl))))
    ok_txt = txt == want_txt if ctx['cov'] == len(ctx['segs']) \
        else txt.startswith(want_txt)
    print('text: %d chars, %s the translation%s'
          % (len(txt), 'matches' if ok_txt else 'DOES NOT match',
             '' if ctx['cov'] == len(ctx['segs'])
             else ' (%d of %d lines, the rest is untouched Japanese)'
                  % (ctx['cov'], len(ctx['segs']))))
    if not ok_txt:
        for n, (a, b) in enumerate(zip(txt, want_txt)):
            if a != b:
                print('   first difference at char #%d: %r vs %r  ctx %r'
                      % (n, a, b, txt[max(0, n - 12):n + 12]))
                break
        print('   lengths %d vs %d' % (len(txt), len(want_txt)))
    ok_grid = verify_grid(ctx['atoms'], pcode, dst, total)
    return ok_ctrl and ok_txt and ok_grid


def verify_grid(jp_atoms, pcode, dst, total):
    """Re-box the patched bytes: the pointer grid must land where Japanese did.

    Re-walking the written stream is what proves no stray $0A, $0C or $A0-$A7
    survived inside a box -- one would cut that box short and shift every box
    after it.
    """
    mine = group(pcode.walk(dst, dst + total))
    theirs = group(jp_atoms)
    bad = [(n, a, b['bytes'], a['raw'].hex(), b['raw'].hex())
           for n, (a, b) in enumerate(zip(theirs[1:], mine[1:]))
           if a['bytes'] != b['bytes'] or a['raw'] != b['raw']]
    print('grid: %d boxes, %s the Japanese spans and terminators'
          % (len(mine) - 1, 'all match' if not bad else '%d MISMATCH' % len(bad)))
    for n, a, bb, _, ar, br in bad[:10]:
        print('   box %d: jp %dB %s vs zh %dB %s' % (n, a['bytes'], ar, bb, br))
    return not bad and len(mine) == len(theirs)


def verify_prompt(char2idx, pcode):
    """Re-read the prompt boxes from the patched bytes.

    Each menu item must still end in one `$0A` on the offset the engine probes --
    the one symptom an overlay edit that grew, or that smuggled a terminator into
    a box's padding, produces -- and must read back as the intended Chinese.
    """
    slot2ch = {i: c for c, i in char2idx.items()}
    ok = True
    for addr, span, line in PROMPT:
        boxes = [b for b in group(pcode.walk(addr, addr + span + 1))
                 if b['bytes']]
        txt, _ = decode_stream(pcode.rom.data, addr, addr + span, pcode, slot2ch)
        good = (len(boxes) == 1 and boxes[0]['bytes'] == span + 1
                and boxes[0]['raw'] == b'\x0a' and txt == line)
        print('prompt %#x: %-6s %r in %d/%d bytes'
              % (addr, 'OK' if good else 'BROKEN', txt, span, span + 1))
        ok &= good
    return ok


def verify_name(char2idx, path):
    """Read the name sites back out of the written file and decode them.

    The immediate sites are `LDA #imm` operands, so a wrong length there would be a
    crash rather than a wrong glyph; decoding the bytes is what shows the operand still
    names a slot this patch gave a WenQuanYi record.  The pool records additionally have
    to keep their null padding and their `$0A` terminator, because the copy routine that
    fills $0E08 reads all three slots.
    """
    slot2ch = {i: c for c, i in char2idx.items()}
    d = open(path, 'rb').read()
    ok = True
    for addr, jp, line in NAME_IMM:
        got = slot2ch.get(((d[addr] << 8) | d[addr + 1]) & 0x0FFF, '?')
        good = got == line
        print('name %#x: %-6s %s -> %s' % (addr, 'OK' if good else 'BROKEN', jp, got))
        ok &= good
    good_rows = 0
    for addr, jp, line in NAME_POOL:
        rec = d[addr:addr + 7]
        idx = [((rec[j] << 8) | rec[j + 1]) & 0x0FFF for j in (0, 2, 4)]
        got = ''.join(slot2ch.get(x, '□') for x in idx if x)
        good = got == line and rec[6] == 0x0A \
            and all(x == 0 for x in idx[len(line):])
        if not good:
            print('pool %#x: BROKEN %s -> %s (%d/%d slots)'
                  % (addr, jp, got, len(line), NAME_SLOTS))
        good_rows += good
        ok &= good
    print('pool %d/%d preset names %s'
          % (good_rows, len(NAME_POOL), 'OK' if ok else 'SEE ABOVE'))
    return ok


def verify_name_tables(char2idx, path):
    """Re-read the two name tables from the written ROM and decode every record.

    Length is what makes this worth checking on the built file rather than on the
    plan: the pool's three offset tables address records by distance, so a record that
    grew would push every name after it out of place -- which shows up as a wrong
    decode two records later.  A record ends at the first `$0A` in a *lead* position,
    exactly as the engine reads it, so `$0A` tucked under a `$F0-$FF` lead (外井's 井 is
    index $20A) is an operand and not a terminator.
    """
    slot2ch = {i: c for c, i in char2idx.items()}
    d = open(path, 'rb').read()
    ok, good_rows, rows = True, 0, []
    for addr, jp, line in NAME_TABLE_ROWS:
        span = 2 * len(jp) + 1
        rec = d[addr:addr + span]
        idx, j = [], 0
        while j < len(rec) and rec[j] != 0x0A:
            idx.append(((rec[j] << 8) | rec[j + 1]) & 0x0FFF)
            j += 2
        got = ''.join(slot2ch.get(x) or '□' for x in idx)
        fill = rec[j:]
        good = got == line and fill == b'\x0a' * len(fill)
        if not good:
            print('names %#x: BROKEN %s -> %r (%s)'
                  % (addr, jp, got, ' '.join('%03X' % x for x in idx)))
        ok &= good
        good_rows += good
        rows.append(line)
    print('name tables: %d/%d records -> %s'
          % (good_rows, len(NAME_TABLE_ROWS), ' '.join(rows)))
    return ok


def verify_ui_text(char2idx, path):
    """Re-read every name-entry run from the written ROM and decode it back.

    Nothing addresses these strings, so a run that gained or lost a code would not
    corrupt a table -- it would just make the engine read the byte after it as a
    glyph.  Decoding each field to exactly the padded text intended is what proves
    that did not happen.
    """
    slot2ch = {i: c for c, i in char2idx.items()}
    stock_rom = T.Rom(SRC_ROM).data
    d = open(path, 'rb').read()
    ok, good_rows, rows = True, 0, []
    for addr, n, jp, line, side in UI_TEXT_ROWS:
        idx = ui_run(d, addr, n)
        good = idx == ui_codes(line, n, side, char2idx, ui_run(stock_rom, addr, n))
        got = ''.join(slot2ch.get(x) or ' ' for x in idx)
        if not good:
            print('ui %#x: BROKEN %r -> %r (%s)'
                  % (addr, line, got, ' '.join('%03X' % x for x in idx)))
        ok &= good
        good_rows += good
        rows.append(got.strip())
    print('name-entry ui: %d/%d runs -> %s'
          % (good_rows, len(UI_TEXT_ROWS), ' '.join(rows)))
    return ok


def verify_bank_slots(char2idx, new):
    """No Chinese slot may back a code the draw-script bank still holds in Japanese.

    Everything at $180C0-$20000 is drawn from 2-byte glyph codes and no text pointer
    reaches the bank, so `used_slots` cannot see it: a fresh slot that a Japanese label
    also uses would print the Chinese bitmap inside that label -- the 干字 defect, one
    screen at a time.  `ui_text_slots` keeps the reserved windows out of the pool; this
    walks every glyph cell in the whole bank, so the ~1700 label runs this batch leaves
    behind are proven clean rather than assumed to be.
    """
    fresh = {char2idx[c] for c in new}
    d = T.Rom(SRC_ROM).data
    lo, hi = BANK_ALL
    hits, i = [], lo
    while i < hi - 1:
        if d[i] >= 0xF0:
            j = i
            while j < hi - 1 and d[j] >= 0xF0:
                j += 2
            for k in range(i, j, 2):
                idx = ((d[k] << 8) | d[k + 1]) & 0x0FFF
                if idx in fresh:
                    hits.append((k, idx))
            i = j
        else:
            i += 1
    for k, idx in hits[:8]:
        print('bank %#x: label code %#x is held for %r'
              % (k, idx, [c for c in new if char2idx[c] == idx][0]))
    print('bank glyph slots: %s in %#x-%#x'
          % ('0 collisions' if not hits else '%d COLLISIONS' % len(hits), lo, hi))
    return not hits


def verify_inplace(glyphs, char2idx):
    """Read those records back out of the written file.

    They live at indices the block streams never address, so no other check in this
    build covers them: the $E8 pair reaches the screen from bank $C3 bodies, and the UI
    labels from the name-entry code.
    """
    out = T.Rom(OUT_ROM).data
    recs = inplace_records(glyphs, char2idx)
    bad = [ch for ch, idx in glyphs.items()
           if out[T.glyph_offset(idx):T.glyph_offset(idx) + 28] != recs[idx]]
    print('in-place glyphs: %d records at stock indices (%s) %s'
          % (len(glyphs), ' '.join(sorted(glyphs)),
             'OK' if not bad else 'FAILED %s' % ''.join(bad)))
    return not bad


def verify_font(pl):
    """Account for every byte of the 3510-record font array in the written file.

    Two claims have to hold at once: each character this build hands the engine finds
    its WenQuanYi bitmap in the slot it was promised, and *no other slot moved* -- that
    second half is the minimal-font requirement, and nothing else here can test it,
    because a fresh slot is addressed only by the streams we re-encoded.
    """
    orig, out = T.Rom(SRC_ROM).data, T.Rom(OUT_ROM).data
    want, conflicts = {}, []

    def claim(idx, rec, label):
        held = want.get(idx)
        if held is not None and held[0] != rec:
            conflicts.append('slot %#x: %r and %r ask for different bitmaps'
                             % (idx, held[1], label))
        want[idx] = (rec, label)

    for ch, rec in wqy_records(pl['char2idx'], pl['need']).items():
        claim(pl['char2idx'][ch], rec, ch)
    ip = inplace_records(pl['inplace'], pl['char2idx'])
    for idx, rec in ip.items():
        claim(idx, rec, T.idx_to_char(idx))
    # Endgame #43: the whole-band backfill moves band records by design, so the
    # minimal-font check must not bark at them.  Recompute the exact set (skips
    # everything claimed above, so no conflict is possible) and verify instead
    # that each backfilled slot really carries its promised bitmap.
    bf = backfill_records(Codec(T.Rom(SRC_ROM)), pl['char2idx'],
                          set(ip) | set(pl['char2idx'].values()))
    wrong = [want[i][1] for i in want
             if out[T.glyph_offset(i):T.glyph_offset(i) + 28] != want[i][0]]
    bad_bf = [i for i, rec in bf.items()
              if out[T.glyph_offset(i):T.glyph_offset(i) + 28] != rec]
    moved = [i for i in range(T.MAX_INDEX)
             if i not in want and i not in bf
             and out[T.glyph_offset(i):T.glyph_offset(i) + 28]
             != orig[T.glyph_offset(i):T.glyph_offset(i) + 28]]
    for m in conflicts[:8]:
        print('font conflict: ' + m)
    for m in moved[:8]:
        print('font: slot %#x (%r) changed but nobody asked'
              % (m, T.idx_to_char(m)))
    print('font: %d/%d slots carry WenQuanYi (%s), %d band record(s) backfilled, '
          '%d unclaimed slot(s) changed'
          % (len(want) - len(wrong), len(want),
             '%d of them at stock indices' % (len(want) - len(pl['new'])),
             len(bf) - len(bad_bf), len(moved)))
    if wrong:
        print('font: %r holds the wrong bitmap' % ''.join(wrong))
    if bad_bf:
        print('font: %d backfilled slot(s) hold the wrong bitmap' % len(bad_bf))
    return not (wrong or moved or conflicts or bad_bf)


# ------------------------------------------------------------------- main

def dump_segments(code, segs, path):
    """JP reference: one line per segment, text runs joined with '|'."""
    with open(path, 'w', encoding='utf-8') as f:
        for n, seg in enumerate(segs):
            runs = seg_runs(seg)
            f.write('%3d  %s   [%s]\n' % (
                n, '|'.join(r[0] for r in runs),
                ' '.join('%02X' % c for c in [x for r in runs for x in r[1]])))


def plan(rom=None, verbose=True):
    """Allocate glyphs, balance the shared code page and pack every translated block.

    One function owns the whole pipeline because the code page is a single global
    resource: the $40-$9F band has ~86 convertible entries and both blocks spend
    from the same pool, so a block can never be packed on its own.
    """
    rom = rom or T.Rom(SRC_ROM)
    code = Codec(rom)
    ctxs = [block_ctx(rom, code, blk, hi,
                      os.path.join(ROOT, 'docs', 'research', name))
            for blk, name, hi in BLOCKS]
    chars = collections.Counter()
    for ctx in ctxs:
        for line in ctx['zh']:
            for t in zh_tokens(line.replace('|', '')):
                chars[t] += 1
    # The prompt's characters get a glyph slot but no code page entry: the text
    # blocks need every one-byte code to stay inside their grids, and the prompt
    # boxes are short enough to pay two bytes per character.  Same for the name
    # tables and the name-entry strings, which are 2-byte glyph code everywhere.
    extra_need = [t for _, _, line in OVERLAY for t in line if t not in chars]
    extra_need += [c for _, _, line in NAME_ROWS + NAME_TABLE_ROWS for c in line
                   if c not in chars and c not in extra_need]
    extra_need += [c for _, _, _, line, _ in UI_TEXT_ROWS for c in line
                   if c not in (UI_KEEP, ' ') and c not in chars
                   and c not in extra_need]
    extra_need += [c for row in UI_LINE_ROWS
                   for c in row[3].replace(LINE_NL, '')
                   if c not in chars and c not in extra_need]
    # A dictionary body we rewrite is Chinese text too, and a character that only
    # ever appears inside one still needs its record.
    gloss = phrase_glossary()
    extra_need += [c for zh in gloss.values() for c in zh
                   if c not in chars and c not in extra_need]
    need = [t for t in chars if not t.startswith('=')] + extra_need
    char2idx, new = allocate(need, code, verbose)
    # The code page settles first, without any help from the dictionary, and only
    # then do the bodies get priced — against that settled page.  A page entry is
    # what makes 「我才是」 4 bytes instead of 7, so judging a body on the static
    # 2 B/hanzi model reports boxes as unfixable that the real build fits.
    # FORCE_PIN: 「日」 must hold a 1-byte page code, or the `bd` body
    # 朝日奈同学 costs 8 B and cannot fit its own 8 B span -- `macro_bodies`
    # prices bodies with folds=() (no nesting), so the eb8d 朝日奈 fold cannot
    # shrink it either.  When bd does not fold, every box that calls it reverts
    # to the literal and ~30 tight 朝日奈同学 boxes across blocks 0/20/21/22/67/
    # 85/104/118 become mathematically unfixable by wording.  At 7 B + $0A the
    # body sits exactly in its span again -- the state block 85 shipped in all
    # summer with 朝日奈桑 (7 B).
    page, pinned, scores = balance_pages(
        ctxs, code, char2idx, chars,
        build_code_page(chars, code, char2idx, FORCE_PIN, verbose=verbose),
        seeds=FORCE_PIN)
    mb, dict_folds, dict_late = macro_bodies(code, char2idx, gloss, page, verbose)
    if verbose:
        print('page (%d codes): %s' % (len(page), ''.join(sorted(page))))
    folds, out = {}, []
    for ctx in ctxs:
        enc, seg_bytes, lines = encode_all(code, ctx['segs'], ctx['zh'],
                                           char2idx, page, dict_folds)
        folds.update(enc.words)
        body, bad = pack_boxes(ctx['boxes'], ctx['spans'], seg_bytes)
        # A box that breaks the grid is left unpadded here so main() can print the
        # whole list; `patch` is what insists the body is byte-exact.
        ctx.update({'enc': enc, 'seg_bytes': seg_bytes, 'lines': lines,
                    'body': body, 'bad': bad})
        out.append(ctx)
    # `scores` comes from the fold-aware encode, not from the balancing pass:
    # balance_pages has to price the page before the bodies exist, so its own
    # numbers are conservative by construction (a fold can only shorten a box).
    scores = [grid_score(ctx, ctx['seg_bytes']) for ctx in out]
    enc = Encoder(code, char2idx, folds, page)   # every block's folds, for overlays
    return {'rom': rom, 'code': code, 'ctxs': out, 'by_blk': {c['blk']: c for c in out},
            'inplace': inplace_glyphs(code, need),
            'chars': chars, 'need': need, 'new': new, 'char2idx': char2idx,
            'page': page, 'pinned': pinned, 'scores': scores, 'enc': enc,
            'bodies': mb, 'dict_folds': dict_folds, 'dict_late': dict_late}


def report(pl, path=None):
    """The per-box grid and per-line encoding of every block, for the other tools."""
    for ctx in pl['ctxs']:
        rep = [{'jp': '|'.join(r[0] for r in seg_runs(seg)), 'zh': line,
                'bytes': b.hex()}
               for line, seg, b in zip(ctx['zh'], ctx['segs'], ctx['seg_bytes'])]
        data = {'block': ctx['blk'], 'total': len(ctx['body']),
                'cap': ctx['hi'] - ctx['lo'], 'cov': ctx['cov'],
                'grid': [[b['bytes'],
                          sum(len(x) for x in ctx['seg_bytes'][lo:hi])
                          if hi <= ctx['cov'] else b['bytes']]
                         for b, (lo, hi) in zip(ctx['boxes'][1:], ctx['spans'])],
                'codepage': {ch: '%02X' % cd for ch, cd in pl['page'].items()},
                'lines': rep}
        p = path or os.path.join(ROOT, 'docs', 'research',
                                 'block%d_enc.json' % ctx['blk'])
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if ctx['blk'] == BLOCK:
            with open(os.path.join(ROOT, 'docs', 'research',
                                   'prologue_enc.json'), 'w',
                      encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)


def main():
    global BLOCKS
    # `--only=144` packs a single block: useful when one block's translation is
    # still in progress and the other must keep building.
    sel = [a for a in sys.argv if a.startswith('--only=')]
    if sel:
        want = {int(x) for a in sel for x in a.split('=', 1)[1].split(',')}
        BLOCKS = tuple(b for b in BLOCKS if b[0] in want)
    pl = plan()
    rom, code, ctxs = pl['rom'], pl['code'], pl['ctxs']
    for ctx in ctxs:
        print('block %d: %d bytes at file %#x, %d atoms, %d lines, %d boxes, '
              '%d translation lines%s'
              % (ctx['blk'], ctx['hi'] - ctx['lo'], ctx['lo'], len(ctx['atoms']),
                 len(ctx['segs']), len(ctx['boxes']) - 1, ctx['cov'],
                 '' if ctx['given'] == ctx['cov'] else
                 ' (%d held back: they cut across a box)'
                 % (ctx['given'] - ctx['cov'])))
    if '--dump' in sys.argv:
        for ctx in ctxs:
            p = os.path.join(ROOT, 'docs', 'research',
                             'block%d_seg.txt' % ctx['blk']
                             if ctx['blk'] != BLOCK else 'prologue_seg.txt')
            dump_segments(code, ctx['segs'], p)
            print('wrote %s' % os.path.relpath(p, ROOT))
        return
    print('folded JP macros: %d, dictionary folds: %d, pinned for the grid: %s'
          % (len(pl['enc'].words) - len(TERM_MACRO) - len(pl['dict_folds']),
             len(pl['dict_folds']), ''.join(pl['pinned'])))
    bad = 0
    for ctx, (over, broken) in zip(ctxs, pl['scores']):
        print('block %d: jp grid %d bytes, chinese content %d, %d over, %d broken'
              % (ctx['blk'], sum(b['bytes'] for b in ctx['boxes'][1:]),
                 sum(len(b) for b in ctx['seg_bytes']), over, broken))
        for bi, kind, a, b, budget in ctx['bad']:
            lo, hi = ctx['spans'][bi]
            print('  %3d %-10s %s%s  budget %dB  %s' % (
                bi, kind, a, ' vs %s' % b if kind == 'terminator' else '',
                budget, ' / '.join(ctx['zh'][lo:hi]).replace('|', ' ')))
        bad += len(ctx['bad'])
    if bad:
        print('%d boxes break the grid' % bad)
        return
    for ctx in ctxs:
        assert len(ctx['body']) == ctx['body_len'], \
            'block %d: packed %d of %d bytes' % (ctx['blk'], len(ctx['body']),
                                                  ctx['body_len'])
    json.dump({'fresh': {c: hex(pl['char2idx'][c]) for c in pl['new']},
               'inplace': {c: hex(pl['char2idx'][c]) for c in pl['need']
                           if c not in pl['new'] and not c.startswith('⟦')
                           and c not in MARK_B},
               # ...and these are WenQuanYi records written at slots that stay in place
               # because the $E8 bodies and the UI labels address them by number.
               'at_stock': {c: hex(i) for c, i in pl['inplace'].items()}},
              open(os.path.join(ROOT, 'docs', 'research', 'glyph_alloc.json'), 'w'),
              ensure_ascii=False, indent=1, sort_keys=True)
    report(pl)
    edits = (prompt_bodies(pl['enc']) + name_bodies(pl['char2idx'], rom)
             + name_table_bodies(pl['char2idx'], rom)
             + ui_text_bodies(pl['char2idx'], rom)
             + ui_line_bodies(pl['char2idx'], rom))
    for (addr, b), (_, span, line), tag in zip(edits, OVERLAY,
                                               ('prompt',) * len(PROMPT)):
        print('%-8s %#07x: %r -> %d/%d bytes %s'
              % (tag, addr, line, len(b), span, b.hex(' ')))
    for (addr, b), (_, jp, line) in zip(edits[len(OVERLAY):len(OVERLAY) + len(NAME_IMM)],
                                         NAME_IMM):
        print('name   %#x: %s -> %s %s' % (addr, jp, line, b.hex(' ')))
    print('pool   %d preset names -> %s'
          % (len(NAME_POOL), ' '.join(line for _, _, line in NAME_POOL)))
    print('tables %d name records -> %s'
          % (len(NAME_TABLE_ROWS),
             ' '.join(line for _, _, line in NAME_TABLE_ROWS)))
    print('ui     %d name-entry runs -> %s'
          % (len(UI_TEXT_ROWS),
             ' '.join(line for _, _, _, line, _ in UI_TEXT_ROWS)))
    print('lines  %d bank line rows -> %s'
          % (len(UI_LINE_ROWS),
             ' '.join(row[3] for row in UI_LINE_ROWS)))
    if '--stats' in sys.argv:
        return
    bank_ok = verify_bank_slots(pl['char2idx'], pl['new'])
    if '--patch' not in sys.argv:
        print('(dry run; pass --patch to write %s)' % os.path.basename(OUT_ROM))
        return
    written = [(ctx['blk'], ctx['lo'], ctx['body'], ctx['hi'] - ctx['lo'])
               for ctx in ctxs]
    # Regression bisection (AGENTS #4): keep every registration, code page, font
    # and dictionary byte-identical, but suppress chosen writes so the shipped
    # ROM can be probed with one variable changed at a time.
    sk = os.environ.get('TK_SKIP_BLOCKS', '')
    if sk:
        want = ({c['blk'] for c in ctxs} if sk == 'all'
                else {int(x) for x in sk.split(',') if x.strip()})
        kept = [w for w in written if w[0] not in want]
        print('SKIP-WRITE blocks: %d of %d suppressed' % (len(written) - len(kept), len(written)))
        written = kept
    patch(rom, code, written, pl['char2idx'], pl['need'], pl['page'], edits,
          pl['inplace'], pl['bodies'])
    ok = bank_ok
    for ctx in ctxs:
        o = verify(pl['char2idx'], ctx, ctx['lo'], len(ctx['body']))
        print('block %d round trip: %s' % (ctx['blk'], 'OK' if o else 'FAILED'))
        ok &= o
    pcode = Codec(T.Rom(OUT_ROM))
    pcode.names = {i: c for c, i in pl['char2idx'].items()}
    o = verify_prompt(pl['char2idx'], pcode)
    print('prompt boxes: %s' % ('OK' if o else 'FAILED'))
    ok &= o
    o = verify_name(pl['char2idx'], OUT_ROM)
    print('default name: %s' % ('OK' if o else 'FAILED'))
    ok &= o
    ok &= verify_name_tables(pl['char2idx'], OUT_ROM)
    ok &= verify_ui_text(pl['char2idx'], OUT_ROM)
    ok &= verify_ui_lines(pl['char2idx'], OUT_ROM)
    ok &= verify_inplace(pl['inplace'], pl['char2idx'])
    ok &= verify_font(pl)
    print('VERDICT: %s' % ('all checks passed' if ok else 'SEE ABOVE'))
    if '--patch' in sys.argv and not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
