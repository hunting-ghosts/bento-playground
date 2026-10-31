"""Verify identity-only scope and execute both real native version consumers."""
import argparse
import hashlib
from pathlib import Path
import struct
import unittest

from preview_identity import (
    BASE, COPY, COPY_AFTER, LABEL, POINTERS, VERSION, W22_SHA, apply,
    displayed_version,
)
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_R7, UC_ARM_REG_R0, UC_ARM_REG_SP

p = argparse.ArgumentParser()
p.add_argument("--w22", type=Path, required=True)
p.add_argument("--preview", type=Path, required=True)
a = p.parse_args()
before = a.w22.read_bytes()
image = a.preview.read_bytes()


class IdentityTests(unittest.TestCase):
    def test_exact_identity_and_reversibility(self):
        expected, writes = apply(before)
        self.assertEqual(image, expected)
        self.assertEqual(displayed_version(image), LABEL)
        restored = bytearray(image)
        for w in reversed(writes):
            o = w["address"] - BASE
            restored[o:o + w["size"]] = bytes.fromhex(w["original_hex"])
        self.assertEqual(bytes(restored), before)
        self.assertEqual(hashlib.sha256(restored).hexdigest(), W22_SHA)

    def test_only_declared_application_ranges_change(self):
        allowed = {i for address, size in [(x, 4) for x in POINTERS] + [(COPY, 12)]
                   for i in range(address - BASE, address - BASE + size)}
        self.assertTrue(all(x == y or i in allowed
                            for i, (x, y) in enumerate(zip(before, image))))
        text = LABEL.encode() + b"\0"
        self.assertEqual(image[len(before):], text + bytes(-len(text) % 4))
        self.assertEqual(image[:0x400], before[:0x400])
        self.assertEqual(image[0xA0000:0xC0000], before[0xA0000:0xC0000])
        self.assertEqual(image[0xC0000:0xC0400], before[0xC0000:0xC0400])
        self.assertEqual(image[0x14BAD4:0x14BAF0], before[0x14BAD4:0x14BAF0])
        self.assertEqual(len(image) % 4, 0)
        self.assertLessEqual(BASE + len(image), 0x081E0000)

    def test_wrong_preimage_refused(self):
        for bad in (image, before[:-4], b"X" + before[1:]):
            with self.assertRaises(ValueError):
                apply(bad)

    def test_native_about_screen_receives_full_name(self):
        u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.mem_map(0x08000000, 0x200000)
        u.mem_write(BASE, image)
        u.mem_map(0x20000000, 0x10000)
        u.reg_write(UC_ARM_REG_SP, 0x20008000)
        u.reg_write(UC_ARM_REG_R7, 0x20001000)
        seen = []

        def capture(uc, address, size, data):
            if address == 0x0817E85E:
                ptr = uc.reg_read(UC_ARM_REG_R1)
                seen.append(bytes(uc.mem_read(ptr, 32)).split(b"\0", 1)[0])
                self.assertEqual(uc.reg_read(UC_ARM_REG_R0), 0x20001000)
                uc.emu_stop()

        hook = u.hook_add(UC_HOOK_CODE, capture)
        u.emu_start(0x08162A98 | 1, 0x08162AAC, count=20)
        self.assertEqual(seen, [LABEL.encode()])
        self.assertIsNotNone(hook)

    def test_native_version_formatter_uses_relocated_string(self):
        # Native 0813103C loads version into r3 for its bounded 64-byte formatter.
        u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.mem_map(0x08000000, 0x200000)
        u.mem_write(BASE, image)
        u.emu_start(0x0813103C | 1, 0x0813103E, count=1)
        self.assertEqual(u.reg_read(UC_ARM_REG_R3), VERSION)
        self.assertEqual(bytes(u.mem_read(VERSION, len(LABEL) + 1)), LABEL.encode() + b"\0")


if __name__ == "__main__":
    unittest.main(argv=[__file__], verbosity=2)
