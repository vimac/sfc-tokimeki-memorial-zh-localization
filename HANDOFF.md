# 《心跳回忆：传说的树下》SFC 汉化项目 — 完整交接文档 (v2, 2026-09-18 深夜)

> **本文件已不再是权威**：请读 `docs/RELEASE_zh.md`（交付状态、验收 gate、实测容量）。
> 本文档的历史价值在于早期侦察记录，但其中若干数字按「总字数」而非「字库增量」计算而失效，
> 例如「主题歌还差约 150 个字」—— 实测 26 句歌词只花 12 个字模，已在 build 29 收录。
> 引用任何结论前先跑一遍 `docs/RELEASE_zh.md` 第四节的 gate 复核。
> 旧过程笔记在 `docs/notes_old.md`（885 行，仅查询用，不必通读）。

---

## 一、项目概述

SFC 游戏《心跳回忆：传说的树下》中文汉化。

**ROM**: `Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc` (4MB LoROM)
- 原始日文版: `rom_original_japanese.sfc`（= 当前主 ROM，已恢复干净状态）
- retro 环境: `~/.local/lib/python3.14/site-packages/stable_retro/data/stable/TokimekiSFC-Snes-v0/rom.sfc`
- retro 环境当前 = **干净原版**（我最后已恢复）

---

## 二、已验证的技术事实

### 2.1 LoROM 地址换算

```
SNES addr → file = (bank - 0x80) * 0x8000 + (addr & 0x7FFF)
bank $81 → file 0x0000-0x7FFF
bank $81:D490 → file 0x5490
```

### 2.2 指针表

```
名字指针: file 0x009872 (145 项 × 3B)
文本指针: file 0x009872 + 435 = 0x009A25
指针 3B = [lo][hi][bank]
块地址 = (bank-0x80)*0x8000 - 0x7E00 + (hi<<8|lo)
```

### 2.3 游戏画面分辨率

**名字画面/序章蒙太奇 = 256×448 隔行（mode 5 + interlace）**
- bsnes 截图 = 512×448（2× 缩放）
- stable-retro 补丁前端 = 可输出 512×224（去隔行半分辨率）或 448 全高
- 旧前端（snes9x核）= 只有 256×224 裁剪
- 字体规格 = 14×16/字，序章对话框可显示约 16 字/行 × 2 行

### 2.4 文本编码体系（多层压缩）

| 字节范围 | 含义 | 编码方式 |
|---|---|---|
| 0x00 | 段结束 | 控制 |
| 0x0A | 换行 | 控制 |
| 0x09 | 全角空格 | 控制 |
| 0x12/0x13 | 姓/名变量 | 控制 |
| 0x14/0x25/0x45 | 清行/等待组 | 控制 |
| 0x2E | 行内等待 | 控制 |
| 0x40-0x6F | **宏码**（46 个，见下方宏表） | 单字节 |
| 0x70-0x9F | 单字节假名 | T1 表 |
| 0xA0-0xFC XX | 2 字节汉字码 | 行 delta 表 |

**关键**：0xA0-0xFC 高字节 × 任意低字节 = 2 字节汉字码。
行 delta 表将 SJIS 行映射到字形页。不同场景可能用不同行表。

### 2.5 行 delta 表（ROWDELTA_DIALOG，大部分行已实证）

```
ROWDELTA_DIALOG = {
  0x81:0x72D8, 0x82:0x7082, 0x83:0x6DBD,
  0x88:0x6926, 0x89:0x68E2, 0x8A:0x689E,
  0x8B:0x685A, 0x8C:0x6816, 0x8D:0x67D3,
  0x8E:0x678E, 0x8F:0x674A, 0x90:0x6706,
  0x91:0x66C2, 0x92:0x667E, 0x93:0x663A,
  0x94:0x65F6, 0x95:0x65B2, 0x96:0x656F,
  0x97:0x652A, 0x98:0x64E7, 0x99:0x64A2,
  0x9A:0x64BE, 0x9B:0x641A, 0x9C:0x63D6,
  0x9D:0x6392, 0x9E:0x634E, 0x9F:0x630A
}
```
这些值在**对话窗口块**（P1 名字画面等）已渲染验证 ✓。
在**序章蒙太奇**中：行 0x8E/0x93 已确认正确，其他行未逐行验证（bsnes 截图中
心→驚 等偏差可能只是行表序号不对，也可能部分行确实有差异）。

### 2.6 控制码详细

```
0x00 = 段结束（0x00-terminated segment）
0x0A = 换行
0x09 = 全角空格
0x12 = 姓变量
0x13 = 名变量
0x14 = 清行/格式
0x25 = 等待
0x2E = 行内等待
0x45/0x25/0x14 = 清行三连
0x4B = 说话人标记
0xA0 = 翻页等待（对话框 ● 等键）
E8 06 = 生日月变量
E8 07 = 血型变量
```

### 2.7 字形库布局

```
对话字形: file 0x3E8000-0x3FFFFF (bank FD/FE/FF)
28B/字形, 14×16 1bpp, big-endian 高 14 位有效
3 页 × 0x492(1170) 字形 = 3510 总容量
字形寻址: 序号 → bank = FD + (序号 / 0x492)
          offset = (bank - 0x80) * 0x8000 + 0x8000 + (序号 % 0x492) * 28
```

### 2.8 0x18200 单字节表

```
file 0x18200 起, 每项 2B (大端)
96 项 (对应单字节码 0x40-0x9F)
每项 = 该单字节码对应的 2 字节字形码
J2E 英文补丁改了 19 段/498B (重定向到拉丁字形)
```

### 2.9 词码表

```
指针表: file 0x1CCAA5 (约 46 项 × 2B LE, 指向 file 内偏移)
词条区: file 0xCB33-0xCC4E
每项 = 游戏编码的词/短语
宏码 0x40-0x6F 引用这些词条
```

### 2.10 J2E 英文补丁 (TM_EN.IPS)

```
44 条 IPS 记录:
- 19 段在 0x18200 (单字节表重映射, 498B, 249 项改写)
- 9 段在 0x019DC8-0x01F490 (脚本文本, 752B)
- 零星: 0x0081C6(14B), 0x00888D(82B), 0x019xxx 若干
- **无字体区写入** — J2E 没有注入新字形
- 0x18200 改写 = 单字节码重定向到已有字形
```

---

## 三、stable-retro 环境（当前状态）

### 3.1 已完成的修改

| 修改 | 状态 | 说明 |
|---|---|---|
| 前端 C++ 补丁 | ✅ 已装 | `m_updateGeometryFromVideoRefresh = true`（所有核） |
| 内核换成 bsnes | ✅ 已装 | `cores/snes9x.json` 的 `lib` → `bsnes` |
| FILTERED 按键白名单 | ✅ 已修 | `actions` 补了 START/SELECT |
| 0x18200 表重映射 | ✅ 已建 | 96 高频字 → 单字节码 |
| encode_zh 优先级 bug | ✅ 已修 | CHAR_TO_CODE 先于 cp932 |

原 .so 备份: `/tmp/retro_backup_original.so`
补丁源码: `/tmp/stable-retro-src`
重新编译: 见 HANDOFF 旧版基础设施一节

### 3.2 当前 retro 环境内核/配置

```
内核: bsnes_libretro.so (nightly, 非 bsnes2014)
json: cores/snes9x.json (lib=bsnes)
actions: 已补 START/SELECT
0x18200 表: 已重映射 (含 START/SELECT)
play.py: use_restricted_actions=Actions.ALL
```

### 3.3 stable-retro 的限制

| 限制 | 影响 | 绕过 |
|---|---|---|
| 448i 隔行渲染黑屏 | 序章蒙太奇不可见 | 只能 bsnes 验证 |
| get_ram() 空 (bsnes核) | RAM 分析不可用 | 切回 snes9x 核 |
| からはじめる软复位循环 | 选了又回选择画面 | 选 は見ない 可跳过进游戏 |
| 捐字字形槽位寻址未验证 | WQY 注入可能写错位置 | 需要字形例程完整逆向 |

---

## 四、游戏流程（已自动化验证）

```
冷启动 (3000帧)
  ↓ START
菜单 (ゲームスタート/オプション)
  ↓ START
文件选择 (続き/初め/書く/消す)
  ↓ A (初めから selected)
  ↓ A (可能的确认)
名字画面 ← 指针在顶部选项(からはじめる)
  ↓ 填名(3字) → START
  ↓ 生日选择 → 終了 → A
  ↓ 詩織生日 → 終了 → A
  ↓ 确认×2
选择画面 (プロローグからはじめる/プロローグは見ない)
  ↓ A (选 からはじめる)
序章蒙太奇 (TKSC144 文本, A 推进)
  ↓
名字登录 → 生日 → ... → 游戏
```

**已自动化**: `tools/startflow3.py` 可从冷启动到选择画面
（导航关键: 文件菜单后按 A×2 选初めから，然后等蒙太奇选择）

---

## 五、序章文本翻译状态

### 5.1 翻译数据

`translations/prologue_zh.py` — 67 框中文翻译
- 日文直译为主，参考 tokt144.euc 英化版
- 已压缩到位（区域1 471/512、区域2 1429/1433、区域3 214/730）
- 全部字符已验证 ROWDELTA 可编码

### 5.2 当前构建的实测状态（2026-09-19 复核；本表**取代**此前那份"已知问题"，旧表里的判断已被实测推翻）

| 检查 | 命令 | 结果 |
|---|---|---|
| 冷启动序章走查 | `python3 tools/prologue_play.py rom_prologue_zh.sfc 96 --boot` | 96 次按键 / 366 个不同 (指针,文本) 页 / 最高重复 52 次（同一页被多次采样，不是死循环） |
| 假名残留 | `grep -cE "[ぁ-ゔァ-ヺ]" /tmp/boot_walk_zh*.txt` | **0** |
| 截图产物 | `python3 tools/prologue_shots.py` | `docs/prologue_zh/` 88 框 183 张 |
| JIS 字形审计 | `python3 tools/jisaudit.py` | 183 张里 2 个外来槽位，全是我们自己用的全角 `￣`/`＿`；`plate`/`inline` 两组为 0 |
| territory 审计 | 构建自带的 `changed ... runs` 报告 | 无 `UNEXPECTED`；`bank glyph slots: 0 collisions in 0x180c0-0x20000` |

（1）旧表说"蒙太奇文本乱码＝序章块行表 ≠ ROWDELTA_DIALOG，未修"：**已修**。行表由 block 8/144 的
`grid: N boxes, all match the Japanese spans and terminators` + `0 over, 0 broken` 逐项证明。
（2）旧表说"きらめき 等假名不可见 → 改用汉字替代"：**该策略已作废**，见 5.3。
（3）截图里 `佗` 是翻页箭头的 OCR 结果、行首 `「` 是开窗装饰，都不是错字（`tools/pagediff.py` 先剔除它们）。

### 5.3 词表限制：JIS 顶替已废除，字库容量成为新的硬限制

ROWDELTA 可编码≈JIS X0208，简体字不在其中——这正是旧版"全部用 JIS 等价字（詩織/歸/説…）"的理由。
**该策略已被明确否决并且不再使用**：现在每个用到的简体字都有自己独立的文泉驿点阵记录，
`rom_original_japanese.sfc`（md5 `cd36eb89…`）永远只读，产物是 `rom_prologue_zh.sfc`。

新的硬限制是字形数组容量：`glyph_offset(idx) = 0x3E8000 + (idx // 0x492) * 0x8000 + (idx % 0x492) * 28`，
即 3 页 × 1170 槽 × 28 B = 3510 条记录，第 3 页正好顶到 4 MB 文件末尾，所以**第 4 页无法就地追加**。
实测原始 ROM 中不存在任何 ≥16 KB 的均匀空白区，因此扩页只有两条路：4 MB→8 MB 扩容＋改 mapper，
或删掉某个 32 KB 图块/数据体腾地方——两者都属于范围决策，需要先确认。
当前用量：967 字（959 个新槽位 / 1166 可用，约 207 槽余量）。而散文区（作文、剧本、约会台词）
经统计还需要约 459 个尚未注入的字，**超出余量**，所以现阶段可负担的只有短标签类文本。

---

## 六、字体系统（卡点 2 → 已解决）

### 6.1 已破解（旧表仍然成立）

| 组件 | 地址 | 说明 |
|---|---|---|
| 主例程入口 | file 0x5230 (SNES $80:D230) | PHX PHY PEA #$D400... |
| 假名修正 $D4BD | file 0x54BD | 查 bank$80 file 0xD4E4 假名码表 |
| 页规格化 $D490 | file 0x5490 | ÷0x492 求页号, ×28 求偏移 |
| 假名码表 | bank$80 file 0xD4E4 | 0x00 结尾, 命中→序号=表索引+基数 |
| 字形数据 | 0x3E8000-0x3FFFFF | 28B/字形, 3页×1170=3510 |

### 6.2 旧"未解"三行，现在都有答案

| 问题 | 结论 |
|---|---|
| 汉字序号推导公式 | 已解，即 5.3 的 `glyph_offset`；实现见 `tools/tmtext.py` 的 `idx_to_char/char_to_idx/glyph_offset` |
| 捐字字形槽位冲突 | 整个 $180C0-$20000 由 `BANK_ALL` 预留，构建期报 `0 collisions`，另有 `tools/uicollide.py` 独立复核 |
| 蒙太奇行表验证 | block 8/144 各自报 `0 over, 0 broken` + `round trip: OK`，并由 183 张截图 + `jisaudit` 复核 |

### 6.3 WQY 注入方案（**已执行并已验证**）

`python3 tools/build_prologue.py --patch` 每次重新计算 `docs/research/glyph_alloc.json`，只给实际用到
的字分配槽位（当前 967 字 / 991 条记录，其中 24 条按原 JIS 索引就地写入，供运行时生成的文本使用），
构建末尾的 `font: 991/991 slots carry WenQuanYi ... 0 unclaimed slot(s) changed` 即"注入的就是用到的、
且没有多占一个槽"的证明。翻译源文件：序章 `prologue_zh.txt`、每日独白池 `block8_zh.txt`、
其余 UI/标签在 `tools/build_prologue.py` 的 `UI_TEXT_ROWS`（640 行）。

---

## 七、工具清单

| 工具 | 功能 | 状态 |
|---|---|---|
| tools/play.py | 模拟器驱动（ALL 模式） | ✅ |
| tools/insert_zh.py | 编码器+回插（TOKI_ROM 可覆盖） | ✅ |
| tools/font_wqy.py | WQY 字形渲染（13px PCF） | ✅ |
| tools/prologue_zh.py | 序章翻译数据（67框） | ✅ |
| tools/prologue_patch.py | 序章回插（check/apply） | ✅ |
| tools/prologue_font.py | 缺字→捐字槽位+WQY 字形 | ✅ |
| tools/prologue_harvest5.py | kana锚点 (码→字) 收割 | ✅ |
| tools/prologue_harvest6.py | difflib 对齐收割 | ✅ |
| tools/calibrate_rows.py | 行表校准（从截图对） | ✅ |
| tools/mouse_nav.py | 指针追踪 | ✅ |
| tools/click_test.py | 点击实验 | ✅ |
| tools/montage_zh.py | 蒙太奇导航+截图 | ✅ |
| tools/startflow3.py | 全流程自动化 | ✅ |
| tools/replay_full.py | 完整重放+逐帧截图 | ✅ |
| tools/disasm65816.py | 65816 反汇编器 | ✅ |
| tools/final_insert.py | 0x18200 重映射+混合编码 | ✅ |
| tools/sbmap_build.py | 单字节频率映射构建 | ✅ |

---

## 八、关键发现（按时间线）

### 发现 1: START 交付修复
stable-retro 默认 FILTERED 模式会丢按键。修复 = `Actions.ALL` + json 白名单补 START/SELECT。
调试 ROM `ctrltest_simple.sfc`（用户找到）一锤定音。

### 发现 2: 512 宽高分辨率
名字画面/序章蒙太奇 = 256×448 隔行（mode 5）。前端补丁后可正确输出。
旧前端只有 256×224 裁剪——这就是历来"画面不完整"的根源。

### 发现 3: 词码系统
文本中 0xA0-0xEF 的单字节 = 高频词码（指向 0x1CCD31 词库）。
不是"2字节汉字码的高字节"——这是两种不同的压缩机制并存的证据。

### 发现 4: 序章蒙太奇 = 选择后触发
从文件菜单选初めから后，注册完成后出现选择画面。
選 プロローグからはじめる = 播放序章旁白（TKSC144 文本）。
選 プロローグは見ない = 跳过旁白直接开始。

### 发现 5: 指针导航
选择画面的选项 = 用 D-pad 移动粉色三角形指针选择。
指针初始 = 顶部选项，DOWN 逐步下移。

### 发现 6: 捐字字形槽位
简体字（们说这请让记谁谢etc.）不在 JIS 字符集。
方案 = 找生僻 JIS 字的槽位 → 用 WQY 渲染简体字覆盖。
已有映射（font_wqy.py S2J_SLOT）= 29 字。需扩展至 ~100 字。

### 发现 7: 行表差异
ROWDELTA_DIALOG 行表大部分正确（88/89/8B/8D/8F/96/97 已验证），
但行 0x90 的 心 → 显示为 驚 = delta 差了 0x492 的倍数 = 字形页偏移。
不同行可能映射到不同的字形页，需要逐行校准。

### 发现 8: 词码系统解密
文本中 0xA0-0xEF 的单字节 = 高频词码（指向 0x1CCD31 词库）。
不是"2字节汉字码的高字节"——这是两种不同的压缩机制并存的证据。

---

## 九、已知问题与限制

### 9.1 stable-retro 限制
| 限制 | 影响 | 状态 |
|---|---|---|
| 448i 隔行黑屏 | 序章蒙太奇不可见 | 未解（需bsnes验证） |
| get_ram() 空 (bsnes核) | RAM分析不可用 | 切snes9x核可解 |
| からはじめる循环 | 选择后软复位 | 需在bsnes验证 |
| 0x18200 表覆盖假名 | 假名字形可能被覆盖 | 已用生僻JIS字规避 |

### 9.2 翻译质量
| 问题 | 说明 |
|---|---|
| JIS 汉字形式 | 部分280字用日文汉字形（訓習験等）非标准简体 |
| 501字未翻译 | 47265段中仅~200段有翻译 |
| 行表部分行未验证 | 行0x90等少数行的delta未经渲染验证 |

### 9.3 工具限制
| 工具 | 限制 |
|---|---|
| stable-retro | 448i 隔行黑屏、からはじめる循环、get_ram 空(bsnes核) |
| bsnes | GUI only，无脚本接口 |
| font_wqy.py | 槽位寻址启发式未完全验证 |
| 词码表 | 部分词码含义未确认 |

---

## 十、文件路径

```
主ROM: Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc
原始日文: rom_original_japanese.sfc
retro环境: ~/.local/lib/python3.14/site-packages/stable_retro/data/stable/TokimekiSFC-Snes-v0/rom.sfc
J2E日文: reference/j2e_full/scripts_x/Scripts/Japanese/Tksc/*.EUC
J2E英译: reference/j2e_full/scripts_x/Scripts/English/
J2E工具: reference/j2e_full/tokistuff_x/ (TOKINS.BAS etc.)
翻译稿: translations/
序章翻译: translations/prologue_zh.py
工具: tools/
调试ROM: ctrltest_simple.sfc
用户截图: start-screenshots/
前端源码: /tmp/stable-retro-src
前端补丁: stable-retro /tmp/retro_backup_original.so
核心配置: ~/.local/lib/python3.14/site-packages/stable_retro/cores/snes9x.json
```

---

## 十一、重要教训

1. **不要直接在主 ROM 上做实验** — 先备份，用副本测试
2. **bytes.replace() 会全局替换** — 永远不要对二进制文件用它
3. **指针表值 = 文件偏移** — 不需要 SNES 地址换算
4. **两套块号** — 指针表 index vs 排序序号，搞混全错
5. **state 重放不可信(旧栈)** — 新栈已修复可放心用
6. **不要用 bsnes GUI 调试** — 太耗时
7. **名称含"到达某画面"的旧结论都要核实**
8. **名字画面 = mode 5 高分辨率** — 画面异常先查前端几何
9. **FILTERED 模式丢按键** — `use_restricted_actions=Actions.ALL` 必须
10. **调试 ROM 是映射问题的决定性工具** — 不要瞎猜
11. **行表差异 = 字形页偏移** — 差值恰为 0x492 的倍数
12. **词码和单字假名共存** — 0xA0-0xEF 是词码，0x40-0x9F 是假名
13. **不要在蒙太奇播放期间按 A** — 会跳过文本框
14. **每个 J2E 工具都有多种变体** — TOKISEQ.BAS 有 3 个版本
15. **np.uint8 和 int 比较时注意类型转换** — 否则广播错误

---

## 十二、下一步建议（按优先级）

### P0: 确认序章蒙太奇中文显示
在真实 bsnes 中加载 `rom_prologue_zh_jis.sfc`，走完注册选 からはじめる，
截图序章蒙太奇的每一屏中文文本，确认编码正确性和可读性。

### P1: 推进简体字形注入
使用 font_wqy.py 的 S2J_SLOT 方法将简体字形写入 JIS 字形槽位。
需要解决：正确的槽位寻址公式。

### P2: 扩展翻译到更多文本块
使用已验证的编码管线（ROWDELTA_DIALOG + kana锚点）逐块翻译回插。

### P3: 完整重放流程脚本
将 tools/montage_zh.py 和 tools/startflow3.py 整合为一个
从冷启动到游戏内对话的完整自动化脚本，用于后续批量验证。
