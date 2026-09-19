# 中文版交付说明 / Chinese patch — delivery status

权威状态文件。`HANDOFF.md` 与 `docs/HANDOFF_old.md` 是上一轮工作的交接记录，其中若干数字已被
实测推翻（见下文「对 HANDOFF 的更正」），引用前请核对本文件。

日期：2026-09-20。

## 一、交付物

| 文件 | md5 | 说明 |
|---|---|---|
| `rom_prologue_zh.sfc` | `aac6c2af23796e66666302f461e609dc` | **交付版本**（4 MB LoROM，日版 Rev 1 基线） |
| `rom_original_japanese.sfc` | `cd36eb8982de4bf8369deb9f2f23e590` | 只读母盘，任何工具都不得写入 |

`rom_prologue_zh_DRAFT_乱码待修.sfc`、`rom_prologue_zh_jis.sfc`、`tokimeki_chinese_font.sfc`、
`ctrltest_simple.sfc` 及其 `.srm` 存档是历史中间产物（JIS 顶替方案时代），2026-09-20 清理时已删除，
完整副本保留在 `~/retro/tokimeki.backup.2609200007.tar.gz`。
当初作为问题证据的 17 张乱码截图已移到 `docs/evidence_2026-09-18_jis/`。

## 一之二、工作区结构（2026-09-20 清理后）

```
tools/            59 个脚本（清理前 131 个）：19 个在验收链路上，其余是文档引用的侦察仪表
docs/RELEASE_zh.md 本文件
docs/research/    逆向证据与构建输入（glyph_alloc.json 是构建必读输入，勿删）
docs/prologue_zh/ 183 张渲染表 + index.txt 转录（可重生成）
translations/     手工中文稿（*.tsv、shrine_zh.json）
start-screenshots/ 日文原版启动流程截图
rom_original_japanese.sfc / rom_prologue_zh.sfc  母盘与交付盘
```

已删除：`out/`（29 MB 从日文 ROM 解出的 dump，可由 `tools/extract_all.py`、`tools/dump_text.py`、
`tools/extract_font.py` 重新生成）、68 个属于废弃方案的脚本（旧 JIS 槽位方案、死循环排查期的
一次性模拟器驱动），以及 4 个引用了已删脚本、删完即坏的工具，共 72 个，`tools/` 从 131 降到 59。
删除后 `tools/build_prologue.py --patch`
仍产出字节完全相同的 `aac6c2af…`，验收链路无恙。

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
* **系统 UI：绘制脚本 bank（`$180C0–$20000`）912 行**——标题/菜单/状态面板/日历/月份表/
  存档界面/社团/校庆/社团秘技/相册/音乐试听标签/姓名输入问题流/假名与汉字键盘。
* **姓名相关**：28 条姓氏表、14×3 说话人名片表、`$1F890` 的 32 条预设姓名池、`$E803/04/05`
  子文本调用；`さん`/`ちゃん` 等称呼改为「同学」「小同学」，宽度与码数不变所以索引表无需改动。
* **运行时字形**：`$E806` 日期（月/日）、`$E807` 血型（ＡＢＯ/型）等在 stock 槽位就地重写。
* **片尾**：滚动字幕的职员表 + **片尾主题歌 26 句歌词**（`$1E4FE–$1E8A0`）。

## 三、字体：真正注入的文泉驿

* 文本编码为 `$F0–$FF` 双字节对，12 位索引上限 4095；字形记录 28 字节/个，每页 1170 槽，
  基址 `0x3E8000`，共 3 页（`tools/tmtext.py`）。
* 本补丁占用 **1146 / 1166** 个可用新槽（86 个 `$40–$9F` 码页项另计），**剩余 20**。
* 构建报告 `font: 1178/1178 slots carry WenQuanYi (32 of them at stock indices)`，
  即屏幕上出现的每一个汉字都是文泉驿点阵，**没有任何一个用 JIS/繁体字形顶替**。
* 注入量是最小的：只为本补丁真正用到的字生成记录，未用到的槽位保持原样
  （`0 unclaimed slot(s) changed`）。

## 四、验收 gate（按顺序，全部通过才算好构建）

```
python3 tools/build_prologue.py --patch          # VERDICT: all checks passed
python3 tools/prologue_play.py rom_prologue_zh.sfc 96 --boot   # 96 presses, 366 distinct pages, kana=0
cp <walk log> /tmp/play/boot_walk_zh.txt
python3 tools/prologue_shots.py /tmp/play/boot_walk_zh.txt docs/prologue_zh   # 88 boxes, 183 sheets
python3 tools/jisaudit.py docs/prologue_zh rom_prologue_zh.sfc  # 2 foreign slots: 010(￣) 011(＿)
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

## 五、剩余工作（已实测代价，不是估计）

字库只剩 20 个字模，以下代价由 `tools/price_block0.py`、`tools/price_rows.py`、
`tools/poolscan.py`、`tools/blocktails.py` 量得：

| 目标 | 代价 | 结论 |
|---|---|---|
| block 0 提示/系统池（726 box / 14,778 B / 312 个不同汉字，已拥有 161） | **151 个字模** | 超出 20，本镜像内无法完成 |
| block 0 的零成本子集（贪心最便宜优先） | 351 box / 5,720 B 用完最后 20 个字模 | 每 box 字节区间被锁死，实际可交付远小于 351；按 2026-09-20 决定**不做** |
| 键盘假名/汉字取样行（`1F3DA/1F482/1F558/1FB50`） | 1–4 个字模 | 现状渲染正常（本就是假名/汉字取样键），半译反而破坏输入法，**不做** |
| `$19Axx` 残句（体感マシ／嵐ヶ原／エメラルド…） | 5–6 个字模 | 实测是长句被切开后的**句中片段**，脱离上下文无法独立成译，**不做** |
| romaji 昵称、`0x18888` 八卦卡等 | — | 属 handle/装饰，故意保留 |

三条互相独立的实测都指向同一个上限：第 3 页距 4 MB 末尾只剩 8 字节；128 个 bank 无重复、
无整块填充（最高单一字节占比 21.8%）可腾；按**打完补丁的 ROM**重新保留槽位只多回 19 个。
因此「扩容」只有一条路：把镜像改成 8 MB / ExLoROM，并按 `docs/research/glyph-addressing.md:563`
给 `$80:D490` 追加一组 `INX/TAY/SBC #$0492/BCC`。由于文本 pair 只能到 4095，第 4 页真正可用的是
**586 个字模**（不是 1170），够 block 0 的 151 加后续大部分正文。**2026-09-20 已决定暂不做扩容**；
若将来要做，先重新确认母盘 md5 与上面的 gate 命令仍然成立。

## 六、对 HANDOFF 的更正

* 主题歌「还差约 150 个字」是**按总字数**算的错账。一批文本只为字库里**还没有**的字付费：
  26 句歌词实测只花 **12** 个字模，本构建已经收录。
* 「需要解决：正确的槽位寻址公式」（HANDOFF P1）——已解决并写入 `tools/tmtext.py`
  （`GLYPH_BASE + (idx//1170)*0x8000 + (idx%1170)*28`），`$80:D490` 的三次 `SBC #$0492` 与之吻合。
* 「P1: 用 S2J_SLOT 把简体字形写入 JIS 槽位」——**已废弃该思路**：借用 JIS/繁体的槽位就是用户
  明确不接受的「用 JIS 汉字代替」。现在的做法是分配全新槽位 + 码页，stock 位置只在确实被
  固定索引引用处就地重写（24 条）。
* 「P0: 确认序章中文显示」——已完成，见第四节 gate 与 `docs/prologue_zh/`（183 张渲染表 + `index.txt`）。
