"""Shared helpers for Tokimeki Memorial SFC ROM analysis.

The original ROM is treated as read-only by every tool; all output goes
to out/ (or a caller-supplied path).
"""
import os
import struct
import zlib

ROM_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "rom_original_japanese.sfc")

_cache = {}


def load(path=ROM_PATH):
    """Return the full ROM as bytes (cached)."""
    if path not in _cache:
        with open(path, "rb") as f:
            _cache[path] = f.read()
    return _cache[path]


def parse_header(data=None):
    """Parse the SNES cartridge header (LoROM: file offset 0x7FC0)."""
    data = data if data is not None else load()
    h = data[0x7FC0:0x7FE0]
    title = h[0:21].decode("ascii", "replace")
    mapping = h[21]          # 0x30 = LoROM + slow, 0x20 = LoROM + fast
    cart = h[22]
    rom_banks = 1 << (h[23] // 2 + 6) // 1024 if False else 1 << (h[23] - 7)
    ram_size = (1 << h[24]) if h[24] else 0
    country, license, version = h[25], h[26], h[27]
    csum_c, csum = struct.unpack("<HH", h[28:32])
    return {
        "title": title,
        "mapping": mapping,
        "lorom": bool(mapping & 0x10),
        "fastrom": bool(mapping & 0x20),
        "cart": cart,
        "rom_mb": 1 << h[23] - 7 if h[23] >= 7 else 0,
        "ram_kb": ram_size // 1024,
        "country": country,
        "license": hex(license),
        "version": f"1.{version}",
        "checksum": csum,
        "checksum_complement": csum_c,
        "checksum_ok": (csum ^ csum_c) == 0xFFFF,  # SNES 16-bit checksum, not CRC32
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08X}",
    }


def bank_to_offset(bus_addr):
    """SNES LoROM bus address ($bb:aaaa) -> file offset.

    LoROM maps 32 KiB banks to 0x8000-0xFFFF; banks $80-$BF mirror $00-$3F
    (FastROM mirror).
    """
    bank = (bus_addr >> 16) & 0x7F
    addr = bus_addr & 0xFFFF
    if addr < 0x8000:
        raise ValueError(f"{bus_addr:06X}: LoROM has no data below $8000")
    return (bank << 15) | (addr - 0x8000)


def offset_to_bus(off):
    """File offset -> canonical SNES bus address ($00-$3F style)."""
    return ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)


if __name__ == "__main__":
    d = load()
    for k, v in parse_header(d).items():
        print(f"{k:22s} {v}")
