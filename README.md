# 心跳回忆：传说的树下（SFC 日版 Rev 1）——简体中文汉化工程

这是把日版《心跳回忆：传说的树下》里**玩家看得见的文本**换成简体中文的整套工程：
编解码工具、字库生成、逐块中文正文、逆向结论文档，以及逐批的工程记录。

文本目标已经达成：游戏里看得见的文本不留日文字符（贴图里烧死的字除外），
显示用的点阵全部由文泉驿 13px 现生成，不拿 JIS 字形或繁体字顶替。

**仓库不含游戏镜像，也不含补丁成品**——交付物是「从使用者自己的镜像一条命令重建」的脚本与正文，
范围与授权见 `LICENSE.md`。

## 需要准备什么

| 需要 | 说明 |
| --- | --- |
| 原镜像 | `Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc`（4 MB LoROM），md5 `cd36eb8982de4bf8369deb9f2f23e590`，放在仓库根目录。工具只读它，没有任何脚本会写它。 |
| 文泉驿点阵字体 | `wenquanyi_13px.pcf`，字库带每次构建由它现生成（默认路径 `/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf`，见 `tools/wqyfont.py` 的 `FONT_PATH`）。 |
| Python 3 + Pillow + numpy | 构建与逐框出图用 Pillow（`PIL.Image/ImageDraw/ImageFont`），模拟器走查用 numpy。 |
| `stable_retro`（可选） | 只有模拟器走查那一层需要（`tools/play.py`／`prologue_play.py`／`prologue_shots.py`／`jisaudit.py`）。不跑走查就不必装。 |
| `reference/`（可选） | 第三方 J2E 同人汉化素材，只作只读查证输入，不入库；没有它整条构建链照样跑。 |

镜像、存档、补丁一律被 `.gitignore` 挡住（`*.sfc`、`*.zip`、`*.srm`、`*.ips`、`*.bps`、`*.bsz`），
不要提交，也不要放在仓库目录里。

## 克隆后的第一步

`docs/research/blockN_work.tsv` 不入库：它是从原镜像解出的逐格**日文原文**加断点表，属于派生物。
重生成一条命令：

```
for i in $(seq 0 144); do python3 tools/block_work.py "$i"; done     # 145 次调用，实测 18 s
```

循环写到 144 会落 143 份表——块 1 是纯数据、块 59 是最后一个指针没有末端，这两块出不了表。
同一条命令顺手写出 `_work.json` 与 `_jp.txt`，两个都是派生物。
跑完这一步，`poolsync.py`／`segtext.py`／`bracketpair.py`／`thin_sweep.py` 才有输入。

## 构建中文镜像

```
python3 tools/build_zh.py --patch
```

它从原镜像重建树、按本批用字生成码表与字库带、把中文写回每一个文本区间，结尾做逐字节回读断言。
规矩是**先跑不带 `--patch` 的 dry run**（约 90 s，不碰镜像）拿超框点名清单，改完再 dry 一遍确认干净，
最后才 `--patch`（约 90 s）。产出
`Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1) (Chinese Localized).sfc`。

## 怎么验

`PROGRESS.md` §三是可整段复制的命令块（静态层＋全库逐框门＋模拟器层）与判据。
改任何一块之前先读 `AGENTS.md`：镜像与措辞纪律 §一、目录归属 §二、验收 §三、
译名与笔调 §四、编码与字模事实 §五、已经关掉的路 §六。逆向结论在 `docs/research/`，
每条都带地址或文件偏移，可复现。

## 已知项（不是缺陷）

* 剩下的工作是逐句措辞裁决，明细在 `PROGRESS.md` §四。
* `docs/research/block133_zh.txt` 里留着 `ーーーー` 这种乱码行。block 133 是引擎指针网格被硬解出来的
  **假文本块**，从没注册进构建（`B.BLOCKS`），游戏里读不到它；这一行留着是为了守住
  「`blockN_zh.txt` 第 n+1 行 ↔ `blockN_work.tsv` 第 n 号步」这个全局复账键。
* 中文正文里 229 处间隔号用的是片假名中点位 `・`（U+30FB），那是字库格位的选择，不是日文残留。
