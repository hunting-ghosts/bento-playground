"""Execute the installed ARM voice, controls, locks and project codec."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import hashlib
import math
import struct
import unittest

from engine_test_support import engine, run, SYMS, _k16, _KEEP
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_LR, UC_ARM_REG_PC
from unicorn import UC_HOOK_CODE

DEFAULT = (78, 55, 50, 65, 35, 30, 0)
FIRMWARE_DEFAULT = (78, 55, 50, 65, 0, 30, 0)  # R6.5 (owner): Metal Sweep Range default 0
KEYS = [N.NKEY(0x1a0), N.NKEY(0x1a1), N.NKEY(0x1a2), N.NKEY(0x1a4), N.NKEY(0x1a5), N.NKEY(0x1a6), N.NKEY(0x1a9)]


def voice(values=DEFAULT, flags=0, lock=None):
    p = engine(15, values, lock)
    p.u.mem_write(0x24043d80, bytes([flags]))
    return p


def controls():
    p = _k16.UI()
    p.path = "BENTO_Synth_Syncussion.wav"
    p.u.mem_map(0xc6000000, 0x1000)
    p.w(0x3000004c, 0xc6000000)
    p.w(0x30000048, 0xc6001000)
    def allocate(u, address, size, data):
        cursor = p.r(0x3000004c)
        p.w(0x3000004c, cursor+u.reg_read(UC_ARM_REG_R0))
        u.reg_write(UC_ARM_REG_R0, cursor)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
    p.u.hook_add(UC_HOOK_CODE, allocate, begin=0x08104c08, end=0x08104c08)
    # This unit fixture substitutes widgets. Native layout/render is covered
    # separately by integration/test_syncussion_ui.py, with real constructors.
    for row in range(3):
        bar = p.v+0x38+row*0x23f8
        p.w(bar+8, 382 if row == 1 else 78 if row == 2 else 178)
        p.w(bar+16, 294 if row == 0 else 90)
    return p


class Tests(unittest.TestCase):
    def test_pad_engine_is_fixed_metal_whatever_the_stored_switches(self):
        # R6.3 (owner): Syncussion retired on pads; engine 15 is "Metal" with
        # fixed switches (B Metallic, sweep down, triangle LFO, no S&H).
        outputs = []
        for mode in range(6):
            p = voice(flags=mode)
            p.call(SYMS["kick_marker"], p.desc)
            self.assertEqual(p.u.reg_read(UC_ARM_REG_R0), 15)
            a = run(p, 20)
            self.assertTrue(all(math.isfinite(x) and abs(x) <= 1 for x in a))
            self.assertGreater(sum(x*x for x in a), .001)
            outputs.append(a)
        for a in outputs[1:]:
            self.assertEqual(a, outputs[0])

    def test_ordinary_sample_and_reserved_analog_id_are_not_recognised(self):
        p = voice()
        p.marker = False
        p.start()
        self.assertEqual(p.render()[0], 0)
        p = voice()
        p.w(p.desc+0x24, 144031)
        p.call(SYMS["kick_marker"], p.desc)
        self.assertEqual(p.u.reg_read(UC_ARM_REG_R0), 0)

    def test_tune_lock_and_native_pitch_both_change_audio(self):
        plain = run(voice(), 20)
        self.assertNotEqual(run(voice(lock=(12, 150-25)), 20), plain)
        p = voice()
        p.f(p.voice+0x48, 2)
        self.assertNotEqual(run(p, 20), plain)
        p = voice()
        p.f(p.voice+0x48, 16)
        self.assertNotEqual(run(p, 20), plain)

    def test_other_family_and_eighth_kick_lock_do_not_change_switches(self):
        plain = run(voice(), 20)
        self.assertEqual(run(voice(lock=(19, 100)), 20), plain)
        self.assertEqual(run(voice(lock=(20, 100)), 20), plain)

    def test_retrigger_is_monophonic_and_bridge_preserves_first_sample(self):
        p = voice()
        p.start()
        before = p.render()[1]
        first = p.voice
        second = first+0x800
        p.w(second+12, p.desc)
        p.f(second+0x48, 1)
        p.f(second+0xb8, 1)
        p.u.mem_write(second, b"\1")
        p.w(p.root+0x60, 2)
        p.w(p.root+0x24, second)
        p.call(SYMS["kick_voice"], second, p.root)
        self.assertEqual(p.u.mem_read(first, 1), b"\0")
        p.voice = second
        self.assertAlmostEqual(p.render()[1][0], 2*before[-1]-before[-2], places=5)  # R6.11: value and step continue

    def test_mod_matrix_changes_tune_without_writing_base_values(self):
        p = voice()
        p.route(KEYS[0], 13, 700)
        self.assertNotEqual(run(p, 20), run(voice(), 20))
        self.assertEqual(bytes(p.u.mem_read(0x24043528, 7)), bytes(DEFAULT))

    def test_motion_a_to_d_reaches_every_drum_engine_without_changing_base(self):
        values = (55, 50, 45, 65, 55, 25, 0)
        changed = (55, 75, 45, 65, 55, 25, 0)
        for model in (1, 3, 5, 7, 9, 15):
            expected = run(engine(model, changed), 20)
            for lane in range(4):
                with self.subTest(engine=model, lane=lane):
                    p = engine(model, values)
                    p.f(p.root + 0x654 + 8 * lane, 1)
                    p.route(KEYS[1], 9 + lane, 250)
                    self.assertEqual(run(p, 20), expected)
                    self.assertEqual(bytes(p.u.mem_read(0x24043528, 7)), bytes(values))

    def test_motion_attack_uses_all_four_lanes_without_changing_sound_mode(self):
        reference = voice(flags=4)
        reference.u.mem_map(0xc6000000, 0x1000)
        reference.w(0x24043508, 0xc6000000)
        reference.w(0xc6000000, 0x41594e53)
        reference.u.mem_write(0xc6000020, b"\x4b")
        expected = run(reference, 20)
        for lane in range(4):
            with self.subTest(lane=lane):
                p = voice(flags=4)
                p.f(p.root + 0x654 + 8 * lane, 1)
                p.route(N.NKEY(0x1b0), 9 + lane, 750)
                self.assertEqual(run(p, 20), expected)
                self.assertEqual(p.u.mem_read(0x24043d80, 1), b"\4")
                self.assertEqual(p.r(0x24043508), 0)

    def test_native_mute_and_postprocessing_remain_chained(self):
        p = voice()
        p.native_postprocess()
        p.start()
        for _ in range(8):
            p.render()
        self.assertGreater(sum(x*x for channel in p.outputs() for x in channel), 1e-6)
        p.u.mem_write(p.root+0x600, b"\1")
        for _ in range(8):
            p.render()
        self.assertLess(sum(x*x for channel in p.outputs() for x in channel), 1e-9)

    def test_attack_and_all_switches_roundtrip(self):
        p = controls()
        p.prepare()
        self.assertEqual(p.values(), list(FIRMWARE_DEFAULT))
        p.event(KEYS[0], 160)
        p.u.mem_write(0x24043d80, b"\x66")
        p.event(N.NKEY(0x1b0), 5)
        p.call("kick_ui_save", p.o, p.params)
        self.assertEqual(p.attrs["bento_drum_model"], 15)
        self.assertEqual(p.attrs["bento_drum_v2_click"], 102)
        self.assertEqual(p.attrs["bento_syncussion_attack"], 5)
        self.assertEqual(p.attrs["bento_kick_v1_tune"], 160)
        p.u.mem_write(0x24043500, bytes(0x900))
        p.call("kick_ui_load", p.params, p.o)
        self.assertEqual(p.values()[0], 160)
        self.assertEqual(p.u.mem_read(0x2404352f, 1), b"\x0f")
        self.assertEqual(p.u.mem_read(0x24043d80, 1), b"\x66")
        self.assertEqual(p.u.mem_read(p.r(0x24043508)+32, 1), b"\5")

    def test_switch_edits_do_not_mutate_continuous_controls(self):
        p = controls()
        p.prepare()
        p.u.mem_write(0x24043d80, b"\x66")
        p.event(N.NKEY(0x1b0), 4)
        self.assertEqual(p.values(), list(FIRMWARE_DEFAULT))
        self.assertEqual(p.u.mem_read(0x24043d80, 1), b"\x66")
        self.assertEqual(p.u.mem_read(p.r(0x24043508)+32, 1), b"\4")
        p.event(KEYS[0], 130)
        self.assertEqual(p.values()[0], 130)

    def test_legacy_projects_default_attack_to_zero_and_pad_reuse_clears_it(self):
        p = controls()
        p.prepare()
        p.event(N.NKEY(0x1b0), 80)
        p.call("kick_ui_save", p.o, p.params)
        del p.attrs["bento_syncussion_attack"]
        p.call("kick_ui_load", p.params, p.o)
        self.assertEqual(p.u.mem_read(p.r(0x24043508)+32, 1), b"\0")
        p.event(N.NKEY(0x1b0), 70)
        p.path = "BENTO_Kick_K2.wav"
        p.w(p.v+0x87c4, N.NKEY(0x141))
        p.prepare()
        self.assertEqual(p.u.mem_read(p.r(0x24043508)+32, 1), b"\0")

    def test_audio_reads_attack_extension_without_changing_original_parameters(self):
        p = voice()
        p.u.mem_map(0xc6000000, 0x1000)
        p.w(0x24043508, 0xc6000000)
        p.w(0xc6000000, 0x41594e53)
        p.u.mem_write(0xc6000020, b"\x50")
        slow = run(p, 20)
        fast = run(voice(), 20)
        self.assertLess(sum(x*x for x in slow[:480]), sum(x*x for x in fast[:480])*.05)
        self.assertEqual(bytes(p.u.mem_read(0x24043528, 7)), bytes(DEFAULT))

    def test_coefficients_reuse_only_identical_complete_inputs(self):
        p = voice()
        address = next(value for name, value in SYMS.items()
                       if "Syncussion" in name and "Coefficients" in name)
        calls = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: calls.append(1),
                            begin=address, end=address)
        try:
            p.start()
            p.render()
            self.assertEqual(len(calls), 1)
            for _ in range(4):
                p.render()
            self.assertEqual(len(calls), 1)
            for index, value in enumerate(DEFAULT):
                p.u.mem_write(0x24043528+index, bytes([value+1]))
                p.render()
                self.assertEqual(len(calls), index+2)
            for address, value in ((p.voice+0x48, 2), (p.voice+0xb8, .5)):
                p.f(address, value)
                before = len(calls)
                p.render()
                self.assertEqual(len(calls), before+1)
            p.u.mem_write(0x24043d80, b"\x01")
            before = len(calls)
            p.render()
            self.assertEqual(len(calls), before)  # R6.3: pad switches are fixed (Metal)
            p.u.mem_map(0xc6000000, 0x1000)
            p.w(0x24043508, 0xc6000000)
            p.w(0xc6000000, 0x41594e53)
            p.u.mem_write(0xc6000020, b"\x50")
            p.render()
            self.assertEqual(len(calls), before+1)
            p.render()
            self.assertEqual(len(calls), before+1)
            p.start()
            p.render()
            self.assertEqual(len(calls), before+1, "Retrigger must retain valid coefficients")
        finally:
            p.u.hook_del(hook)

    def test_instruction_work_is_bounded_for_all_modes(self):
        costs = []
        for mode in range(6):
            run(voice(flags=mode), 12, costs)
        print("Syncussion emulated instructions/sample A..F:", costs, flush=True)
        self.assertLess(max(costs), 500)
        # R6.3: every stored mode now plays the fixed Metal path (B Metallic with
        # sweep and triangle LFO), within the old D-mode budget plus the level gain.
        for mode, cost in enumerate(costs):
            self.assertLess(cost, 440, mode)

    def test_arp_disabled_path_still_calls_clock_once_and_leaves_active_voice_unchanged(self):
        p = voice()
        p.start()
        before = bytes(p.u.mem_read(0x24045820, 288))
        calls = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: calls.append(1),
                            begin=SYMS["kick_sync_clock"], end=SYMS["kick_sync_clock"])
        try:
            p.call(0x080d2508, 64, 0)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(calls, [1])
        self.assertEqual(bytes(p.u.mem_read(0x24045820, 288)), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
