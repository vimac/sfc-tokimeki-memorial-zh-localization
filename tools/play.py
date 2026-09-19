"""Headless play driver with save-state checkpoints.

Run stages:
  python3 tools/play.py stage1   # boot -> title -> game start -> intro
Checkpoints saved to /tmp/play/states/*.state
"""
import os
import sys
import time

import numpy as np
from PIL import Image

import stable_retro as retro

OUT = "/tmp/play"
STATEDIR = os.path.join(OUT, "states")
os.makedirs(STATEDIR, exist_ok=True)

env = retro.make("TokimekiSFC-Snes-v0", players=1, use_restricted_actions=retro.Actions.ALL)
obs, info = env.reset()
BTN = {name: i for i, name in enumerate(env.buttons)}
NB = env.num_buttons


def act(**kw):
    a = np.zeros(NB, dtype=np.uint8)
    for k, v in kw.items():
        a[BTN[k]] = v
    return a


NONE = act()


def step(n=1, a=None):
    a = NONE if a is None else a
    for _ in range(n):
        env.step(a)


def shot(name):
    Image.fromarray(env.get_screen()).save(os.path.join(OUT, f"{name}.png"))
    print("shot", name)


def save_state(name):
    with open(os.path.join(STATEDIR, name + ".state"), "wb") as f:
        f.write(env.em.get_state())
    print("saved state", name)


def load_state(name):
    with open(os.path.join(STATEDIR, name + ".state"), "rb") as f:
        env.em.set_state(f.read())
    print("loaded state", name)


def press(button, n=8, settle=40, shots=None):
    a = act(**{button: 1})
    for _ in range(n):
        env.step(a)
    step(settle)
    if shots:
        shot(shots)


def ram():
    return bytes(env.get_ram())


def stage1():
    """Boot, wait for title, select game start, walk into intro dialogs."""
    step(150)                       # Konami logo
    shot("s1_00_logo")
    step(200)                       # title fade-in
    shot("s1_01_title")
    press("START", 8, 90)           # select game start
    shot("s1_02_after_start")
    press("START", 8, 120)          # confirm / next
    shot("s1_03_next1")
    press("A", 8, 120)
    shot("s1_04_next2")
    press("A", 8, 120)
    shot("s1_05_next3")
    press("A", 8, 120)
    shot("s1_06_next4")
    save_state("s1_end")


def ramdiff_probe():
    """From a checkpoint, dump RAM, step some frames, diff."""
    ram0 = ram()
    shot("probe_0")
    step(60)
    ram1 = ram()
    shot("probe_1")
    diff = [i for i in range(min(len(ram0), len(ram1))) if ram0[i] != ram1[i]]
    print(f"changed bytes: {len(diff)}; first: {diff[:40]}")
    return ram0, ram1


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "stage1"
    t0 = time.time()
    if stage == "stage1":
        stage1()
    elif stage == "probe":
        load_state(sys.argv[2])
        ramdiff_probe()
    print(f"{time.time() - t0:.1f}s")
    env.close()
