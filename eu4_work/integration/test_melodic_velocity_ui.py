"""Melodic Vel Mode through native piano/encoder constructors and raster code."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest

from test_tracks import emu, render, UC_HOOK_CODE
from test_integration import IMAGE, UU
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R3,
                               UC_ARM_REG_LR, UC_ARM_REG_PC)

VIEW, POINT = 0xc0400000, 0x24070000
MODEL = 0x30024b00
KEEP = []


class Piano:
    def __init__(self):
        KEEP.append(self)
        self.e = emu.Emu(IMAGE)
        self.u = self.e.u
        render.boot_gfx(self.e)
        self.e.call(0x081639a8, 0)
        self.e.call(0x0815930c, VIEW)
        self.hooks = [self.u.hook_add(UC_HOOK_CODE, self.service, begin=a, end=a)
                      for a in (0x08133cfc, 0x08133f7c, 0x08133614, 0x081599bc)]
        self.u.mem_write(MODEL+0x12c, b"\x17")
        for offset, value in ((0x11cd00, 0x140), (0x11cd08, 0x13e),
                              (0x11cd18, 16), (0x11cd14, 10)):
            self.e.w(VIEW+offset, value)
        self.u.mem_write(VIEW+0x125dae, b"\0")
        self.u.mem_write(POINT, struct.pack("<5I", 0x1054, 0, 0, 0, 0))
        assert self.call("piano_eu_event", VIEW, POINT) == 1
        self.bar = VIEW+0x55f0
        self.slot = self.bar+0x38+6*0x468
        self.u.mem_write(POINT, struct.pack("<4i", 6, 382, 1268, 90))
        self.e.call(self.e.r(self.e.r(self.bar)+0x20), self.bar, POINT)
        self.e.w(POINT+0x100, 0x101)
        self.e.call(self.e.r(self.e.r(self.bar)), self.bar, POINT+0x100)
        self.call("piano_eu_header", VIEW)

    def service(self, u, address, size, data):
        result = 1
        if address == 0x08133cfc:
            self.e.w(u.reg_read(UC_ARM_REG_R1), 0x13e)
        elif address == 0x08133f7c:
            result = 15
        elif address == 0x08133614:
            self.e.w(u.reg_read(UC_ARM_REG_R3), 0)
        # Header navigation/model lookup is outside this focused fixture;
        # descriptor binding, widget initialization and drawing remain native.
        u.reg_write(UC_ARM_REG_R0, result)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def call(self, name, *args):
        result = self.e.call(UU[name], *args)
        assert self.u.reg_read(UC_ARM_REG_PC) == emu.RET
        return result

    def paint(self, full):
        self.e.w(render.CTX, 0x101 if full else 0x100)
        render.paint(self.e, self.bar)
        self.call("melodic_eu_glyph_paint", VIEW, render.CTX)


class Tests(unittest.TestCase):
    def test_native_value_is_blank_while_velocity_symbol_remains_visible(self):
        import numpy as np
        p = Piano()
        self.assertEqual(p.u.mem_read(p.slot+0x9c, 2), b"\x94\x01")
        self.assertEqual(p.e.text(p.slot+0x3c8+0x31), "Vel Mode")
        label = p.slot+0xa8
        x, y, w, h = struct.unpack("<4i", p.u.mem_read(label+4, 16))
        symbols = set()
        for mode in range(10):
            with self.subTest(mode=mode):
                p.u.mem_write(POINT, struct.pack("<5I", 0xcf, 0x140, N.NKEY(0x194), mode, 0))
                self.assertEqual(p.call("piano_eu_event", VIEW, POINT), 1)
                p.call("piano_eu_header", VIEW)
                self.assertEqual(p.e.text(p.slot+0xd9), " ")
                p.paint(True)
                full = render.ui(p.e)[480-y-h:480-y, x:x+w].copy()
                self.assertGreater(np.count_nonzero(full == 0xf2), 0)
                symbols.add(full.tobytes())
                p.paint(False)
                partial = render.ui(p.e)[480-y-h:480-y, x:x+w]
                self.assertTrue(np.array_equal(full, partial))
                self.assertEqual(p.e.text(p.slot+0xd9), " ")
        self.assertEqual(len(symbols), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
