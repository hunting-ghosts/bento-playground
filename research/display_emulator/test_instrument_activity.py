"""W6 native sample-publication evidence, not an audio or hardware test."""
import argparse
import hashlib
import struct
import unittest
from pathlib import Path

import emu
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1


class NativeActivity(unittest.TestCase):
    image = None

    def setUp(self):
        self.e = emu.Emu(self.image)
        self.root, self.voice, self.file = 0xC0400000, 0xC0410000, 0xC0420000
        self.context, self.publication, self.copied = 0xC0430000, 0xC0600000, 0x24070000
        self.events, self.callbacks = [], []
        self.e.w(0x3000F650, self.publication)
        self.service(0x08065600, self.capture)
        self.service(0x08054EC0, lambda: 10000)
        self.service(0x08054F60, lambda: 0)
        self.service(0x08071220, lambda: 0)
        self.e.w(self.root + 0x60, 1)
        self.e.w(self.root + 0x20, self.voice)
        self.e.w(self.root + 0xC, 0x91)
        self.e.u.mem_write(self.root + 0x670, struct.pack("<HH", 1, 0))
        self.e.u.mem_write(self.voice, b"\x01\x00\x01")
        self.e.w(self.voice + 0xC, self.file)
        self.e.w(self.file + 4, 0x1234)
        self.call(0x08082280, self.publication, 16, 3, 0xFFFFFFFF)

    def service(self, address, function):
        def callback(u, addr, size, data):
            u.reg_write(UC_ARM_REG_R0, function() or 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        self.callbacks.append(callback)
        self.e.u.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)

    def call(self, address, *args):
        result = self.e.call(address, *args)
        self.assertEqual(self.e.u.reg_read(UC_ARM_REG_PC), emu.RET)
        return result

    def capture(self):
        address = self.e.u.reg_read(UC_ARM_REG_R1)
        self.events.append(bytes(self.e.u.mem_read(address, 24)))
        return 1

    def report(self):
        start = len(self.events)
        self.call(0x08093780, self.root, self.context)
        reports = self.events[start:]
        # Native 08058148 / 08058204 dispatches these exact report fields.
        # Run after the reporter returns, avoiding nested emulator execution.
        for event in reports:
            pad = struct.unpack_from("<H", event, 6)[0]
            if event[0] == 0x55:
                self.call(0x080821E0, self.publication, pad, struct.unpack_from("<I", event, 16)[0])
                self.call(0x080822A0, self.publication, pad,
                          struct.unpack_from("<h", event, 20)[0] & 0xFFFFFFFF)
                self.call(0x08082200, self.publication, pad, struct.unpack_from("<I", event, 12)[0])
            else:
                self.assertEqual(event[0], 0x57)
                self.call(0x08082280, self.publication, pad, 3, 0xFFFFFFFF)
        self.call(0x081311B8, self.copied, 0, 1, 0)
        record = struct.unpack("<hBBIB", bytes(self.e.u.mem_read(self.copied, 9)))
        return reports, record

    def test_single_voice_reports_zero_mid_end_and_completion(self):
        for position, ending in ((1, 0), (5000, 0), (9999, 0), (9999, 1)):
            with self.subTest(position=position, ending=ending):
                self.e.w(self.voice + 0x40, position)
                self.e.u.mem_write(self.voice + 1, bytes([ending]))
                reports, record = self.report()
                self.assertEqual([event[0] for event in reports], [0x57 if ending else 0x55])
                self.assertEqual(record, (-1 if ending else position // 10, 3, 0, 0x1234, 0))

    def test_completion_clears_publication_with_another_voice_active(self):
        second = self.voice + 0x1000
        self.e.u.mem_write(second, bytes(self.e.u.mem_read(self.voice, 0x800)))
        self.e.u.mem_write(second, b"\x01\x01\x01")
        self.e.w(self.voice + 0x40, 1000)
        self.e.w(second + 0x40, 9999)
        self.e.w(self.root + 0x60, 2)
        self.e.w(self.root + 0x24, second)
        reports, record = self.report()
        self.assertEqual([event[0] for event in reports], [0x55, 0x55, 0x57])
        self.assertEqual(self.e.u.mem_read(self.voice, 1)[0], 1)
        self.assertEqual(self.e.r(self.root + 0x60), 1)
        self.assertEqual(record, (-1, 3, 0, 0x1234, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    NativeActivity.image = args.image.read_bytes()
    digest = hashlib.sha256(NativeActivity.image).hexdigest()
    if digest != "cf83652215b8d96424fb29b8074e15a713247359845b172494bfaabf272fb8c3":
        parser.error("This evidence fixture requires the exact W6 application image.")
    unittest.main(argv=[__file__], verbosity=2)
