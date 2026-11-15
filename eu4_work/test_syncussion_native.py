"""Installed Syncussion through native Multisample admission and rendering.

Provider I/O and the hardware LFO clock are substituted, not note admission,
zone lookup, descriptor copying, voice initialization or audio postprocessing.
"""
import os
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

from test_hihat_native import NativeHat, matched_symbols


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = Path(os.environ["BENTO_FX_CANDIDATE"])
        cls.image = (out / "bento1.bin").read_bytes()
        cls.symbols = matched_symbols(
            cls.image, (out / "workspace/eu4_work/drums/kick.elf").read_bytes())

    def probe(self, pitch=60, polyphony=1):
        p = NativeHat(self.image, self.symbols, None)
        self.addCleanup(p.close)
        p.u.mem_map(0xc0000000, 0x100000)
        proxy, database, context = 0x2001a000, 0x2001a100, 0x20002000
        p.w(p.root + 0x14, proxy)
        p.w(p.root + 0x18, context)
        p.w(proxy, database)
        p.w(proxy + 4, p.provider)
        p.w(database + 8, 0xc0000000)
        p.w(p.root + 0x670, 0)
        p.w(p.root + 0x604, 60)
        p.w(p.root + 0xf4, polyphony)
        p.u.mem_write(p.root + 0x1d, b"\1")
        p.u.mem_write(p.root + 0x625, b"\1")
        p.u.mem_write(p.voice, b"\0")
        # Triangle uses the real native oscillator without a boot-allocated
        # sine table. Its native modulation depth remains zero.
        p.u.mem_write(p.r(p.voice + 0x5dc) + 4, b"\2")
        p.frames = 144035
        for note in range(1, 128):
            zone = 0xc0000000 + note * 0x244
            p.u.mem_write(zone, struct.pack(
                "<I5H2x5I", 7, 60, 1, 127, 0, 127,
                0, p.frames, 0, 0, p.frames))
            p.u.mem_write(zone + 0x240, b"\1\0")
        p.w(0x2003f000, 100)
        p.w(0x2003f004, 0)
        p.w(0x2003f008, 0)
        p.call(0x08094760, p.root, 0x20021000, 0, pitch)
        return p

    def test_native_mono_admits_melodic_carrier_and_produces_audio(self):
        p = self.probe()
        self.assertEqual(p.r(p.voice) & 0xff, 1)
        self.assertEqual(p.r(p.voice + 12), p.desc)
        self.assertEqual(p.call(self.symbols["kick_marker"], p.desc), 15)
        audio = [value for _ in range(32) for value in p.render()]
        self.assertGreater(sum(value * value for value in audio), 1e-6)

    def test_inserted_defaults_execute_through_the_real_native_property_queue(self):
        p = self.probe()
        defaults = (
            (0x1d, 0), (2, 0), (3, 0), (4, 0), (5, 1), (8, 0),
            (0x1c, 0), (0x1e, 0), (0x1f, 0), (0x20, 1000), (0x21, 200),
            (0x2d, 0), (0x2e, 0), (0x31, 0), (0x32, 0), (0x33, 500),
            (0x36, 0), (0x37, 0), (0xe5, 0), (0x3a, 1), (0x3b, 0),
            (0x49, 0), (0x4a, 0), (0x4b, 100), (0x4c, 1000),
            (0x4d, 0), (0x4e, 0), (0x4f, 0), (0x55, 0), (0x73, 0),
            (0x1e0, 0), (0x34, 60), (0x79, 0), (0x7a, 1), (0x7b, 127),
            (0x7c, 0), (0x7d, 0), (0x7e, 0), (0x22, 0), (0x23, 0),
            (0x26, 0), (0x24, 0), (0x25, 0))
        commands = [struct.pack("<6I", 0x3e, 0, 101, key, value, 0)
                    for key, value in defaults]
        consumed = []

        def queue(u, address, size, data):
            if address in (0x0809f0c0, 0x0809ed20):
                p.ret(0x2001c000)
            elif address == 0x080655a0:
                index = u.reg_read(UC_ARM_REG_R1)
                if index < len(commands):
                    u.mem_write(u.reg_read(UC_ARM_REG_R2), commands[index])
                    consumed.append(index)
                p.ret(int(index < len(commands)))
            else:
                u.emu_stop()

        hooks = [p.u.hook_add(UC_HOOK_CODE, queue, begin=a, end=a)
                 for a in (0x0809f0c0, 0x0809ed20, 0x080655a0, 0x0808eca0)]
        p.w(0x2001c000, 0x20002000)
        p.u.reg_write(UC_ARM_REG_R0, p.root)
        p.u.reg_write(UC_ARM_REG_R1, 0x2001c000)
        p.u.reg_write(UC_ARM_REG_SP, 0x2003f000)
        p.u.reg_write(UC_ARM_REG_LR, p.stop | 1)
        try:
            p.u.emu_start(0x080945e1, 0, count=1000000)
        finally:
            for hook in hooks:
                p.u.hook_del(hook)
        self.assertEqual(p.u.reg_read(UC_ARM_REG_PC), 0x0808eca0)
        self.assertEqual(consumed, list(range(len(commands))))
        self.assertEqual(p.r(p.root+0xf4), 1)
        self.assertEqual(p.r(p.root+0x604), 60)
        # As in probe(), use a table-free LFO waveform in this unbooted fixture.
        p.u.mem_write(p.r(p.voice+0x5dc)+4, b"\2")
        p.u.mem_write(p.voice, b"\0")
        p.call(0x08094760, p.root, 0x20021000, 0, 60)
        audio = [value for _ in range(32) for value in p.render()]
        self.assertGreater(sum(value * value for value in audio), 1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
