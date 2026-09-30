# 心跳回忆（SFC，日版 Rev-1）——65816 事实速查

**本页只列已用反汇编或实机帧证明过的事实，全部可复现。**同目录的
`glyph-addressing.md`、`control-codes.md`、`control-widths.md` 是推导过程与逐码语义表；
状态与验收在 `PROGRESS.md`；动手纪律在 `AGENTS.md`。
破解期的旧交接笔记（`docs/history/`，已从树里删除）里有三条**已证伪**的模型，不要照着开工：
`ROWDELTA` 行差表、`$0153` 带的 SJIS 重映射、以及「文本表 `0x2371BF` ＋字偏移×2」那个池指针公式。

## ROM 与地址换算

* 4 MB LoROM，日版 Rev 1，原镜像 `Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc`（md5 `cd36eb8982de4bf8369deb9f2f23e590`，
  **只读**）。校验头在 file `0x7FC0`。
* file = (bank - 0x80) * 0x8000 + addr - 0x8000，即 `$80:D490` = file `0x5490`。
  旧笔记里 `$81:D490` / `0xD490` 两种写法混用过，本项目一律用 `$80:xxxx` + 括号里的 file 偏移。
* 反汇编仪表：`python3 tools/dis2.py <rom> <file_off> <len> <base>`。

## 文本调度器与码带

* 分发器 `$80:CA6D`；处理函数表（LE16）在 file `0x4B0B`，只有 `$00-$2E` 是表内项，
  `$30-$37` / `$38-$3F` 由 `$80:CAEB` 各自索引到 `$CD8C` / `$CD67`，是合法码。
* 码带：`00-3F` 控制、`40-9F` SB 单字节字形（BE16 表 file `0x18000`，`idx = BE16 & $0FFF`）、
  `A0-E7` phrase 宏（表 file `0x1CCAA5`，体在 bank `$B9`）、`E8-EF` 双字节 sub-text
  （表 file `0x2196A8`，体在 bank `$C3`）、`F0-FF` 双字节字形（`idx = ((hi<<8)|lo) & $0FFF`）。
* **`$A0-$FC` 不是双字节汉字码**（旧笔记的错误）：`$A0-$A7` 是句末标点宏，且句末标点带随机性。
* 有些控制码**吃操作数**：`$00/$01/$02/$04/$07/$08/$28` 与 `$30-$37` 吃 2 字节、`$09` 吃 3、
  `$03` 吃 4、`$0F` 吃 5。`$01 xx`（`$80:CB73`）是**计算式前跳**，其后的字节部分是跳转表不是文本。
  逐码表：`docs/research/control-codes.md`；某块实际执行到哪些码：`tools/ctrl_widths.py`。
* `$12/$13/$16/$17` 是**子解析**（压游标后重进分发器到 WRAM `$0E00/$0E08/$0E10`/`$83:8318`），
  其中 `$0E00` 姓、`$0E08` 名就是玩家姓名缓冲，编码与字库同页。

## 文本块定位

* TEXT_PTRS 块起点来自 `$82:A1D6`：**per-object base（表在 `$82:$9A25`）+ 2 × 事件脚本操作数**，
  随后只探测一字节决定去留：`byte @ P-1 ∈ {$0A} ∪ $A0-$A7` 才保留，否则**递减**回退。
  所以 box 终止符的文件偏移不能动，`capacity_i = span_i`，框间无余量。
* 块内被 `$14` 分行、被 `$0A` 分框；一句中文可能被 sub-text 调用切成跨 bank 的三段。

## 字形库

* 索引→记录：`0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28`，3 页 × 1170 槽，
  `MAX_INDEX = 0xDB6`（**3,510 条记录，不是 4,096**）；JIS X0208 顺序，`JIS_KANJI = 0x1C5`。
* 记录 28 字节 = 14 个小端 16 位行字，bit15 = 该行最左像素，**只有高 14 位会被画**；14 行放进
  16×16 cell 的第 1..14 行（`$80:D23D` 用 `STZ $C100` / `STZ $C11E` 强制清空第 0/15 行）。
  **可写区 14×14，无缩放**；`plane1 = w | (w>>1)`（`$80:D337`）只是第二个色平面，粗体才是
  `w |= (w<<1)`。取址例程 `$80:D490`，假名风格重定向 `$80:D4BD`。
* 样式标志 `$7E:0A2C`：bit4 假名变体、bit5 粗体、bit1 描边、bit0 平面模式。计数器 `$0A22`，
  BG-map 格游标 `$0A26`。
* 对话框几何（`$80:CF36`，由 `$14` 调用）：三行 VRAM `$5A88/$5AC8/$5B08`，pitch `$40`，
  每字进 1 格。帧 512×224，文本行 y=161/177/193，格宽 16，cell 0 在 x=63，
  **格子左上恒满足 `x % 16 == 15, y % 16 == 1`**，正文从 cell 4 起、cell 3 是框体装饰。

## 存档区（不是 ROM 的一部分）

* `tools/slot.py` 管模拟器唯一的 `rom.sfc` 槽位；同一时刻只允许一条 trace，trace 期间禁止重建 ROM。
* 除根目录那个原镜像与 `Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1) (Chinese Localized).sfc` 外，ROM/`.srm` 一律放在项目外的 `~/retro/roms/`。
