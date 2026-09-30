# 心跳回忆：传说的树下（SFC 日版 Rev 1）——简体中文汉化工程

这是把日版《心跳回忆：传说的树下》里**玩家看得见的文本**换成简体中文的整套工程：
编码／解码工具、字库生成、逐块中文正文、逆向结论文档，以及每一批的裁决账本。

**本仓库不含、也不提供游戏镜像。**构建过程需要你自己那份日版 Rev 1 原镜像，
仓库里既没有它，也没有补丁文件（IPS／BPS）或任何可直接烧进主机的成品——
交付物是「一条命令从你自己的镜像重建」这套脚本与正文。

## 你要准备什么

| 需要 | 说明 |
| --- | --- |
| 原镜像 | `Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1).sfc`（4 MB LoROM），md5 `cd36eb8982de4bf8369deb9f2f23e590`，放在仓库根目录。**工具只读它，任何脚本都不写它**。 |
| 文泉驿点阵字体 | `wenquanyi_13px.pcf`。字库带每次构建由它现生成（默认路径 `/usr/share/fonts/wqy-bitmap/wenquanyi_13px.pcf`，见 `tools/wqyfont.py` 的 `FONT_PATH`）。本项目不用 JIS 字形或繁体字顶替显示，所以这个字体是必需的。 |
| Python 3 + Pillow + numpy | 构建与逐框出图用 Pillow（`PIL.Image/ImageDraw/ImageFont`）；模拟器层的走查用 numpy。 |
| `stable_retro`（可选） | 只有模拟器走查那一层需要（`tools/play.py`／`prologue_play.py`／`prologue_shots.py`／`jisaudit.py`）。不跑走查就不用装。 |
| `reference/`（可选） | 第三方 J2E 同人素材，只作查证输入，**不入库**；没有它整条构建链照样跑。 |

镜像、存档、补丁一律被 `.gitignore` 挡住（`*.sfc`、`*.zip`、`*.srm`、`*.ips`、`*.bps`、`*.bsz`…），
别把它们提交进来，也别放到仓库目录里。

## 克隆后的第一步

`docs/research/blockN_work.tsv`（144 份译稿预算表）**不入库**——它的 `runs(jp)` 列是逐格日文原文，
144 份合起来等于原作剧本的明文表。它完全可重生成，且实测逐字节重现：

```
for i in $(seq 0 144); do python3 tools/block_work.py "$i"; done     # 单块 0.25 s，全量约 40 s
```

跑完 `poolsync.py`／`segtext.py`／`bracketpair.py`／`thin_sweep.py` 才有输入。
（同一条命令顺手写出 `_work.json` 与 `_jp.txt`，两个也都是派生物。）

## 构建中文镜像

```
python3 tools/build_zh.py --patch
```

它会从原镜像重建树、按本批用字生成码表与字库带、把中文写回每一个文本区间，并在结尾做
逐字节回读断言。规矩是**先跑不带 `--patch` 的 dry run**（约 90 s，不碰镜像）拿超框点名清单，
改完再 dry 一遍确认干净，最后才 `--patch`（约 90 s）。产出：
`Tokimeki Memorial - Densetsu no Ki no Shita de (Japan) (Rev 1) (Chinese Localized).sfc`。

## 验收

* `PROGRESS.md` §三 是可整段复制的命令块（静态层＋全库逐框门＋模拟器层）与判据。
* `AGENTS.md` 是工程纪律：镜像与措辞口径 §一、目录归属 §二、验收 §三、译名与笔调 §四、
  编码与字模事实 §五、已经关掉的路 §六。改任何一块之前先读它。
* `docs/research/` 是逆向结论，每条都带地址或文件偏移，可复现。

## 已知项（不是缺陷）

* 文本目标已经达成：**游戏里看得见的文本不留日文字符**（贴图里烧死的字除外）。
  剩下的工作是逐句措辞裁决，账在 `PROGRESS.md` §四。
* `docs/research/block133_zh.txt` 里留着 `ーーーー` 这种乱码行。block 133 是引擎指针网格被硬解成的
  **假文本块**，从没注册进构建（`B.BLOCKS`），玩家读不到它；这一行留着是为了守住
  「`blockN_zh.txt` 第 n+1 行 ↔ `blockN_work.tsv` 第 n 号步」这个全局复账键。
* 中文正文里 229 处间隔号用的是片假名中点位 `・`（U+30FB），那是字库格位的选择，不是日文残留。

## 授权

见 `LICENSE.md`：`tools/` 与文档代码是 MIT；中文正文是粉丝同人成果、**非商用**，
本项目不针对原作品的任何文本、图像或字体主张权利。
