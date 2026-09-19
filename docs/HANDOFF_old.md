# 《心跳回忆:传说的树下》汉化项目交接文档

## 项目现状总览
**已完成可用的**:P1「請教名字?」中文渲染(截图验证)、公园捡书对话全段中文(126B)、
神社对话 34 片段中文——全部已写入主 ROM 并通过往返自检。
**翻译管线全通**:模板 47265 段 → TM 翻译记忆 → 编码器 → 就地回插 → 自检。

## 工具链(全部可运行)
- `tools/extract_all.py` — 全文本抽取(145 块,指针表公式已验证)
- `tools/insert_zh.py` — 中文编码器+就地回插(list/patch 命令,双行表)
- `tools/translate_batch.py` — TM 翻译记忆流水线(translations/tm.json 可增量)
- `tools/collect_anchors2.py` — 锚字收集器(覆盖表扩容)
- `tools/build_template.py` / `build_codetable` 待建
- 数据:`out/script/`(模板/映射/覆盖表/行表)、`translations/`(TKSC2/3 稿+神社译文)

## 已破解的技术事实(全部实证)
1. 文本块指针表:NAME_PTR=0x9872, TEXT_PTR=0x9A25,各 145 项×3B
   file = (bank-0x80)*0x8000 - 0x7E00 + (b1<<8|b0)
2. 窗口块编码(UI):假名 SJIS+0x6E0B;汉字 SJIS+ROWDELTA[row](0x88-0x98)
3. 对话块编码:行表 = UI 表变体(0x89:0x68E2, 0x8B:0x685A, 0x8F:0x674A,
   0x91:0x66C2, 0x94:0x65F6, 0x95:0x65B2, 0x96:0x656F, 0x98:0x64E7, 0x9A:0x64BE)
4. 控制码:~12=名字变量、~A0=空格、~2E=等待、0x0A=换行(UI)、$80:D4E4=假名码表
5. 池条目格式 = SNES 2bpp 64B tile(16x16,白/影/透明 3 色)
6. 字库(网格/菜单假名+部分汉字)= 0x3E8002+idx*32,32B 1bpp,3072 槽
7. 名字画面文本源 = file 0x1F094(UI 块);F000=空格前缀,F008=问号,0A=换行

## 未破解(两个硬缺口,均需调试器实证)
### A. 对话字形位流格式
- FONT ROUTINE = SNES $81:D23D(file 0x523D),已反汇编主流程
- $D490:页规格化(商+0xFD=bank 回绕,余×28|0x8000)
- $D4BD:假名码表修正($80:D4E4,码域 AB-FC)
- **缺口**:LDA [$00],Y 的地址计算与码的传入方式未实证
- **破解法**:bsnes Debugger 断点 $7E:0A80(名字缓冲写),抓 FONT ROUTINE 调用栈
  与 [$00] 装载指令 → 反推流偏移公式
### B. 姓→名转场判定
- 黑盒穷尽(按键矩阵/状态 patch/计数器),需断点 $7E:0A80 读 + $0D50-52 计数器
- 或 bsnes Trace Logger 全程记录一次输入流程

## 关键数据文件
- `/tmp/rom_backup_pretalk.sfc` — 公园插入前备份
- `/tmp/rom_backup_today.sfc` — 本日备份(含公园中文)
- `/tmp/romA.sfc`(請)/`romB2.sfc`(私)/`stateA.bin`/`stateB2.bin` — diff 法样本
- 主 ROM:TKSC 神社块(0x1C8200)34 片段中文 + 公园(0x250200)+ P1(0x1F094)

## 翻译资源
- `translations/TKSC2_zh.tsv`、`TKSC3_zh.tsv`(已完成 95 段)
- `translations/shrine_zh.json`(神社 71 片段,34 已回插)
- `translations/pending.json`(全 26033 段待翻清单)
- JIS 缺字清单(需 Unifont):你 说 这 们 吧 啊 呢 嗯 嗎 么 签 谢...

## 下一步建议优先级
1. 【需调试器】字库位流格式(bsnes 断点法,~1 小时)
2. 【无需调试器】块133 系统消息翻译(JIS 措辞,片假名锚定后)
3. 【无需调试器】剩余神社片段高行 delta 校准后补翻
4. 【需调试器】转场判定 → 公园/神社场景截图验证
5. 【大工程】Unifont→2bpp tile 转换器(格式 A 破解后)

## 附:bsnes 手动 trace 操作指南 (字库格式破解, 约 10 分钟)

**准备**: 主 ROM 已含神社中文; 需要的断言地址: $7E:0A80 (名字缓冲写)

1. 启动 ~/retro/bsnes/bsnes, 载入主 ROM
2. 菜单 Tools → Debugger 打开调试器面板
3. 启用 Trace Logger:
   - 勾选 "Mask off bytes"? 不需要
   - 断言(Assembly Watch/Breakpoint): 写地址 $7E:0A80
4. 冷启动: File → Power Cycle
5. 走到名字画面 (START → ゲームスタート → A → 初めから → A)
6. 输入 2-3 个假名 (网格选字按 A)
7. 断点命中时, 记录调试器显示的 PC 地址 (即名字输入引擎!)
8. 单步运行 20-50 条指令, 记录寄存器 A/X/Y 变化

**拿到 trace/PC 地址后我能立即**:
- 反汇编输入引擎 → 破解「码→字形位流」公式
- 定位決定键判定 → 打通姓→名转场
- 公园/神社中文场景截图验证

## 附: 转场判定调试指南
1. 断点: $7E:0052 (光标计数器) 读
2. 姓 3 字满后按 START — 若断点命中 = 游戏在检查字数
3. 观察 PC 路径 → 找到拒绝原因

## ★ 重要发现 (最新)
stable-retro 模拟器对该游戏的 START 按键存在兼容性问题——
即使原版未修改 ROM，START 也无法推进名字输入画面。
这意味着：ROM 中的中文文本编码是正确的，
只是无法通过 stable-retro 来验证对话场景的渲染。

**验证方法：用 bsnes 或其他模拟器加载汉化 ROM，正常游玩即可看到中文。**
