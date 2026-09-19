# 中文版交付说明 / Chinese patch — delivery status

权威状态文件。**动手前先读 `AGENTS.md`**（ROM/文档/脚本的存放规则与工程纪律）。旧交接记录
（`docs/history/HANDOFF_v1_2026-09-16.md`、`docs/history/HANDOFF_v2_2026-09-18.md`）里的若干数字已被
实测推翻（见下文「对旧交接的更正」），不得引用。

日期：2026-09-20。

## 一、交付物

| 文件 | md5 | 说明 |
|---|---|---|
| `rom_prologue_zh.sfc` | `4059c0cbc50a7a870f2f3006d6f77b20` | **交付版本**（4 MB LoROM，日版 Rev 1 基线） |
| `rom_original_japanese.sfc` | `cd36eb8982de4bf8369deb9f2f23e590` | 只读母盘，任何工具都不得写入 |

`rom_prologue_zh_DRAFT_乱码待修.sfc`、`rom_prologue_zh_jis.sfc`、`tokimeki_chinese_font.sfc`、
`ctrltest_simple.sfc` 及其 `.srm` 存档是历史中间产物（JIS 顶替方案时代），2026-09-20 清理时已删除，
完整副本保留在 `~/retro/tokimeki.backup.2609200007.tar.gz`。
当初作为问题证据的 17 张乱码截图已归档到 `docs/history/evidence_jis_2026-09-18/`。
上游命名的原版转储（`Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc`，与母盘
字节相同）和它的两个 `.srm` 已移出项目，放在 `~/retro/roms/`；**项目根目录从此只留上面这两颗 `.sfc`**，
所有工具一律按 `rom_original_japanese.sfc` 这个名字读母盘（`tools/extract_all.py`、`tools/romlib.py`
已改）。

## 一之二、工作区结构（2026-09-20 两轮清理后）

```
AGENTS.md         规则：ROM/文档/脚本存放、工程纪律、后续 agent 待办
tools/            40 个脚本（清理前 131 → 61 → 40）：验收链路 import 闭包 12 个，其余是文档引用的侦察仪表
docs/RELEASE_zh.md 本文件（唯一权威状态）
docs/research/    逆向证据与构建输入（glyph_alloc.json 是构建必读输入，勿删）
docs/prologue_zh/ 183 张渲染表 + index.txt 转录（可重生成）
docs/history/     旧交接/破解笔记/乱码截图，非权威（README 说明为何作废）
docs/ALL_CHARACTERS.txt  wiki 角色资料（15 个人物的日文名/生日/爱好/声优），人名译法的原始依据
translations/     手工中文稿（*.tsv、shrine_zh.json）＋ **name_glossary.tsv（人名对照表）
                  ＋ term_glossary.tsv（系统术语对照表：能力点标签等，翻译必读）**
start-screenshots/ 日文原版启动流程截图
rom_original_japanese.sfc / rom_prologue_zh.sfc  母盘与交付盘（根目录只此两颗 .sfc）
~/retro/roms/     项目外的 ROM 库：上游命名的原版转储与 .srm
```

第一轮删除：`out/`（29 MB 从日文 ROM 解出的 dump，可由 `tools/extract_all.py`、`tools/dump_text.py`、
`tools/extract_font.py` 重新生成）、68 个属于废弃方案的脚本（旧 JIS 槽位方案、死循环排查期的
一次性模拟器驱动），以及 4 个引用了已删脚本、删完即坏的工具，共 72 个，`tools/` 从 131 降到 61。
当时 `tools/build_prologue.py --patch` 仍产出字节完全相同的 `aac6c2af…`（该盘此后又被第一节的
交付盘取代了两轮：字形位移修正 → 人名修正），验收链路无恙。

第二轮（同日，字形修正之后）再删 21 个：编码破解期的一次性仪表（`align_table`、`build_table`、
`textdec_final`、`validate_encoding`、`prologue_vocab`）、被 `dis2.py` 取代的反汇编器（`disasm`、
`disasm65816`）、被 `poolscan.py` + `allocate()` 取代的「找空槽」方案（`find_slots`、`slotalloc`、
`census`、`fontcensus`）、被 `wqyfont.py` 取代的旧注入器 `font_wqy` 与被 `glyphview.py` 取代的
`show_glyph`、序章提取的早期版本（`prologue_atoms`、`prologue_script`、`prologue_struct`；
`prologue_boxes` 留着，因为活着的 `block_boxes.py`/`corpusmap.py` 真的 import 它）、J2E 模板生成器
`build_template`，以及结题的一次性实验（`start_matrix`、`ipsparse`、`price_rows`、`ptrscan`）。
它们写过的 10 份孤立产物
（`prologue_atoms.json`、`prologue_script.{json,txt}`、`prologue_frames.txt`、`slot_census.json`、
`glyph_usage.json`、`free_slots.txt`、
`block0_segments.txt`、`block0_span.txt`、`system_block_jp.txt`）一并删除；需要时从 git 历史取回。
删完复跑：`--patch` 仍产出 `9710c49b…`，`jisaudit`/`name_tables` 判定不变。

git 只跟踪源码、文档与手工译文；ROM/存档、`reference/`（18 MB 第三方素材）、`out/`、
渲染 PNG 与 `translations/pending.json`（可重生成的解包缓存）都在 `.gitignore` 里。

一条命令即可复现（1.5 秒，确定性；重复运行 md5 不变）：

```
python3 tools/build_prologue.py --patch
```

## 二、已完成的中文化范围

* **序章（block 144）全部 88 个文本框**，从标题界面 → 姓名输入 → 生日/血型 → 藤崎诗织问答 →
  序章蒙太奇 → 第一天字幕 → 状态界面，冷启动 96 次 A 键全程可玩，无死循环、无指针漂移。
* **每日事件池（block 8）125 个文本框**（晨间独白、提示语）。
* **系统 UI：绘制脚本 bank（`$180C0–$20000`）914 行**——标题/菜单/状态面板/日历/月份表/
  存档界面/社团/校庆/社团秘技/相册/音乐试听标签/姓名输入问题流/假名与汉字键盘。
* **能力点九项标签**（面板 `$1835A–$1839A` 与列表页 `$1AFB8–$1B007`，两处各 9 个）：
  体力 文科 理科 艺术 运动 杂学 容姿 毅力 **压力**。第 9 项日文是 `ストレス`，但它不是四个假名码，
  而是半宽双字格 `0x153`(スト)+`0x154`(レス) 两格，所以按字符搜镜像搜不到（见 `AGENTS.md` §四）。
  这一条由用户提供原版截图 `docs/research/status_panel_jp_original.png` 证实；构建新增 9 行、
  新增字模 **0** 个（压/力 序章早已拥有）。本批 9 个标签合计只改了 36 字节。
* **姓名相关**：28 条姓氏表、14×3 说话人名片表、`$1F890` 的 32 条预设姓名池、`$E803/04/05`
  子文本调用；`さん`/`ちゃん` 等称呼改为「同学」「小同学」，宽度与码数不变所以索引表无需改动。
* **运行时字形**：`$E806` 日期（月/日）、`$E807` 血型（ＡＢＯ/型）等在 stock 槽位就地重写。
* **片尾**：滚动字幕的职员表 + **片尾主题歌 26 句歌词**（`$1E4FE–$1E8A0`）。

## 三、字体：真正注入的文泉驿

* 文本编码为 `$F0–$FF` 双字节对，12 位索引上限 4095；字形记录 28 字节/个，每页 1170 槽，
  基址 `0x3E8000`，共 3 页（`tools/tmtext.py`）。
* **槽位账（2026-09-20 就地改写落地后重算）**：本批 1,152 个字里
  **617 个绑在自己码位的 stock 索引上**（A 档，`allocate()` 的 `stock_binding()`，零槽位成本），
  8 个共用标点走 `$40–$9F` 单字节码，只有 **527 个**真正占用新槽 —— 可用新槽 1,091，**剩余 564**。
  同一次构建改前是 1,144/1,166、只剩 22，也就是说这一步把可用容量放大了 **25 倍**；
  剩下 527 个新槽的字都是 JIS 带里**没有码位**的简体专用字（见 气 绘 压 运 习 说 你 吗…）。
* 构建报告 `font: 1169/1169 slots carry WenQuanYi (642 of them at stock indices)`，
  即屏幕上出现的每一个汉字都是文泉驿点阵，**没有任何一个用 JIS/繁体字形顶替**。
  （1,176 条生成记录落在 1,169 个槽上：7 个名字牌/数字格与本批用字同码位，合并了。）
* 就地改写的安全性就是「码位相等」这一条断言：`T.idx_to_char(T.char_to_idx(c)) == c` 才绑，
  所以仍在读那条索引的日文（文本块、`$A0–$EF` 宏体、绘制脚本 bank 的 ~1,700 条标签、姓名牌）
  事后读到的还是同一个字。守卫：`bank glyph slots: 0 collisions`、`0 unclaimed slot(s) changed`。
* 注入量是最小的：只为本补丁真正用到的字生成记录，未用到的槽位保持原样
  （`0 unclaimed slot(s) changed`）。

### 三之二、字模几何：14×14 点阵 field，全程 1:1，没有任何缩放

这是「右侧丢 1~2 px」问题的答案，也是校准字形位置时必须记住的换算：

* **记录**：28 字节 = 14 个小端 16 位行字。bit15 是该行**最左**一个像素，但**只有高 14 位会被画**
  （每字低 2 位恒为 0），所以一行实际只有 14 列可写。
* **落位**：14 行放在 16 行 cell 的第 1..14 行，第 0 与第 15 行由展开例程 `$80:D23D` 强制清空
  （`STZ $C100` @ `80D25F`、`STZ $C11E` @ `80D271`）。**cell 是 16×16，可写区是 14×14，
  右下角 2 列与上下各 1 行永远画不出来。**
* **运行时**只做 1bpp→2bpp：`plane1 = w | (w>>1)`。那个右移一位是**色平面**复制（描边/阴影用），
  **不是缩放**。整条链路点→点 1:1，屏幕上也不做放大。
* 因此**唯一合法的比例是「文泉驿位图 → 14 列 field → 16 px cell」**：`/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf`
  是 bitmap strike（FreeType size 14，asc 12 / desc 3），汉字墨迹恰好 **13 列 × 13 行**，advance 14，
  46 字抽样里 42 字左bearing 为 0（1 个 1、3 个 2），`装` 是 14 列宽，`（ Ｒ ［ ］` 会顶到第 14 行。
  日文原版字体的设计盒是**列 2..13 × 行 0..13**（600 个汉字里 462 个正好是这个 bbox）。
* **丢弃的机制**：`wqyfont.bitmap()` 以画布 `(9+dx, 9+dy)` 落笔后从 x=9 裁 14 列，所以
  记录列号 = 墨迹列号 + dx。旧的 `WQY_DX = 2` 让 13 列宽的字第 12 列落到记录第 14 列 —— 硬件不画 ——
  **1,154 个字里 1,023 个在 dx=2 下放不下，其中 1,019 个的右笔真的被切掉**。`WQY_DX = 1` 是不丢笔的最大
  位移（只有 `装` 等 5 字需回退）。
* `tools/wqy_calibrate.py` 当初**奖励了这种裁切**：它按「墨迹 bbox 与原版 bbox 的差」打分，被切掉右边的字
  反而完美匹配（dx=2 误差 1.93 / 40 字被切，dx=1 误差 2.11 / 0 字被切）。全局单偏移本身是对的（保住标点
  的左下位置），但必须在**不裁切**的约束下选。现在 `wqyfont.ink()` + `fit()` 在落笔前量墨迹并把偏移夹回
  14×14 内，所以后续几千个字不可能再退回去；`wqy_calibrate.py` 也改成**只在 `clip=0` 的候选里选优**，
  重跑它现在独立给出 `BEST (no clip): dx=+1 dy=+0 (err 2.11)`（dx=0/1 是仅有的两个零裁切候选，1 更接近原版）。
* **修正后实测**：右边缘落在记录第 13 列（与日文字体同边）的字 **1,019 / 1,154**，被丢弃的墨点 **0**。

## 四、验收 gate（按顺序，全部通过才算好构建）

```
python3 tools/build_prologue.py --patch          # VERDICT: all checks passed
python3 tools/prologue_play.py rom_prologue_zh.sfc 96 --boot   # 96 presses, 366 distinct pages, kana=0
cp <walk log> /tmp/play/boot_walk_zh.txt
python3 tools/prologue_shots.py /tmp/play/boot_walk_zh.txt docs/prologue_zh   # 88 boxes, 183 sheets
python3 tools/jisaudit.py docs/prologue_zh rom_prologue_zh.sfc  # on-grid foreign: 0（余下 3 项全是离格噪声，见下）
python3 tools/name_tables.py rom_prologue_zh.sfc # PASS: 0/55 name records still hold kana or an unknown slot
```

注意事项（都是踩过的坑）：

1. trace 运行期间不要重新构建 ROM；模拟器同一时刻只能有一个 `rom.sfc` 槽位，禁止并行 trace。
2. `prologue_shots.py` 从 `dirname(transcript)/pp_rom_prologue_zh` 读帧，字幕与帧必须来自同一次
   walk，否则会退化成 `88 boxes, 3 sheets` + 一长串 `no frame for:`。
3. `no frame for: 14`、`pin '大': over-budget 1 B`、`pin '搭': over-budget 0 B`、以及 `佗`
   （闪烁前进箭头）和 0 行的 `「`（框体装饰）都是正常现象，不是缺陷。
4. `prologue_play.py | grep -c` 在干净日志上会以 1 退出（零匹配），kana=0 即为通过。
5. `jisaudit` 必须跑在**当前 ROM 之后**重截的帧上，否则会用旧字形的判定冒充新构建。
6. 不要用 `bytes.replace()` 改二进制；对 ROM 的写入只允许 `tools/build_prologue.py`。
7. `jisaudit` 的输出按 **on/off grid** 分成两组，**判定只看 `on`**（文本 cell 恒定起于
   `x % 16 == 15`、`y % 16 == 1`）。`ui_refs.cells()` 会把 14×14 窗口在**每一个像素**上滑动，因此也会
   报出离格匹配：框线/高亮（`off symbol 010(￣) 011(＿)`），以及**真实 cell 左上 1 px 处仍存活的日文字模**
   （当前构建只剩 `off inline 210(一)`）。后者是 dx=1 之后我们的字形比日文原版恰好左 1 px、上 1 行
   造成的窗口错位：原版记录墨迹盒是列 2..13 / 行 1..13，我们的记录是列 1..13 / 行 0..12，
   于是把 14×14 窗口放在真格子左上 1 px 处去读，读出来的图案正好等于那条**没被改写过的** stock 记录；
   而落在格子上（正确位置）的窗口匹配的是我们自己的记录。
   历史文档里「2 foreign slots: 010/011」这条基线本身就是离格噪声，不要拿它当期望值。
   **这一条同时是就地改写的屏幕侧证据**：上一个构建的离格项里有 `5DE(三)` 与 `7AB(是)`，
   这次两者消失，正是因为 A 档把 0x5DE/0x7AB 那两条记录就地换成了文泉驿的 `三`/`是`——
   离 1 px 的窗口再也读不到日文字模，而落在格子上的窗口读到的还是同一个字。
   本次构建实测：**on-grid 零外来记录，off 只剩 3 项噪声（210x21 / 010x66 / 011x34）**。

## 五、剩余工作（2026-09-20 目标变更后重估）

目标已改为**游戏内文本不留一个日文字符**（图片素材/贴图除外）。这使「整体换字」成为合法策略，
本节原先记的上限随之作废：`1166` 从来不是引擎限制，而是我们自己定的保留规则（不去覆盖仍被
**未翻译**日文引用的 stock 槽位）。撤掉该规则后，可用记录 = 可寻址字模空间本身。

实测口径改用 `tools/corpus_from_dump.py`（读 J2E 解码后的完整脚本），**不要再引用**
`tools/corpusmap.py` 的总数——它按排序指针推 block 结尾，把 block 133 之后 1,764,113 字节的非文本
当成正文，所有总量都被放大到不可信。

| 全剧本规模 | 142 个 TKSC 文件 / **25,777 行** / **485,739** 个字形位置 |
| 源文本不同汉字 | **1,259**，且 **100% 已在 stock 汉字带内**（`BIGTOKI.EUC` 1267、`bigtoki2.euc` 1294，互相印证） |
| 源文本不同假名 | 158 个，占**位置数的 62.3%**，在译文里几乎全部消失 |
| 可寻址字模 | `MAX_INDEX 0xDB6` = **3,510**；其中 **126** 个的 pair 低字节撞 TERM（`$0A`、`$A0-$A7`）会被回退扫描切断 → **3,384 可用**；汉字带 3,057，假名区 453 在无人再发 1 字节假名码后可回收 |
| 就地改写率 | 96 行真实译文（`translations/TKSC2/3_zh.tsv`）实测：**66% 的目标汉字已有字模**；需新增的 34% 是一批**封闭**的简体独有高频字（为 这 说 还 门 间 阳 让 变 办 …），早于语料饱和。**已落地**：`allocate()` 的 `stock_binding()` 把本批 1,152 字中 **617 字**绑回各自的 stock 索引，新槽开销从 1,144 降到 **527**（可用新槽 1,091，剩 **564**） |
| 字节 | 同内容中文只用 **0.58 倍**字形数；两批已译文本 **0/213 个 box 溢出**，省 18% 与 24% → box 平铺可谈，不是墙 |
| 1 字节码表 | `$40-$9F` = 96 项：71 假名 + 15 汉字 + 3 符号，**0 个 ASCII**，94 个不同目标槽位 → 不存在「半字节英文字母」问题 |
| 行内控制码 | 整个抽取语料里只有 `<N>`（3,943 次）与 `<END>`（309 次），译者需保留的控制面就这两项 |

剩下的真实工作量因此是三件事，没有一件是字库容量：

1. **翻译 25,777 行**。已完成：序章 88 box、block 8 的 125 box、系统 UI 与 912 行字卡、名字表，
   以及对白 98 行（`translations/TKSC2/3_zh.tsv`）。`translations/pending.json` 就是全量工单
   （142 文件 × 行号 × 日文原文）。
2. **汉字化的姓名输入键盘**（任务 #17）：取样行 `1F3DA/1F482/1F558/1FB50` 与 96 项 1 字节码表都是
   可重指的数据表，属数据改动而非引擎改动；旧日文名字码表按用户指示放弃其正确性。
3. **块流之外的日文**（任务 #18）：`$A0-$EF` 的 phrase/macro 体在 bank `$B9`，`$E8xx-$EFxx` 的
   sub-text 体在 bank `$C3`；翻完 160 个 TEXT_PTRS block 也覆盖不到它们，只走 block 的「零日文」
   审计会**假通过**。

**必须记住的代价**：整体覆盖 stock 记录之后，尚未翻译的块不再是显示日文，而是显示**读得通但
完全错误**的中文——半成品比现状更糟。所以**「把索引改指成别的语素」（B 档）**必须与「该索引被所有
仍存活的引用翻译完毕」同时发生，不能作为中间状态发布。**但不受此限的是「同码位就地改写」（A 档）**：
只要新记录画的正是该索引本来的那个码位（`T.idx_to_char(idx) == c`），残余日文读到的仍是同一个字，
换的只是字体，所以随时可做——这正是本批 617 个字所走的路。判据只有一句：改完之后那个索引还读得出原文吗？
旧的 8 MB / ExLoROM 第 4 页扩容（真实增益只有 586 个字模）在
3,384 的预算下**不再需要**；`$19Axx` 残句与 romaji 昵称这类零散项，并入整体翻译后自然消化。

## 六、对旧交接（`docs/history/`）的更正

* 主题歌「还差约 150 个字」是**按总字数**算的错账。一批文本只为字库里**还没有**的字付费：
  26 句歌词实测只花 **12** 个字模，本构建已经收录。
* 「需要解决：正确的槽位寻址公式」（v2 交接 P1）——已解决并写入 `tools/tmtext.py`
  （`GLYPH_BASE + (idx//1170)*0x8000 + (idx%1170)*28`），`$80:D490` 的三次 `SBC #$0492` 与之吻合。
* v2 交接（`docs/history/HANDOFF_v2_2026-09-18.md` §码表）里的「`0xA0-0xFC` 高字节 × 任意低字节
  = 2 字节汉字码，走行 delta 表」**是错的**：`$A0-$E7` 是 phrase 宏、`$E8-$EF` 是 sub-text 调用，
  `$A0-$A7` 具体是句末标点宏，双字节字形只存在于 `$F0-$FF`。同样错的还有
  `notes_crack_2026-09-17.md` 的「`0x09` = 空格已确认」——`$09` 吃 3 字节，`$80:CC20` 把 16 位操作数
  装进格游标，它**不是**全角空格。见 `docs/research/glyph-addressing.md` 与
  `docs/research/control-codes.md`。
* 「字形偏移按 bbox 校准到原版」这条方法论**要加约束**：记录只有 14 列会被画，按 bbox 打分会奖励
  把右边切掉的位移（见 §三之二）。`dx=2` 就是这么被选中的，现已改为 `dx=1`。
* 「P1: 用 S2J_SLOT 把简体字形写入 JIS 槽位」——**思路已按新目标重新采纳，但含义要分清**：
  用户拒绝的是「拿 JIS/繁体字**当成另一个字显示**」（字不对）。而**复用槽位地址**、位图仍是我们
  自己渲染的文泉驿、且该槽位原本的日文汉字与我们的汉字**是同一个字**（如 日/月/藤/院），既不改变
  玩家看到的字，也不新占槽位——这已在生产里跑通 24 条（`inplace`）。整体换字方案就是把这条规则
  从 24 条推广到全部可就地改写的字（任务 #15）。
* 「P0: 确认序章中文显示」——已完成，见第四节 gate 与 `docs/prologue_zh/`（183 张渲染表 + `index.txt`）。
