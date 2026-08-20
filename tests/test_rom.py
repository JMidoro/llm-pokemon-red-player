from pathlib import Path
import unittest

import _path  # noqa: F401

from pokemon_player.rom import fingerprint_rom, read_rom_title


class RomTests(unittest.TestCase):
    def test_read_rom_title(self) -> None:
        data = bytearray(0x150)
        data[0x134 : 0x134 + 11] = b"POKEMON RED"
        self.assertEqual(read_rom_title(bytes(data)), "POKEMON RED")

    def test_fingerprint_rom(self) -> None:
        data = bytearray(0x150)
        data[0x134 : 0x134 + 4] = b"TEST"
        test_dir = Path(__file__).parent / ".tmp"
        test_dir.mkdir(exist_ok=True)
        rom = test_dir / "test.gb"
        rom.write_bytes(data)

        try:
            fingerprint = fingerprint_rom(rom)
        finally:
            rom.unlink(missing_ok=True)

        self.assertEqual(fingerprint.title, "TEST")
        self.assertEqual(fingerprint.size_bytes, len(data))
        self.assertEqual(len(fingerprint.md5), 32)
        self.assertEqual(len(fingerprint.sha256), 64)
