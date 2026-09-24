# 心跳回忆 SFC 汉化 · 现状

这份文件只写「现在是什么样」：做到哪了、盘是哪颗、怎么验、目录里有什么。
规则和工作纪律在 `AGENTS.md`；每批干了什么的流水账不在这里，看 git log；
`docs/history/` 的旧交接文档已作废，只用来查历史，数字不能引用。

最后核对：2026-09-25。下面每个数字都是当天从当前这颗盘上量出来的。

## 一、进度

目标是一句话：**游戏里看得见的文本不留一个日文字符**（图片、贴图里烧死的字除外）。

| 做了什么 | 现在的量 | 从哪量出来的 |
|---|---|---|
| 剧情文本块 | 142 块全部注册、全部译完，构建报告 142/142 都是 `0 over, 0 broken` | `tools/build_prologue.py --patch` |
| 全库逐框覆盖 | 142 块逐块全框渲染，22,600 框 / 270,517 格：假名 0、未知格 0、没画到的汉字格 0 | `tools/render_prologue.py rom_prologue_zh.sfc <块> 0:<末框>`，142 个注册块挨个跑 |
| 中文正文 | 143 个译文源文件合计 45,933 行，逐行扫假名字母为 0 | `docs/research/*_zh.txt`（含 `prologue_zh.txt`） |
| 序章 | 88 框，冷启动走查全程通 | `render_prologue.py … 144 0:87` |
| 每日提示池 | 125 框 | 同上，block 8 |
| 电话 / 系统池 | 725 框 | 同上，block 0 |
| 画面固定文字 | 姓名输入等 1,026 条、设置与播报 477 行全部落库 | 构建报告 `ui:` / `bank lines:` |
| 共享短语词典 | 1,015 条，1,011 条原地写入中文；剩 4 条（`e809`/`eb6c`/`eca9`/`ed35`）自己的跨度只有 1~5 B，塞不下正文，于是永不折叠、由调用点把中文写在框里 | 构建报告 `phrase bodies:` / `shorten eXXXX` |
| 词典体回读 | 中文行实际调用到的 968 条词典体、共 59,378 次调用，逐条按本次码表回读：**0 条还带假名**；每次构建都断言这一条 | 构建报告 `bodies drawn:`，明细 `python3 tools/segtext.py rom_prologue_zh.sfc --dict` |
| 人名 / 地点池 | 76 条记录零假名 | `tools/name_tables.py` |
| 拼接接缝 | 同一段里「标点紧跟标点」238 行（删「，」211、「、」25、「；」1、「。」1）已全部瘦身，现在**全库 INSIDE = 0**（母盘自己量出 196 处，我们比原版还干净）；跨步之间「。」叠两遍 115 处——**母盘同族 111 处，是引擎在步界自己补的，不是文案缺陷** | `python3 tools/segtext.py rom_prologue_zh.sfc --blocks`（母盘基线：把盘名换成 `rom_original_japanese.sfc` 再跑一遍） |
| 字库 | 2,304 格全部是文泉驿点阵（1,190 格写在自己码位上、972 格整带回填），无一处用日文字形顶替 | 构建报告 `font:` |
| 用字 | 出货文本 2,160 个不同汉字，2,159 个已有字模 | `tools/charledger.py report` |

验收抽查（就在当前交付盘上）：block 0/2/8/144 四段共 981 框，`0 kana cells, 0 "?" cells`；
`name_tables` PASS；`segtext --blocks` 全库段内标点缝 0 处。
唯一还留在译文里的假名区段字符是 `・`（中点，681 处）和 `ー`（长音符，16 处），
它们在这套字库里就是顿号和横线的字形，画出来是标点不是假名。

还剩什么：

1. **文案质量**，不是覆盖问题。全库口吻通读、批次 Z 那几池的抽查还没做——这是剩下唯一的大活。
2. 绘制脚本 bank 里还有 135 段三字以上的原文没动。它们要么是中日同形的汉字（`清川`、`科学部`、
   `海水浴`、`胆 蛋`），要么是符号和罗马字（`（左）`、`ＡＢ型`、`ＫＮＭ`），玩家看不出是日文。
   要清零也做得到，只是收益很低。（复扫：`python3 tools/bank_rows.py rom_prologue_zh.sfc`）
3. 图片素材里的字（贴图、LOGO）不在目标里。

## 二、盘

| 文件 | md5 | 说明 |
|---|---|---|
| `rom_prologue_zh.sfc` | `8acd098ce386d1f710a677beaa60894c` | 唯一的中文盘。只有 `tools/build_prologue.py --patch` 能写它 |
| `rom_original_japanese.sfc` | `cd36eb8982de4bf8369deb9f2f23e590` | 日版 Rev 1 母盘，只读，谁都不许写 |

根目录只留这两颗 `.sfc`（`.gitignore` 已屏蔽所有 ROM、存档和 IPS）。上游命名的原版和 `.srm`
在项目外的 `~/retro/roms/`。全量备份：`~/retro/tokimeki.backup.2609200007.tar.gz`。
两件待用户处置：根目录还有两颗模拟器写出来的存档（`rom_original_japanese.srm`、
`rom_prologue_zh.srm`），按上面的规矩该挪去 `~/retro/roms/`，但那是用户的通关进度，没动它。
构建是确定性的：同一份文案重复跑，盘号不变（这批落库后又完整跑了一次，还是 `8acd098c…`）。
所以盘号不需要版本管理，也**不出中间交付盘**——这颗盘每批都被覆盖着重建，只为了跑验收链，
真正的交付只有全文翻译完成、字库整带回填之后的最后一次。历史上那些被取代的盘号不在本文档里，
它们只活在 git log 的提交说明中。

复现整颗盘：

```
python3 tools/build_prologue.py --patch        # 约一分半
```

## 三、验收

**静态层**，每批改完译文都要跑，全绿才算好构建：

```
python3 tools/build_prologue.py --patch            # 每块 0 over, 0 broken + bodies drawn: 0 kana，末尾 VERDICT: all checks passed
python3 tools/render_prologue.py rom_prologue_zh.sfc 0 0:724     # 0 kana cells, 0 "?" cells
python3 tools/render_prologue.py rom_prologue_zh.sfc 2 0:42
python3 tools/render_prologue.py rom_prologue_zh.sfc 8 0:124
python3 tools/render_prologue.py rom_prologue_zh.sfc 144 0:87
python3 tools/name_tables.py rom_prologue_zh.sfc   # PASS: 0/76
python3 tools/segtext.py rom_prologue_zh.sfc --blocks            # 段内标点缝 INSIDE 0（JOIN 那 115 处是引擎步界，母盘同族 111）
python3 tools/charledger.py ingest && python3 tools/charledger.py report
```

`render_prologue.py` 直接从**打好补丁的盘**上把每个框解出来画图，并把画到的字模跟台账对一遍，
所以「框里还有没有假名」不用开模拟器就能判。第三个参数是闭区间，必须显式写——它同时是
「这批声称覆盖到哪一框」的声明。它读 `docs/research/blockN_enc.json`，那是每次构建顺手刷新的派生物，
现在不入库了。

两道新加的判据，都是补「字库整带回填之后回读不可信」这个洞：

* **构建内的 `bodies drawn:`**——`verify()` 把每行译文按本次码表展开，凡是中文行调用到的词典体
  （`$A0-$E7` 短语宏和 `$E8xx` 子句）都回读一遍，出现假名或没登记的字模槽就判失败。
  回填之后槽位的名字还是旧 JIS 字符，所以「读出来像日文」不再是证据，「这个槽画的是哪个字」才是。
* **`tools/segtext.py`**——按**脚本步**（`blockN_work.tsv` 那一行，也就是指针网格冻结的 span）
  而不是按框走字节，并且把 `〔姓〕/〔名〕`、`⟦E8xx⟧` 这类插入点留在原位。
  它把标点缝分三类：`INSIDE` 是同一段里真写出来的（可修，也是唯一该修的），
  `JOIN` 是引擎把两步拼进一个框时自己的终止标点和下一步首字符撞上（母盘同样有 111 处，别去追），
  `POOL-steps` 是插入点替出来的字符，列出来只为不再被当成缺字。
  `--dict` 那一路把每张词典体和它的引用数、容量、口径表行一起 dump，是「拼接读不懂」这类报告的唯一入口。

**模拟器层**只在改动会出现在序章画面上时才跑（改了序章本身、人名表、UI，或那些画面用到的字模）。
剧情池、电话池在序章里根本走不到，拿序章 walk 去验它们等于没验。

```
python3 tools/prologue_play.py rom_prologue_zh.sfc 96 --boot     # 记下日志路径
python3 tools/prologue_shots.py <那份日志> docs/prologue_zh
python3 tools/jisaudit.py docs/prologue_zh rom_prologue_zh.sfc
```

判读口径（字库整带回填之后就变了，别照旧文档理解）：`jisaudit` 报出来的名字是按 JIS 码位回读的
**索引旧名**，像素其实已经是重画后的中文点阵，所以「假名标签」不再等于缺陷。现在证明字库干净靠三条：
构建断言每一格都携带文泉驿格（`font: 2304/2304 … 0 unclaimed slot(s) changed`）、命中的格子逐条
比对位图、再加高频格抽查。`jisaudit` 只有落在文本网格上的那一半（`on`）有意义，`off` 是滑窗噪声。

最近一次模拟器整链（批次Z，盘 `3628a9f7…`）：冷启动→相册→姓名输入→生日→黑板→序章全程无黑屏，
`96 presses`、`88 boxes / 181 sheets`、`kana=0`，日期面板配色与母盘逐项一致。
本批（`8acd098c…`）没重走它：改的只有剧情池和电话池里多余的标点，那些画面序章本来就走不到，
走一遍等于没走；序章自己的 88 框和 UI/人名表是靠静态层按像素重画的（`render_prologue.py … 144 0:87`）。

## 四、目录

```
AGENTS.md                规则与工程纪律
docs/RELEASE_zh.md       本文件：现状
docs/research/           逆向结论（*.md）+ 构建输入 + 活译文源
docs/prologue_zh/        序章渲染表与 index.txt 转录（PNG 不入库）
docs/history/            旧交接与破解笔记，非权威（README 写了为什么作废）
docs/ALL_CHARACTERS.txt  wiki 角色资料（15 个人物），人名译法依据
tools/                   32 个脚本：验收链及其依赖 16 个，侦察仪表 16 个
translations/            三张口径表（人名/术语/短语）+ TM 命中表，中文正文在 docs/research/
reference/               J2E 第三方素材，只读输入，不入库
start-screenshots/       日文原版启动流程截图
out/                     分析文本与字库总览，由 `tools/dump_text.py`／`tools/extract_font.py` 从母盘重生成；
                         `charledger.py` 的用字台账 sqlite 也住在这里。都可重生成，不入库
```

`docs/research/` 里**删了就构建不出来**的：`glyph_alloc.json`、`nameplate_glyph_indices.json`、
`ui_glyph_indices.json`，以及全部 `blockN_zh.txt`（含 `prologue_zh.txt`、`block8_zh.txt`）——
这些是人写的中文正文，构建直接读。`blockN_work.tsv` 也留着：`poolsync.py` 每批要拿它做全库比对，
重生成得跑 142 次。

其余都是派生物，不入库、目录里也不留：`blockN_jp.txt`、`blockN_work.json` 由 `tools/block_work.py <块号>` 重生成，`blockN_enc.json`、`*_seg.txt` 由构建重生成。
整棵树现在 369 个跟踪文件；早期草稿和侦察期脚本清过两轮，名单在 git log 里（`cacb6b2`、`aa6cb4f`），要找回就从历史取。

`translations/` 里 `name_glossary.tsv`（64 行人名）、`term_glossary.tsv`（43 行系统术语）、
`phrase_glossary.tsv`（1,022 行短语词典）是口径表，改译法之前先看它们。
`pending.json` 是从 J2E 解码脚本导出的全量清单（142 个 TKSC 文件 / 25,769 行原文）。它只能用来
核对总量：TKSC 文件号和 ROM 里的块号大多相同**但不是一一对应**——`block_work.py 59` 就直接报
「TEXT_PTRS 最后一项，边界未知」，TKSC59 那些行的日文实际落在 block 60/64/65 里，而 TKSC3/TKSC137
是空文件。逐块的覆盖情况要看 `blockN_work.tsv` 与 `blockN_zh.txt` 的行数对不对得上，不要拿这张表当工单。

## 五、这套补丁怎么工作

从下往上三层。

**字模。** 引擎的字形记录是 28 字节 = 14 个小端 16 位行字，bit15 是最左像素，只有高 14 位会上屏。
所以格子是 16×16，能写的只有 14×14，右下两列和上下各一行永远画不出来；整条链路点对点，不做放大。
文泉驿点阵（`/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf`）的汉字墨迹正好 13×13，位移只能取
`dx=1`——取 `dx=2` 就会把 13 列宽的字切掉最后一笔。
索引到文件偏移：`0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28`。
可写范围到 `0x0DA5` 为止，**第 3 页最后 16 格不是字模，是引擎的画笔调色板**（日期面板的粉红和蓝色
住在那里，详见 `docs/research/calendar-colour.md`）。
对位时不要把「墨迹的 bbox 跟原版对齐」当目标：只有 14 列会上屏，按 bbox 评分会奖励那种把右边切掉的
位移——`wqyfont.fit()` 在落笔前先把越界墨迹夹掉，别绕过它自己画。

**编码。** 一个字的写法有三种，同一句里可能混用：`$F0-$FF` 双字节字形码、`$40-$9F` 单字节码表
（96 项，去掉共享标点剩 86 项可派字，按全盘词频分配，用满就是零和——新批次的高频字会把老字挤出去，
老框立刻多 1~2 字节溢出，所以每批都要跑全部块）、以及 `$A0-$EF` / `$E8-$EF` 两段宏。
当前码表把 270,794 个字形位置中的 139,123 个压成了 1 字节。逐码语义见 `docs/research/control-codes.md`。

**框。** 文本框起点来自指针网格，每个框的容量就等于日文那个框的跨度，没有余量，也不能跨框借字节。
框的最后一个字节必须等于日文框的终止码：写成 `？` 而那边是 `。`，或者多写了 `。」`，构建就会报
`terminator a0 vs a1` / `a0 vs a4`。这是编码对不齐，不是文案问题。
2~3 字节的紧格子里本来就放不下句子——句子活在共享短语词典里，一个宏体平均被七个框调用，
改一条词典体就同时覆盖所有引用它的框。所以正确做法是照 `phrase_glossary.tsv` 的正文写，
而不是把中文硬塞进格子。

## 六、已知的取舍

* 五十音图不再保真：姓名输入的假名键盘读出来是中文同音字，打出去的仍是假名索引。
  键盘那 71 条池行是**输入语义**数据，重编成中文索引会让姓名输入直接黑屏（那颗盘实测过）。
* 字库容量已经不是问题（可用新格 1,329，全文只用 2,160 个不同汉字），所以任何一批都不用再为了
  「这个字买不买得起槽」改写文案。8 MB / ExLoROM 扩容、第 4 页字形表这条路关掉。
* 真墙只有两条：框宽度（窄框只能按 `term_glossary.tsv` 的简称写）和码表零和。
* 剧透保护：隐藏角色在揭示前保持「谜之少女」，丽的露馅句单独按女性口吻处理。
