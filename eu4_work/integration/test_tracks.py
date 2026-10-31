"""Tracks native widgets, hardware finger routing, cached paint and navigation.

The firmware constructor, glyphs, fonts, DMA2D renderer, hit dispatcher, track
selection and type-aware INST/SEQ routing execute. Project data, model edits,
navigation endpoints and meter publication are controlled fixture boundaries.
No device CPU percentage or hardware acceptance is inferred.
"""
import json
import os
from pathlib import Path
import struct
import sys
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_PC
from test_integration import IMAGE, UU, CANDIDATE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/display_emulator"))
import emu
import render

MODEL, VIEW, POINT = 0x30024b00, 0xc1800000, 0x24070000
MANAGER, REPORT = 0x20010000, 0x20011000
KEEP = []


class Tracks:
    def __init__(self):
        KEEP.append(self)
        self.e = emu.Emu(IMAGE)
        self.u = self.e.u
        render.boot_gfx(self.e)
        self.call(0x081639a8, 0)
        self.call(0x0816022c, VIEW)
        self.selected = 0
        self.types = [14, 18, 19, 15, 16, 17, 20, 22]
        self.muted = [0] * 8
        self.fail_mute = False
        self.diagnostics = []
        self.events, self.navs, self.outputs, self.fills, self.labels = [], [], [], [], []
        self.meters = {i: (-60.0, -60.0) for i in range(8, 12)}
        self.hooks = [self.u.hook_add(UC_HOOK_CODE, self.hook, begin=a, end=a)
                      for a in [0x0810770e, 0x08133960, 0x08133614,
                                0x08133f7c, 0x08133cfc, 0x0816fc34,
                                0x081403ec, 0x081420ec, 0x08138164,
                                0x08166ef6, 0x08133e54, 0x0813391a, 0x0813390e,
                                0x08104c00, 0x0817e448]]
        self.w(MODEL, 0x20014000)
        self.u.mem_write(MODEL + 0x12c, b"\2")
        self.u.mem_write(MODEL + 0x19be, b"\0")
        self.w(MODEL + 0x13c, 100)
        self.w(0x3001fe2c, 1000)
        for i, name in enumerate(["Drums", "Analog", "Granular", "Piano",
                                  "Slices", "Loop", "Grain", "External"]):
            c = self.col(i)
            self.w(POINT, 100 + i)
            self.call(0x08181110, c, POINT)
            self.u.mem_write(POINT + 8, name.encode() + b"\0")
            self.call(0x081808fc, c, POINT + 8)
            icon = self.call(0x08140fca, self.types[i])
            self.call(0x08180920, c, icon)
            self.level(i, -30, -45)
        self.w(0x24043500, 0x35424e4b)
        self.w(0x24043520, 2)
        self.w(0x24043524, 101)
        self.u.mem_write(0x2404352f, b"\x0d")
        self.call(0x08160b68, VIEW)
        self.u.mem_write(self.bar() + 0x30, b"\0")
        self.u.mem_write(MANAGER, bytes(0x500))
        self.call(0x0816fb28, MANAGER + 0x470)
        self.call(0x0816fb64, MANAGER + 0x470, VIEW)
        self.w(MANAGER + 0x470 + 0x3c, VIEW)

    def call(self, address, *args):
        result = self.e.call(UU[address] if isinstance(address, str) else address, *args)
        if self.u.reg_read(UC_ARM_REG_PC) != emu.RET:
            raise AssertionError("Native call did not complete")
        return result

    def w(self, address, value):
        self.e.w(address, value)

    def ret(self, value=0):
        from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC
        self.u.reg_write(UC_ARM_REG_R0, value)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR))

    def hook(self, u, address, size, data):
        r = [u.reg_read(reg) for reg in
             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        if address == 0x0810770e:
            self.ret(1)
        elif address == 0x08133960:
            self.w(r[2], self.e.r(self.col(r[1]) + 0x2dc) if r[1] < 8 else 0)
            self.ret(int(r[1] < 8))
        elif address == 0x08133f7c:
            handle = self.e.r(r[1])
            self.ret(self.types[handle - 100] if 100 <= handle < 108 else 3 if handle == 200 else 5 if handle == 201 else 0)
        elif address == 0x08133cfc:
            self.w(r[1], 100 + self.selected)
            self.ret(1)
        elif address == 0x08133e54:
            self.w(r[1], 42)
            self.ret(1)
        elif address == 0x0813391a:
            found = self.e.r(r[1]) == 100 and r[2] < 2
            self.w(r[3], 200 + r[2] if found else 0)
            self.ret(int(found))
        elif address == 0x0813390e:
            self.u.mem_write(r[3], b"\0")
            self.ret(1)
        elif address == 0x08133614:
            if self.fail_mute and r[2] == 0x13d:
                self.ret(0)
                return
            handle = self.e.r(r[1])
            value = (self.muted[handle - 100] if r[2] == 0x13d and 100 <= handle < 108
                     else self.selected if r[2] == 0x131
                     else 120 if r[2] == 0x8c else 0)
            self.w(r[3], value)
            self.ret(1)
        elif address in (0x0816fc34, 0x081403ec):
            raw = struct.unpack("<5I", u.mem_read(r[1], 20))
            event = (raw[0] & 65535, *raw[1:])
            self.events.append(event)
            if event[0] == 0x37:
                self.selected = event[2]
                self.w(MODEL + 0x13c, 100 + self.selected)
            elif event[0] == 0xd3:
                self.muted[event[1] - 100] = event[3]
            self.ret(0)
        elif address == 0x081420ec:
            self.navs.append(r[1])
            self.u.mem_write(MODEL + 0x12c, bytes([r[1]]))
            self.ret()
        elif address == 0x08138164:
            channel = self.e.h(r[1])
            left, right = self.meters.get(channel, (-60, -60))
            self.outputs.append(channel)
            u.mem_write(r[2], struct.pack("<f", left))
            u.mem_write(r[3], struct.pack("<f", right))
            self.ret(1)
        elif address == 0x08166ef6:
            self.fills.append((struct.unpack("<4i", u.mem_read(r[0], 16)), r[1]))
        elif address == 0x08104c00:
            self.diagnostics.append(self.e.text(r[0]))
            self.ret()
        elif address == 0x0817e448:
            self.labels.append((self.e.text(r[0] + 0x31),
                                self.u.mem_read(r[0] + 0x55, 1)[0]))

    def col(self, index):
        return VIEW + 0x34 + index * 0x4c4

    def bar(self):
        return VIEW + 0x2658

    def level(self, index, left, right):
        for k, value in enumerate((left, right)):
            self.u.mem_write(self.col(index) + 0x31c + k * 0x4c,
                             struct.pack("<f", value))

    def finger(self, index, top, down, dx=0):
        report = bytearray(16)
        if down:
            struct.pack_into("<h", report, 0, 1)
            struct.pack_into("<hhB", report, 4, 84 + 159 * index + dx, 480 - top, 1)
        self.u.mem_write(REPORT, bytes(report))
        self.call(0x0816332c, MANAGER, REPORT)

    def tap(self, index, top, tick=1000):
        self.w(0x3001fe2c, tick)
        self.finger(index, top, True)
        self.finger(index, top, False)

    def direct(self, function, index, top, ident=0, dx=0):
        self.w(POINT, 84 + 159 * index + dx)
        self.w(POINT + 4, 480 - top)
        self.call(function, self.col(index), POINT, ident)

    def paint(self, full=True):
        self.u.mem_write(render.CTX, struct.pack("<II", 1 if full else 256, render.SURF))
        render.paint(self.e, VIEW)

    def pixels(self):
        return render.ui(self.e)

    def save(self):
        from PIL import Image
        image = Image.frombytes("P", (1280, 480), self.pixels().tobytes())
        base = [self.e.r(0x30000000 + 4 * i) for i in range(16)]
        palette = []
        for index in range(256):
            alpha, colour = index >> 4, base[index & 15]
            palette.extend(((colour >> shift) & 255) * alpha // 15 for shift in (16, 8, 0))
        image.putpalette(palette)
        out = Path(os.environ.get("BENTO_FX_CANDIDATE", CANDIDATE)) / "screens"
        out.mkdir(exist_ok=True)
        image.convert("RGB").save(out / "tracks.png")


class NativeTracks(Tracks):
    """Execute real track lookup, mute getter/setter and audio packet writer."""
    def __init__(self):
        self.ready = False
        super().__init__()
        self.notifications = []
        self.engine = 0x30010000
        self.w(0x3000f650, self.engine)
        root = self.e.r(MODEL)
        self.w(root + 0x30, 8)
        vtable = 0x20016000
        self.w(vtable + 0x14, emu.RET + 0x101)
        self.u.mem_write(emu.RET + 0x100, bytes.fromhex("00207047"))
        for i in range(8):
            obj, props = 0x20015000 + i * 0x100, 0x20017000 + i * 0x100
            self.w(root + 4 * i, obj)
            self.w(obj, vtable)
            self.w(obj + 16, 100 + i)
            self.w(obj + 8, props)
            self.w(obj + 12, 3)
            self.u.mem_write(props, struct.pack("<IHBB", i, 0x73, 1, 0)
                            + struct.pack("<IHBB", 0, 0x13d, 1, 0)
                            + struct.pack("<IHBB", 0, 0x13e, 1, 0))
        for address in [0x08106d84, 0x08173272]:
            self.hooks.append(self.u.hook_add(UC_HOOK_CODE, self.hook,
                                             begin=address, end=address))
        self.ready = True

    def hook(self, u, address, size, data):
        r = [u.reg_read(reg) for reg in
             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        if self.ready:
            if address == 0x08133614 and r[2] == 0x13d:
                return
            if address == 0x081403ec and self.e.h(r[1]) == 0xd3:
                return
            if address == 0x08106d84:
                self.ret()
                return
            if address == 0x08173272:
                self.notifications.append(struct.unpack("<5I", u.mem_read(r[1], 20)))
                self.ret()
                return
        return super().hook(u, address, size, data)

    def packet(self, index):
        return struct.unpack("<BBh4I2h", self.u.mem_read(self.engine + 24 * index, 24))


class Tests(unittest.TestCase):
    def test_native_mute_updates_audio_and_widget_without_synthetic_ui_mutation(self):
        for index in range(8):
            p = NativeTracks()
            p.tap(index, 130)
            self.assertEqual(p.packet(0)[4:8], (0xfffffffe, 0x13d, 1, index))
            self.assertEqual(p.notifications[-1], (0xc3, 100 + index, 0x13d, 1, 0))
            self.assertEqual(p.u.mem_read(p.col(index) + 0x2e0, 1), b"\1")
            self.assertEqual(p.selected, 0)
            p.tap(index, 130, 1200)
            self.assertEqual(p.packet(1)[4:8], (0xfffffffe, 0x13d, 0, index))
            self.assertEqual(p.u.mem_read(p.col(index) + 0x2e0, 1), b"\0")

    def test_native_mute_wakes_idle_paint_and_draws_feedback_without_audio_activity(self):
        p = NativeTracks()
        for i in range(8):
            p.level(i, -60, -60)
        p.paint()
        unmuted_name = p.pixels()[106:136, 487:646].copy()
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.call("pg_tracks_tick", VIEW, render.CTX)
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.tap(3, 130)
        p.call("pg_tracks_tick", VIEW, render.CTX)
        self.assertNotEqual(p.u.mem_read(render.CTX, 2), b"\0\0")
        p.labels.clear()
        render.paint(p.e, VIEW)
        self.assertIn(("M", 0), p.labels)
        self.assertNotIn(("MUTED", 0), p.labels)
        self.assertTrue((p.pixels()[330:360, 487:646] == 0xf1).all())
        self.assertFalse((p.pixels()[106:136, 487:646] == unmuted_name).all())
        p.fills.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.call("pg_tracks_tick", VIEW, render.CTX)
        render.paint(p.e, VIEW)
        self.assertEqual(p.fills, [])
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.tap(3, 130, 1200)
        p.call("pg_tracks_tick", VIEW, render.CTX)
        p.labels.clear()
        render.paint(p.e, VIEW)
        self.assertNotIn(("M", 0), p.labels)
        self.assertTrue((p.pixels()[106:136, 487:646] == unmuted_name).all())

    def test_header_mutes_without_selecting_through_hardware_dispatch(self):
        p = Tracks()
        p.tap(3, 130)
        self.assertEqual(p.selected, 0)
        self.assertEqual(p.muted, [0, 0, 0, 1, 0, 0, 0, 0])
        self.assertIn((0xd3, 103, 0x13d, 1, 0), p.events)
        p.tap(3, 130, 1100)
        self.assertEqual(p.muted[3], 0)
        self.assertEqual(p.selected, 0)

    def test_first_target_tap_and_meter_tap_select_without_opening(self):
        p = Tracks()
        for i, top in [(1, 210), (2, 310), (4, 375)]:
            p.tap(i, top)
            self.assertEqual(p.selected, i)
        self.assertEqual([e[0] for e in p.events], [0x37, 0x37, 0x37])
        self.assertEqual(p.navs, [])

    def test_failed_mute_read_diagnoses_without_writing_or_selecting(self):
        p = Tracks()
        p.fail_mute = True
        p.tap(3, 130)
        self.assertEqual(p.events, [])
        self.assertEqual(len(p.diagnostics), 1)
        self.assertEqual(p.selected, 0)

    def test_instrument_double_tap_uses_native_type_routing(self):
        for index, expected in [(0, 1), (1, 0x16), (2, 0x16), (7, 7)]:
            p = Tracks()
            p.tap(index, 210)
            p.tap(index, 210, 1200)
            self.assertEqual(p.selected, index)
            self.assertIn(expected, [e[0] for e in p.events])

    def test_seq_double_tap_uses_real_native_button_handler(self):
        for index, page in [(0, 0x27), (1, 0x17), (2, 0x17), (5, 0x25)]:
            p = Tracks()
            p.tap(index, 375)
            p.tap(index, 375, 1200)
            self.assertEqual(p.selected, index)
            self.assertEqual(p.navs, [page])

    def test_native_selection_refresh_between_taps_keeps_both_shortcuts(self):
        for top, expected in [(210, 0x16), (375, 0x17)]:
            p = Tracks()
            p.tap(1, top)
            # The track model is already supplied by this fixture; retain that
            # snapshot while executing the real refresh event dispatcher.
            p.hooks.append(p.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: p.ret(),
                                       begin=0x08160c1c, end=0x08160c1c))
            p.u.mem_write(POINT, struct.pack("<5I", 0x78, 0, 0, 0, 0))
            p.call("pg_tracks_event", VIEW, POINT)
            p.tap(1, top, 1200)
            self.assertEqual(p.selected, 1)
            if top == 210:
                self.assertIn(expected, [e[0] for e in p.events])
            else:
                self.assertEqual(p.navs, [expected])

    def test_double_taps_do_not_cross_track_destination_or_timeout(self):
        for first, second in [((0, 210, 1000), (1, 210, 1100)),
                              ((1, 210, 1000), (1, 375, 1100)),
                              ((1, 210, 1000), (1, 210, 1450))]:
            p = Tracks()
            p.tap(*first)
            p.tap(*second)
            self.assertEqual([e[0] for e in p.events], [0x37, 0x37])
            self.assertEqual(p.navs, [])

    def test_drag_long_press_multitouch_and_project_change_cancel(self):
        for reason in ("drag", "hold", "multi", "project", "page", "zone", "id", "track"):
            p = Tracks()
            p.direct("pg_column_down", 1, 210)
            if reason == "drag":
                p.direct("pg_column_move", 1, 210, dx=35)
                p.direct("pg_column_move", 1, 210)
            elif reason == "hold":
                p.w(0x3001fe2c, 1700)
            elif reason == "multi":
                p.direct("pg_column_down", 2, 210, ident=1)
                p.direct("pg_column_up", 2, 210, ident=1)
            elif reason == "project":
                p.w(MODEL, 0x20015000)
            elif reason == "page":
                p.u.mem_write(MODEL + 0x12c, b"\x17")
            elif reason == "track":
                p.w(p.col(1) + 0x2dc, 0)
            p.direct("pg_column_up", 1, 310 if reason == "zone" else 210,
                     ident=1 if reason == "id" else 0)
            self.assertEqual(p.events, [], reason)

    def test_navigation_clears_pending_double_tap_without_idle_allocation(self):
        p = Tracks()
        before = p.e.r(0x3000004c)
        p.call("pg_tracks_nav")
        self.assertEqual(before, p.e.r(0x3000004c))
        p.tap(1, 210)
        p.call("workflow_nav")
        p.tap(1, 210, 1100)
        self.assertEqual([e[0] for e in p.events], [0x37, 0x37])

    def test_empty_track_retains_native_instrument_chooser_and_no_empty_seq(self):
        p = Tracks()
        p.w(p.col(3) + 0x2dc, 0)
        p.tap(3, 130)
        self.assertEqual(p.events, [])
        p.tap(3, 210, 1100)
        p.tap(3, 210, 1200)
        self.assertIn(0x2d, [e[0] for e in p.events])
        p.events.clear()
        p.tap(3, 375, 1300)
        p.tap(3, 375, 1400)
        self.assertEqual(p.navs, [])

    def test_hidden_outside_and_other_page_do_not_capture(self):
        p = Tracks()
        for top, hidden, page in [(72, 0, 2), (424, 0, 2), (210, 1, 2), (210, 0, 0x17)]:
            p.u.mem_write(p.col(0) + 0x30, bytes([hidden]))
            p.u.mem_write(MODEL + 0x12c, bytes([page]))
            p.w(POINT, 84)
            p.w(POINT + 4, 480 - top)
            self.assertEqual(p.call("pg_column_hit", p.col(0), POINT, POINT + 8), 0)

    def test_geometry_real_glyphs_mute_solo_and_stereo_db_meter(self):
        p = Tracks()
        p.u.mem_write(p.col(2) + 0x2e0, b"\1")
        p.u.mem_write(p.col(4) + 0x2e1, b"\1")
        p.paint()
        pixels = p.pixels()
        self.assertTrue((pixels[74:77, 6:20] == 0xa3).all())
        self.assertTrue((pixels[74:77, 169:318] == 0xf1).all())
        self.assertTrue((pixels[408:431, 6:165] == 0xa3).all())
        self.assertTrue((pixels[408:431, 165:324] == 0xf1).all())
        self.assertEqual(int(pixels[311, 38 + 45]), 0xf7)
        self.assertNotEqual(int(pixels[311, 38 + 46]), 0xf7)
        self.assertTrue((pixels[378, 72:96] == 0x62).all())
        self.assertTrue((pixels[197:233, 227:259] != 0xf1).any())
        self.assertEqual(int(pixels[223, 223]), 0xf8)
        self.assertEqual(int(pixels[197, 236]), 0xf8)
        self.assertTrue((pixels[197:225, 236:238] == 0xf8).all())
        self.assertTrue(all(rect[1] >= 480 - 431 for rect, colour in p.fills))
        p.save()

    def test_labels_use_native_size_and_real_bold_font_without_empty_title(self):
        p = Tracks()
        p.w(p.col(3) + 0x2dc, 0)
        p.paint()
        for name in ["Drums", "Analog", "Granular"]:
            self.assertIn((name, 1), p.labels)
        for name in ["01", "One-shot", "Phones", "Brightness"]:
            self.assertIn((name, 0), p.labels)
        self.assertFalse(any(text == "Empty" for text, font in p.labels))

    def test_selection_repaints_old_and_new_full_width_columns_without_gutters(self):
        p = Tracks()
        p.paint()
        p.tap(1, 310)
        p.paint(False)
        pixels = p.pixels()
        self.assertTrue((pixels[408:431, 6:165] == 0xf1).all())
        self.assertTrue((pixels[408:431, 165:324] == 0xa3).all())

    def test_db_meter_saturation_nonfinite_and_pixel_quantization(self):
        p = Tracks()
        p.paint()
        for value, width in [(-60, 0), (-90, 0), (0, 92), (6, 92),
                             (-30, 46), (float("nan"), 0), (float("inf"), 0)]:
            p.level(0, value, value)
            p.paint(False)
            self.assertEqual(int((p.pixels()[311, 38:130] == 0xf7).sum()), width)
        p.level(0, -30, -45)
        p.paint(False)
        p.fills.clear()
        p.level(0, -29.99, -44.99)
        p.paint(False)
        self.assertEqual(p.fills, [])

    def test_meter_only_updates_do_not_repaint_static_text_or_column(self):
        p = Tracks()
        p.paint()
        p.fills.clear()
        p.paint(False)
        self.assertEqual(p.fills, [])
        p.level(0, -12, -45)
        p.paint(False)
        self.assertEqual(len(p.fills), 2)
        self.assertEqual(p.fills[0][0], (38, 167, 92, 2))
        self.assertEqual(p.fills[1][0], (38, 167, 73, 2))

    def test_output_row_keeps_native_bindings_and_real_stereo_output_indices(self):
        p = Tracks()
        self.assertEqual([p.e.h(p.bar() + 0x38 + 0x468 * i + 0x9c) for i in range(8)],
                         [0x138, 0x137, 0x136, 0x135, 0, 0x8c, 0, 0x83])
        p.paint()
        p.meters[8] = (-30, -45)
        p.call("pg_tracks_tick", VIEW, render.CTX)
        self.assertEqual(p.outputs[-4:], [8, 9, 10, 11])
        p.paint(False)
        pixels = p.pixels()
        self.assertEqual(int(pixels[62, 16 + 66]), 0xf6)
        self.assertEqual(int(pixels[62, 16 + 67]), 0x22)
        self.assertTrue((pixels[63:73, 16:151] == 0xf1).all())
        self.assertTrue((pixels[59:62, 16:151] == 0xf1).all())

    def test_other_bars_fall_through_and_mixer_hooks_are_exact(self):
        p = Tracks()
        p.w(p.bar() + 0x2c, 0)
        called = []
        for address, name in [(0x0816faec, "paint"), (0x0816f9e8, "walk")]:
            p.hooks.append(p.u.hook_add(
                UC_HOOK_CODE, lambda u, a, n, d: (called.append(d), p.ret()),
                user_data=name, begin=address, end=address))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        p.call("pg_bar_walk", p.bar(), render.CTX, 0)
        self.assertEqual(called, ["paint", "walk"])
        baseline = Path(os.environ["BENTO_K16_IMAGE"]).read_bytes()
        for address, length in [(0x081b2a4c, 56), (0x0819dd20, 56)]:
            offset = address - 0x08040000
            expected = bytearray(baseline[offset:offset+length])
            if address == 0x0819dd20:
                for slot, function in [(0, "tick"), (1, "paint"), (2, "walk"),
                                       (4, "down"), (5, "move"), (6, "up"),
                                       (10, "hit"), (12, "receive"), (13, "event")]:
                    struct.pack_into("<I", expected, slot * 4, UU["pg_mixer_" + function] | 1)
            self.assertEqual(IMAGE[offset:offset+length], expected)

    def test_macro_overlay_bypasses_custom_bar_and_invalidates_its_cache(self):
        p = Tracks()
        p.paint()
        native = []
        overlay = p.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: p.ret(1),
                               begin=UU["macro_overlay"], end=UU["macro_overlay"])
        p.hooks.append(overlay)
        for address, name in [(0x0816faec, "paint"), (0x0816f9e8, "walk")]:
            p.hooks.append(p.u.hook_add(
                UC_HOOK_CODE, lambda u, a, n, d: (native.append(d), p.ret()),
                user_data=name, begin=address, end=address))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        p.call("pg_bar_walk", p.bar(), render.CTX, 0)
        self.assertEqual(native, ["paint", "walk"])
        p.u.hook_del(overlay)
        p.fills.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 256, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        self.assertTrue(p.fills)


if __name__ == "__main__":
    unittest.main(verbosity=2)
