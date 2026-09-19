# AGENTS.md — 《心跳回忆：传说的树下》SFC 汉化项目

目标：**游戏内文本不留一个日文字符**（图片素材/贴图除外）。字库必须真的是文泉驿点阵，
不接受用 JIS/繁体字「当成另一个字」顶替显示。

**唯一权威状态文件是 `docs/RELEASE_zh.md`**（交付物 md5、验收 gate、实测容量、剩余工作）。
本文件只写规则与纪律，不复制它的数字。动手前先读它的第四节（验收 gate）与第五节（剩余工作）。

## 一、ROM 与模拟器规则

* 根目录**只允许两个** `.sfc`，文件名固定，20 个脚本按这两个名字硬编码：
  * `rom_original_japanese.sfc` —— 母盘（日版 Rev 1，md5 `cd36eb8982de4bf8369deb9f2f23e590`）。
    **只读，任何工具都不得写入**；它不在 git 里，所以 md5 是唯一的守卫，动完手必须复述。
  * `rom_prologue_zh.sfc` —— 唯一交付盘，**只能由 `tools/build_prologue.py --patch` 写**
    （当前 `9710c49b40f5a29d14178d698c99a74f`）。
* 不要往项目目录里再放任何 ROM / 存档 / IPS。上游命名的原版与 `.srm` 库放在
  **`~/retro/roms/`（项目外）**；`.gitignore` 已经屏蔽 `*.sfc *.smc *.srm *.ips *.bps *.xdelta`。
* 模拟器只有一个共享槽位：`tools/slot.py` 会把指定 ROM 装进
  `stable_retro/.../TokimekiSFC-Snes-v0/rom.sfc`。因此**同一时刻只允许一条 trace**，
  且 **trace 运行期间禁止重新构建 ROM**——否则工具会静默追踪上一次留下的那颗盘。
* 帧/状态是易腐的：改了 ROM 就必须重跑 walk 并重截帧，旧帧上的判定不能冒充新构建。
* 全量备份在 `~/retro/tokimeki.backup.2609200007.tar.gz`（含清理前的 131 个脚本与上游命名的 ROM）。

## 二、目录归属

```
tools/         40 个脚本：验收链路 + 再推导仪表（见 §三）
AGENTS.md      本文件：规则
docs/RELEASE_zh.md        权威状态（md5 / gate / 容量 / 剩余工作）
docs/research/   逆向证据（*.md 是结论，附地址与偏移）与构建输入/输出
docs/prologue_zh/  183 张渲染表 + index.txt 转录（可重生成；PNG 不入库）
docs/history/    旧交接与破解笔记，**非权威**，只查不引（README 里写明为何作废）
docs/ALL_CHARACTERS.txt  wiki 角色资料（15 个人物），人名译法的原始依据
translations/    手工中文稿 *.tsv / *_zh.txt 是真值；**name_glossary.tsv（人名）与
                 term_glossary.tsv（系统术语）是译法口径表**；pending.json 可重生成、不入库
reference/       J2E 第三方素材（18 MB），只读输入，不入库
out/             从日文 ROM dump 出来的分析用文本，可重生成，不入库（当前不存在；
                 需要时由 tools/extract_all.py、tools/dump_text.py、tools/extract_font.py 生成）
```

* `docs/research/` 里这三份是**构建必读输入**，删了就构建不出来：`glyph_alloc.json`、
  `nameplate_glyph_indices.json`、`ui_glyph_indices.json`；`prologue_zh.txt` / `block8_zh.txt` 是
  `BLOCKS` 直接读的活译文源。其余 json/txt 多为工具输出，引用它之前先确认还有生产者。
* 新脚本放 `tools/`，snake_case，docstring 第一句写清**它证明什么事实**；默认只读母盘，
  产物写 `/tmp` 或 `docs/research/`。一次性实验脚本用完就删（git 历史留得回来），
  不要把探索期脚本堆进目录——上一轮就是这样攒出 131 个脚本再清掉 68 个的。
* `docs/history/` 里的旧交接文档与破解笔记**数字不可引用**。凡是「某处还差 N 个字」这类账，
  按 `glyph_alloc.json` 的增量口径重算。

## 三、验收 gate（顺序即语义，全绿才算好构建）

见 `docs/RELEASE_zh.md` §四：`build_prologue.py --patch` → `prologue_play.py … --boot` →
`prologue_shots.py` → `jisaudit.py` → `name_tables.py`。要点：

1. 字幕与帧必须来自**同一次** walk。
2. `jisaudit` 的判定只看 **`on`（落在文本网格 x%16==15、y%16==1 上）** 那一半；
   `off` 是滑窗噪声，不是缺陷。
3. `prologue_play.py | grep -c` 在干净日志上以 1 退出，kana=0 即通过。
4. 禁止用 `bytes.replace()` 之类改二进制；对 ROM 的写入只允许走构建脚本。
5. 构建是确定性、1.5 秒的，所以**每次编辑后都重跑**，让 round-trip 断言去证明编码。

## 四、工程纪律（都是踩过的坑）

* **人名一律照 `translations/name_glossary.tsv`，系统术语照 `translations/term_glossary.tsv`**
  （依据 `docs/ALL_CHARACTERS.txt` 的 wiki 资料 + 对全部日文脚本说话人标签的实测）。人名表的第 3 列
  区分 `name`（专名，译法固定）/ `role`（身份词，按上下文）/ `ph`（占位符）；
  `tools/translate_batch.py` 的 `<N>` 占位就是读这一列，**不要**再往脚本里手写人名列表。
  踩过的三个坑：`伊集院レイ` 曾按音译写成「伊集院零」，通行译法是**伊集院丽**（レイ＝麗）；
  能力点标签里 `体調` 曾被译成「健康」、`容姿` 曾被译成「容貌」，标准译名是**体力**与**容姿**
  （后者日文本来就写作容姿）；第 9 项 `ストレス`（标准译名**压力**）曾被判成「本盘没有」，
  其实面板与列表页各有 **9** 个标签，只是第 9 个用半宽双字格拼出来、按字符搜不到（见下一条）。
  旧人名列表里还留着三个本作出场数为 0 的二代名字
  （`皐月優`/`篠原鞠絵`/`鏡美帆`）。
* **找一个词必须逐字允许全部三种拼法**：同一个字符既可能是 `$F0-$FF` 双字节字形码，也可能是
  `$40-$9F` 单字节 SB 码（表在 file `0x18000`，96 项），还可能是 `$0153-$01C4` 那批**不对应任何
  JIS 字符**的补充格（半宽假名**两字一格**，如 0x153=スト、0x154=レス）。一个词常常三种混用：
  `ストレス` 在剧情里是 `F1 15 / 4C(ト的 SB 码) / F1 48 / F1 15`，只按双字节整词搜镜像会**漏报**，
  据此下「本盘没有某词」的结论是错的。
  另外两种证据要分开说：镜像里的**字节匹配**可能只是巧合（没解析过上下文就不能据此下「本盘有/没有
  某词」的结论），而 `$180C0-$20000` 绘制脚本 bank、`$A0-$EF` phrase 体与 `$E8xx` sub-text 体
  （任务 #18）根本不在按 TEXT_PTRS 解出的语料里，那边「查不到」也不等于「没有」。
* **先翻译、后生成字库**：字库是「用到的字」的集合，任何批次只为字库里**还没有**的字付费。
* **半成品比现状更糟**：整体覆盖 stock 记录之后，未翻译的块不再是日文，而是读得通但完全错误的
  中文。所以「骑乘/覆盖某个 stock 索引」必须与「该索引被所有仍存活的引用翻译完毕」同时发生。
* **长度改动只在被执行的码全为 1 字节时才安全**：有些控制码吃操作数（`$00/$01/$28` 吃 2、
  `$09` 吃 3、`$0F` 吃 5）。每个块在重排前都要用 `tools/ctrl_advance.py` / `ctrl_widths.py` 查。
* **box 起点来自指针网格**：每个 box 的终止符必须落在与日文 box 相同的文件偏移上，
  `capacity_i = span_i`（无余量），所以只能在框内重排，不能跨框借字节。
* **句子的组成部分可能散在三个 bank**：`$A0-$EF` 的 phrase 体和 `$E8xx` 的 sub-text 体会被
  调用点插入句中，所以整段连续字节扫描会**查不到游戏明明显示的句子**。定位文本先数相邻字节对，
  再跟 `SUB_TABLE + (BE16 & $07FF)*2`。
* **`«A0»-«A7»` 是随机的句号变体**：同一行冷启动之间结尾标点会 legitimately 变化，不是 bug。
* **闪烁的粉色前进箭头**会盖住它所在的格子，OCR 出一堆假「坏字形」；诊断疑似坏字要裁格子
  跟 `glyph_offset(idx)` 记录做位距，dist 0-2 才算真画错了。

## 五、字形与编码速查（最容易踩错的几条）

* 字模记录 28 字节 = 14 个小端 16 位行字，bit15 是最左像素，**只有高 14 位会被画**；
  14 行放进 16×16 cell 的第 1..14 行。**可写区 14×14，右下角 2 列与上下各 1 行永远画不出来，
  全程 1:1，不存在缩放。** 细节与推导：`docs/RELEASE_zh.md` §三之二、
  `docs/research/glyph-addressing.md`。
* 文泉驿 13px 是位图 strike（汉字墨迹 13×13），所以位移只能是 `dx=1`；`wqyfont.fit()`
  在落笔前夹住越界墨迹，别绕过它自己画。`wqy_calibrate.py` 现在只在 `clip=0` 的候选里选优。
* 索引→记录：`0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28`，`MAX_INDEX = 0xDB6`。
* 码带：`00-3F` 控制、`40-9F` SB 单字节（表在 file `0x18000`）、`A0-E7` phrase 宏、
  `E8-EF` sub-text、`F0-FF` 双字节字形。**`$A0-$FC` 不是双字节汉字码**（旧笔记的错误）。
  逐码语义表：`docs/research/control-codes.md`。

## 六、后续 agent 需要跟进的事

按 `docs/RELEASE_zh.md` §五，容量与字节都不是墙，**墙是翻译量**（25,777 行 / 485,739 个字形位置，
工单就是 `translations/pending.json`）。明确待办：

1. **#15 让 `allocate()` 骑乘 stock 索引**：当 JIS 字与我们的字是同一个字（日/月/藤/院…）时
   就地重写那条 stock 记录，不新占槽位——现在这条路只跑了 24 条。
   验收：`in-place glyphs: N records … OK` 增长且 `0 unclaimed slot(s) changed` 不破。
2. **#16 词表预算 gate**：把「本批新增字模数」变成构建期断言（增量口径，见 §四 第一条）。
3. **#17 汉字化的姓名输入键盘**：`$40-$9F` 96 项表与 `$1F2D4` 键盘网格都是可重指的数据表，
   属数据改动；旧日文名字码表的正确性按用户指示放弃。
4. **#18 宏体与 sub-text 体（bank `$B9` / `$C3`）**：翻完 160 个 TEXT_PTRS block 也覆盖不到它们，
   只走 block 的「零日文」审计会**假通过**。`tools/macroband.py` 是现成的侦察仪表。
5. 每条文字批次落库后，**必须**重跑 §三 全链并更新 `docs/RELEASE_zh.md`（含 md5）。

`tools/prologue_play.py` 走的是黑板式鼠标点选（`OPTION1 = (110, 165)`，指针要停在选项文字上按 A
才有响应），盲按 A 会让序章看起来不可达——那是脚本问题，不是补丁缺陷。
