"""Compile only the changed M4 units; exercise the existing candidate's native
encoder, real registry construction and Settings adapters. No firmware build."""
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R1

from test_integration import UU, Fixture
from test_perf import Page, EV, OUT
import os

ROOT = Path(__file__).resolve().parent
BUILD = ROOT.parents[1] / "build" / "encoder-speed"
BASE = 0x081E0000
KEY = 0xA8
SLOT = 0xC0180070
LIMIT = 0x01111111
PROBE = None


def build_probe():
    BUILD.mkdir(parents=True, exist_ok=True)
    linker = BUILD / "probe.ld"
    linker.write_text(
        "EXTERN(" + " ".join(name for name in UU
                            if name.startswith("perf_") or name == "workflow_state_slot") + ")\n"
        "SECTIONS { . = 0x081e0000; .text : { *(.text*) *(.rodata*) *(.pad) *(.pad2) *(.pad3*) } "
        "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n"
        + "\n".join(f"PROVIDE({name} = {address | 1:#x});"
                    for name, address in UU.items()))
    elf = BUILD / "probe.elf"
    subprocess.run([
        sys.executable, "-m", "ziglang", "cc", "-target", "thumb-freestanding-eabi",
        "-mcpu=cortex_m4", "-mfloat-abi=soft", "-Oz", "-g", "-ffreestanding",
        "-fno-builtin", "-fno-stack-protector", "-nostdlib",
        "-Wl,--entry=kick_ui_increment", "-Wl,--script=" + str(linker),
        str(ROOT / "kick_ui.c"), str(ROOT / "perf_ui.c"),
        str(ROOT / "macro_ui.c"), "-o", str(elf),
    ], check=True)
    data = elf.read_bytes()
    offset = struct.unpack_from("<I", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 46)
    sections = [struct.unpack_from("<10I", data, offset + i * size)
                for i in range(count)]
    allocated = [s for s in sections if s[2] & 2]
    assert len(allocated) == 1 and allocated[0][3] == BASE
    section = allocated[0]
    assert BASE + section[5] < 0x081FF000
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        strings = sections[section[6]]
        strings = data[strings[4]:strings[4] + strings[5]]
        for offset in range(0, section[5], section[9]):
            name, address, _, info, _, _ = struct.unpack_from(
                "<IIIBBH", data, section[4] + offset)
            if info == 0x12 and BASE <= (address & ~1) < 0x081FF000:
                symbols[strings[name:].split(b"\0")[0].decode()] = address & ~1
    section = allocated[0]
    return data[section[4]:section[4] + section[5]], symbols


def install_probe(page, force=False):
    global PROBE
    if not force and "encoder_fx_delta" in UU and not os.environ.get("BENTO_ENCODER_FORCE_PROBE"):
        page.speed_symbols = UU
        return
    if PROBE is None:
        PROBE = build_probe()
    code, symbols = PROBE
    page.u.mem_write(BASE, code)
    assembler = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    for name, address in symbols.items():
        if name in UU:
            page.u.mem_write(UU[name], bytes(assembler.asm(
                "b.w " + hex(address), UU[name])[0]))
    page.speed_symbols = symbols


class SpeedPage(Page):
    def registry(self):
        install_probe(self)
        super().registry()

    def settings(self):
        self.open()
        self.header()
        self.u.mem_write(EV, struct.pack("<5I", 0x1074, 0, 0, 0, 0))
        self.call(UU["perf_navigation"], EV)
        self.header()

    def speed(self, mode):
        self.edit(KEY, mode & 0xFFFFFFFF)

    def scaled(self, delta, slot=SLOT, key=0x33, handle=123):
        self.w(slot + 0x34, handle)
        self.u.mem_write(slot + 0x9C, struct.pack("<H", key))
        value = self.call(self.speed_symbols["encoder_speed_delta"],
                          slot, delta & 0xFFFFFFFF)
        return value if value < 1 << 31 else value - (1 << 32)

    def native_slot(self, key=0x33, value=500):
        self.call(0x08145B7C, SLOT - 0x70)
        self.call(0x08171C1C, SLOT, key, value, 1)
        self.w(SLOT + 0x34, 123)
        self.encoder_events = []

        def capture(u, address, size, data):
            event = u.reg_read(UC_ARM_REG_R1)
            code, handle, key, value = struct.unpack("<4I", u.mem_read(event, 16))
            self.encoder_events.append((code & 0xFFFF, handle, key, value))
            self.ret()

        self.u.hook_add(UC_HOOK_CODE, capture, begin=0x0816FC34, end=0x0816FC34)

    def turn(self, delta):
        self.w(0x3001FE2C, self.r(0x3001FE2C) + 100)
        self.call(0x08171E44, SLOT, delta & 0xFFFFFFFF)
        return self.r(SLOT + 0xA0)


class EncoderSpeedTests(unittest.TestCase):
    def page(self, mode=0):
        page = SpeedPage()
        page.settings()
        page.speed(mode)
        return page

    def test_native_registry_slot_is_empty_then_owned_without_other_changes(self):
        p = SpeedPage()
        registry = p.r(0x30031484)
        before = bytes(p.u.mem_read(registry, 499 * 32))
        self.assertEqual(before[KEY * 32:(KEY + 1) * 32], bytes(32))
        p.settings()
        self.assertEqual(p.text(p.r(registry + KEY * 32 + 4)), "Enc Speed")
        self.assertEqual(p.keys(3)[0], [0x83, 0xA2, 0xA3, 0xE1, 0x67, 0xA4, KEY, 0])
        self.assertEqual(p.keys(3)[1], [0x1D4, 0x1D5, 0x1D6, 0, 0, 0, 0x1D7, 0x1D8])
        self.assertEqual(p.get(KEY), 0)
        self.assertEqual(p.r(registry + KEY * 32 + 12), 4)
        self.assertEqual(p.model_events, [])
        self.assertEqual(before[0x83 * 32:0x84 * 32],
                         bytes(p.u.mem_read(registry + 0x83 * 32, 32)))

    def test_foreign_descriptor_is_preserved_and_field_omitted(self):
        p = SpeedPage()
        descriptor = p.r(0x30031484) + KEY * 32
        p.w(descriptor, KEY | 2 << 16)
        p.w(descriptor + 4, 0x20010000)
        before = bytes(p.u.mem_read(descriptor, 32))
        p.settings()
        self.assertEqual(bytes(p.u.mem_read(descriptor, 32)), before)
        self.assertEqual(p.keys(3)[0][6], 0)
        self.assertEqual(p.get(KEY), 0xDEAD)
        self.assertEqual(p.edit(KEY, 2), 0)
        self.assertEqual(p.scaled(160), 160)

    def test_settings_clamps_and_returns_to_default_without_native_write(self):
        p = self.page()
        p.speed(99)
        self.assertEqual(p.get(KEY), 3)
        p.speed(-1)
        self.assertEqual(p.get(KEY), 0)
        self.assertEqual(p.model_events, [])
        self.assertEqual(p.scaled(123), 123)
        self.assertEqual(p.scaled(-123), -123)

    def test_slow_preserves_single_unit_turns_in_both_directions(self):
        p = self.page(1)
        self.assertEqual([p.scaled(1) for _ in range(6)], [0, 1, 0, 1, 0, 1])
        self.assertEqual([p.scaled(-1) for _ in range(6)], [0, -1, 0, -1, 0, -1])
        self.assertEqual([p.scaled(1), p.scaled(-1)], [0, 0])

    def test_slow_remainders_do_not_leak_between_slots_handles_or_keys(self):
        p = self.page(1)
        self.assertEqual(p.scaled(1), 0)
        self.assertEqual(p.scaled(1, slot=SLOT + 0x468), 0)
        self.assertEqual(p.scaled(1), 1)
        self.assertEqual(p.scaled(1, handle=124), 0)
        self.assertEqual(p.scaled(1, key=0x32, handle=124), 0)
        p.speed(0)
        p.speed(1)
        self.assertEqual(p.scaled(1), 0)

    def test_all_modes_and_speed_selector_exemption(self):
        p = self.page()
        for mode, expected in [(0, 51), (1, 25), (2, 102), (3, 204)]:
            p.speed(mode)
            self.assertEqual(p.scaled(51), expected)
            self.assertEqual(p.scaled(51, key=KEY), 51)
        for mode in (1, 2, 3):
            p.speed(mode)
            self.assertLessEqual(abs(p.scaled(0x7FFFFFFF)), LIMIT)
            self.assertLessEqual(abs(p.scaled(-0x80000000)), LIMIT)
        p.speed(0)
        self.assertEqual(p.scaled(0x7FFFFFFF), 0x7FFFFFFF)
        self.assertEqual(p.scaled(-0x80000000), -0x80000000)

    def test_stock_default_matches_unhooked_native_byte_for_byte(self):
        p, q = self.page(), self.page()
        p.native_slot()
        q.native_slot()
        q.u.mem_write(0x08171E44, bytes.fromhex("f0b587b0"))
        for delta in [1, 160, 4000, -1, -160, -4000, 160000, -160000]:
            self.assertEqual(p.turn(delta), q.turn(delta))
            self.assertEqual(bytes(p.u.mem_read(SLOT, 0x468)),
                             bytes(q.u.mem_read(SLOT, 0x468)))
        self.assertEqual(p.encoder_events, q.encoder_events)

    def test_stock_fast_scales_once_and_native_clamps_both_ends(self):
        p, q = self.page(2), self.page()
        p.native_slot()
        q.native_slot()
        for delta in [400, 400, -160, 2000, -2000]:
            self.assertEqual(p.turn(delta), q.turn(delta * 2))
        p.turn(10000000)
        self.assertEqual(p.r(SLOT + 0xA0), 1000)
        p.turn(-10000000)
        self.assertEqual(p.r(SLOT + 0xA0), 0)

    def test_inherited_synth_correction_is_not_applied_to_stock(self):
        p = self.page()
        for key, expected in [(0x1A0, 800), (0x195, 800), (0x33, 160)]:
            p.scaled(0, key=key)
            self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), expected)
        p.speed(2)
        p.scaled(0, key=0x1A0)
        self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), 1600)

    def test_macro_consumes_globally_scaled_delta_once_before_synth_correction(self):
        p = self.page()
        received = []

        def consume(u, address, size, data):
            received.append(u.reg_read(UC_ARM_REG_R1))
            p.ret(1)

        for address in {UU["macro_increment"], p.speed_symbols["macro_increment"]}:
            p.u.hook_add(UC_HOOK_CODE, consume, begin=address, end=address)
        p.scaled(0, key=0x195)
        self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), 0)
        p.speed(2)
        self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), 0)
        self.assertEqual(received, [160, 320])

    def test_native_slow_turns_accumulate_to_half_of_default(self):
        p, q = self.page(1), self.page()
        p.native_slot()
        q.native_slot()
        for _ in range(640):
            p.turn(1)
        for _ in range(320):
            q.turn(1)
        self.assertEqual(p.r(SLOT + 0xA0), q.r(SLOT + 0xA0))
        self.assertGreater(p.r(SLOT + 0xA0), 500)

    def test_session_setting_survives_navigation_but_is_not_project_storage(self):
        p = self.page(2)
        p.call(UU["perf_nav"], 0x27)
        self.assertEqual(p.scaled(23), 46)
        p.settings()
        self.assertEqual(p.get(KEY), 2)
        self.assertEqual(p.attrs, {})
        self.assertEqual(self.page().get(KEY), 0)


class FxSpeedTests(unittest.TestCase):
    def page(self, key, initial, mode=0):
        p = SpeedPage()
        p.settings()
        p.speed(mode)
        p.call(UU["perf_nav"], 0x27)
        Fixture.open(p)
        p.header()
        p.native_slot(key, initial)
        return p

    def test_numeric_fields_cover_native_range_in_one_slow_sweep(self):
        for key, lo, hi in [(0x1B2, 20, 20000), (0x1B3, -12, 12),
                            (0x1B4, 20, 20000), (0x1B5, -12, 12),
                            (0x1B6, 1, 6), (0x1B7, 20, 20000),
                            (0x1B9, -12, 12), (0x1BF, -60, 0),
                            (0x1C0, 1, 20), (0x1C1, 1, 100),
                            (0x1C2, 10, 2000), (0x1C4, 0, 12),
                            (0x1C5, 0, 100), (0x1CA, -12, 0)]:
            with self.subTest(key=hex(key)):
                p = self.page(key, lo)
                for _ in range(160):
                    value = p.turn(1000)
                self.assertEqual(value, hi & 0xFFFFFFFF)
                for _ in range(160):
                    value = p.turn(-1000)
                self.assertEqual(value, lo & 0xFFFFFFFF)

    def test_half_sweep_is_range_appropriate_for_hz_db_and_time(self):
        for key, lo, hi in [(0x1B2, 20, 20000), (0x1B3, -12, 12),
                            (0x1C2, 10, 2000)]:
            with self.subTest(key=hex(key)):
                p = self.page(key, lo)
                for _ in range(80):
                    value = p.turn(1000)
                value = value if value < 1 << 31 else value - (1 << 32)
                self.assertLessEqual(abs(value - (lo + hi) / 2), 1)

    def test_fractional_q_turns_are_not_lost(self):
        # Test the raw normalizer separately: native quantum is 12800, range 5.
        p = self.page(0x1B6, 1)
        values = [p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 1)
                  for _ in range(10)]
        self.assertEqual(sum(values), 4)

    def test_toggle_type_is_unchanged_and_track_selector_not_normalized(self):
        for key in (0x1B1, 0x1BC, 0x1C3, 0x1C6, 0x1D0):
            p = self.page(key, 1 if key == 0x1D0 else 0)
            self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)

    def test_global_multiplier_applies_exactly_once_before_fx_range_scaling(self):
        p, q = self.page(0x1B2, 20, 2), self.page(0x1B2, 20)
        for _ in range(40):
            self.assertEqual(p.turn(1000), q.turn(2000))

    def test_extreme_deltas_clamp_and_reverse_without_overflow(self):
        for key, lo, hi in [(0x1B2, 20, 20000), (0x1B3, -12, 12),
                            (0x1C2, 10, 2000)]:
            p = self.page(key, lo, 3)
            self.assertEqual(p.turn(0x7FFFFFFF), hi & 0xFFFFFFFF)
            self.assertEqual(p.turn(-0x80000000), lo & 0xFFFFFFFF)

    def test_stock_same_key_outside_fx_is_untouched(self):
        p = SpeedPage()
        p.settings()
        p.native_slot(0x1B2)
        self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)

    def test_fx_normalization_works_before_perform_has_ever_opened(self):
        p = SpeedPage()
        self.assertEqual(p.r(p.call(UU["perf_state_slot"])), 0)
        Fixture.open(p)
        p.header()
        p.native_slot(0x1B2, 20)
        self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 1000), 1598400)
        self.assertNotEqual(p.r(p.call(UU["perf_state_slot"])), 0)

    def test_foreign_bounds_and_invalid_native_quantum_are_not_normalized(self):
        p = self.page(0x1B2, 20)
        for offset, value in [(0x450, 21), (0x454, 19999), (0x88, 0)]:
            old = p.r(SLOT + offset)
            p.w(SLOT + offset, value)
            self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)
            p.w(SLOT + offset, old)


if __name__ == "__main__":
    unittest.main()
