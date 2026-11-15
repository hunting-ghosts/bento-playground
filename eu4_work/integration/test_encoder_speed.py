"""Compile only the changed M4 units; exercise the existing candidate's native
encoder, real registry construction and Settings adapters. No firmware build."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
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
        "SECTIONS { . = 0x081e0000; .text : { *(.text*) *(.rodata*) *(.step*) *(.pad) *(.pad2) *(.pad3*) *(.kit*) *(.panel) *(.mixstrip) } "
        "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n"
        + "\n".join(f"PROVIDE({name} = {address | 1:#x});"
                    for name, address in UU.items()))
    elf = BUILD / "probe.elf"
    subprocess.run([
        sys.executable, "-m", "ziglang", "cc", "-target", "thumb-freestanding-eabi",
        "-mcpu=cortex_m4", "-mfloat-abi=soft", "-Oz", "-g", "-ffreestanding",
        "-fno-builtin", "-fno-stack-protector", "-nostdlib",
        "-Wl,--entry=kick_ui_increment", "-Wl,--script=" + str(linker),
        *(["-DBENTO_SYNCUSSION=1"] if os.environ.get("BENTO_SYNCUSSION") == "1" else []),
        str(ROOT / "kick_ui.c"), str(ROOT / "perf_ui.c"),
        str(ROOT / "macro_ui.c"), str(ROOT.parent / "drums/drum_models.c"),
        "-o", str(elf),
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

    def turn(self, delta, elapsed=100):
        self.w(0x3001FE2C, self.r(0x3001FE2C) + elapsed)
        self.w(0x30035F40, self.r(0x30035F40) + elapsed)
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
        self.assertEqual(p.keys(3)[1], [N.NKEY(0x1D4), N.NKEY(0x1D5), N.NKEY(0x1D6), 0, 0, 0, N.NKEY(0x1D7), N.NKEY(0x1D8)])
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
        for key, expected in [(N.NKEY(0x1A0), 800), (N.NKEY(0x195), 800), (0x33, 160)]:
            p.scaled(0, key=key)
            self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), expected)
        p.speed(2)
        p.scaled(0, key=N.NKEY(0x1A0))
        self.assertEqual(p.call(UU["kick_ui_increment"], SLOT, 160), 1600)

    def test_macro_consumes_globally_scaled_delta_once_before_synth_correction(self):
        p = self.page()
        received = []

        def consume(u, address, size, data):
            received.append(u.reg_read(UC_ARM_REG_R1))
            p.ret(1)

        for address in {UU["macro_increment"], p.speed_symbols["macro_increment"]}:
            p.u.hook_add(UC_HOOK_CODE, consume, begin=address, end=address)
        p.scaled(0, key=N.NKEY(0x195))
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


def accel_functions(p):
    """The two native functions the native increment calls for the acceleration (history push, factor),
    read from the native increment of this firmware image: the first two BLs after its entry."""
    out = []; at = 0x08171E44 + 4
    stock = Path(os.environ['BENTO_STOCK_IMAGE']).read_bytes()
    while len(out) < 2:
        h, l = struct.unpack_from("<HH", stock, at - 0x08040000)
        if h & 0xF800 == 0xF000 and l & 0xD000 == 0xD000:
            s_ = (h >> 10) & 1; j1 = (l >> 13) & 1; j2 = (l >> 11) & 1
            imm = (s_ << 24) | ((1 - (j1 ^ s_)) << 23) | ((1 - (j2 ^ s_)) << 22) | ((h & 0x3FF) << 12) | ((l & 0x7FF) << 1)
            if s_:
                imm -= 1 << 25
            out.append(at + 4 + imm); at += 4
        else:
            at += 2
    return out


FINE = (N.NKEY(0x1B3), N.NKEY(0x1B5), N.NKEY(0x1B6), N.NKEY(0x1B9))  # exp6: Low/Mid/High dB, Mid Q


class FxSpeedTests(unittest.TestCase):
    def page(self, key, initial, mode=0):
        p = SpeedPage()
        p.settings()
        p.speed(mode)
        p.call(UU["perf_nav"], 0x27)
        Fixture.open(p)
        p.header()
        p.native_slot(key, initial)
        # Run 6: Track FX follows the native acceleration. The device clock is far from 0 when a
        # control is turned (an empty history must not look like a fast turn).
        p.w(0x3001FE2C, 50000000); p.w(0x30035F40, 50000000)
        return p

    SLOW = 2000  # ms between turns of 1000 units: native acceleration factor 1

    def test_numeric_fields_cover_native_range_in_one_slow_sweep(self):
        for key, lo, hi in [(N.NKEY(0x1B2), 20, 20000), (N.NKEY(0x1B3), -120, 120),
                            (N.NKEY(0x1B4), 20, 20000), (N.NKEY(0x1B5), -120, 120),
                            (N.NKEY(0x1B6), 100, 600), (N.NKEY(0x1B7), 20, 20000),
                            (N.NKEY(0x1B9), -120, 120), (N.NKEY(0x1BF), -60, 0),
                            (N.NKEY(0x1C0), 1, 20), (N.NKEY(0x1C1), 1, 100),
                            (N.NKEY(0x1C2), 10, 2000), (N.NKEY(0x1C4), 0, 12),
                            (N.NKEY(0x1C5), 0, 100),
                            *(((N.NKEY(0x1CA), 0, 24), (0x129, -12, 12)) if N.FW168 else ((N.NKEY(0x1CA), -12, 0),))]: # run 17 (1.6.8): Drive, Level
            with self.subTest(key=hex(key)):
                # exp5: ranges of up to 24 values move like a native whole number (12800 units a value),
                # so their slow sweep is range x 12800 units; wider ranges keep one sweep in 160000.
                # exp6: EQ gains (tenths of a dB) and Mid Q (hundredths) move 5 values per native step.
                turns = (hi - lo) // 5 * 13 if key in FINE else 160 if hi - lo > 24 else (hi - lo) * 13
                p = self.page(key, lo)
                for _ in range(turns):
                    value = p.turn(1000, self.SLOW)
                self.assertEqual(value, hi & 0xFFFFFFFF)
                for _ in range(turns):
                    value = p.turn(-1000, self.SLOW)
                self.assertEqual(value, lo & 0xFFFFFFFF)

    def test_half_sweep_is_range_appropriate_for_hz_db_and_time(self):
        for key, lo, hi in [(N.NKEY(0x1B2), 20, 20000), (N.NKEY(0x1B3), -120, 120),
                            (N.NKEY(0x1C2), 10, 2000)]:
            with self.subTest(key=hex(key)):
                p = self.page(key, lo)
                for _ in range((hi - lo) // 5 * 64 // 10 if key in FINE else 80 if hi - lo > 24 else (hi - lo) * 64 // 10):   # exp5: half of its own sweep
                    value = p.turn(1000, self.SLOW)
                value = value if value < 1 << 31 else value - (1 << 32)
                expected = (lo*hi)**0.5 if key == N.NKEY(0x1B2) else (lo+hi)/2
                self.assertLessEqual(abs(value-expected), 5 if key in FINE else 1)  # exp6: one 0.5 dB step

    def test_fractional_q_turns_are_not_lost(self):
        # Test the raw normalizer separately: native quantum is 12800; exp6: Mid Q in hundredths, 0.05 (5 values)
        # per native whole-number step.
        p = self.page(N.NKEY(0x1B6), 100)
        values = [p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 1)
                  for _ in range(10)]
        self.assertEqual(sum(values), 0)
        values = [p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 100)
                  for _ in range(320)]
        self.assertEqual(sum(values), 2 * 5 * 12800)
        self.assertTrue(all(value % (5 * 12800) == 0 for value in values))

    def test_frequency_is_fine_at_low_hz_and_proportional_at_high_hz(self):
        for key in (N.NKEY(0x1B2), N.NKEY(0x1B4), N.NKEY(0x1B7)):
            low, high = self.page(key, 20), self.page(key, 10000)
            self.assertLessEqual(low.turn(1600)-20, 2)
            self.assertGreater(high.turn(1600)-10000, 500)

    def test_numeric_substeps_survive_native_forced_row_refresh(self):
        for key, lo, hi in [(N.NKEY(0x1B2), 20, 20000), (N.NKEY(0x1B6), 100, 600)]:
            p = self.page(key, lo)
            sub = 1600 if key in FINE else 160   # exp6: Q has 100 steps of 12800; still 1/8 of a step per turn
            for delta, expected in ((sub, hi), (-sub, lo)):
                for _ in range(1000):
                    value = p.turn(delta)
                    p.call(0x08171C1C, SLOT, key, value, 1)
                self.assertEqual(value, expected)

    def native_factors(self, turns):
        """Oracle: the acceleration factors the native code of this firmware gives a native control for
        these turns (history push and factor function called by the native increment, on an empty history)."""
        p = SpeedPage(); history = 0x20002000; now = 50000000; out = []
        p.u.mem_write(history, bytes(0x44))
        push, factor = accel_functions(p)
        for delta, elapsed in turns:
            now += elapsed
            p.call(push, history, delta & 0xFFFFFFFF, now)
            out.append(p.call(factor, history))
        return out

    def test_controlled_sweeps_follow_the_native_acceleration(self):
        # Until run 6 Track FX suppressed the acceleration ("sweeps do not depend on encoder velocity");
        # owner, 1.6.8 hardware: our controls are much slower than native ones. Now the same turns move a
        # Track FX control by exactly the native factor (1..6) times what a slow turn moves it.
        for key, lo, hi in ((N.NKEY(0x1B3), -120, 120), (N.NKEY(0x1C1), 1, 100), (N.NKEY(0x1BF), -60, 0)):
            for elapsed in (1, 20, 100, 400, 2000):
                with self.subTest(key=hex(key), elapsed=elapsed):
                    turns = [(160, elapsed)] * 60
                    factors = self.native_factors(turns)
                    p = self.page(key, lo)
                    for delta, wait in turns:
                        value = p.turn(delta, wait)
                    value = value if value < 1 << 31 else value - (1 << 32)
                    # exp5: units per value q (12800 up to 24 values, else the largest divisor of 12800 within
                    # one 160000 sweep); the factor is still exactly the native one.
                    q = 12800 if hi - lo <= 24 or key in FINE else max(d for d in range(1, 12801) if 12800 % d == 0 and d * (hi - lo) <= 160000)
                    expected = min(hi, lo + sum(160 * f for f in factors) // q * (5 if key in FINE else 1))  # exp6: 0.5 dB per step
                    self.assertEqual(value, expected)
        self.assertEqual(set(self.native_factors([(160, 2000)] * 20)), {1})
        self.assertEqual(self.native_factors([(160, 20)] * 20)[-1], 6)

    def test_wide_number_fields_of_ours_cover_the_share_of_a_native_percent_control(self):
        # A Playground number field registered as a native whole number moved one step per 12800 units
        # (Ratchet amount 0..100: 1 % of the range where the native Release 0..100.0 % covers 7.4 %).
        # Oracle: the native percent control of this firmware, turned by the same turns.
        for elapsed in (20, 2000):
            p = SpeedPage(); p.settings()
            key = N.NKEY(0xB6)   # Perform: Ratchet amount 0..100, registered by us as a native whole number
            self.assertEqual(p.text(p.r(p.r(0x30031484) + key * 32 + 4)), "Ratchet")
            self.assertEqual(p.u.mem_read(p.r(0x30031484) + key * 32 + 2, 1), b"\2")
            p.native_slot(key, 0); p.w(0x3001FE2C, 50000000); p.w(0x30035F40, 50000000)
            q = SpeedPage(); q.settings(); q.native_slot(0x21, 300); q.w(0x3001FE2C, 50000000); q.w(0x30035F40, 50000000)
            for _ in range(24):
                ours, native = p.turn(160, elapsed), q.turn(160, elapsed)
            share_native = (native - 300) / 1000
            self.assertGreater(share_native, .02)
            self.assertLess(abs(ours / 100 - share_native), .02 + .1 * share_native, (elapsed, ours, native))

    def native_whole_number_steps(self, turns):
        """Oracle: what the native whole-number control Swing (1..99) of this firmware does for these
        turns through the native increment: the change of its value after each turn."""
        q = SpeedPage(); q.settings(); q.native_slot(0x8F, 2)
        q.w(0x3001FE2C, 50000000); q.w(0x30035F40, 50000000)
        out, last = [], 2
        for delta, wait in turns:
            v = q.turn(delta, wait); out.append(v - last); last = v
        return out

    @staticmethod
    def signed(v):
        return v - (1 << 32) if v >= 1 << 31 else v

    def test_exp5_small_track_fx_ranges_step_exactly_like_a_native_whole_number(self):
        # P168 exp5 (owner: EQ gain / Q and compressor steps "wrong", "uneven / jumpy"). On exp4 a native
        # whole-number step (12800 units) moved gain by 1.92 and Q by 0.4 values: 1/2 and 0/1 jumps.
        # Now ranges up to 24 values move exactly like the native whole number Swing, step for step,
        # for slow and for fast turns (native acceleration as oracle).
        for elapsed in (self.SLOW, 400, 20):
            turns = [(12800, elapsed)] * 8
            native = self.native_whole_number_steps(turns)
            self.assertEqual(native[0], 1)
            small = ((N.NKEY(0x1CA), 0, 24), (0x129, -12, 12)) if N.FW168 else ((N.NKEY(0x1CA), -12, 0),) # run 17 (1.6.8): Drive 0..24 dB (was Ceiling), Level
            for key, lo, hi in ((N.NKEY(0x1B3), -120, 120), (N.NKEY(0x1B6), 100, 600), (N.NKEY(0x1C4), 0, 12),
                                (N.NKEY(0x1C0), 1, 20), *small):
                with self.subTest(key=hex(key), elapsed=elapsed):
                    p = self.page(key, lo); last = lo; ours = []
                    for delta, wait in turns:
                        v = self.signed(p.turn(delta, wait)); ours.append(v - last); last = v
                    expected, at = [], lo
                    for step in native:   # exp6: gains/Q move 5 of their finer values per native step
                        nxt = min(hi, at + step * (5 if key in FINE else 1)); expected.append(nxt - at); at = nxt
                    self.assertEqual(ours, expected)

    def test_exp5_middle_track_fx_ranges_move_an_even_number_of_values_per_native_step(self):
        # Threshold -60..0, Attack 1..100, Mix 0..100: every slow native whole-number step moves the same
        # number of values, and the whole range still takes at most 160000 units.
        for key, lo, hi in ((N.NKEY(0x1BF), -60, 0), (N.NKEY(0x1C1), 1, 100), (N.NKEY(0x1C5), 0, 100)):
            with self.subTest(key=hex(key)):
                p = self.page(key, lo); last = lo; steps = []
                while last < hi:
                    v = self.signed(p.turn(12800, self.SLOW)); steps.append(v - last); last = v
                self.assertEqual(len(set(steps[:-1])), 1, steps)
                self.assertLessEqual(len(steps) * 12800, 160000 + 12800)
                p = self.page(key, lo)
                for _ in range(160):
                    v = self.signed(p.turn(1000, self.SLOW))
                self.assertEqual(v, hi)

    def test_exp5_frequency_moves_on_an_even_logarithmic_grid(self):
        # Every slow step moves the frequency by one point of a fixed logarithmic grid (3.5 %, at least
        # 1 Hz): never a step without a change, never a larger jump; 200 steps from 20 Hz reach 20 kHz and
        # the same steps back return exactly to 20 Hz (the grid, not a rounding remainder, decides).
        r = 1000 ** (1 / 200)
        for key in (N.NKEY(0x1B2), N.NKEY(0x1B4), N.NKEY(0x1B7)):
            with self.subTest(key=hex(key)):
                p = self.page(key, 20); up = [20]
                for _ in range(200):
                    up.append(p.turn(800, self.SLOW))
                self.assertEqual(up[-1], 20000)
                for a, b in zip(up, up[1:]):
                    self.assertGreater(b, a)
                    self.assertTrue(b - a == 1 or abs(b / a - r) <= 1.5 / a + 0.002, (a, b))
                down = [up[-1]]
                for _ in range(200):
                    down.append(p.turn(-800, self.SLOW))
                self.assertEqual(down[::-1], up)

    def test_a_native_whole_number_keeps_its_native_step(self):
        p = SpeedPage(); p.settings(); p.native_slot(0x8F, 50)   # native Swing 1..99: one step per 12800
        self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)

    def test_numeric_remainders_do_not_leak_between_handles_or_keys(self):
        p = self.page(N.NKEY(0x1B6), 100)
        normalize = p.speed_symbols["encoder_fx_delta"]
        self.assertEqual(p.call(normalize, SLOT, 8000), 0)   # exp5: one Q step per 12800 units (exp6: 0.05 = 5 values)
        p.w(SLOT+0x34, 124)
        self.assertEqual(p.call(normalize, SLOT, 8000), 0)
        self.assertEqual(p.call(normalize, SLOT, 8000), 5 * 12800)
        p.call(0x08171C1C, SLOT, N.NKEY(0x1B3), 0, 1)
        self.assertEqual(p.call(normalize, SLOT, 1), 0)

    def test_toggle_type_is_unchanged_and_track_selector_not_normalized(self):
        for key in (N.NKEY(0x1B1), N.NKEY(0x1BC), N.NKEY(0x1C3), N.NKEY(0x1C6), N.NKEY(0x1D0)):
            p = self.page(key, 1 if key == N.NKEY(0x1D0) else 0)
            self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)

    def test_global_multiplier_applies_exactly_once_before_fx_range_scaling(self):
        p, q = self.page(N.NKEY(0x1B2), 20, 2), self.page(N.NKEY(0x1B2), 20)
        for _ in range(40):
            self.assertEqual(p.turn(1000), q.turn(2000))

    def test_extreme_deltas_clamp_and_reverse_without_overflow(self):
        for key, lo, hi in [(N.NKEY(0x1B2), 20, 20000), (N.NKEY(0x1B3), -120, 120),
                            (N.NKEY(0x1C2), 10, 2000)]:
            p = self.page(key, lo, 3)
            self.assertEqual(p.turn(0x7FFFFFFF), hi & 0xFFFFFFFF)
            self.assertEqual(p.turn(-0x80000000), lo & 0xFFFFFFFF)

    def test_stock_same_key_outside_fx_is_untouched(self):
        p = SpeedPage()
        p.settings()
        p.native_slot(N.NKEY(0x1B2))
        self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), 160)

    def test_fx_normalization_works_before_perform_has_ever_opened(self):
        p = SpeedPage()
        self.assertEqual(p.r(p.call(UU["perf_state_slot"])), 0)
        Fixture.open(p)
        p.header()
        p.native_slot(N.NKEY(0x1B2), 20)
        self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 1000),
                         p.r(SLOT+0x88))
        self.assertNotEqual(p.r(p.call(UU["perf_state_slot"])), 0)

    def test_foreign_bounds_and_invalid_native_quantum_are_not_normalized(self):
        # Run 6: a field of ours whose bounds are not the Track FX table's is no longer left at one step
        # per 12800 units: it gets the plain range scale of its own bounds (never the Hz curve).
        p = self.page(N.NKEY(0x1B2), 20)
        quantum = p.r(SLOT + 0x88)
        carried = 0   # the fraction of a step is kept per control between turns
        for offset, value, span in [(0x450, 21, 20000 - 21), (0x454, 19999, 19999 - 20), (0x88, 0, 0)]:
            old = p.r(SLOT + offset)
            p.w(SLOT + offset, value)
            p.w(0x3001FE2C, p.r(0x3001FE2C) + 5000); p.w(0x30035F40, p.r(0x30035F40) + 5000)
            steps, carried = divmod(160 * span + carried, 160000) if span else (0, carried)
            self.assertEqual(p.call(p.speed_symbols["encoder_fx_delta"], SLOT, 160), steps * quantum if span else 160)
            p.w(SLOT + offset, old)



class FxValueTextTests(unittest.TestCase):
    """exp6 (owner: EQ gain in 0.5 dB steps or finer, finer Q). The native value formatter of this image
    (found by its content, as the build finds it) prints integer descriptors with "%ld"; for the Track FX
    EQ gains (tenths of a dB) and Mid Q (hundredths) it shows decimals. Oracle for every other integer key:
    the same native formatter of the STOCK image of this version, character for character."""

    @staticmethod
    def entry(image):
        pat = bytes.fromhex("2de9f0418ab004460d4688461746")
        at = image.find(pat)
        assert at > 0 and image.find(pat, at + 1) < 0, "value formatter entry"
        return 0x08040000 + at

    def text(self, p, image, key, value):
        out = 0x20031000
        p.u.mem_write(out, bytes(256))
        p.call(self.entry(image), out, key, value & 0xFFFFFFFF)
        return bytes(p.u.mem_read(out, 64)).split(b"\0")[0].decode()

    def page(self):
        p = FxSpeedTests.page(FxSpeedTests(), N.NKEY(0x1B2), 20)
        return p

    def test_gain_and_q_show_decimals(self):
        from test_integration import IMAGE
        p = self.page()
        for key in (N.NKEY(0x1B3), N.NKEY(0x1B5), N.NKEY(0x1B9)):
            for value, want in ((0, "+0.0 dB"), (5, "+0.5 dB"), (-5, "-0.5 dB"), (15, "+1.5 dB"),
                                (-120, "-12.0 dB"), (120, "+12.0 dB"), (-35, "-3.5 dB")):
                with self.subTest(key=hex(key), value=value):
                    self.assertEqual(self.text(p, IMAGE, key, value), want)
        for value, want in ((100, "1.00"), (105, "1.05"), (250, "2.50"), (600, "6.00")):
            with self.subTest(q=value):
                self.assertEqual(self.text(p, IMAGE, N.NKEY(0x1B6), value), want)

    def test_other_integers_are_printed_like_stock(self):
        import os
        from test_integration import IMAGE
        stock = Path(os.environ["BENTO_STOCK_IMAGE"]).read_bytes()
        p = self.page()
        q = self.page()
        q.u.mem_write(0x08040000, stock)   # same RAM state (registry), stock code
        for key, value in ((0x8F, 50), (N.NKEY(0x1BF), -18), (N.NKEY(0x1C2), 120), (N.NKEY(0x1C1), 10),
                           (N.NKEY(0x1B2), 1000), *(() if N.FW168 else ((N.NKEY(0x1CA), -1),))):
            with self.subTest(key=hex(key)):
                self.assertEqual(self.text(p, IMAGE, key, value), self.text(q, stock, key, value))
        if N.FW168: # run 17: Drive and Level are ours and print dB with a sign; every other integer stays stock
            for key, value, text in ((N.NKEY(0x1CA), 6, '+6 dB'), (N.NKEY(0x1CA), 0, '0 dB'), (0x129, -5, '-5 dB'), (0x129, 3, '+3 dB')):
                with self.subTest(key=hex(key), value=value):
                    self.assertEqual(self.text(p, IMAGE, key, value), text)

if __name__ == "__main__":
    unittest.main()
