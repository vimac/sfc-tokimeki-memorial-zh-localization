"""Sync the emulator's single ROM slot before any tool imports play.py.

stable_retro builds the env from one fixed path at import, so a tool that names a
ROM on the command line has to install it there first.  Skipping that silently
traces whichever ROM the last run left behind -- which once made a Chinese patch
report byte-identical pointers to the Japanese original.
"""
import os
import shutil

SLOT = os.path.expanduser(
    '~/.local/lib/python3.14/site-packages/stable_retro/data/stable/'
    'TokimekiSFC-Snes-v0/rom.sfc')


def use(rom):
    with open(SLOT, 'rb') as f:
        cur = f.read()
    with open(rom, 'rb') as f:
        want = f.read()
    if cur != want:
        shutil.copyfile(rom, SLOT)
    return SLOT
