"""Native Mixer widgets, property/audio packets and bounded cached painting.

Project enumeration, global settings and meter publications are controlled
fixture boundaries. Track property edits and the native audio packet writer
execute; these checks do not establish device CPU use or hardware acceptance.
"""
import os
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from test_tracks import NativeTracks, MODEL, VIEW, POINT, MANAGER, UU, render

MIXER = 0xc1840000
KEYS = (0x134, 0x13f, 0x140, 0x141)
COMP = (0x9c, 0x123, 0x124, 0x125, 0x126, 0x12e, 0x127, 0x130)
PROJECT = 0x2a  # native 08133E54 project node: compressor is Project Settings
OUTPUTS = (0x138, 0x137, 0x136, 0x135, 0, 0, 0x18, 0xa9)


class Mixer(NativeTracks):
    def __init__(self):
        self.mix_ready = False
        self.encoder = False
        super().__init__()
        self.global_values = dict.fromkeys(OUTPUTS + COMP, 0)
        self.global_values.update({0x123: 30, 0x124: 200, 0x125: -18000,
                                   0x126: 4, 0x12e: 1000})
        for i in range(8):
            props = 0x20017000 + i * 0x100
            values = [(0x73, i), (0x13d, 0), (0x13e, 0),
                      (0x134, -3000), (0x13f, 0), (0x140, 100), (0x141, 200)]
            self.w(0x20015000 + i * 0x100 + 12, len(values))
            self.u.mem_write(props, b"".join(struct.pack("<IHBB", value & 0xffffffff, key, 1, 0)
                                            for key, value in values))
        self.hooks.append(self.u.hook_add(UC_HOOK_CODE, self.hook,
                                         begin=0x0813393e, end=0x0813393e))
        self.mix_ready = True
        self.call(0x0814ad54, MIXER)
        self.u.mem_write(MODEL + 0x12c, b"\x1f")
        self.u.mem_write(VIEW + 0x30, b"\1")
        self.call(0x0816fb64, MANAGER + 0x470, MIXER)
        self.w(MANAGER + 0x470 + 0x3c, MIXER)
        self.event("pg_mixer_event", 0x78)
        self.u.mem_write(self.bar() + 0x30, b"\0")
        self.tick()
        self.events.clear()

    def strip(self, index):
        return MIXER + 0x34 + index * 0x750

    def bar(self):
        return MIXER + 0x7610 if self.mix_ready else super().bar()

    def hook(self, u, address, size, data):
        if self.mix_ready:
            r = [u.reg_read(reg) for reg in
                 (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            if address == 0x0813393e:
                self.w(r[2], 100 + r[1] if r[1] < 8 else 0)
                self.ret(int(r[1] < 8))
                return
            if address == 0x0813390e:
                h = self.e.r(r[1])
                self.u.mem_write(r[3], (f"Track {h - 99}".encode() if 100 <= h < 108 else b"") + b"\0")
                self.ret(1)
                return
            if address == 0x08133614:
                h = self.e.r(r[1])
                if 100 <= h < 108 and r[2] in KEYS + (0x13d, 0x13e, 0x73):
                    return
                if h == 0xfffffffe and r[2] not in COMP or h == PROJECT and r[2] in COMP:
                    self.w(r[3], self.global_values.get(r[2], 0) & 0xffffffff)
                    self.ret(1)
                    return
            if address == 0x0816fc34 and self.encoder and self.bar() <= r[0] < self.bar() + 0x23f8:
                return
            if address == 0x081403ec and self.e.h(r[1]) == 0xcf:
                e = struct.unpack("<5I", u.mem_read(r[1], 20))
                self.events.append(e)
                self.global_values[e[2]] = e[3]
                self.ret()
                return
        return super().hook(u, address, size, data)

    def event(self, function, code, handle=0, key=0, value=0):
        address = POINT + 0x80
        self.u.mem_write(address, struct.pack("<5I", code, handle, key, value & 0xffffffff, 0))
        return self.call(function, MIXER, address)

    def direct(self, function, index, top, ident=0, dx=0):
        self.w(POINT, 84 + 159 * index + dx)
        self.w(POINT + 4, 480 - top)
        self.call(function, MIXER, POINT, ident)

    def get(self, index, key):
        self.w(POINT + 0x60, 100 + index)
        self.call(0x08133614, MODEL, POINT + 0x60, key, POINT + 0x64)
        return struct.unpack("<i", self.u.mem_read(POINT + 0x64, 4))[0]

    def paint(self, full=True):
        self.u.mem_write(render.CTX, struct.pack("<II", 1 if full else 256, render.SURF))
        parent = MANAGER + 0x470
        self.u.mem_write(POINT + 0x200, struct.pack("<4i", 0, 0, 1280, 480))
        self.call(self.e.r(self.e.r(parent) + 4), parent, render.CTX)
        self.call(self.e.r(self.e.r(parent) + 8), parent, render.CTX, POINT + 0x200)

    def tick(self):
        self.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        self.call("pg_mixer_tick", MIXER, render.CTX)

    def bindings(self):
        return [self.e.h(self.bar() + 0x38 + 0x468 * i + 0x9c) for i in range(8)]


class Tests(unittest.TestCase):
    def test_compressor_transition_and_value_repaint_leave_no_old_output_glyphs(self):
        p = Mixer()
        p.paint()
        p.event("pg_mixer_receive", 0x1076)
        p.paint(False)
        q = Mixer()
        q.event("pg_mixer_receive", 0x1076)
        q.paint()
        self.assertTrue((p.pixels()[:73] == q.pixels()[:73]).all())
        p.global_values[0x123] = 5
        p.event("pg_mixer_event", 0xc3, 0xfffffffe, 0x123, 5)
        p.tick()
        p.paint(False)
        q.global_values[0x123] = 5
        q.event("pg_mixer_receive", 0x1076)
        q.paint()
        self.assertTrue((p.pixels()[:73] == q.pixels()[:73]).all())
        p.labels.clear()
        before = p.pixels().copy()
        p.tick()
        p.paint(False)
        self.assertFalse(any(name == "Pan" or name.startswith("Track ")
                             for name, font in p.labels))
        self.assertTrue((p.pixels() == before).all())

    def test_native_header_mute_audio_and_feedback_without_selection(self):
        p = Mixer()
        p.paint()
        p.tap(3, 130)
        self.assertEqual(p.get(3, 0x13d), 1)
        self.assertEqual(p.packet(0)[4:8], (0xfffffffe, 0x13d, 1, 3))
        self.assertEqual(p.selected, 0)
        self.assertEqual(p.u.mem_read(p.strip(3) + 0x3e0, 1), b"\1")
        p.tick()
        self.assertNotEqual(p.u.mem_read(render.CTX, 2), b"\0\0")
        p.labels.clear()
        p.paint(False)
        self.assertIn(("M", 0), p.labels)
        self.assertFalse(any(s == "MUTED" for s, font in p.labels))

    def test_relative_level_no_jump_native_bounds_and_duplicate_suppression(self):
        p = Mixer()
        p.direct("pg_mixer_down", 2, 200)
        self.assertEqual(p.get(2, 0x134), -3000)
        p.direct("pg_mixer_move", 2, 200)
        self.assertEqual(p.get(2, 0x134), -3000)
        p.direct("pg_mixer_move", 2, 170)
        self.assertEqual(p.get(2, 0x134), 6000)
        p.direct("pg_mixer_move", 2, 170)
        p.direct("pg_mixer_up", 2, 170)
        self.assertEqual(p.packet(0)[4:8], (0xfffffffe, 0x134, 6000, 2))
        self.assertEqual(p.packet(1), (0,) * 9)
        self.assertEqual(p.selected, 2)

    def test_pan_and_both_sends_use_exact_native_units_and_bounds(self):
        for top, key, hi in [(372, 0x13f, 1000), (395, 0x140, 1000), (418, 0x141, 1000)]:
            p = Mixer()
            start = p.get(1, key)
            p.direct("pg_mixer_down", 1, top)
            p.direct("pg_mixer_move", 1, top - 40)
            self.assertEqual(p.get(1, key), start)
            p.direct("pg_mixer_move", 1, top, dx=300)
            self.assertEqual(p.get(1, key), hi)
            p.direct("pg_mixer_move", 1, top, dx=-300)
            self.assertEqual(p.get(1, key), -1000 if key == 0x13f else 0)

    def test_drag_cancels_on_project_page_identity_and_multitouch(self):
        for reason in ("project", "page", "id", "track", "multi", "mode", "compressor"):
            p = Mixer()
            p.direct("pg_mixer_down", 1, 200)
            if reason == "project":
                p.w(MODEL, 0x20019000)
            elif reason == "page":
                p.u.mem_write(MODEL + 0x12c, b"\2")
            elif reason == "track":
                p.w(p.strip(1) + 0x34, 102)
            elif reason == "multi":
                p.direct("pg_mixer_down", 2, 210, ident=1)
            elif reason == "mode":
                p.event("pg_mixer_receive", 0x109)
            elif reason == "compressor":
                p.event("pg_mixer_receive", 0x1076)
            p.direct("pg_mixer_move", 1, 170, ident=1 if reason == "id" else 0)
            self.assertEqual(p.packet(0), (0,) * 9, reason)

    def test_native_modes_and_output_parameter_ownership(self):
        p = Mixer()
        for command, key in [(0x108, 0x134), (0x109, 0x13f), (0x10a, 0x140), (0x10b, 0x141)]:
            p.event("pg_mixer_receive", command)
            self.assertEqual(p.e.r(MIXER + 0x75bc), key)
            self.assertEqual(p.bindings(), [key] * 8)
        p.direct("pg_mixer_down", 0, 40)
        self.assertEqual(p.bindings(), list(OUTPUTS))
        self.assertEqual(p.selected, 0)

    def test_native_tab_lights_do_not_rearm_header_relayout(self):
        # W7 hardware: Mixer footer stayed black. Native 0x68 lights made the
        # snapshot stale, so every prepare re-armed ROOT+117C and relayout.
        p = Mixer()
        root = 0x30034D48
        p.call(0x08180198, root)
        template = bytes(p.u.mem_read(0x08199008 + 24 * 0x1C4, 0x1C4))

        def cycle():
            p.u.mem_write(POINT + 0x400, template)
            p.u.mem_write(root + 0x117C, b"\0")
            p.call("device_header_prepare", POINT + 0x400)
            flag = p.u.mem_read(root + 0x117C, 1)[0]
            p.call(0x0817FAF8, root, POINT + 0x400)
            return flag, [p.u.mem_read(root + 0xA2C + i * 0xD0 + 0xAC, 1)[0] for i in range(4)]

        for _ in range(3):
            cycle()
        for tab in (0x108, 0x109, 0x10A, 0x10B):
            for other in range(0x108, 0x10C):
                p.u.mem_write(POINT + 0x300, struct.pack("<5I", 0x68, 0, other, int(other == tab), 0))
                p.call("header_root_event", root, POINT + 0x300)
            lit = [1 if i == tab - 0x108 else 0 for i in range(4)]
            for _ in range(3):
                self.assertEqual(cycle(), (0, lit), hex(tab))

    def test_solo_mute_mode_has_no_strip_buttons_and_keeps_name_mute(self):
        p = Mixer()
        if not p.u.mem_read(MIXER + 0x9a08, 1)[0]:
            p.event("pg_mixer_receive", 0x10c)
        p.paint()
        self.assertNotIn("Solo", [name.strip() for name, font in p.labels])
        self.assertNotIn("Mute", [name.strip() for name, font in p.labels])
        self.assertFalse(any("%" in name for name, font in p.labels))
        self.assertNotIn("C", [name.strip() for name, font in p.labels])
        self.assertFalse({"Pan", "Dly", "Rev"} & {name.strip() for name, font in p.labels})
        p.direct("pg_mixer_down", 1, 167, dx=-40)
        p.direct("pg_mixer_up", 1, 167, dx=-40)
        self.assertEqual(p.get(1, 0x13e), 0)
        self.assertEqual(p.get(1, 0x13d), 0)
        p.direct("pg_mixer_down", 2, 120)
        p.direct("pg_mixer_up", 2, 120)
        self.assertEqual(p.get(2, 0x13d), 1)
        self.assertEqual(p.get(2, 0x13e), 0)

    def test_compressor_native_bindings_and_global_cf_not_track_d3(self):
        p = Mixer()
        p.event("pg_mixer_receive", 0x1076)
        self.assertEqual(p.bindings(), list(COMP))
        p.labels.clear()
        p.paint()
        self.assertIn("Attack", [name.strip() for name, font in p.labels])
        self.assertIn("Release", [name.strip() for name, font in p.labels])
        self.assertTrue((p.pixels()[:73, 164:322] == 0xf2).any())
        self.assertEqual([p.e.r(p.bar() + 0x38 + 0x468 * i + 0x34) for i in range(8)],
                         [PROJECT] * 8)
        p.events.clear()
        p.event("pg_mixer_receive", 0xcf, 100, 0x125, -12000)
        self.assertEqual(p.events, [(0xcf, PROJECT, 0x125, 0xffffd120, 0)])
        p.event("pg_mixer_receive", 0x109)
        self.assertEqual(p.bindings(), [0x13f] * 8)

    def test_compressor_footer_removed_without_changing_burger(self):
        p = Mixer()
        root = 0x30034d48
        p.call(0x08180198, root)
        template = 0x08199008 + 24 * 0x1c4
        out = POINT + 0x400
        p.u.mem_write(out, bytes(p.u.mem_read(template, 0x1c4)))
        p.call("pg_mixer_toolbar", MODEL, out)
        self.assertEqual([p.e.h(out + 0x74 + i * 48 + 44) for i in range(6)],
                         [0x108, 0x109, 0x10a, 0x10b, 0, 0x10c])
        self.assertEqual(p.e.h(out + 0x194), p.e.h(template + 0x194))
        p.call("device_header_prepare", out)
        p.call(0x0817faf8, root, out)
        self.assertEqual(p.u.mem_read(root + 0x54c + 5 * 0xd0 + 0x30, 1), b"\0")
        self.assertEqual(p.u.mem_read(root + 0xa2c + 4 * 0xd0 + 0x30, 1), b"\1")

    def test_footer_root_parented_by_native_set_page_is_painted_and_walked(self):
        # Native setPage (0816E2A0) adds the footer root, popups and overlays
        # as children of the active page; generic page paint reaches them.
        root = 0x30034d48
        footers = []
        for compressor in (False, True):
            p = Mixer()
            if compressor:
                p.event("pg_mixer_receive", 0x1076)
                p.tick()
            p.call(0x08180198, root)
            out = POINT + 0x400
            p.u.mem_write(out, bytes(p.u.mem_read(0x08199008 + 24 * 0x1c4, 0x1c4)))
            p.call("pg_mixer_toolbar", MODEL, out)
            p.call("device_header_prepare", out)
            p.call(0x0817faf8, root, out)
            self.assertEqual(p.e.r(root + 0x2c), 0)
            p.call(0x0816fb64, MIXER, root)
            vt = p.e.r(root)
            calls = []
            hooks = [p.u.hook_add(UC_HOOK_CODE, lambda u, a, s, d, k=k: u.reg_read(UC_ARM_REG_R0) == root and calls.append(k),
                                  begin=p.e.r(vt + 4 * k) & ~1, end=p.e.r(vt + 4 * k) & ~1)
                     for k in (1, 2)]
            p.paint()
            self.assertIn(1, calls)
            self.assertIn(2, calls)
            footers.append(p.pixels()[438:480].copy())
            self.assertTrue((footers[-1] != footers[-1][0, 0]).any())
            p.u.mem_write(root + 0x30, b"\1")
            calls.clear()
            p.paint()
            self.assertEqual(calls, [])
            for h in hooks:
                p.u.hook_del(h)

    def test_compressor_real_encoder_routes_through_native_strip_to_global_cf(self):
        p = Mixer()
        p.event("pg_mixer_receive", 0x1076)
        p.encoder = True
        p.events.clear()
        p.call(0x08171e44, p.bar() + 0x38 + 0x468, 10000)
        self.assertTrue(any(e[0] == 0xcf and e[1] == PROJECT and e[2] == 0x123
                            and e[3] > 30 for e in p.events), p.events)
        self.assertFalse(any(e[0] == 0xd3 for e in p.events))

    def test_compressor_turns_on_through_project_node_not_global(self):
        p = Mixer()
        p.event("pg_mixer_receive", 0x1076)
        p.encoder = True
        p.events.clear()
        p.call(0x08171e44, p.bar() + 0x38, 1000)
        self.assertEqual(p.events, [(0xcf, PROJECT, 0x9c, 1, 0)])
        p.tick()
        self.assertEqual(p.e.r(p.bar() + 0x38 + 0x34), PROJECT)
        self.assertEqual(p.e.r(p.bar() + 0x38 + 0xa0), 1)

    def test_hold_mixer_adapter_restores_native_mode_without_losing_compressor(self):
        p = Mixer()
        if p.u.mem_read(MIXER + 0x9a08, 1)[0]:
            p.event("pg_mixer_receive", 0x10c)
        p.event("pg_mixer_receive", 0x1076)
        p.w(0x24048cc0, 0x354d5442)
        p.w(0x24048cc4, 5)
        p.w(0x24048cc0 + 44, 1)
        p.tick()
        self.assertEqual(p.u.mem_read(MIXER + 0x9a08, 1), b"\1")
        self.assertEqual(p.bindings(), list(COMP))
        p.w(0x24048cc4, 0)
        p.tick()
        self.assertEqual(p.u.mem_read(MIXER + 0x9a08, 1), b"\0")
        self.assertEqual(p.bindings(), list(COMP))

    def test_output_change_wakes_idle_paint_and_metronome_has_no_fake_meter(self):
        p = Mixer()
        p.paint()
        p.u.mem_write(p.strip(8) + 0x1f5, b"-12.0dB\0")
        p.tick()
        self.assertNotEqual(p.u.mem_read(render.CTX, 2), b"\0\0")
        p.labels.clear()
        p.paint(False)
        self.assertIn(("-12.0dB", 0), p.labels)
        p.fills.clear()
        p.u.mem_write(p.strip(14) + 0x498, struct.pack("<f", -1))
        p.paint(False)
        self.assertEqual(p.fills, [])

    def test_settled_paint_and_quantized_meter_only_update(self):
        p = Mixer()
        p.paint()
        p.fills.clear()
        p.labels.clear()
        p.paint(False)
        self.assertEqual(p.fills, [])
        self.assertEqual(p.labels, [])
        p.meters[0] = (-12, -60)
        p.tick()
        p.paint(False)
        self.assertEqual(len(p.fills), 2)
        self.assertEqual(p.labels, [])

    def test_native_stereo_publications_drive_real_meter_samples_not_palette_fields(self):
        p = Mixer()
        p.paint()
        colour = p.call(0x08140ebc, 0)
        self.assertNotEqual(int(p.pixels()[270, 48]), colour)
        p.meters[0] = (-12, -45)
        p.tick()
        self.assertEqual(struct.unpack("<f", p.u.mem_read(p.strip(0) + 0x498, 4))[0], -12)
        self.assertEqual(struct.unpack("<f", p.u.mem_read(p.strip(0) + 0x4e4, 4))[0], -45)
        p.paint(False)
        self.assertEqual(int(p.pixels()[220, 48]), colour)
        self.assertNotEqual(int(p.pixels()[220, 58]), colour)
        self.assertEqual(int(p.pixels()[310, 58]), colour)

    def test_meter_and_fader_rails_are_shortened_evenly_without_moving_readout(self):
        p = Mixer()
        p.paint()
        pixels = p.pixels()

        # Both endpoints are inset by four pixels; the output text stays at its
        # established baseline and the hit/drag region remains unchanged.
        self.assertEqual(int(pixels[143, 46]), 0xa3)
        self.assertEqual(int(pixels[144, 46]), 0x22)
        self.assertEqual(int(pixels[324, 46]), 0x22)
        self.assertEqual(int(pixels[325, 46]), 0xa3)
        self.assertEqual(int(pixels[143, 97]), 0xa3)
        self.assertEqual(int(pixels[144, 97]), 0xf3)
        self.assertEqual(int(pixels[324, 97]), 0xf3)
        self.assertEqual(int(pixels[325, 97]), 0xa3)
        self.assertIn(("-3.0 dB", 0), p.labels)

    def test_typography_seamless_background_and_no_empty_name(self):
        p = Mixer()
        p.w(p.strip(2) + 0x34, 0)
        p.paint()
        self.assertIn(("Track 1", 1), p.labels)
        self.assertNotIn(("Pan", 0), p.labels)
        self.assertFalse(any(s in ("Empty", "MUTED") for s, f in p.labels))
        self.assertEqual(int(p.pixels()[415, 7]), 0xa3)
        self.assertEqual(int(p.pixels()[415, 164]), 0xa3)

    def test_hardware_vertical_output_drag_and_no_macro_swipe(self):
        p = Mixer()
        p.tick()
        p.finger(0, 40, True)
        p.finger(0, 60, True)
        p.finger(0, 60, False)
        self.assertTrue(any(e[0] == 0xcf and e[2] == 0x138 for e in p.events))
        self.assertEqual(p.call("macro_overlay"), 0)
        p.finger(3, 40, True)
        p.finger(3, 40, True, dx=-200)
        p.finger(3, 40, False, dx=-200)
        self.assertEqual(p.call("macro_overlay"), 0)  # W13: swipe overlay removed

    def test_settings_keeps_set_time_second_and_removes_duplicate_compressor(self):
        p = Mixer()
        p.call("perf_dispatch", MODEL, 0xaf, 7)
        p.event("perf_event", 0x1074)
        out = MIXER + 0x93c4
        self.assertEqual(p.call("perf_header", out, 0x08145f22), 1)
        self.assertEqual(p.u.mem_read(out, 1), b"\3")
        self.assertEqual([p.e.h(out + 0x14 + i * 2) for i in range(8)],
                         [0x83, 0xa2, 0xa3, 0xe1, 0x67, 0xa4, 0xa8, 0])
        self.assertEqual([p.e.h(out + 0x24 + i * 2) for i in range(8)],
                         [0x1d4, 0x1d5, 0x1d6, 0, 0, 0, 0x1d7, 0x1d8])
        self.assertEqual([p.e.h(out + 0x34 + i * 2) for i in range(8)],
                         [0x102, 0x11c, 0x178, 0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
