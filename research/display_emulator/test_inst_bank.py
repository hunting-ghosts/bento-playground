"""Isolated INST paint candidate on W6; no firmware delivery or audio rebuild."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import emu
import render
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eu4_work/integration"))
from build_fx import elf

VIEW, BUFFER, SLOT = 0xC0400000, 0x24071000, 0x24072000


class BankPaint(unittest.TestCase):
    image = None
    symbols = None
    output = None

    def setUp(self):
        self.e = emu.Emu(self.image)
        render.boot_gfx(self.e)
        self.call(0x081505D8, VIEW)
        self.fills, self.labels = [], []
        self.callback = self.observe
        self.hooks = [self.e.u.hook_add(UC_HOOK_CODE, self.callback, begin=a, end=a)
                      for a in (0x08166EF6, 0x0817E448)]
        for pad in range(16):
            self.call(0x081793A2, self.tile(pad), 0)
            for offset in (0x250, 0x29C):
                self.e.u.mem_write(self.tile(pad) + offset + 0x34, struct.pack("<f", -100.0))
            self.e.u.mem_write(BUFFER, struct.pack("<hBBIB", -1, 3, 0, 0, 0))
            self.call(0x08178C54, self.tile(pad) + 0x1FC, BUFFER)
        self.call(0x081793A2, self.tile(8), 1)
        self.e.w(VIEW + 0x6B34, 8)

    def call(self, address, *args):
        value = self.e.call(self.symbols[address] if isinstance(address, str) else address, *args)
        self.assertEqual(self.e.u.reg_read(UC_ARM_REG_PC), emu.RET)
        return value

    def tile(self, pad):
        return VIEW + 0x50 + pad * 0x400

    def observe(self, u, address, size, data):
        a, b = u.reg_read(UC_ARM_REG_R0), u.reg_read(UC_ARM_REG_R1)
        if address == 0x08166EF6:
            self.fills.append((struct.unpack("<4i", bytes(u.mem_read(a, 16))), b))
        else:
            self.labels.append((self.e.text(a + 0x31), u.mem_read(a + 0x55, 1)[0]))

    def name(self, pad, text):
        self.e.u.mem_write(BUFFER, text.encode() + b"\0")
        self.call(0x081797C4, self.tile(pad), BUFFER)

    def paint(self, pad, full=True):
        self.e.u.mem_write(render.CTX, struct.pack("<II", 1 if full else 256, render.SURF))
        self.call("inst_bank_paint", self.tile(pad), render.CTX)
        self.call("inst_bank_walk", self.tile(pad), render.CTX, 0)

    def tick(self, pad):
        self.e.u.mem_write(BUFFER, bytes(8))
        self.call(0x08179370, self.tile(pad), BUFFER)

    def test_exact_native_scope_and_touch_encoder_ownership(self):
        original = self.original
        for vt, slots in ((0x081B2E88, range(14)), (0x0819E5C4, range(14))):
            for slot in slots:
                address = vt + slot * 4
                if vt == 0x081B2E88 and slot in (1, 2):
                    continue
                self.assertEqual(self.e.r(address), struct.unpack_from("<I", original, address - emu.BASE)[0])
        self.assertEqual(self.image[:0xC0400], original[:0xC0400])
        before = bytes(self.e.u.mem_read(VIEW, 0x6B60))
        self.name(8, "Kick Degraded")
        rects = [bytes(self.e.u.mem_read(self.tile(i) + 4, 16)) for i in range(16)]
        self.paint(8)
        self.assertEqual(rects, [bytes(self.e.u.mem_read(self.tile(i) + 4, 16)) for i in range(16)])
        self.assertEqual(bytes(self.e.u.mem_read(VIEW + 0x4050, 0x2B10)), before[0x4050:0x6B60])

    def test_selection_native_size_numbers_and_no_empty_label(self):
        self.paint(8)
        self.assertIn(("09", 0), self.labels)
        self.assertFalse(any(text in ("Empty", "+") for text, font in self.labels))
        self.assertTrue(any(colour == 0xA3 for rect, colour in self.fills))
        self.assertEqual(self.e.u.mem_read(self.tile(8) + 0x3F9, 1), b"\0")

    def test_native_touch_identity_matches_each_painted_tile(self):
        for pad in range(16):
            self.paint(pad)
            x, y, width, height = struct.unpack(
                "<4i", bytes(self.e.u.mem_read(self.tile(pad) + 4, 16)))
            self.e.u.mem_write(BUFFER, struct.pack("<ii", x + width // 2, y + height // 2))
            self.assertEqual(self.call(0x08150970, VIEW, BUFFER), pad)
            self.assertIn((f"{pad + 1:02d}", 0), self.labels)

    def test_native_wrapped_names_and_mute_feedback(self):
        self.name(8, "Kick Degraded Vinyl")
        self.call(0x081797A4, self.tile(8), 0, 1)
        self.paint(8)
        name = self.tile(8) + 0x70
        self.assertEqual(self.e.text(name + 0x31), "Kick Degraded Vinyl")
        self.assertEqual(self.e.u.mem_read(name + 0x71, 1), b"\0")
        self.assertEqual(self.e.u.mem_read(name + 0x75, 1), b"\xa3")
        self.assertEqual(self.e.u.mem_read(name + 0x74, 1), b"\x62")
        self.assertGreater(self.e.r(name + 0x118), 1)
        self.assertIn(("M", 0), self.labels)

    def test_unchanged_partial_does_not_repaint_static_bank(self):
        self.name(8, "Kick")
        self.paint(8)
        self.tick(8)
        self.paint(8, False)
        self.tick(8)
        self.fills.clear()
        self.labels.clear()
        self.paint(8, False)
        # Native level/status children keep their stock partial painting.
        self.assertFalse(any(rect[3] >= 140 for rect, colour in self.fills))
        self.assertEqual([t for t, font in self.labels if t], [])

    def test_native_activity_is_preserved_not_replaced_with_a_light(self):
        self.name(8, "Kick")
        publication = self.tile(8) + 0x1FC
        self.e.u.mem_write(BUFFER, struct.pack("<hBBIB", 500, 3, 0, 0x1234, 0))
        self.call(0x08178C54, publication, BUFFER)
        before = bytes(self.e.u.mem_read(publication + 0x44, 9))
        self.paint(8)
        self.assertEqual(bytes(self.e.u.mem_read(publication + 0x44, 9)), before)
        x, y, width, height = struct.unpack("<4i", bytes(self.e.u.mem_read(publication + 4, 16)))
        self.assertIn(((x, y, width // 2, height), 0xF2), self.fills)

    def test_partial_feedback_updates_without_static_repaint(self):
        self.name(8, "Kick")
        self.paint(8)
        self.tick(8)
        self.paint(8, False)
        self.fills.clear()
        self.labels.clear()
        self.e.u.mem_write(BUFFER, struct.pack("<hBBIB", 750, 3, 0, 0x1234, 0))
        self.call(0x08178C54, self.tile(8) + 0x1FC, BUFFER)
        self.tick(8)
        self.paint(8, False)
        self.assertTrue(self.fills)
        self.assertEqual([t for t, font in self.labels if t], [])
        self.assertFalse(any(rect[2] >= 150 and rect[3] >= 140 for rect, colour in self.fills))

    def test_selection_load_and_mute_transitions(self):
        self.name(8, "Kick")
        self.paint(8)
        self.e.w(VIEW + 0x6B34, 9)
        self.fills.clear()
        self.paint(8, False)
        self.assertTrue(any(colour == 0xF1 and rect[3] == 182 for rect, colour in self.fills))
        self.call(0x081797A4, self.tile(8), 0, 1)
        self.labels.clear()
        self.paint(8, False)
        self.assertIn(("M", 0), self.labels)
        self.call(0x081797A4, self.tile(8), 0, 0)
        self.labels.clear()
        self.paint(8, False)
        self.assertNotIn(("M", 0), self.labels)
        self.name(8, "")
        self.paint(8, False)
        self.assertEqual(self.e.u.mem_read(self.tile(8) + 0x3F9, 1), b"\0")
        self.assertFalse(any(text in ("Empty", "+") for text, font in self.labels))

    def test_native_terminal_publication_erases_previous_progress(self):
        self.name(8, "Kick")
        for position in (750, -1):
            self.e.u.mem_write(BUFFER, struct.pack("<hBBIB", position, 3, 0, 0x1234, 0))
            self.call(0x08178C54, self.tile(8) + 0x1FC, BUFFER)
            self.fills.clear()
            self.paint(8, position == 750)
        rect = struct.unpack("<4i", bytes(self.e.u.mem_read(self.tile(8) + 0x200, 16)))
        self.assertIn((rect, 0xA3), self.fills)
        self.assertFalse(any(colour == 0xF2 for area, colour in self.fills))

    def test_hidden_feedback_and_allocation_failure(self):
        self.name(8, "Kick")
        self.paint(8)
        self.e.u.mem_write(self.tile(8) + 0x22C, b"\x01")
        self.fills.clear()
        self.paint(8, False)
        self.assertTrue(any(rect[3] == 182 for rect, colour in self.fills))
        self.e.w(SLOT, 0)
        self.e.w(0x30000048, self.e.r(0x3000004C))
        self.labels.clear()
        self.paint(8)
        self.assertEqual(self.e.r(SLOT), 0)
        self.assertNotIn(("09", 0), self.labels)

    def test_other_parent_keeps_native_drawing_without_allocating_bank_state(self):
        self.e.w(self.tile(0) + 0x2C, 0)
        self.paint(0)
        self.assertEqual(self.e.r(SLOT), 0)
        self.assertFalse(any(text == "01" for text, font in self.labels))

    def test_render_native_bank_fixture(self):
        names = ["Kick Dark", "Snare Clean", "Guiro Clean", "Clap Vinyl",
                 "CH Lite", "OH Degraded", "Ride Phaser", "Tom Degraded",
                 "Kick Degraded Vinyl", "Snare", "Tamb", "Snap",
                 "CH Lite 02", "OH Clean", "", "Tom"]
        render.clear(self.e, 0xF1)
        for pad, name in enumerate(names):
            if name:
                self.name(pad, name)
            self.paint(pad)
        from PIL import Image
        image = Image.frombytes("P", (1280, 480), render.ui(self.e).tobytes())
        colours = [self.e.r(0x30000000 + i * 4) for i in range(16)]
        palette = []
        for index in range(256):
            alpha, colour = index >> 4, colours[index & 15]
            palette.extend(((colour >> shift) & 255) * alpha // 15 for shift in (16, 8, 0))
        image.putpalette(palette)
        image.convert("RGB").save(self.output / "inst-bank-partial.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    original = args.image.read_bytes()
    if hashlib.sha256(original).hexdigest() != "cf83652215b8d96424fb29b8074e15a713247359845b172494bfaabf272fb8c3":
        parser.error("Expected exact W6 application image.")
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / "fixture.c").write_text("void **inst_bank_state_slot(void){return (void**)0x24072000u;}\n")
        (work / "fixture.ld").write_text("SECTIONS { . = 0x081ee000; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n")
        subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "thumb-freestanding-eabi",
                        "-mcpu=cortex_m4", "-mfloat-abi=soft", "-Oz", "-g", "-ffreestanding",
                        "-fno-builtin", "-fno-stack-protector", "-nostdlib", "-Wl,--entry=inst_bank_paint",
                        "-Wl,--script=" + str(work / "fixture.ld"),
                        str(ROOT / "eu4_work/integration/inst_bank_ui.c"), str(work / "fixture.c"),
                        "-o", str(work / "fixture.elf")], check=True)
        chunks, symbols = elf(work / "fixture.elf")
        assert len(chunks) == 1 and chunks[0][0] == 0x081EE000
        address, payload = chunks[0]
        assert address >= emu.BASE + len(original) and address + len(payload) <= 0x08200000
        image = bytearray(original)
        image.extend(bytes(address - emu.BASE - len(image)) + payload)
        image.extend(bytes(-len(image) % 4))
        for slot, old, name in ((1, 0x0816FAED, "inst_bank_paint"), (2, 0x0816F9E9, "inst_bank_walk")):
            off = 0x081B2E88 + slot * 4 - emu.BASE
            assert struct.unpack_from("<I", original, off)[0] == old
            struct.pack_into("<I", image, off, symbols[name] | 1)
        restored = bytearray(image[:len(original)])
        restored[0x081B2E8C - emu.BASE:0x081B2E94 - emu.BASE] = original[0x081B2E8C - emu.BASE:0x081B2E94 - emu.BASE]
        assert restored == original
        BankPaint.image, BankPaint.original = bytes(image), original
        BankPaint.symbols, BankPaint.output = symbols, args.out
        (args.out / "INST_PATCH_SCOPE.txt").write_text(
            "Isolated emulator payload, not a delivered firmware image.\n"
            "Only native tile paint slots 1/2 differ below the appended payload.\n"
            "Exact W6 reversal; M7/intercore gap/M4 vectors unchanged; four-byte alignment.\n")
        unittest.main(argv=[__file__], verbosity=2)
