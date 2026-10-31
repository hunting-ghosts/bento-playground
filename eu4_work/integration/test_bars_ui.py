"""Bars encoder: the leftmost option maps to native open-length recording."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_integration import Fixture

SOURCE = Path(__file__).resolve().parent
ORIGIN = 0x081E0000
REGISTRY = 0xC0180000
VIEW = 0xC0000000
EVENT = 0x20028000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]


def elf(path):
    data = path.read_bytes()
    offset = struct.unpack_from("<I", data, 32)[0]
    stride, count = struct.unpack_from("<HH", data, 46)
    chunks, symbols = [], {}
    sections = [struct.unpack_from("<10I", data, offset + i * stride)
                for i in range(count)]
    for section in sections:
        if section[2] & 2 and section[1] != 8:
            chunks.append((section[3], data[section[4]:section[4] + section[5]]))
        if section[1] != 2:
            continue
        strings_section = sections[section[6]]
        strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
        for i in range(0, section[5], section[9]):
            name, value, _, info, _, index = struct.unpack_from(
                "<IIIBBH", data, section[4] + i)
            if index and info & 15 == 2:
                symbols[strings[name:].split(b"\0")[0].decode()] = value & ~1
    return chunks, symbols


def compile_bars():
    with tempfile.TemporaryDirectory(prefix="bento-bars-") as directory:
        out = Path(directory)
        linker = out / "bars.ld"
        linker.write_text(
            f"SECTIONS {{ . = {ORIGIN:#x}; .text : {{ *(.text*) *(.rodata*) }} "
            "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n")
        support = out / "support.c"
        support.write_text(
            "int chord_view_visible(void){return *(volatile int*)0x2003f100;}\n")
        command = [
            os.environ.get("BENTO_ZIG_PYTHON", "python3"), "-m", "ziglang", "cc",
            "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4",
            "-mfloat-abi=soft", "-Oz", "-g", "-ffreestanding", "-fno-builtin",
            "-fno-stack-protector", "-nostdlib", "-Wl,--entry=bars_event",
            "-Wl,--script=" + str(linker), str(SOURCE / "bars_ui.c"),
            str(support),
            "-o", str(out / "bars.elf")]
        subprocess.run(command, check=True, capture_output=True, text=True)
        chunks, symbols = elf(out / "bars.elf")
        return chunks, symbols


class BarsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks, cls.symbols = compile_bars()

    def setUp(self):
        self.p = Fixture()
        for address, code in self.chunks:
            self.p.u.mem_write(address, code)
        self.p.w(0x30031484, REGISTRY)
        self.p.w(VIEW + 0x11CD00, 77)
        self.p.w(VIEW + 0x11CD10, 0)
        self.p.w(VIEW + 0x11CD14, 10)
        self.p.w(VIEW + 0x11CD18, 0)
        self.calls = []
        for address in (0x0815A598, 0x081599BC, 0x08170656,
                        0x08171C1C, 0x0817E85E):
            self.p.u.hook_add(UC_HOOK_CODE, self.native,
                              begin=address, end=address)

    def native(self, u, address, size, data):
        regs = [u.reg_read(reg) for reg in REGS]
        if address == 0x0815A598:
            self.calls.append(tuple(self.p.r(regs[1] + i * 4) for i in range(5)))
        self.p.ret()

    def test_open_is_first_bars_encoder_choice_and_sets_native_zero_length(self):
        self.assertEqual(self.p.call(self.symbols["bars_registry"], VIEW), 1)
        descriptor = REGISTRY + 0x177 * 32
        choices = self.p.r(descriptor + 8)
        self.assertEqual(self.p.text(self.p.r(choices)), "Open")
        self.assertEqual((self.p.r(descriptor + 12),
                          self.p.r(descriptor + 16),
                          self.p.r(descriptor + 20)), (17, 0, 16))
        self.p.call(self.symbols["bars_bind"], VIEW, 4)
        self.assertEqual(self.p.r(VIEW + 0x11BCD0 + 4 * 4), 0)

        self.p.w(EVENT, 0xCF)
        self.p.w(EVENT + 8, 0x177)
        self.p.w(EVENT + 12, 0)
        self.assertEqual(self.p.call(self.symbols["bars_event"], VIEW, EVENT), 1)
        self.assertEqual(self.calls, [(0xCF, 0, 0x62, 0, 0)])

    def test_one_bar_remains_the_next_choice_and_keeps_native_step_count(self):
        self.p.w(VIEW + 0x11CD18, 16)
        self.assertEqual(self.p.call(self.symbols["bars_registry"], VIEW), 1)
        descriptor = REGISTRY + 0x177 * 32
        self.assertEqual(self.p.text(self.p.r(self.p.r(descriptor + 8))), "Open")
        self.p.call(self.symbols["bars_bind"], VIEW, 4)
        self.assertEqual(self.p.r(VIEW + 0x11BCD0 + 4 * 4), 1)

        self.p.w(EVENT, 0xCF)
        self.p.w(EVENT + 8, 0x177)
        self.p.w(EVENT + 12, 1)
        self.assertEqual(self.p.call(self.symbols["bars_event"], VIEW, EVENT), 1)
        self.assertEqual(self.calls, [(0xCF, 0, 0x62, 16, 0)])

    def test_chord_editor_keeps_its_existing_zero_based_bar_values(self):
        labels = self.p.call(self.symbols["bars_names"])
        self.assertEqual(self.p.text(self.p.r(labels)), "1")
        self.p.w(0x2003F100, 1)
        self.p.w(EVENT, 0xCF)
        self.p.w(EVENT + 8, 0x177)
        self.p.w(EVENT + 12, 0)
        self.assertEqual(self.p.call(self.symbols["bars_event"], VIEW, EVENT), 1)
        self.assertEqual(self.calls, [(0xCF, 0, 0x62, 16, 0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
