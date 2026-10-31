"""Perform's real native widgets, fonts, touch dispatcher and cached painting."""
import os
import json
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R3

from test_tracks import Tracks, MODEL, MANAGER, POINT, REPORT, VIEW as TRACKS_VIEW, render
from test_integration import UU, CANDIDATE

VIEW = 0xc1a00000


class Perform(Tracks):
    def hook(self, u, address, size, data):
        if address == 0x0816fc34:
            return
        super().hook(u, address, size, data)

    def __init__(self):
        super().__init__()
        self.call("perf_dispatch", MODEL, 0xaf, 7)
        self.call(0x08145b7c, VIEW)
        self.w(POINT, 0xfffffffe)
        self.call(0x08145efc, VIEW, POINT)
        self.call(0x0816fb82, MANAGER + 0x470, TRACKS_VIEW)
        self.u.mem_write(TRACKS_VIEW + 0x30, b"\1")
        self.call(0x0816fb64, MANAGER + 0x470, VIEW)
        self.w(MANAGER + 0x470 + 0x3c, VIEW)
        self.call(0x08180198, render.ROOT)
        self.u.mem_write(POINT, render.tpl(self.e, 20))
        self.call("device_header_prepare", POINT)
        self.call(0x0817faf8, render.ROOT, POINT)
        self.values()

    def bar(self, row=0):
        return VIEW + 0x38 + row * 0x23f8

    def values(self):
        for i in range(8):
            slot = self.bar(1) + 0x38 + i * 0x468
            key = self.e.h(slot + 0x9c)
            self.call("perf_get", MODEL, POINT, key, POINT + 4)
            self.call(0x08171c1c, slot, key, self.e.r(POINT + 4), 1)

    def edit(self, key, value):
        self.u.mem_write(POINT, struct.pack("<5I", 0xcf, 0xfffffffe, key, value, 0))
        self.call("perf_event", VIEW, POINT)
        self.values()

    def mapped(self):
        data = bytearray([2])
        for macro in range(8):
            data += bytes([64, 3 if macro == 0 else 0]) + bytes(12)
            if macro == 0:
                for track, name, start, end in [(0, "Filter", 20, 85),
                                               (1, "Resonance", 80, 25),
                                               (2, "Pan", 0, 100)]:
                    data += bytes([track, 255, 255]) + struct.pack("<Hiiii", 0x33, 0, 100, start, end)
                    data += name.encode().ljust(12, b"\0")
        raw = data.hex().upper().encode() + b"\0"
        string = 0xc1b00000
        self.u.mem_write(string, raw)
        hooks = []
        for address, result in [(0x08109268, POINT), (0x08109c64, POINT), (0x081094c2, string)]:
            hooks.append(self.u.hook_add(UC_HOOK_CODE,
                         lambda u, a, n, d, result=result: self.ret(result),
                         begin=address, end=address))
        try:
            self.call("macro_load", POINT, POINT)
        finally:
            for hook in hooks:
                self.u.hook_del(hook)

    def finger_at(self, x, top, down):
        report = bytearray(16)
        if down:
            struct.pack_into("<h", report, 0, 1)
            struct.pack_into("<hhB", report, 4, x, 480 - top, 1)
        self.u.mem_write(REPORT, bytes(report))
        self.call(0x0816332c, MANAGER, REPORT)

    def tap_at(self, x, top):
        self.finger_at(x, top, True)
        self.finger_at(x, top, False)
        self.values()

    def paint(self, full=True):
        self.u.mem_write(render.CTX, struct.pack("<II", 1 if full else 256, render.SURF))
        render.paint(self.e, VIEW)
        render.paint(self.e, render.ROOT)

    def save(self, filename="perform.png"):
        from PIL import Image
        image = Image.frombytes("P", (1280, 480), self.pixels().tobytes())
        base = [self.e.r(0x30000000 + 4 * i) for i in range(16)]
        palette = []
        for index in range(256):
            colour, alpha = base[index & 15], index >> 4
            palette.extend(((colour >> shift) & 255) * alpha // 15 for shift in (16, 8, 0))
        image.putpalette(palette)
        out = Path(os.environ.get("BENTO_FX_CANDIDATE", CANDIDATE)) / "screens"
        out.mkdir(exist_ok=True)
        image.convert("RGB").save(out / filename)

    def open_track_fx(self):
        slot = self.call("perf_state_slot")
        self.w(self.e.r(slot) + 4, 0)
        self.u.mem_write(MODEL + 0x12c, b"\2")
        for tick, code in ((1000, 0xaf), (1100, 0xb0),
                           (1200, 0xaf), (1300, 0xb0)):
            self.w(0x3001fe2c, tick)
            self.call("fx_dispatch", MODEL, code, 0, 2)
        self.assert_page(0x1a)
        self.call(0x08145b7c, VIEW)
        self.w(POINT, 0xfffffffe)
        self.call(0x08145efc, VIEW, POINT)
        self.call("fx_header", MODEL, 0, VIEW + 0x93c4, 0, 0x08145f22)

    def fx_values(self):
        for i in range(8):
            slot = self.bar() + 0x38 + i * 0x468
            key = self.e.h(slot + 0x9c)
            if not key:
                continue
            self.call("fx_get", MODEL, POINT, key, POINT + 4)
            self.call(0x08171c1c, slot, key, self.e.r(POINT + 4), 1)

    def assert_page(self, page):
        actual = self.u.mem_read(MODEL + 0x12c, 1)[0]
        if actual != page:
            raise AssertionError(f"expected page {page:#x}, got {actual:#x}")


class Tests(unittest.TestCase):
    def transfer_keys(self, audio, ui):
        from test_chord_audition import BANK, BANK_BYTES
        ui.u.mem_write(BANK, bytes(audio.u.mem_read(BANK, BANK_BYTES)))
        ui.u.mem_write(0x24041fc0, bytes(audio.u.mem_read(0x24041fc0, 32)))

    def test_native_audio_snapshot_lights_piano_and_release_keeps_dimmed_text(self):
        from test_chord_audition import Pads, MOD
        audio, p = Pads(), Perform()
        p.types[0] = 18
        p.tap_at(45, 225)
        p.call("perf_tick")
        p.mapped()
        p.call("perf_pad", 0xac, 8)
        audio.w(MOD + 0x2cc, 100)
        audio.w(MOD + 0x2ec, 100)
        audio.mail([0, 4, 7])
        audio.press(8)
        self.transfer_keys(audio, p)
        p.call("perf_tick")
        p.paint()
        # W14 HW4: owner asked for the standard font (0) on all Perform text.
        self.assertIn(("Held notes", 0), p.labels)
        self.assertIn(("C3 E3 G3", 0), p.labels)
        self.assertIn(("C", 0), p.labels)
        self.assertEqual(p.pixels()[390, 470], 0xf7)
        self.assertEqual(p.pixels()[390, 584], 0xf7)
        self.assertEqual(p.pixels()[340, 500], 0xf1)
        p.save("perform-held.png")
        audio.release(8)
        self.transfer_keys(audio, p)
        p.labels.clear()
        p.paint(False)
        self.assertEqual(p.pixels()[390, 470], 0xf1)
        self.assertIn(("Released", 0), p.labels)
        self.assertIn(("C3 E3 G3", 0), p.labels)
        p.save("perform-released.png")
        p.fills.clear()
        p.labels.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 256, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        p.call("pg_bar_paint", p.bar(1), render.CTX)
        self.assertEqual(p.fills, [])
        self.assertEqual(p.labels, [])

    def test_piano_does_not_fold_notes_outside_the_visible_octaves(self):
        from test_chord_audition import Pads, MOD
        audio, p = Pads(), Perform()
        audio.w(MOD + 0x2cc, 100)
        audio.w(MOD + 0x2ec, 100)
        audio.u.mem_write(MOD + 0x428, struct.pack("<hh", 3, 6))
        audio.press(8)
        self.transfer_keys(audio, p)
        p.paint()
        self.assertIn(("C5", 0), p.labels)
        self.assertEqual(p.pixels()[390, 470], 0xf1)

    def test_chord_readout_recognises_actual_quality_and_inversion(self):
        p = Perform()
        words, out = POINT, POINT + 32
        for root, notes, expected in [(48, [48, 52, 55], "C"),
                                      (48, [48, 51, 55], "Cm"),
                                      (48, [52, 55, 60], "C/E"),
                                      (50, [50, 53, 57, 60], "Dm7")]:
            mask = [0] * 4
            for note in notes:
                mask[note >> 5] |= 1 << (note & 31)
            p.u.mem_write(words, struct.pack("<4I", *mask))
            self.assertEqual(p.call("perf_notes_name", root, words, out), 1)
            self.assertEqual(p.e.text(out), expected)

    def test_new_note_snapshot_requests_redraw_but_torn_data_is_not_displayed(self):
        from test_chord_audition import Pads, MOD, PUB
        audio, p = Pads(), Perform()
        audio.w(MOD + 0x2cc, 100)
        audio.w(MOD + 0x2ec, 100)
        p.paint()
        audio.press(8)
        audio.w(PUB, audio.r(PUB) | 1)
        self.transfer_keys(audio, p)
        p.paint(False)
        self.assertEqual(p.pixels()[390, 470], 0xf1)
        audio.w(PUB, audio.r(PUB) + 1)
        self.transfer_keys(audio, p)
        p.w(0x3001fe2c, 1200)
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.call("pg_perform_tick", p.bar(), render.CTX)
        self.assertEqual(bytes(p.u.mem_read(render.CTX + 1, 1)), b"\1")
        p.paint(False)
        self.assertEqual(p.pixels()[390, 470], 0xf7)
        p.selected = 1
        p.labels.clear()
        p.paint(False)
        self.assertEqual(p.pixels()[390, 470], 0xf1)
        # Only the piano's own octave label; no torn chord name or note list.
        self.assertEqual(p.labels.count(("C3", 0)), 1)

    def test_macro_names_use_standard_font_with_original_twenty_six_pixel_line_pitch(self):
        p = Perform()
        p.mapped()
        rows = []
        def capture(u, a, n, d):
            label = u.reg_read(UC_ARM_REG_R0)
            name = p.e.text(label + 0x31)
            if name in ("1 / Filter", "2 / Resonance", "3 / Pan"):
                rect = struct.unpack("<4i", u.mem_read(label + 4, 16))
                rows.append((480 - rect[1] - rect[3], rect[3],
                             bytes(u.mem_read(label + 0x55, 1))[0]))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
        try:
            p.paint()
        finally:
            p.u.hook_del(hook)
        self.assertEqual(rows, [(114, 26, 0), (140, 26, 0), (166, 26, 0)])

    def test_native_finger_changes_focus_and_single_macro_tap_arms(self):
        p = Perform()
        self.assertEqual(p.call("perf_display_state", 0) & 15, 0)
        p.tap_at(800, 275)
        self.assertEqual(p.call("perf_display_state", 0) & 1, 1)
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 1)
        self.assertEqual(p.call("macro_armed"), 0)
        p.tap_at(850, 80)
        self.assertEqual(p.call("perf_display_state", 0) & 15, 10)
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 0)
        self.assertEqual(p.call("macro_armed"), p.call("perf_macro_focus", 0xffffffff) + 1)

    def test_touch_and_arrows_share_correctly_bounded_focus_frames(self):
        p = Perform()
        for top, row in ((275, 1), (70, 0)):
            p.tap_at(800, top)
            p.fills.clear()
            p.paint()
            self.assertEqual(p.call("perf_display_state", 0) & 1, row)
            self.assertEqual(p.u.mem_read(VIEW + 0x9220 + 0x30, 1), b"\1")
            bounds = (6, 480 - (208 if row else 8) - (96 if row else 194), 1268, 2)
            self.assertTrue(any(rect == (bounds[0], bounds[1] + (94 if row else 192), bounds[2], 2)
                                and colour == 0xf2 for rect, colour in p.fills))

    def test_native_single_tap_arms_focused_macro_and_proj_disarms(self):
        p = Perform()
        p.tap_at(850, 80)
        focus = p.call("perf_macro_focus", 0xffffffff)
        self.assertEqual(p.call("macro_armed"), focus + 1)
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 1000)
        p.tap_at(850, 80)
        self.assertEqual(p.call("macro_armed"), 0)
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 1000)
        p.tap_at(850, 80)
        self.assertEqual(p.call("macro_armed"), focus + 1)
        p.call("perf_dispatch", MODEL, 0xaf, 7)
        self.assertEqual(p.call("macro_armed"), 0)

    def test_native_header_toggles_are_independent_and_do_not_change_focus(self):
        p = Perform()
        p.tap_at(50, 225)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 16)
        p.tap_at(525, 225)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 48)
        p.tap_at(800, 275)
        p.tap_at(50, 225)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 33)

    def test_drag_or_release_outside_header_never_toggles(self):
        p = Perform()
        p.finger_at(50, 225, True)
        p.finger_at(110, 225, True)
        p.finger_at(110, 225, False)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 0)
        p.finger_at(50, 225, True)
        p.finger_at(50, 320, True)
        p.finger_at(50, 320, False)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 0)

    def test_arp_latch_is_available_on_native_eighth_encoder(self):
        p = Perform()
        p.edit(0xa6, 2)
        self.assertEqual(p.call("perf_display_state", 0) & 96, 64)
        slot = p.bar(1) + 0x38 + 7 * 0x468
        self.assertEqual(p.e.h(slot + 0x9c), 0xa6)
        self.assertEqual(p.e.r(slot + 0xa0), 2)
        p.tap_at(525, 225)
        self.assertEqual(p.call("perf_display_state", 0) & 96, 0)

    def test_chord_and_arp_state_follow_selected_track(self):
        p = Perform()
        p.edit(0xa6, 2)
        p.tap_at(50, 225)
        self.assertEqual(p.call("perf_display_state", 0) & 112, 80)
        p.selected = 1
        self.assertEqual(p.call("perf_display_state", 0) & 112, 0)
        p.selected = 0
        self.assertEqual(p.call("perf_display_state", 0) & 112, 80)

    def test_native_eighth_encoder_routes_to_arp_not_macro(self):
        p = Perform()
        p.tap_at(800, 275)
        p.call(0x08171e44, p.bar(1) + 0x38 + 7 * 0x468, 160000)
        self.assertNotEqual(p.call("perf_display_state", 0) & 96, 0)
        self.assertEqual(p.call("macro_armed"), 0)

    def test_native_macro_encoder_works_after_real_bar_and_header_ticks(self):
        p = Perform()
        p.mapped()
        p.u.mem_write(render.CTX, bytes(16))
        for row in (0, 1):
            p.call("macro_bar_tick", p.bar(row), render.CTX)
        p.call("macro_periodic", POINT)
        self.assertEqual(p.call("macro_overlay"), 1)
        p.call(0x08171e44, p.bar() + 0x38, 160000)
        p.call("macro_snapshot", 0, POINT)
        self.assertEqual(p.e.r(POINT), 87) # 0 current + 65-point range, normalized within 20..85
        self.assertEqual(p.e.r(POINT + 4), 3)
        self.assertEqual(p.call("macro_armed"), 0)
        p.tap_at(800, 275)
        p.call(0x08171e44, p.bar(1) + 0x38 + 7 * 0x468, 160000)
        self.assertNotEqual(p.call("perf_display_state", 0) & 96, 0)
        p.call("macro_snapshot", 7, POINT)
        self.assertEqual(p.e.r(POINT), 64)

    def test_native_paint_uses_readable_fonts_and_keeps_unrelated_bars_native(self):
        p = Perform()
        p.mapped()
        p.paint()
        self.assertEqual(p.call("perf_bar_kind", p.bar()), 1)
        self.assertEqual(p.call("perf_bar_kind", p.bar(1)), 2)
        self.assertEqual(p.call("perf_bar_kind", p.bar(2)), 0)
        self.assertEqual(bytes(p.u.mem_read(VIEW + 0x9370 + 0x30, 1)), b"\1")
        shown = dict(p.labels)
        for name in ("1 / Filter", "2 / Resonance", "3 / Pan"):
            self.assertIn(name, shown)
            self.assertEqual(shown[name], 0)
        self.assertEqual(shown["M1"], 0)
        self.assertEqual(shown["Track 1"], 0)
        self.assertEqual(sum(name == "64" for name, font in p.labels), 8)
        p.save()
        p.tap_at(800, 275)
        p.labels.clear()
        p.paint()
        self.assertTrue({"1 / Filter", "2 / Resonance", "3 / Pan"} <= set(dict(p.labels)))

    def test_macro_editor_uses_readable_labels_and_selected_column_ground(self):
        p = Perform()
        p.mapped()
        p.u.mem_write(POINT, struct.pack("<5I", 0x1072, 0, 0, 0, 0))
        self.assertEqual(p.call("perf_navigation", POINT), 1)
        p.call("perf_dispatch", MODEL, 0xaf, 8)
        p.call("perf_dispatch", MODEL, 0xb0, 8)
        self.assertEqual(p.call("perf_macro_targets"), 1)
        p.call(0x08145b7c, VIEW)
        p.w(POINT, 0xfffffffe)
        p.call(0x08145efc, VIEW, POINT)
        p.call(0x08180198, render.ROOT)
        p.u.mem_write(POINT, render.tpl(p.e, 20))
        p.call("device_header_prepare", POINT)
        p.call(0x0817faf8, render.ROOT, POINT)
        p.paint()
        shown = dict(p.labels)
        self.assertTrue({"Filter", "Min 20%", "Max 85%", "Sensitivity", "M1"} <= shown.keys())
        self.assertNotIn("M2", shown)
        dividers = {rect[0] for rect, _ in p.fills
                    if rect[2:] == (1, 423) and rect[1] == 49}
        self.assertEqual(dividers, set())
        self.assertFalse(any(name == "Normal" or name.startswith("LIVE ")
                             for name, font in p.labels))
        self.assertTrue(any(rect == (6, 52, 159, 340) and colour == 0xa3
                            for rect, colour in p.fills))
        for name, font in p.labels:
            if name in ("1 / Filter", "2 / Resonance", "3 / Pan"):
                self.assertEqual(font, 0)
        p.save("macro-editor.png")

    def test_macro_header_exclusively_swaps_rings_and_parameter_controls(self):
        p = Perform()
        p.mapped()
        p.u.mem_write(POINT, struct.pack("<5I", 0x1072, 0, 0, 0, 0))
        p.call("perf_navigation", POINT)
        p.call(0x08145b7c, VIEW)
        p.w(POINT, 0xfffffffe)
        p.call(0x08145efc, VIEW, POINT)
        p.call(0x08180198, render.ROOT)
        p.u.mem_write(POINT, render.tpl(p.e, 20))
        p.call("device_header_prepare", POINT)
        p.call(0x0817faf8, render.ROOT, POINT)
        body = None
        # W14 HW4: a single header tap selects and arms; the body tap only selects
        # (and resets the double-tap memory), so the third tap disarms.
        for controls, armed in ((False, 1), (True, 1), (False, 0)):
            p.tap_at(80, 220 if controls else 40)
            p.labels.clear()
            p.fills.clear()
            p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
            p.call("pg_bar_paint", p.bar(), render.CTX)
            self.assertEqual(p.call("perf_macro_targets"), int(controls))
            self.assertEqual(p.call("macro_armed"), armed)
            dots = [rect for rect, colour in p.fills if rect[2:] == (2, 2)]
            if controls:
                self.assertEqual(dots, [])
                self.assertIn(("Min 20%", 0), p.labels)
            else:
                self.assertGreater(len(dots), 100)
                self.assertTrue(all(8 <= 480 - y - h and 480 - y <= 88
                                    for x, y, w, h in dots))
                self.assertNotIn(("Min 20%", 0), p.labels)
                for i in range(1, 9):
                    self.assertEqual(p.labels.count((f"M{i}", 0)), 1)
            self.assertIn(("1 / Filter", 0), p.labels)
            # Same body for rings and controls; only the armed "MAP" marker differs.
            current_body = p.pixels()[88:428].tobytes()
            if armed:
                if body is None:
                    body = current_body
                else:
                    self.assertEqual(current_body, body)
            else:
                self.assertNotEqual(current_body, body)
                self.assertNotIn(("MAP", 0), p.labels)
            render.paint(p.e, render.ROOT)
            p.save("macro-controls.png" if controls else "macro-amounts.png")

    def test_macro_controls_eighth_encoder_changes_selected_macro_amount(self):
        p = Perform()
        p.mapped()
        p.u.mem_write(POINT, struct.pack("<5I", 0x1072, 0, 0, 0, 0))
        p.call("perf_navigation", POINT)
        p.call("perf_dispatch", MODEL, 0xaf, 8)
        p.call("perf_dispatch", MODEL, 0xb0, 8)
        p.call(0x08145b7c, VIEW)
        p.w(POINT, 0xfffffffe)
        p.call(0x08145efc, VIEW, POINT)
        p.call("macro_bar_tick", p.bar(), render.CTX)
        p.call("macro_periodic", POINT)
        self.assertEqual(p.call("macro_overlay"), 1)
        p.call("perf_macro_focus", 1)
        p.call("macro_snapshot", 1, POINT)
        before = p.e.r(POINT)
        p.call(0x08171e44, p.bar() + 0x38 + 7 * 0x468, 1600)
        p.call("macro_snapshot", 1, POINT)
        self.assertEqual(p.e.r(POINT), before + 1)
        p.call("macro_snapshot", 0, POINT)
        self.assertEqual(p.e.r(POINT), 64)

    def test_track_fx_headers_touch_banks_and_custom_screen(self):
        p = Perform()
        p.open_track_fx()
        self.assertTrue(p.call("fx_screen_active"))
        self.assertEqual([p.e.h(VIEW + 0x93c4 + 0x14 + i * 2) for i in range(8)],
                         [0x1b1, 0x1b2, 0x1b3, 0x1b4, 0x1b5, 0x1b6, 0x1b7, 0x1b9])
        p.w(POINT, 800)
        p.w(POINT + 4, 380)
        self.assertEqual(p.call("fx_screen_hit", POINT, POINT + 8), 1)
        self.assertEqual(p.e.r(POINT + 8), p.bar())
        p.call("pg_fx_touch_down", p.bar(), POINT)
        p.call("pg_fx_touch_up", p.bar(), POINT)
        p.call("fx_header", MODEL, 0, VIEW + 0x93c4, 0, 0x08145f22)
        self.assertEqual([p.e.h(VIEW + 0x93c4 + 0x14 + i * 2) for i in range(8)],
                         [0x1bc, 0x1bf, 0x1c0, 0x1c1, 0x1c2, 0x1c3, 0x1c4, 0x1c5])
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), 0x1bc)
        p.fx_values()
        p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        self.assertTrue({"EQ", "Compressor", "Soft Clip"} <= set(dict(p.labels)))
        for name, font in p.labels:
            self.assertNotIn(name, {"EQ response from current settings",
                                   "Static transfer / dB", "SoftClip response",
                                   "Odd-symmetric curve", "Relative to ceiling",
                                   "TRACK FX / CHANNEL STRIP"})
            self.assertNotEqual(font, 3)
        p.w(POINT, 1150)
        p.w(POINT + 4, 480 - 240)
        self.assertEqual(p.call("fx_screen_hit", POINT, POINT + 8), 1)
        p.call("pg_fx_touch_down", p.bar(), POINT)
        p.call("pg_fx_touch_up", p.bar(), POINT)
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), 0x1c6)
        p.u.mem_write(POINT, struct.pack("<5I", 0x1077, 0, 0, 0, 0))
        self.assertEqual(p.call("fx_event", VIEW, POINT), 1)
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), 0x1b1)
        p.fx_values()
        out = POINT + 0x400
        p.u.mem_write(out, render.tpl(p.e, 20))
        p.call("device_header_prepare", out)
        self.assertEqual([p.e.h(out + 0x74 + i * 48 + 44) for i in (1, 2, 3)],
                         [0x1077, 0x1078, 0x1079])
        self.assertEqual(p.e.text(out), "Track 1")
        def track_name(u, a, n, data):
            u.mem_write(u.reg_read(UC_ARM_REG_R3), b"Drum Kit\0")
            p.ret(1)
        name_hook = p.u.hook_add(UC_HOOK_CODE, track_name, begin=0x0813390e, end=0x0813390e)
        try:
            p.call("device_header_prepare", out)
            self.assertEqual(p.e.text(out), "Drum Kit")
            p.call(0x0817faf8, render.ROOT, out)
        finally:
            p.u.hook_del(name_hook)
        p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        render.paint(p.e, render.ROOT)
        self.assertIn(("Drum Kit", 0), p.labels)
        p.save("track-fx.png")
        p.call(0x0816fb64, VIEW, render.ROOT)
        for x, key in ((560, 0x1bc), (720, 0x1c6), (400, 0x1b1)):
            p.tap_at(x, 452)
            self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), key)
        p.tap_at(800, 240)
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), 0x1bc)

    def test_macro_header_and_body_taps_change_real_encoder_mode(self):
        p = Perform()
        p.mapped()
        p.u.mem_write(POINT, struct.pack("<5I", 0x1072, 0, 0, 0, 0))
        p.call("perf_navigation", POINT)
        p.call(0x08145b7c, VIEW)
        p.w(POINT, 0xfffffffe)
        p.call(0x08145efc, VIEW, POINT)
        p.tap_at(80, 220)
        self.assertEqual(p.call("perf_macro_targets"), 1)
        self.assertEqual(p.call("perf_macro_focus", 0xffffffff), 0)
        p.call("macro_bar_tick", p.bar(), render.CTX)
        p.call("macro_periodic", POINT)
        p.call(0x08171e44, p.bar() + 0x38, 8000)
        p.call("macro_snapshot", 0, POINT)
        self.assertGreater(p.e.r(POINT + 20 + 12), 20)
        p.tap_at(250, 40)
        self.assertEqual(p.call("perf_macro_targets"), 0)
        p.tap_at(250, 240)
        self.assertEqual(p.call("perf_macro_targets"), 1)
        self.assertEqual(p.call("perf_macro_focus", 0xffffffff), 1)

    def test_settled_partial_paints_do_not_repeat_native_fills_or_labels(self):
        p = Perform()
        p.paint()
        p.fills.clear()
        p.labels.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 256, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        p.call("pg_bar_paint", p.bar(1), render.CTX)
        self.assertEqual(p.fills, [])
        self.assertEqual(p.labels, [])

    def test_snapshot_polling_is_throttled_and_does_not_allocate_or_redraw_when_settled(self):
        p = Perform()
        p.mapped()
        p.paint()
        cursor = p.e.r(0x3000004c)
        for tick in (1100, 1101, 1200, 1300):
            p.w(0x3001fe2c, tick)
            p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
            p.call("pg_perform_tick", p.bar(), render.CTX)
            self.assertEqual(bytes(p.u.mem_read(render.CTX, 2)), b"\0\0")
            self.assertEqual(p.e.r(0x3000004c), cursor)

    def test_native_set_time_and_palette_are_unchanged(self):
        from test_integration import IMAGE
        source = os.environ.get("BENTO_PERFORM_W6")
        if not source:
            self.skipTest("Set BENTO_PERFORM_W6 to the source-matched W6 application")
        original = Path(source).read_bytes()
        palette = json.loads((CANDIDATE / "PALETTE_MANIFEST.json").read_text())
        spans = [(0x08145e74, 112)] + [(item["address"], item["size"]) for item in palette["writes"]]
        for address, size in spans:
            offset = address - 0x08040000
            self.assertEqual(IMAGE[offset:offset + size], original[offset:offset + size])

    def test_piano_telemetry_keeps_intercore_and_vectors_identical_to_w6(self):
        from test_integration import IMAGE
        source = os.environ.get("BENTO_PERFORM_W6")
        if not source:
            self.skipTest("Set BENTO_PERFORM_W6 to the source-matched W6 application")
        original = Path(source).read_bytes()
        for lo, hi in [(0, 0x400), (0xa0000, 0xc0000), (0xc0000, 0xc0400)]:
            self.assertEqual(IMAGE[lo:hi], original[lo:hi])


if __name__ == "__main__":
    unittest.main(verbosity=2)
