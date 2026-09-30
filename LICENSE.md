# 许可

本仓库分两层授权，**两层都不覆盖原游戏《心跳回忆：传说的树下》的任何内容**。

## 一、`tools/` 与文档：MIT

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

这一层包括：全部 Python 脚本、`AGENTS.md`／`PROGRESS.md`／`README.md`、`docs/research/*.md`
里的逆向结论与账本（地址、偏移、裁决记录），以及 `docs/research/*.json` 那些索引表。

## 二、中文正文：非商用

`docs/research/*_zh.txt`（含 `prologue_zh.txt`、`block8_zh.txt`）与 `translations/` 三张口径表里的
中文译文是粉丝同人成果。你可以为了自己在正版卡带上使用而复制、修改、重新构建，也可以转载、
继续润色、二次整理——**唯一条件是不得用于商业目的**（不收费、不打包进收费产品、不用于引流变现）。
请在再分发时保留本文件与本段说明。

这些中文文本是**衍生作品**：它依赖原作的台词、人名、剧情才成立。本项目的作者不对原作文本主张
任何权利，也不代表原作版权方。任何商业使用请自行去取得版权方授权。

## 三、仓库里不含的东西

* **游戏镜像与补丁**：本仓库不含 `.sfc`／`.smc` 镜像，也不含 IPS／BPS／xdelta 成品补丁。
  `.gitignore` 把这一族全部挡住（`*.sfc`、`*.zip`、`*.srm`、`*.ips`、`*.bps`、`*.bsz`）。
  构建必须由使用者自备正版镜像跑 `tools/build_zh.py --patch`。
* **存档与模拟器截图**：`.srm`、按镜像名自动出的 `.bmp`、走查渲染目录同理不入库。
* **`reference/`**：第三方 J2E 同人素材（约 18 MB），只作只读查证输入，不属于本仓库、不随仓库分发。
* **字库带**：镜像里生成的点阵字模来自**文泉驿 13px**（`wenquanyi_13px.pcf`，GPL 附加字体例外条款），
  字体版权仍属文泉驿项目；本仓库不复制该字体文件，只按 `tools/wqyfont.py` 在构建时读取本机安装的它。

## 四、跑起来需要什么

见 `README.md` 的「你要准备什么」。
