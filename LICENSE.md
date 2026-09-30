# 许可

本仓库是粉丝自作的简体中文汉化工程，授权分两层。两层都不覆盖原作
《心跳回忆：传说的树下》的任何内容——原作的文本、图像、音乐版权归原作版权方所有，
本项目不对它们主张任何权利，也不代表原作版权方。

## 一、代码与文档：MIT

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

这一层覆盖 `tools/` 下的全部 Python 脚本、`README.md`／`AGENTS.md`／`PROGRESS.md`、
`docs/research/` 里的逆向结论与工程记录，以及 `docs/research/*.json` 那几张索引表。

## 二、中文正文：非商用

`docs/research/*_zh.txt`（含 `prologue_zh.txt`、`block8_zh.txt`）与 `translations/` 三张口径表里的
中文译文，授权范围是：复制、修改、重新构建、转载、继续润色、二次整理，**条件只有一个——
不得用于任何商业目的**（不收费、不打包进收费产品、不用于引流变现），再分发时保留本段说明。

这一层是衍生作品：它依附原作的台词、人名与剧情才成立，所以本段授权的只是本项目作者自己写下的
那部分中文文字。商业用途需要自行向原作版权方取得授权。

## 三、分发范围

仓库里只有工具、文档和中文正文，不含游戏内容本体：

* 不含镜像（`*.sfc`／`*.smc`）、补丁成品（`*.ips`／`*.bps`／`*.xdelta`）、
  存档（`*.srm`／`*.bsz`）与镜像压缩包（`*.zip`）——`.gitignore` 把这一族整批挡住。
  中文镜像由使用者拿自己的日版 Rev 1 镜像跑 `tools/build_zh.py --patch` 重建。
* 不含从镜像解出的原作文本。`docs/research/` 下那批派生表（`blockN_jp.txt`、`blockN_work.tsv`、
  `blockN_enc.json` 等）是原镜像的逐格日文原文与断点表，一条命令重生成，流程见 `README.md`。
* 不含 `reference/`：那是第三方 J2E 同人汉化素材（约 18 MB），只在本机作为只读查证输入。
* 不含字体文件。镜像里写进去的点阵字模每次构建时从本机安装的**文泉驿 13px**
  （`wenquanyi_13px.pcf`，GPL 附加字体例外条款）现生成，该字体版权仍属文泉驿项目。
