"""Perform's real native widgets, fonts, touch dispatcher and cached painting."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import os
import json
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R3

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
        self.w(0x30035f40, 1000)
        self.rows = 3
        self.call("perf_dispatch", MODEL, 0xaf, 7)
        self.call("perf_dispatch", MODEL, 0xb0, 7)
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
        for row in range(self.rows):
            for i in range(8):
                slot = self.bar(row) + 0x38 + i * 0x468
                key = self.e.h(slot + 0x9c)
                if key:
                    self.call("perf_get", MODEL, POINT, key, POINT + 4)
                    self.call(0x08171c1c, slot, key, self.e.r(POINT + 4), 1)

    def open_chord_arp(self):
        self.assert_page(0x1a)
        self.values()

    def select_project_view(self, action):
        self.u.mem_write(POINT, struct.pack("<5I", action, 0, 0, 0, 0))
        self.call("perf_navigation", POINT)
        self.w(POINT, 0xfffffffe)
        self.call(0x08145efc, VIEW, POINT)
        self.rows = self.e.r(VIEW + 0x9018 + 0x204)
        self.values()

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
        self.w(0x30035f40, self.e.r(0x30035f40) + 16)
        self.u.mem_write(POINT, render.tpl(self.e, 20))
        # Live snapshots supply the title colour; the flash template leaves it zero.
        self.u.mem_write(POINT + N.HDR(0x68), b"\xf2")
        self.call(0x0817faf8, render.ROOT, POINT)
        self.u.mem_write(render.CTX, struct.pack("<II", 257 if full else 256, render.SURF))
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


class NativeClockOwnership(unittest.TestCase):
    """Existing-image ownership probe, not validation of edited source."""

    def test_native_rtc_child_visibility_removes_only_clipped_date_pixels(self):
        captures = []
        for hidden in (False, True):
            p = Perform()
            clock = VIEW + 0x9558
            self.assertEqual(p.e.r(clock), 0x081b35c0)
            self.assertEqual([p.e.r(clock + i) for i in (4, 8, 12, 16)],
                             [799, 50, 477, 26])
            def rtc(u, address, size, data):
                u.mem_write(u.reg_read(UC_ARM_REG_R1),
                            struct.pack("<6BH", 12, 34, 56, 11, 5, 0, 2026))
                p.ret(1)
            hook = p.u.hook_add(UC_HOOK_CODE, rtc, begin=0x0810709c, end=0x0810709c)
            try:
                p.w(0x30035f40, p.e.r(0x30035f40) + 1500)
                p.call(0x08146170, VIEW, POINT)
            finally:
                p.u.hook_del(hook)
            self.assertEqual(p.e.text(clock + 0x31), "Thu 2026-11-05 12:34:56")
            # Isolate native hidden-child semantics on either old or new images.
            p.u.mem_write(clock + 0x30, bytes([hidden]))
            render.clear(p.e, 0xf1)
            p.paint()
            captures.append(p.pixels().copy())
        y, x = (captures[0] != captures[1]).nonzero()
        self.assertGreater(len(x), 0)
        self.assertGreaterEqual(int(x.min()), 799)
        self.assertLess(int(x.max()), 1276)
        self.assertGreaterEqual(int(y.min()), 404)
        self.assertLess(int(y.max()), 430)


def rebuild_view(p):
    """What the native navigation does for page 1A: a new GenericProperties view (constructor 08145B7C on
    cleared memory, setup 08145EFC asking our header hook), registered with the manager, and the footer
    snapshot through the model hooks (device_header_prepare) applied by the native root (0817FAF8)."""
    p.u.mem_write(VIEW, bytes(0xa000))
    p.call(0x08145b7c, VIEW); p.w(POINT, 0xfffffffe); p.call(0x08145efc, VIEW, POINT)
    p.call(0x0816fb64, MANAGER + 0x470, VIEW); p.w(MANAGER + 0x470 + 0x3c, VIEW)
    p.u.mem_write(POINT, render.tpl(p.e, 20)); p.call("device_header_prepare", POINT); p.call(0x0817faf8, render.ROOT, POINT)
    p.values()


def screen(p):
    render.clear(p.e, 0xf1); p.paint()
    footer = [(p.e.h(render.ROOT + 0x34 + N.HDR(0x74) + i * 48 + 44),
               bytes(p.u.mem_read(render.ROOT + 0x34 + N.HDR(0x74) + i * 48, 32)).split(b"\0")[0]) for i in range(6)]
    return p.pixels().copy(), footer


class ProjCycle(unittest.TestCase):
    """P168 exp5 (owner, 12 Nov): PROJ cycles Perform -> Macro -> Settings -> Projects -> Perform. The views
    replace the whole screen; a view reached from another one must look exactly like the same view opened
    on its own (pixels of the native paint and the footer records). The native project browser view itself
    is not built by this fixture (page 13 is a navigation stub): for Projects the footer and our state are
    compared, and leaving Projects must give the target view unchanged."""
    VIEWS = {0x1071: "Perform", 0x1072: "Macro", 0x1074: "Settings", 0x1075: "Projects"}

    def shot(self, actions):
        p = Perform()
        for a in actions:
            p.select_project_view(a); rebuild_view(p)
        return screen(p)

    def test_every_view_switch_both_ways_leaves_no_bleed(self):
        fresh = {v: self.shot([v]) for v in self.VIEWS}
        self.assertGreater(int((fresh[0x1071][0] != fresh[0x1072][0]).sum()), 0)   # the views do differ
        self.assertGreater(int((fresh[0x1071][0] != fresh[0x1074][0]).sum()), 0)
        for a in self.VIEWS:
            for b in self.VIEWS:
                if a != b:
                    with self.subTest(frm=self.VIEWS[a], to=self.VIEWS[b]):
                        pixels, footer = self.shot([a, b])
                        self.assertEqual(footer, fresh[b][1])
                        self.assertEqual(int((pixels != fresh[b][0]).sum()), 0)

    def test_proj_presses_cycle_the_four_views(self):
        p = Perform()   # its constructor pressed PROJ once: Perform
        fresh = {v: self.shot([v]) for v in self.VIEWS}
        self.assertEqual(p.navs[-1], 0x1a)
        tick = p.e.r(0x3001fe2c)
        for want, page in ((0x1072, 0x1a), (0x1074, 0x1a), (0x1075, 0x13), (0x1071, 0x1a), (0x1072, 0x1a)):
            with self.subTest(view=self.VIEWS[want]):
                tick += 1000; p.w(0x3001fe2c, tick); p.call("perf_dispatch", MODEL, 0xaf, 7)
                p.w(0x3001fe2c, tick + 60); p.call("perf_dispatch", MODEL, 0xb0, 7)
                self.assertEqual(p.navs[-1], page)
                rebuild_view(p); pixels, footer = screen(p)
                self.assertEqual(footer, fresh[want][1])
                self.assertEqual(int((pixels != fresh[want][0]).sum()), 0)

    def test_one_footer_on_all_four_views_and_the_label_as_plain_footer_text(self):
        # exp6 (owner, exp5 photos): Perform | Macro | Settings | Projects always in slots 0..3, the current one
        # lit; the view's own actions beside them (exp7, owner 12 Nov: Settings has NO Motion, slot 5 empty); the firmware label is plain text on the LEFT OF THE SETTINGS
        # FOOTER (the footer title text, no button) and no view shows the old label record 1073.
        from test_integration import IMAGE
        at = struct.unpack_from("<I", IMAGE, 0x08162ad8 - 0x08040000)[0]
        label = IMAGE[at - 0x08040000:IMAGE.index(b"\0", at - 0x08040000)]
        self.assertTrue(label.startswith((b"P168", b"R6.")), label)
        tabs = [(0x1071, b"Perform"), (0x1072, b"Macro"), (0x1074, b"Settings"), (0x1075, b"Projects")]
        # Run 18 (native_perform.png): Perform shows Tap (1073) beside Motion and the build label on its left too.
        actions = {0x1071: [(0x1073, b"Tap"), (0x1076, b"Motion")], 0x1072: [(0, b""), (0x1076, b"Motion")],
                   0x1074: [(0x36, b"Set Time"), (0, b"")], 0x1075: [(0x8f, b"Save"), (0x8b, b"Load")]}
        for v in self.VIEWS:
            with self.subTest(view=self.VIEWS[v]):
                self.assertEqual(self.shot([v])[1], tabs + actions[v])
                p = Perform(); p.select_project_view(v); rebuild_view(p)
                footer_title = bytes(p.u.mem_read(render.ROOT + 0x34, 32)).split(b"\0")[0]
                if v in (0x1074, 0x1071):
                    self.assertEqual(footer_title, label[:31])
                else:
                    self.assertNotEqual(footer_title, label[:31])
        p = Perform(); p.select_project_view(0x1074); rebuild_view(p)
        title = p.e.r(VIEW + 0x93c4 + 4)
        self.assertEqual(bytes(p.u.mem_read(title, 64)).split(b"\0")[0], b"Global Settings")

    def test_settings_clean_text_is_native_size_and_switches_are_style_a(self):
        """Run 16 (OWNER RULE 13 Nov, design/native/native_settings_drum.png, design/switch_styles.png): the shared
        SectionGroup Clean look draws section titles and cell names at the native 24 px (font 0, never font 3), dim
        grey (F6); a two-state cell shows switch style A instead of On/Off: 1 px outline pill 45x21, 13 px knob, Off =
        grey (A6) with the knob left, On = white (F2) with the knob right, no fill."""
        p = Perform(); p.select_project_view(0x1074); rebuild_view(p)
        p.u.mem_write(render.CTX, struct.pack("<II", 0x101, render.SURF))
        p.e.call(p.e.r(p.e.r(VIEW)), VIEW, render.CTX)          # the view tick restyles the labels (as on the device)
        p.labels.clear()
        pixels = screen(p)[0]
        fonts = dict(p.labels)
        for word in ("Global Settings", "Date and Time", "Brightness", "Sleep", "MIDI Type", "Year", "Fixed Vel", "Velocity"):
            self.assertEqual(fonts.get(word), 0, word)
        self.assertNotIn("GLOBAL SETTINGS", fonts)
        title = pixels[18:42, 10:170]
        self.assertGreater(int((title == 0xf6).sum()), 100)        # dim title, mixed case, native size
        self.assertEqual(int((title == 0xf2).sum()), 0)
        cell = pixels[82:118, 340:470]                            # Sleep: Off
        ys, xs = (cell != 0xf1).nonzero()
        self.assertEqual((int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)), (21, 45))
        self.assertEqual(int((cell == 0xf2).sum()), 0)
        grey = (cell == 0xa6).nonzero()[1]
        knob = cell[ys.min() + 10, xs.min():xs.max() + 1] == 0xa6
        self.assertTrue(knob[5:18].all() and not knob[22:40].any())  # knob left, hollow pill (no fill)
        self.assertEqual(len(grey), int((cell != 0xf1).sum()))
        render.clear(p.e, 0xf1)
        p.call("pg_switch", render.SURF, 600, 200, 1)
        on = p.pixels()[190:230, 590:660]
        ys, xs = (on != 0xf1).nonzero()
        self.assertEqual((int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)), (21, 45))
        self.assertTrue((on[ys.min():ys.max() + 1, xs.min():xs.max() + 1][(on[ys.min():ys.max() + 1, xs.min():xs.max() + 1] != 0xf1)] == 0xf2).all())
        row = on[ys.min() + 10, xs.min():xs.max() + 1] == 0xf2
        self.assertTrue(row[27:40].all() and not row[5:20].any())   # knob right

    def test_proj_tabs_have_no_divider_lines_and_other_tabs_keep_them(self):
        """exp6 (owner, exp5 photo: stray dividers before Perform and between Perform and Macro in the Settings
        footer). The native tab paint draws a two-pixel left divider when the widget's +CE flag is set (the
        constructor sets it on every tab). On all four PROJ views the four tabs are drawn without it: the
        pixel columns of the tab edges show no divider (fails on exp5/the first exp6 build). Leaving the PROJ
        views (perf_nav) gives every tab the native flag back."""
        for v in self.VIEWS:
            with self.subTest(view=self.VIEWS[v]):
                p = Perform(); p.select_project_view(v); rebuild_view(p)
                pixels = screen(p)[0]
                for slot in range(4):
                    tab = render.ROOT + N.ROOT_TABS + slot * 0xd0
                    self.assertEqual(p.u.mem_read(tab + 0xce, 1), b"\0")
                    x = p.e.h(tab + 4)
                    if p.u.mem_read(tab + 0xac, 1) == b"\0":   # an unselected tab: its left edge is background
                        self.assertEqual(int((pixels[440:470, x:x + 2] != pixels[440, x + 6]).sum()), 0)
        # another page: native tab records (Steps / Seq / Auto ids) in slots 0..3 get the divider again
        p.call("perf_nav", 0x17)
        out = POINT + 0x100
        p.u.mem_write(out, bytes(p.u.mem_read(render.ROOT + 0x34, N.HDR_SIZE)))
        for slot, ident in enumerate((0x49, 0x4a, 0x4b, 0x4b)):
            p.u.mem_write(out + N.HDR(0x74) + slot * 48 + 44, struct.pack("<H", ident))
        p.call("header_sync", out)
        for slot in range(4):
            self.assertEqual(p.u.mem_read(render.ROOT + N.ROOT_TABS + slot * 0xd0 + 0xce, 1), b"\1")


class Tests(unittest.TestCase):
    def test_project_footer_right_edge_and_clock_visibility_follow_real_views(self):
        # exp6: the four view tabs fill slots 0..3 (current lit), Motion is the rightmost action (slot 5); run 18:
        # Perform has Tap in slot 4, on Macro slot 4 stays empty; clock visibility follows the views as before.
        p = Perform()
        for action, active in ((0x1071, 0), (0x1072, 1), (0x1071, 0)):
            p.select_project_view(action)
            p.paint()
            self.assertEqual(p.u.mem_read(VIEW + 0x9558 + 0x30, 1), b"\1")
            tap = action == 0x1071
            for slot, ident in ((0, 0x1071), (1, 0x1072), (2, 0x1074), (3, 0x1075), (4, 0x1073), (5, 0x1076)):
                record = render.ROOT + 0x34 + N.HDR(0x74) + slot * 48
                if slot == 4 and not tap:
                    self.assertEqual(p.e.h(record + 44), 0)
                    continue
                self.assertEqual(p.e.h(record + 44), ident)
                tab = slot < 4
                button = render.ROOT + (N.ROOT_TABS if tab else N.ROOT_SLOTS) + slot * 0xd0
                self.assertEqual(p.u.mem_read(button + 0x30, 1), b"\0")
                if tab:
                    self.assertEqual(p.u.mem_read(button + 0xac, 1), bytes([int(slot == active)]))
            if not tap:
                for base in (N.ROOT_SLOTS, N.ROOT_TABS):
                    self.assertEqual(p.u.mem_read(render.ROOT + base + 4 * 0xd0 + 0x30, 1), b"\1")
        p.select_project_view(0x1074)
        self.assertEqual(p.u.mem_read(VIEW + 0x9558 + 0x30, 1), b"\0")

    def transfer_keys(self, audio, ui):
        from test_chord_audition import BANK, BANK_BYTES
        ui.u.mem_write(BANK, bytes(audio.u.mem_read(BANK, BANK_BYTES)))
        ui.u.mem_write(0x24041fc0, bytes(audio.u.mem_read(0x24041fc0, 32)))

    def test_native_audio_snapshot_names_chord_on_the_page_and_dims_it_on_release(self):
        # Run 18 (native_perform.png): the played chord's name is drawn big (font 2) in the track colour on the
        # Perform page with its notes and the piano keys; after the release it stays, dimmed. The footer keeps
        # the build label (no chord name there any more).
        from test_chord_audition import Pads, MOD
        audio, p = Pads(), Perform()
        p.types[0] = 18
        p.edit(0x104, 1)
        p.call("perf_tick")
        p.mapped()
        p.call("perf_pad", 0xac, 8)
        audio.w(MOD + N.PADMOD(0x2cc), 100)
        audio.w(MOD + N.PADMOD(0x2ec), 100)
        audio.mail([0, 4, 7])
        audio.press(8)
        self.transfer_keys(audio, p)
        p.call("perf_tick")
        p.labels.clear()
        p.paint()
        self.assertNotEqual(p.e.text(render.ROOT+0x34), "C")
        self.assertIn(("C", 2), p.labels)
        self.assertIn(("C3 E3 G3", 0), p.labels)
        colour = p.call(0x08140ebc, 0)
        keys = p.pixels()[46:177, 400:1212]
        self.assertGreater(int((keys == colour).sum()), 3 * 40 * 40)  # three white keys lit in the track colour
        p.save("perform-held.png")
        audio.release(8)
        self.transfer_keys(audio, p)
        p.labels.clear()
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 100)
        p.paint(False)
        self.assertIn(("C", 2), p.labels)
        self.assertEqual(int((p.pixels()[46:177, 400:1212] == colour).sum()), 0)  # dimmed, not the live colour
        self.assertGreater(int((p.pixels()[46:177, 400:1212] == ((colour & 15) | 0x70)).sum()), 3 * 40 * 40)
        p.save("perform-released.png")
        p.fills.clear()
        p.labels.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 256, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        self.assertEqual(p.fills, [])
        self.assertEqual(p.labels, [])

    def test_page_shows_a_single_played_note_and_no_chord_name_without_chord(self):
        # Run 18: the page shows what the keyboard plays; with Chord off one pad is one note (its name, never a
        # chord name), and nothing reaches the footer label.
        from test_chord_audition import Pads, MOD
        audio, p = Pads(), Perform()
        audio.w(MOD + N.PADMOD(0x2cc), 100)
        audio.w(MOD + N.PADMOD(0x2ec), 100)
        audio.u.mem_write(MOD + N.PADMOD(0x428), struct.pack("<hh", 3, 6))
        audio.press(8)
        self.transfer_keys(audio, p)
        p.labels.clear()
        p.paint()
        self.assertNotEqual(p.e.text(render.ROOT+0x34), "C")
        self.assertNotIn(("C", 2), p.labels)
        self.assertFalse([t for t, f in p.labels if f == 2 and t not in ("--",) and " " in t])

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

    def test_torn_note_snapshot_and_track_change_do_not_publish_stale_chord(self):
        from test_chord_audition import Pads, MOD, PUB
        audio, p = Pads(), Perform()
        audio.w(MOD + N.PADMOD(0x2cc), 100)
        audio.w(MOD + N.PADMOD(0x2ec), 100)
        audio.mail([0, 4, 7])
        p.types[0] = 18
        p.edit(0x104, 1)
        p.paint()
        audio.press(8)
        audio.w(PUB, audio.r(PUB) | 1)
        self.transfer_keys(audio, p)
        p.labels.clear()
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 100)
        p.paint(False)
        self.assertNotIn(("C", 2), p.labels)  # run 18: the name is on the page (font 2), not in the footer
        audio.w(PUB, audio.r(PUB) + 1)
        self.transfer_keys(audio, p)
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 100)
        p.paint(False)
        self.assertIn(("C", 2), p.labels)
        p.selected = 1
        p.labels.clear()
        p.w(0x3001fe2c, p.e.r(0x3001fe2c) + 100)
        p.paint(False)
        self.assertNotIn(("C", 2), p.labels)
        self.assertNotIn(("C3 E3 G3", 0), p.labels)

    def test_perform_has_no_macro_row_and_macros_stay_on_the_macro_tab(self):
        # Run 18 (owner, 13 Nov): no macro row on Perform; the macro rings and targets stay on the Macro tab.
        p = Perform()
        p.mapped()
        p.paint()
        names = {name for name, font in p.labels}
        self.assertFalse({f"M{i}" for i in range(1, 9)} & names)
        self.assertFalse({"1 / Filter", "2 / Resonance", "3 / Pan"} & names)
        self.assertIn(("Chord", 0), p.labels)
        self.assertIn(("Arp", 0), p.labels)
        self.assertEqual(p.call("perf_macro_view"), 0)
        p.select_project_view(0x1072)
        self.assertEqual(p.call("perf_macro_view"), 1)

    def test_track_strip_taps_and_left_right_select_tracks_and_row_taps_set_focus(self):
        # Run 18: the Chord row is active first; a tap on a row makes it active; a tap on the track strip or
        # Left/Right select the track (native model event 37, as the Tracks view posts it, no wrap); a tap in
        # the chord name / piano area changes nothing and never arms a macro.
        p = Perform()
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 1)
        p.tap_at(800, 330)
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 2)
        p.tap_at(800, 220)
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 1)
        p.events.clear()
        p.tap_at(850, 80)
        self.assertEqual(p.e.r(VIEW + 0x9018 + 0x39c), 1)
        self.assertEqual(p.call("macro_armed"), 0)
        self.assertEqual([e for e in p.events if e[0] == 0x37], [])
        p.tap_at(3 * 160 + 80, 15)
        self.assertEqual(p.selected, 3)
        for button, want in ((9, 4), (9, 5), (0, 4)):
            self.assertEqual(p.call("perf_dispatch", MODEL, 0xaf, button), 1)
            self.assertEqual(p.call("perf_dispatch", MODEL, 0xb0, button), 1)
            self.assertEqual(p.selected, want)
        p.tap_at(7 * 160 + 80, 15)
        p.call("perf_dispatch", MODEL, 0xaf, 9); p.call("perf_dispatch", MODEL, 0xb0, 9)
        self.assertEqual(p.selected, 7)
        p.tap_at(80, 15)
        p.call("perf_dispatch", MODEL, 0xaf, 0); p.call("perf_dispatch", MODEL, 0xb0, 0)
        self.assertEqual(p.selected, 0)
        self.assertEqual([e for e in p.events if e[0] == 0x37], [(0x37, 0, t, 0, 0) for t in (3, 4, 5, 4, 7, 0)])

    def test_touch_and_arrows_share_correctly_bounded_focus_frames(self):
        # Run 18: the Chord row (top 206) and the Arp row (top 314), 89 px; the thin frame A (our drawing, colour
        # A6) on the active row only; the native box stays hidden at the same rectangle.
        p = Perform()
        p.open_chord_arp()
        for top, row in ((220, 1), (360, 2), (70, 2), (250, 1)):
            p.tap_at(800, top)
            p.fills.clear()
            p.paint()
            self.assertEqual(p.e.r(VIEW+0x9018+0x39c), row)
            self.assertEqual(p.u.mem_read(VIEW + 0x9220 + 0x30, 1), b"\1")
            box = VIEW + 0x9220
            self.assertEqual(struct.unpack("<4i",p.u.mem_read(box+4,16)), (4,185-(row-1)*108,1272,89))
            pixels = p.pixels()
            on, off = (206, 314) if row == 1 else (314, 206)
            self.assertTrue((pixels[on, 4:1276] == 0xa6).all())
            self.assertFalse((pixels[off, 4:1276] == 0xa6).any())
        for button, row in ((8, 2), (8, 2), (1, 1), (1, 1)):
            p.call("perf_dispatch", MODEL, 0xaf, button)
            p.call("perf_dispatch", MODEL, 0xb0, button)
            self.assertEqual(p.e.r(VIEW+0x9018+0x39c), row)

    def test_native_single_tap_arms_focused_macro_and_proj_disarms(self):
        # Run 18: macros are armed on the Macro tab (no macro row on Perform any more).
        p = Perform()
        p.tap_at(850, 80)
        self.assertEqual(p.call("macro_armed"), 0)
        p.select_project_view(0x1072)
        p.tap_at(850, 40)
        focus = p.call("perf_macro_focus", 0xffffffff)
        self.assertEqual(p.call("macro_armed"), focus + 1)
        p.call("perf_dispatch", MODEL, 0xaf, 7)
        self.assertEqual(p.call("macro_armed"), 0)

    def test_main_screen_track_strip_key_piano_and_chord_arp_rows(self):
        # Run 18 (native_perform.png): track names on top (selected bold with a bar under it), the project key,
        # a two-octave piano 130 px high from x 400, then the Chord and Arp rows with 8 native-size cells each
        # (Chord: Chord, Type, Voicing, Inversion, -, Velocity, Fixed Vel, -; Arp: Arp, Mode, Rate, Octaves, Gate,
        # Ratchet, Swing, BPM); Chord/Fixed Vel/Arp Off-On as switches without text. Stable across frames.
        p=Perform()
        p.open_chord_arp()
        render.clear(p.e)
        p.labels.clear()
        p.paint()
        names={name for name,font in p.labels}
        self.assertTrue({"Chord","Type","Voicing","Inversion","Velocity","Fixed Vel","Arp","Mode","Rate","Octaves","Gate","Ratchet","Swing","BPM"}<=names,names)
        self.assertFalse({"Arp Mode","Off","On"}&names)
        self.assertFalse({f"M{i}" for i in range(1,9)}&names)
        self.assertTrue(any(n.startswith("Key ") for n in names))
        self.assertEqual(p.e.r(VIEW+0x9018+0x204), 3)
        px=p.pixels()
        self.assertTrue((px[126:150, 400:455] == 0xf3).all())  # first white key below the black keys, idle (its C label below)
        self.assertTrue((px[50:120, 442:474] == 0x12).all())   # first black key
        self.assertEqual(int((px[206, 4:1276] == 0xa6).sum()), 1272)  # Chord row framed
        for top in (206, 314):
            self.assertGreater(int((px[top+6:top+34, 20:1260] != 0xf1).sum()), 500)  # labels
            self.assertGreater(int((px[top+36:top+66, 20:1260] != 0xf1).sum()), 300)  # values/switches
        regions = [(0, 200), (206, 296), (314, 404), (438, 468)]
        shots = [px[lo:hi].tobytes() for lo, hi in regions]
        for frame in range(3):
            p.w(0x30035f40, 1100 + 100 * frame)
            p.paint()
            self.assertEqual([p.pixels()[lo:hi].tobytes() for lo, hi in regions], shots)
        p.save("perform-rows.png")

    def test_chord_and_arp_controls_are_separate_native_banks(self):
        p = Perform()
        p.types[0] = 18
        p.open_chord_arp()
        p.edit(0x104, 1)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 17)  # run 18: bit 0 = a row is active (always on Perform)
        p.edit(0xa6, 1)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 49)
        p.tap_at(800, 360)
        p.edit(0x104, 0)
        self.assertEqual(p.call("perf_display_state", 0) & 113, 33)
        self.assertEqual((p.call("perf_display_state", 0) >> 16) & 3, 2)

    def test_drag_or_release_outside_header_never_toggles(self):
        p = Perform()
        p.finger_at(50, 225, True)
        p.finger_at(110, 225, True)
        p.finger_at(110, 225, False)
        self.assertEqual(p.call("perf_display_state", 0) & 112, 0)
        self.assertEqual((p.call("perf_display_state", 0) >> 16) & 3, 1)
        p.finger_at(50, 225, True)
        p.finger_at(50, 330, True)
        p.finger_at(50, 330, False)
        self.assertEqual(p.call("perf_display_state", 0) & 112, 0)
        self.assertEqual((p.call("perf_display_state", 0) >> 16) & 3, 1)  # a drag selects no row
        p.events.clear()
        p.finger_at(250, 15, True)
        p.finger_at(250, 120, True)
        p.finger_at(250, 120, False)
        self.assertEqual(p.selected, 0)  # nor a track

    def test_arp_latch_is_available_on_first_encoder_of_arp_bank(self):
        p = Perform()
        p.types[0] = 18
        p.open_chord_arp()
        p.edit(0xa6, 2)
        self.assertEqual(p.call("perf_display_state", 0) & 96, 64)
        slot = p.bar(2) + 0x38
        self.assertEqual(p.e.h(slot + 0x9c), 0xa6)
        self.assertEqual(p.e.r(slot + 0xa0), 2)
        p.edit(0xa6, 0)
        self.assertEqual(p.call("perf_display_state", 0) & 96, 0)

    def test_chord_and_arp_state_follow_selected_track(self):
        p = Perform()
        p.types[0] = 18
        p.open_chord_arp()
        p.edit(0xa6, 2)
        p.edit(0x104, 1)
        self.assertEqual(p.call("perf_display_state", 0) & 112, 80)
        p.selected = 1
        self.assertEqual(p.call("perf_display_state", 0) & 112, 0)
        p.selected = 0
        self.assertEqual(p.call("perf_display_state", 0) & 112, 80)

    def test_native_arp_bank_encoder_routes_to_arp_not_macro(self):
        p = Perform()
        p.types[0] = 18
        p.open_chord_arp()
        p.w(0x3001fe2c, p.e.r(0x3001fe2c)+1000)
        for row in (2, 1, 0, 1, 2):
            p.call("macro_bar_tick", p.bar(row), render.CTX)
        p.call("macro_periodic", POINT)
        p.tap_at(800, 360)
        p.call(0x08171e44, p.bar(2) + 0x38, 160000)
        self.assertNotEqual(p.call("perf_display_state", 0) & 96, 0)
        self.assertEqual(p.call("macro_armed"), 0)

    def test_native_macro_encoder_works_after_real_bar_and_header_ticks(self):
        # Run 18: the macro overlay runs on the Macro tab (not on Perform any more); on Perform the Arp row's
        # encoder changes the arp and leaves the macros alone.
        p = Perform()
        p.mapped()
        p.u.mem_write(render.CTX, bytes(16))
        p.call("macro_bar_tick", p.bar(), render.CTX)
        p.call("macro_periodic", POINT)
        self.assertEqual(p.call("macro_overlay"), 0)
        p.select_project_view(0x1072)
        p.call("macro_bar_tick", p.bar(), render.CTX)
        p.call("macro_periodic", POINT)
        self.assertEqual(p.call("macro_overlay"), 1)
        # exp3: macros follow the native acceleration (sum of turns / ms in the
        # slot history). This fixture means one slow sweep: native factor 1.
        p.e.w(0x30035f40, 1000000)
        p.call(0x08171e44, p.bar() + 0x38, 160000)
        p.call("macro_snapshot", 0, POINT)
        self.assertEqual(p.e.r(POINT), 87) # 0 current + 65-point range, normalized within 20..85
        self.assertEqual(p.e.r(POINT + 4), 3)
        self.assertEqual(p.call("macro_armed"), 0)
        p.select_project_view(0x1071)
        p.call("macro_periodic", POINT)
        self.assertEqual(p.call("macro_overlay"), 0)
        p.types[0] = 18
        p.open_chord_arp()
        p.tap_at(800, 360)
        p.call(0x08171e44, p.bar(2) + 0x38, 160000)
        self.assertNotEqual(p.call("perf_display_state", 0) & 96, 0)
        p.call("macro_snapshot", 7, POINT)
        self.assertEqual(p.e.r(POINT), 64)

    def test_native_paint_uses_readable_fonts_and_keeps_unrelated_bars_native(self):
        # Run 18 (OWNER RULE: no normal text below the native 24 px): cells, key line and notes in font 0, the
        # chord name in the big native font 2; only the piano's C labels use the small font (as the reference).
        p = Perform()
        p.mapped()
        p.paint()
        self.assertEqual(p.call("perf_bar_kind", p.bar()), 1)
        self.assertEqual(p.call("perf_bar_kind", p.bar(1)), 4)
        self.assertEqual(p.call("perf_bar_kind", p.bar(2)), 5)
        self.assertEqual(bytes(p.u.mem_read(VIEW + 0x9370 + 0x30, 1)), b"\1")
        shown = dict(p.labels)
        for name in ("1 / Filter", "2 / Resonance", "3 / Pan", "M1"):
            self.assertNotIn(name, shown)
        for name in ("Chord", "Arp", "Type", "Rate", "BPM"):
            self.assertEqual(shown[name], 0)
        self.assertEqual(shown["--"], 2)
        small = {name for name, font in p.labels if font == 3} - {"  0%"}  # the native battery readout
        self.assertEqual(small, {"C4", "C5"})
        p.save()
        p.tap_at(800, 275)
        p.labels.clear()
        p.paint()
        self.assertIn("Chord", dict(p.labels))

    def test_mapping_readout_keeps_priority_over_played_chord(self):
        from test_chord_audition import Pads, MOD
        audio, p = Pads(), Perform()
        p.types[0] = 18
        p.edit(0x104, 1)
        audio.w(MOD+N.PADMOD(0x2cc), 100)
        audio.w(MOD+N.PADMOD(0x2ec), 100)
        audio.mail([0, 4, 7])
        audio.press(8)
        self.transfer_keys(audio, p)
        p.labels.clear()
        p.paint()
        self.assertIn(("C", 2), p.labels)  # run 18: on the page, the footer label stays free
        p.call("macro_touch", 0)
        p.paint()
        self.assertTrue(p.e.text(render.ROOT+0x34).startswith("MAP M1"))

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
        self.assertTrue(any(rect == (6, 52, 159, 310) and colour == 0xa3
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
                self.assertTrue(all(8 <= 480 - y - h and 480 - y <= 118
                                    for x, y, w, h in dots))
                self.assertNotIn(("Min 20%", 0), p.labels)
                for i in range(1, 9):
                    self.assertEqual(p.labels.count((f"M{i}", 0)), 1)
            self.assertIn(("1 / Filter", 0), p.labels)
            # Same body for rings and controls; only the armed "MAP" marker differs.
            current_body = p.pixels()[118:428].tobytes()
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
                         [N.NKEY(0x1b1), N.NKEY(0x1b2), N.NKEY(0x1b3), N.NKEY(0x1b4), N.NKEY(0x1b5), N.NKEY(0x1b6), N.NKEY(0x1b7), N.NKEY(0x1b9)])
        p.w(POINT, 800)
        p.w(POINT + 4, 380)
        self.assertEqual(p.call("fx_screen_hit", POINT, POINT + 8), 1)
        self.assertEqual(p.e.r(POINT + 8), p.bar())
        p.call("pg_fx_touch_down", p.bar(), POINT)
        p.call("pg_fx_touch_up", p.bar(), POINT)
        p.call("fx_header", MODEL, 0, VIEW + 0x93c4, 0, 0x08145f22)
        self.assertEqual([p.e.h(VIEW + 0x93c4 + 0x14 + i * 2) for i in range(8)],
                         [N.NKEY(0x1bc), N.NKEY(0x1bf), N.NKEY(0x1c0), N.NKEY(0x1c1), N.NKEY(0x1c2), N.NKEY(0x1c3), N.NKEY(0x1c4), N.NKEY(0x1c5)])
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), N.NKEY(0x1bc))
        p.fx_values()
        p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        self.assertTrue({"EQ", "Compressor", "Saturator" if N.FW168 else "Soft Clip"} <= set(dict(p.labels))) # run 17 (1.6.8): Saturator
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
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), N.NKEY(0x1c6))
        if N.FW168: # run 17: no section toggles in the footer; Left (button 0) selects the previous section
            for _ in range(2):
                self.assertEqual(p.call("fx_dispatch", MODEL, 0xaf, 0, 0), 1); self.assertEqual(p.call("fx_dispatch", MODEL, 0xb0, 0, 0), 1)
            p.call("fx_header", MODEL, 0, VIEW + 0x93c4, 0, 0x08145f22)
        else:
            p.u.mem_write(POINT, struct.pack("<5I", 0x1077, 0, 0, 0, 0))
            self.assertEqual(p.call("fx_event", VIEW, POINT), 1)
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), N.NKEY(0x1b1))
        p.fx_values()
        out = POINT + 0x400
        p.u.mem_write(out, render.tpl(p.e, 20))
        p.call("device_header_prepare", out)
        if N.FW168: # run 17: footer view toggles Tracks | Track FX (slots 4, 5)
            self.assertEqual([p.e.h(out + N.HDR(0x74) + i * 48 + 44) for i in range(6)], [0, 0, 0, 0, 0x1077, 0x1078])
        else:
            self.assertEqual([p.e.h(out + N.HDR(0x74) + i * 48 + 44) for i in (1, 2, 3)],
                             [0x1077, 0x1078, 0x1079])
        self.assertEqual(p.e.text(out), "Track 1")
        def track_name(u, a, n, data):
            u.mem_write(u.reg_read(UC_ARM_REG_R3), N.native_string(b"Drum Kit"))
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
        for x, key in (((800, N.NKEY(0x1bc)), (1100, N.NKEY(0x1c6)), (300, N.NKEY(0x1b1))) if N.FW168 else
                       ((560, N.NKEY(0x1bc)), (720, N.NKEY(0x1c6)), (400, N.NKEY(0x1b1)))):
            p.tap_at(x, 240 if N.FW168 else 452) # run 17 (1.6.8): a tap on the section picture selects it
            self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), key)
        p.tap_at(800, 240)
        self.assertEqual(p.e.h(p.bar() + 0x38 + 0x9c), N.NKEY(0x1bc))

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

    def test_run18_a_tap_selects_the_settings_section_and_up_down_keep_working(self):
        # Run 18 (owner: rows are chosen by a tap or Up/Down on every row page): natively neither the bars nor the
        # SectionGroup take touches; a tap on a row now makes its section active (native setter 08170C86).
        p = Perform()
        p.select_project_view(0x1074)
        g = VIEW + 0x9018
        self.assertEqual(p.e.r(g + 0x39c), 0)
        for top, want in ((200, 1), (320, 2), (80, 0)):
            p.tap_at(400, top)
            self.assertEqual(p.e.r(g + 0x39c), want, top)

    def test_settled_partial_paints_do_not_repeat_native_fills_or_labels(self):
        p = Perform()
        p.paint()
        p.fills.clear()
        p.labels.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 256, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
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
