"""START 失效矩阵实验 (bsnes + 补丁前端):
先测 state 存取是否忠实 (忠实则每个试验从检查点重放, 干净且快)。
变体: 短按 / 长按60/180帧 / 三连快打 / SELECT+START / START+UP / 转场途中按START
"""
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play import env, act, step, press, NONE  # noqa: E402

OUT = "/tmp/play/start_matrix"
os.makedirs(OUT, exist_ok=True)
TEMPLATE = np.asarray(Image.open("/tmp/play/patched_name.png"), dtype=float)
GRID = (slice(48, 140), slice(95, 260))
BTN = {name: i for i, name in enumerate(env.buttons)}


def fb():
    return np.asarray(env.get_screen(), dtype=np.uint8)


def save(tag):
    Image.fromarray(env.get_screen()).save(f"{OUT}/{tag}.png")


def grid_mad():
    img = fb()
    if img.shape[1] < 260:
        return 999.0
    return np.abs(img[GRID].astype(float) - TEMPLATE[GRID]).mean()


def hold(button, frames):
    arr = np.zeros(env.num_buttons, dtype=np.uint8)
    arr[BTN[button]] = 1
    for _ in range(frames):
        env.step(arr)


def combo(buttons, frames):
    arr = np.zeros(env.num_buttons, dtype=np.uint8)
    for b in buttons:
        arr[BTN[b]] = 1
    for _ in range(frames):
        env.step(arr)


def release(frames=30):
    for _ in range(frames):
        env.step(NONE)


log = open(f"{OUT}/log.txt", "a")


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def save_cp():
    open(f"{OUT}/cp.state", "wb").write(env.em.get_state())


def load_cp():
    env.em.set_state(open(f"{OUT}/cp.state", "rb").read())
    step(10)


t0 = time.time()
# 到名字画面
step(2200)
for btn in ["START", "START", "A", "A", "A", "A"]:
    press(btn, 12, 90)
    step(60)
    if grid_mad() < 10:
        break
P(f"到达名字画面: {grid_mad() < 10} t={time.time()-t0:.0f}s")
save("M0_name")
save_cp()

# state 忠实性: DOWN 移动光标 -> 存档 -> 移动 -> 读档 -> 应该回到原位
press("DOWN", 10, 40)
after_down = fb().copy()
save_cp() if False else None
open(f"{OUT}/cp2.state", "wb").write(env.em.get_state())
press("DOWN", 10, 40)
load_cp()
same = np.abs(fb().astype(float) - after_down.astype(float)).mean()
P(f"state忠实性: 读档后与存档时差异={same:.2f} (小=忠实)")
save("M1_state_test")

# 试验矩阵: 每个试验前读档
def trial(name, fn):
    load_cp()
    fn()
    step(180)
    m = grid_mad()
    P(f"[{name}] 之后MAD={m:.1f} {'<<< 变化!' if m > 10 else ''}")
    save(f"M_{name}")


trial("hold60", lambda: hold("START", 60))
trial("hold180", lambda: hold("START", 180))
trial("tap3", lambda: [hold("START", 3) or release(4) for _ in range(3)])
trial("sel+start", lambda: combo(["SELECT", "START"], 30))
trial("start+up", lambda: combo(["START", "UP"], 30))
trial("start+A", lambda: combo(["START", "A"], 30))
P(f"总耗时{time.time()-t0:.0f}s")

# 转场途中按 START: 全新冷启动, 在文件菜单按A后立刻连按START
P("=== 转场时序实验: 选初めから后转场期间连按 START ===")
env.close() if False else None
step(2200)
press("START", 12, 90)
step(60)
press("START", 12, 90)
step(60)
press("A", 12, 90)  # 初めから
for i in range(20):  # 转场期间每30帧按一次START, 持续600帧
    hold("START", 6)
    release(24)
    if grid_mad() < 10:
        P(f"转场中按START: 到达名字画面 (第{i}次时)")
        break
P(f"转场实验结束: 在名字画面={grid_mad() < 10}")
save("M2_transition")
# 转场后仍然按几次 START
for k in range(3):
    img = fb()
    hold("START", 12)
    release(60)
    P(f"到达后再按START{k}: MAD={np.abs(fb().astype(float)-img.astype(float)).mean():.2f}")
    save(f"M3_after{k}")
P(f"总耗时{time.time()-t0:.0f}s")
log.close()
