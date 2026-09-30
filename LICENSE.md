# License / 许可

Two complete texts follow: the English version first, then the Chinese version. They state the same
terms; the English text is the canonical one, and the Chinese rendering of the MIT permission block is
an unofficial translation for convenience.

下面依次是**完整的英文版**与**完整的中文版**。两份表述的是同一套授权条款；英文那份是原文，
中文那份里的 MIT 许可段落是非官方译文，只是为了方便阅读。

---

## English

This repository is a fan-made Simplified-Chinese localisation project: tooling, engineering
documentation, and the Chinese text written by its author.

Neither grant below covers any content of the original game
*Tokimeki Memorial: Densetsu no Ki no Shita de* (SNES, Konami). The original text, artwork, music,
character names and font data belong to their rights holders; this project claims no rights over them
and does not speak on their behalf.

### 1. Tools and documentation — MIT

Copyright (c) 2026 vimac <vimac@users.noreply.github.com>

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This layer covers every Python script under `tools/`, the files `README.md`, `AGENTS.md`,
`PROGRESS.md` and `LICENSE.md`, the reverse-engineering notes and engineering records under
`docs/research/*.md`, and the index tables under `docs/research/*.json`.

### 2. Chinese text — non-commercial

The Chinese text in this repository — every `docs/research/*_zh.txt` (including `prologue_zh.txt` and
`block8_zh.txt`) and the three glossaries under `translations/` — is licensed separately.

You may copy, modify, rebuild, republish, continue revising and re-arrange it, for any purpose
**except a commercial one**. The single condition is: no charging for it, no bundling it into a paid
product, no using it to monetise traffic. Keep this notice and this file with any redistribution.

That text is a derivative work: it exists only because of the original game's dialogue, names and
story, so this grant covers only the Chinese wording this project's author wrote, and nothing beyond it.
Commercial use requires authorisation from the rights holders of the original work.

### 3. What this repository distributes

Only the tooling, the documentation and the Chinese text above. It contains no game content of its own:

* No ROM image (`*.sfc`, `*.smc`), no patch file (`*.ips`, `*.bps`, `*.xdelta`), no saved state or
  battery save (`*.srm`, `*.bsz`), and no archive of any of those (`*.zip`) — `.gitignore` blocks the
  whole family. The patched image is rebuilt locally by running
  `python3 tools/build_zh.py --patch` against a copy of the Japanese Rev 1 image that the user
  supplies; see `README.md` for the required md5.
* No text extracted from that image. The per-cell tables under `docs/research/` (`blockN_jp.txt`,
  `blockN_work.tsv`, `blockN_enc.json` and their siblings) hold the original Japanese writing, are
  regenerable in one command, and are deliberately not committed.
* No third-party material: the J2E fan-translation drop referred to as `reference/` (about 18 MB) is
  used read-only on the author's machine and is not part of, or distributed by, this repository.
* No font file. The bitmap glyphs written into the image are generated at build time from
  **WenQuanYI 13px** (`wenquanyi_13px.pcf`, distributed under the GPL with the font exception);
  copyright in that font remains with the WenQuanYI project.

Runtime requirements are listed in `README.md`.

---

## 中文

本仓库是一个粉丝自作的简体中文汉化工程：工具脚本、工程文档，以及作者自己写下的中文正文。

下面两层授权**都不覆盖原作《心跳回忆：传说的树下》（SFC，KONAMI）的任何内容**。
原作的文本、美术、音乐、角色名与字体数据版权归原作权利方所有；本项目对这些不主张任何权利，
也不代表权利方发言。

### 一、工具与文档：MIT

版权所有 (c) 2026 vimac <vimac@users.noreply.github.com>

现授予任何取得本软件与相关文档文件（下称「软件」）副本的人不受限制的权利，包括但不止于
使用、复制、修改、合并、发布、分发、再许可和／或出售软件副本的权利，并允许获得软件的人如此行事，
条件如下：

上述版权声明与本许可声明须包含在软件的所有副本或实质部分中。

软件按「现状」提供，不含任何明示或默示的保证，包括但不限于对适销性、特定用途的适用性与非侵权的
保证。作者或版权持有人对任何索赔、损害或其他责任概不负责，无论该责任源于合同纠纷、侵权行为或其他
与软件及其使用相关的事由。

这一层覆盖 `tools/` 下全部 Python 脚本、`README.md`、`AGENTS.md`、`PROGRESS.md`、`LICENSE.md`、
`docs/research/*.md` 里的逆向结论与工程记录，以及 `docs/research/*.json` 那些索引表。

### 二、中文正文：非商用

本仓库里的中文正文单独授权：全部 `docs/research/*_zh.txt`（含 `prologue_zh.txt`、`block8_zh.txt`）
与 `translations/` 三张口径表。

你可以复制、修改、重新构建、转载、继续润色、二次整理，**唯一条件是不用于任何商业目的**——
不收费、不打包进收费产品、不用于引流变现。再分发时请连同本文件与本段说明一起保留。

这些中文是衍生作品：它依附原作的台词、人名与剧情才成立，所以本段授权的只是本项目作者自己写下的
中文文字，不含其余。商业用途需要自行向原作权利方取得授权。

### 三、本仓库分发什么

只分发上面那两层：工具、文档、中文正文。仓库里没有游戏内容本体：

* 没有镜像（`*.sfc`、`*.smc`）、没有补丁（`*.ips`、`*.bps`、`*.xdelta`）、没有存档（`*.srm`、`*.bsz`），
  也没有这几样的压缩包（`*.zip`）——`.gitignore` 把这一族整批挡住。补丁镜像由使用者拿自己的
  日版 Rev 1 镜像跑 `python3 tools/build_zh.py --patch` 在本地重建，镜像校验值见 `README.md`。
* 没有从镜像解出的文本。`docs/research/` 下那批逐格表（`blockN_jp.txt`、`blockN_work.tsv`、
  `blockN_enc.json` 及其同类）装的是原作日文原文，一条命令即可重生成，因此有意不入库。
* 没有第三方素材：被称为 `reference/` 的那份 J2E 同人汉化转储（约 18 MB）只在作者本机作只读查证，
  不属于、也不随本仓库分发。
* 没有字体文件。写进镜像的点阵字模在每次构建时由 **文泉驿 13px**（`wenquanyi_13px.pcf`，
  以 GPL 附加字体例外条款发布）现生成，该字体版权归文泉驿项目所有。

运行依赖见 `README.md`。
