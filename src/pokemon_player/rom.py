from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5, sha256
from pathlib import Path


@dataclass(frozen=True)
class RomFingerprint:
    path: Path
    size_bytes: int
    title: str
    md5: str
    sha256: str


def read_rom_title(data: bytes) -> str:
    """Read the Game Boy cartridge title bytes from the ROM header."""
    raw_title = data[0x134:0x144].split(b"\x00", 1)[0]
    return raw_title.decode("ascii", errors="replace").strip()


def fingerprint_rom(path: str | Path) -> RomFingerprint:
    rom_path = Path(path)
    data = rom_path.read_bytes()
    return RomFingerprint(
        path=rom_path,
        size_bytes=len(data),
        title=read_rom_title(data),
        md5=md5(data, usedforsecurity=False).hexdigest().upper(),
        sha256=sha256(data).hexdigest().upper(),
    )

