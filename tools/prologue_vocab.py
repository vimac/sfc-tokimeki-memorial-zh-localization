"""序章词表分析: 从 code_gaps 提取每个码的候选字。
单字符 gap = 单字码; 多字符一致 gap = 词码。输出可用码表清单。
"""
import json
from collections import defaultdict, Counter

gaps = json.load(open('/tmp/prologue_code_gaps.json'))
KANA_SET = set("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわをんっゃゅょ、。「」…・ー？！〜§◇ ")

info = {}
for c, (p, n, g) in gaps.items():
    code = int(c, 16)
    core = ''.join(ch for ch in g if ch not in KANA_SET)
    info[code] = {'gaps': g, 'core': core, 'count': len(g)}

# 单字码
single = {}
for code, d in info.items():
    if len(d['core']) == 1 and d['count'] >= 1:
        single.setdefault(d['core'], []).append(code)
# 多字词码 (core 2-6 字, 多次出现同 core)
words = {}
for code, d in info.items():
    if 2 <= len(d['core']) <= 6:
        words.setdefault(d['core'], []).append(code)

print("=== 单字码 ===")
for ch in sorted(single):
    codes = ','.join(f'{c:04X}' for c in single[ch])
    print(f"  {ch}: {codes}")
print("=== 词码 (core 2-6字) ===")
for w in sorted(words):
    codes = ','.join(f'{c:04X}' for c in words[w])
    print(f"  {w}: {codes}")
json.dump({'single': single, 'words': words},
          open('/tmp/prologue_vocab_full.json', 'w'), ensure_ascii=False, indent=1)
