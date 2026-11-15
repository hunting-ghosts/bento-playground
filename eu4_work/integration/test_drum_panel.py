"""DaisyDrums panels through native constructors, encoders and finger dispatch."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest

from test_syncussion_ui import Panel, VIEW, POINT, render, UC_HOOK_CODE
from test_integration import CANDIDATE, UU
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_LR, UC_ARM_REG_PC

NAMES = ("Kick", "Snare", "HiHat", "Clap", "Tom")
KEYS = (N.NKEY(0x1a0), N.NKEY(0x1a1), N.NKEY(0x1a2), N.NKEY(0x1a4), N.NKEY(0x1a5), N.NKEY(0x1a6), N.NKEY(0x1a9))
MIX_KEYS = (2, 3, 4, 0xe5, 0x36, 0x37, 0x32, 0x33)


class Drums(Panel):
    def __init__(self, engine=0):
        super().__init__(self.engine_path(engine))
        self.assigned = []
        self.hooks.append(self.u.hook_add(UC_HOOK_CODE, self.assign,
                                         begin=UU["drum_assign"], end=UU["drum_assign"]))

    @staticmethod
    def engine_path(engine):
        return ("\\Drum Synths\\"+NAMES[engine]+".wav\0").encode()

    def assign(self, u, address, size, data):
        pad, cell, engine = [u.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
        self.assigned.append((pad, self.e.r(cell), engine))
        self.path = self.engine_path(engine)
        u.reg_write(UC_ARM_REG_R0, 1)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def engine_point(self, index):
        return 6+10+index*159+78, 8+30+20  # R6.4: footer toggle size (157, pitch 159)

    def pointer(self, index):
        x, top = self.engine_point(index)
        self.e.w(POINT, x)
        self.e.w(POINT+4, 480-top)

    def values(self):
        return bytes(self.u.mem_read(0x24043528, 7)), bytes(self.u.mem_read(0x24043d80, 1))

    def set_track(self, track):
        # Execute the real property getter; leave the unrelated +131 byte zero.
        self.e.w(0x30024b0c, 0x20018000)
        self.e.w(0x30024b10, 1)
        self.u.mem_write(0x20018000, struct.pack("<IHBB", track, 0x131, 1, 0))


class Tests(unittest.TestCase):
    def test_engine_picker_has_five_drums_and_syncussion_but_not_subtractive(self):
        p = Panel()
        descriptor = p.e.r(0x30031484)+N.NKEY(0x1ad)*32
        choices = p.e.r(descriptor+8)
        self.assertEqual(p.e.r(descriptor+12), 6)
        self.assertEqual([p.e.text(p.e.r(choices+4*i)) for i in range(6)],
                         ["Kick", "Snare", "HiHat", "Clap", "Tom", "Metal"])
        self.assertEqual(p.call("drum_assign", 0, 0x2003f000, 6), 0)

    def test_all_five_engines_render_with_exact_encoder_keys(self):
        out = CANDIDATE/"screens"
        out.mkdir(exist_ok=True)
        for engine, name in enumerate(NAMES):
            with self.subTest(engine=name):
                p = Drums(engine)
                expected = KEYS+(N.NKEY(0x1b0),) if engine == 0 else KEYS+(0,) if engine == 4 else KEYS[:5]+(0,)*3
                self.assertEqual(struct.unpack("<8H", p.u.mem_read(VIEW+0x703c, 16)), expected)
                # Engine row: E1 is the engine selector, E2..E8 stay unbound.
                self.assertEqual(struct.unpack("<8H", p.u.mem_read(VIEW+0x703c+0xa0, 16)), (N.NKEY(0x1ad),)+(0,)*7)
                self.assertEqual(p.e.text(render.ROOT+0x34), "")
                self.assertEqual(p.e.text(VIEW+0x80b4+0x31), name+" / Pad 1")
                p.paint()
                p.save(out/("daisydrums-"+name.lower()+".png"))

    def test_engine_row_is_untouchable_and_keeps_fader_focus(self):
        # R6.5 (owner): switching here is unreliable on hardware; the row stays
        # visible but every touch is swallowed (switch from the INST page).
        p = Drums()
        for engine in (1, 2, 3, 4, 5, 0):
            p.finger(*p.engine_point(engine), True)
            p.finger(*p.engine_point(engine), False)
        self.assertEqual(p.assigned, [])
        self.assertEqual(p.e.text(VIEW+0x80b4+0x31), "Kick / Pad 1")
        group = p.e.r(VIEW+0x38+0x2c)
        self.assertEqual(p.e.r(group+0x39c), 0)

    def test_lower_third_touch_keeps_the_focus_box_on_the_faders(self):
        # R6.5 (owner: full-width rectangle above the footer).
        p = Drums()
        p.paint()
        box = p.e.r(VIEW+0x38+0x2c)+0x208
        p.finger(600, 420, True)
        p.finger(600, 420, False)
        p.paint(False)
        self.assertEqual([p.e.r(box+o) for o in (4, 8, 12, 16)], [6, 49, 1268, 333])

    def test_drag_pad_engine_and_view_changes_cancel_pending_engine_taps(self):
        for change in ("drag", "pad", "engine", "view", "finger"):
            with self.subTest(change=change):
                p = Drums()
                bar = VIEW+0x4828
                p.pointer(2)
                p.call("macro_bar_down", bar, POINT, 1)
                if change == "drag":
                    p.e.w(POINT, p.e.r(POINT)+60)  # R6.3: 40 px tap tolerance
                    p.call("macro_bar_move", bar, POINT, 1)
                elif change == "pad":
                    p.e.w(VIEW+0x87bc, 0x222)
                elif change == "engine":
                    p.path = p.engine_path(1)
                    p.call("kick_ui_before", VIEW)
                    p.call("kick_ui_after", VIEW)
                elif change == "view":
                    p.select_view(True)
                    p.select_view(False)
                p.pointer(2)
                p.call("macro_bar_up", bar, POINT, 2 if change == "finger" else 1)
                self.assertEqual(p.assigned, [])

    def test_real_footer_selects_synth_mix_and_keeps_native_mix_controls(self):
        p = Drums()
        before = p.values()
        for mix in (True, False, True):
            p.select_view(mix)
            self.assertEqual(struct.unpack("<8H", p.u.mem_read(VIEW+0x703c+0x50, 16)), MIX_KEYS)
            for offset, hidden in ((0x38, False), (0x2430, not mix), (0x4828, mix)):
                self.assertEqual(p.u.mem_read(VIEW+offset+0x30, 1), bytes([hidden]))
            group = p.e.r(VIEW+0x38+0x2c)
            self.assertEqual(p.e.r(group+0x39c), int(mix))
            self.assertEqual([p.e.r(render.ROOT+0x34+N.HDR(0x74)+i*48+44) for i in (2, 3, 4, 5)],
                             [0, 0x1067, 0x1068, 0x1076])
        self.assertEqual(p.values(), before)
        p.pointer(1)
        self.assertEqual(p.call("drum_panel_point", VIEW+0x4828, POINT, POINT+16), 1)
        p.paint()
        p.save(CANDIDATE/"screens/daisydrums-mix.png")

    def test_native_encoders_edit_sound_and_click_without_editor_rebuilds(self):
        p = Drums()
        rebuilt = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: rebuilt.append(1),
                            begin=0x08152144, end=0x08152144)
        try:
            for column, key in enumerate(KEYS+(N.NKEY(0x1b0),)):
                slot = VIEW+0x70+column*0x468
                self.assertEqual(struct.unpack("<H", p.u.mem_read(slot+0x9c, 2))[0], key)
                p.e.w(0x3001fe2c, 1000+column*100)
                p.e.call(0x08171e44, slot, 1280000)
                actual = p.values()[1][0] if column == 7 else p.values()[0][column]
                self.assertEqual(actual, 180 if column == 0 else 100)
                p.e.w(0x3001fe2c, 2000+column*100)
                p.e.call(0x08171e44, slot, -1280000 & 0xffffffff)
                actual = p.values()[1][0] if column == 7 else p.values()[0][column]
                self.assertEqual(actual, 25 if column == 0 else 0)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(rebuilt, [])

    def test_black_panel_keeps_fader_scale_marks_and_is_not_touch_draggable(self):
        p = Drums()
        fills = []
        def capture(u, address, size, data):
            x, y, w, h = struct.unpack("<4i", u.mem_read(u.reg_read(UC_ARM_REG_R0), 16))
            fills.append((x, 480-y-h, w, h, u.reg_read(UC_ARM_REG_R1)))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x08166ef6, end=0x08166ef6)
        try:
            p.e.w(render.CTX, 0x101)
            p.call("pg_bar_paint", VIEW+0x38, render.CTX)
        finally:
            p.u.hook_del(hook)
        self.assertNotIn((10, 12, 628, 286, 0x83), fills)
        self.assertNotIn((646, 12, 628, 286, 0x63), fills)
        self.assertEqual(sum(r[2:4] == (22, 178) for r in fills), 8)
        self.assertEqual(sum(r[2:] == (38, 10, 0xf2) for r in fills), 8)
        self.assertEqual(sum(r[2:4] == (6, 1) for r in fills), 144)
        self.assertNotIn((56, 8), [r[2:4] for r in fills])
        before = p.values()
        p.e.w(POINT, 85)
        p.e.w(POINT+4, 480-180)
        self.assertEqual(p.call("drum_panel_point", VIEW+0x38, POINT, POINT+16), 0)
        p.finger(85, 180, True)
        p.finger(85, 100, True)
        p.finger(85, 100, False)
        self.assertEqual(p.values(), before)

    def test_fader_endpoints_stay_in_channels_for_every_engine(self):
        for engine in range(5):
            p = Drums(engine)
            p.e.w(0x30035f40, 100)
            for high in (False, True):
                with self.subTest(engine=NAMES[engine], high=high):
                    count = 8 if engine == 0 else 7 if engine == 4 else 5
                    for column in range(count):
                        value = (180 if high else 25) if column == 0 and engine in (0, 4) else 100 if high else 0
                        key = N.NKEY(0x1b0) if column == 7 else KEYS[column]
                        p.u.mem_write(POINT, struct.pack("<4I", 0xcf, 0x13e, key, value))
                        p.call("kick_ui_event", VIEW, POINT)
                    handles = []
                    def capture(u, address, size, data):
                        x, y, w, h = struct.unpack("<4i", u.mem_read(u.reg_read(UC_ARM_REG_R0), 16))
                        if (w, h, u.reg_read(UC_ARM_REG_R1)) == (38, 10, 0xf2):
                            handles.append((x, 480-y-h))
                    hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x08166ef6, end=0x08166ef6)
                    try:
                        p.e.w(render.CTX, 0x101)
                        p.call("pg_bar_paint", VIEW+0x38, render.CTX)
                    finally:
                        p.u.hook_del(hook)
                    self.assertEqual(handles, [(66+159*i, 180 if high else 338) for i in range(count)])
                    if high:
                        p.paint()
                        p.save(CANDIDATE/("screens/daisydrums-"+NAMES[engine].lower()+"-max.png"))

    def test_original_sized_readouts_do_not_clip_four_digit_tuning_values(self):
        import numpy as np
        p = Drums()
        label, string = POINT+0x1000, POINT+0x1100
        p.e.call(0x0817e7c0, label)
        p.e.call(0x0817e810, label, 0)
        for value in ("1170 Hz", "1855 Hz", "3200 Hz"):
            p.u.mem_write(string, value.encode()+b"\0")
            p.e.call(0x0817e85e, label, string)
            glyphs = []
            for width in (146, 200):
                p.u.mem_write(render.FB, bytes([0xf1])*(1280*480))
                p.u.mem_write(label+4, struct.pack("<4i", 0, 480-64, width, 64))
                p.u.mem_write(label+0x51, b"\2")
                p.u.mem_write(label+0x53, bytes([0xf2, 0xf1]))
                p.u.mem_write(label+0x56, b"\1")
                p.u.mem_write(label+0x5c, b"\1")
                p.e.w(render.CTX, 0x101)
                p.e.call(0x0817e448, label, render.CTX, label+4)
                pixels = render.ui(p.e)[:64, :width]
                ys, xs = np.nonzero(pixels != 0xf1)
                self.assertTrue(len(xs), value)
                glyphs.append(pixels[ys.min():ys.max()+1, xs.min():xs.max()+1].copy())
            self.assertTrue(np.array_equal(*glyphs), value)

    def test_readouts_use_large_white_values_and_native_size_dim_labels_on_black(self):
        # Run 16 (OWNER RULE, design/native/native_settings_drum.png): every text at the native size (Rajdhani 24,
        # font 0): values white, labels dim grey, section titles in the track colour (mixed case); never font 3.
        p = Drums()
        labels = []
        def capture(u, address, size, data):
            label = u.reg_read(UC_ARM_REG_R0)
            labels.append((p.e.text(label+0x31), bytes(u.mem_read(label+0x53, 3)),
                           struct.unpack("<4i", u.mem_read(label+4, 16))[2:]))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
        try:
            p.e.w(render.CTX, 0x101)
            p.call("pg_bar_paint", VIEW+0x38, render.CTX)
        finally:
            p.u.hook_del(hook)
        values = [entry for entry in labels if entry[0].endswith((" Hz", "%"))]
        self.assertEqual(len(values), 8)
        for text, style, rect in values:
            self.assertEqual(style, bytes([0xf2, 0xf1, 0]))
            self.assertEqual(rect, (146, 26))
        colour = p.e.call(0x08140ebc, 0)
        titles = [entry for entry in labels if entry[1][0] == colour]
        self.assertEqual([(t, st) for t, st, _ in titles], [(t, bytes([colour, 0xf1, 0])) for t in ("Body", "Sweep", "Transient")])
        names = [entry for entry in labels if entry[1][0] == 0xf6]
        self.assertEqual([entry[0] for entry in names], ["Tune", "Decay", "Tone", "Impact", "Sweep", "Sweep Dec", "Punch", "Click"])
        for text, style, rect in names:
            self.assertEqual(style, bytes([0xf6, 0xf1, 0]))
            self.assertEqual(rect, (150, 26))
        self.assertFalse([entry for entry in labels if entry[1][2] == 3])  # no small (15 px) text at all

    def test_symbol_buttons_have_matching_hit_bounds_and_no_waveform_hit(self):
        p = Drums()
        # R6.4 (owner): the whole engine row takes the touch (taps off a button
        # are swallowed, so no native focus rectangle); above the row is native.
        for index in range(6):
            x = 6+10+index*159
            for px, top, expected in ((x, 38, 1), (x+156, 77, 1),
                                      (x-1, 58, 1), (x+157, 58, 1),
                                      (x+78, 37, 1), (x+78, 7, 0)):
                p.e.w(POINT, px)
                p.e.w(POINT+4, 480-top)
                self.assertEqual(p.call("drum_panel_point", VIEW+0x4828, POINT, POINT+16),
                                 expected, (index, px, top))
        p.finger(1200, 57, True)
        p.finger(1200, 57, False)
        self.assertEqual(p.assigned, [])
        labels = []
        def capture(u, address, size, data):
            labels.append(p.e.text(u.reg_read(UC_ARM_REG_R0)+0x31))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
        try:
            p.e.w(render.CTX, 0x101)
            p.call("pg_bar_paint", VIEW+0x4828, render.CTX)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(labels, ["Kick"])  # Run 16: no "ENGINE" title (native-size reference)
        pixels = render.ui(p.e)
        symbols = []
        for index in range(6):
            x = 6+10+index*159+78-16
            symbol = pixels[46:70, x:x+32]
            # Run 15 Clean: the engine shown in the track colour inside the thin dark-grey frame A,
            # the other engines dimmed grey without a frame.
            mask = symbol == (0xf7 if index == 0 else 0xf6)
            self.assertGreater(int(mask.sum()), 60)
            symbols.append(mask.tobytes())
            left = 6+10+index*159
            edge = pixels[38, left:left+157]
            self.assertEqual(int((edge == 0xa6).sum()), 157 if index == 0 else 0, index)  # run 18: frame A is the lighter A6
        self.assertEqual(len(set(symbols)), 6)

    def test_illustrative_shape_updates_from_every_sound_control_without_audio_or_rebuilds(self):
        import numpy as np
        for engine in range(5):
            p = Drums(engine)
            p.e.w(0x30035f40, 100)
            p.paint()
            rebuilt = []
            hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: rebuilt.append(1),
                                begin=0x08152144, end=0x08152144)
            try:
                count = 8 if engine == 0 else 7 if engine == 4 else 5
                for column in range(count):
                    with self.subTest(engine=NAMES[engine], column=column):
                        shapes = []
                        for high in (False, True):
                            value = (180 if high else 25) if column == 0 and engine in (0, 4) else 100 if high else 0
                            key = N.NKEY(0x1b0) if column == 7 else KEYS[column]
                            p.u.mem_write(POINT, struct.pack("<4I", 0xcf, 0x13e, key, value))
                            p.call("kick_ui_event", VIEW, POINT)
                            self.assertEqual(bytes(p.u.mem_read(VIEW+0x4828+0x31, 1)), b"\1")
                            p.paint(False)
                            shapes.append(render.ui(p.e)[38:78, 1006:1254].copy())
                        self.assertFalse(np.array_equal(*shapes))
                partial = render.ui(p.e).copy()
                p.paint()
                self.assertTrue(np.array_equal(partial, render.ui(p.e)))
            finally:
                p.u.hook_del(hook)
            self.assertEqual(rebuilt, [])

    def test_settled_paint_is_cached_and_values_and_track_colour_invalidate(self):
        p = Drums()
        p.e.w(0x30035f40, 100)
        p.paint()
        fills = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: fills.append(1),
                            begin=0x08166ef6, end=0x08166ef6)
        try:
            p.e.w(render.CTX, 0x100)
            for offset in (0x38, 0x4828):
                p.call("pg_bar_paint", VIEW+offset, render.CTX)
            self.assertEqual(fills, [])
            p.u.mem_write(POINT, struct.pack("<4I", 0xcf, 0x13e, N.NKEY(0x1a1), 80))
            p.call("kick_ui_event", VIEW, POINT)
            p.call("pg_bar_paint", VIEW+0x38, render.CTX)
            self.assertTrue(fills)
            fills.clear()
            p.set_track(2)
            p.call("pg_bar_paint", VIEW+0x38, render.CTX)
            self.assertTrue(fills)
        finally:
            p.u.hook_del(hook)

    def test_modern_fader_height_and_baseline_match_native_syncussion_render(self):
        # Run 15: Metal (Panel) draws the same fader as the other engines (one table-driven layout).
        rails = []
        for panel, width in ((Panel(), 4), (Drums(), 4)):
            found = []
            def capture(u, address, size, data):
                x, y, w, h = struct.unpack("<4i", u.mem_read(u.reg_read(UC_ARM_REG_R0), 16))
                if w == width and h == 168:
                    found.append((480-y-h, h))
            hook = panel.u.hook_add(UC_HOOK_CODE, capture, begin=0x08166ef6, end=0x08166ef6)
            panel.e.w(render.CTX, 0x101)
            panel.call("pg_bar_paint", VIEW+0x38, render.CTX)
            panel.u.hook_del(hook)
            self.assertEqual(found, [(180, 168)]*8)
            rails.append(found)
        self.assertEqual(*rails)

    def test_mix_toggle_replaces_only_the_switch_row(self):
        import numpy as np
        for panel in (Panel(), *(Drums(engine) for engine in range(5))):
            with self.subTest(path=panel.path):
                panel.paint()
                synth = render.ui(panel.e).copy()
                panel.select_view(True)
                panel.paint()
                mixed = render.ui(panel.e).copy()
                # Owner: Mix swaps the switch row for the eight Mix encoders
                # at full height; the sound faders below stay untouched.
                self.assertTrue(np.array_equal(synth[100:428, 10:1270],
                                               mixed[100:428, 10:1270]))
                self.assertFalse(np.array_equal(synth[38:78, 16:1254],
                                                mixed[38:78, 16:1254]))
                panel.paint(False)
                self.assertTrue(np.array_equal(mixed, render.ui(panel.e)))
                panel.select_view(False)
                panel.paint()
                self.assertTrue(np.array_equal(synth, render.ui(panel.e)))

    def test_actual_native_track_property_colours_all_drum_panel_regions(self):
        p = Drums()
        p.e.w(0x30035f40, 100)
        for track in (0, 3, 6):
            p.set_track(track)
            colour = p.e.call(0x08140ebc, track)
            self.assertEqual(p.u.mem_read(0x30024b00+0x131, 1), b"\0")
            p.paint(False)
            pixels = render.ui(p.e)
            self.assertGreater(int((pixels[190:358, 70:100] == colour).sum()), 20)
            # Run 15 Clean: active engine symbol, engine name, section titles and the waveform carry the
            # track colour; the other symbols are dim grey, the values white.
            self.assertGreater(int((pixels[46:70, 78:110] == colour).sum()), 60)
            self.assertEqual(int((pixels[46:70, 237:269] == colour).sum()), 0)
            self.assertGreater(int((pixels[46:70, 237:269] == 0xf6).sum()), 60)
            self.assertGreater(int((pixels[38:78, 1006:1254] == colour).sum()), 100)
            self.assertGreater(int((pixels[104:134, 16:1264] == colour).sum()), 20)  # Body, Sweep, Transient (Run 16: native 24 px)
            self.assertEqual(int((pixels[368:394, 10:160] == colour).sum()), 0)
            self.assertGreater(int((pixels[368:394, 10:160] == 0xf2).sum()), 30)
            p.save(CANDIDATE/("screens/daisydrums-track-"+str(track+1)+".png"))

    def test_leaving_drums_restores_native_sample_layout(self):
        native = Panel(b"\\Piano.wav\0")
        rects = [bytes(native.u.mem_read(VIEW+offset+4, 16)) for offset in (0x38, 0x2430, 0x4828)]
        hidden_offsets = tuple(offset+0x30 for offset in
                               (0x7f30, 0x7e60, 0x8000, 0x803c, 0x8078, 0x715c,
                                0x710c, 0x8284, 0x8244, 0x8204, 0x8194, 0x8124))
        hidden = [bytes(native.u.mem_read(VIEW+offset, 1)) for offset in hidden_offsets]
        p = Drums()
        self.assertEqual([bytes(p.u.mem_read(VIEW+offset, 1)) for offset in hidden_offsets],
                         [b"\1"]*12)
        p.select_view(True)
        p.path = b"\\Piano.wav\0"
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        p.header()
        self.assertEqual([bytes(p.u.mem_read(VIEW+offset+4, 16)) for offset in (0x38, 0x2430, 0x4828)], rects)
        self.assertEqual([bytes(p.u.mem_read(VIEW+offset, 1)) for offset in hidden_offsets],
                         hidden)
        self.assertEqual(p.call("drum_panel", VIEW+0x38, 0), 0)
        self.assertEqual([p.e.r(render.ROOT+0x34+N.HDR(0x74)+i*48+44) for i in (2, 3, 4, 5)],
                         [0, 3, 8, 0x1076])

    def group(self, p):
        return p.e.r(VIEW+0x38+0x2c)

    def focus(self, p):
        group = self.group(p)
        box = struct.unpack("<4i", p.u.mem_read(group+0x208+4, 16))
        return p.e.r(group+0x39c), box

    def bar_rect(self, p, row):
        return struct.unpack("<4i", p.u.mem_read(VIEW+0x38+row*0x23f8+4, 16))

    def test_up_down_focus_two_full_rows_and_box_covers_each_row(self):
        p = Drums()
        self.assertEqual(self.focus(p), (0, self.bar_rect(p, 0)))
        self.assertEqual(self.bar_rect(p, 0)[3], 333)
        # R6.3 (owner): only the fader rectangle is a focus area.
        for index, row in ((1, 0), (1, 0), (8, 0), (8, 0), (1, 0)):
            self.assertEqual(p.call("drum_panel_rows", 0xaf, index), 1)
            self.assertEqual(p.call("drum_panel_rows", 0xb0, index), 1)
            p.call("kick_ui_after", VIEW)
            self.assertEqual(self.focus(p), (row, self.bar_rect(p, row)))
        # Left/Right and other buttons are not consumed by the row handler.
        for index in (0, 9, 2):
            self.assertEqual(p.call("drum_panel_rows", 0xaf, index), 0)

    def test_mix_view_and_syncussion_keep_their_own_focus(self):
        p = Drums()
        p.select_view(True)
        before = self.focus(p)
        self.assertEqual(p.call("drum_panel_rows", 0xaf, 8), 1)
        p.call("kick_ui_after", VIEW)
        self.assertEqual(self.focus(p), before)
        p.select_view(False)
        self.assertEqual(self.focus(p)[0], 0)
        s = Panel()
        self.assertEqual(s.call("drum_panel_rows", 0xaf, 1), 1)
        self.assertEqual(self.focus(s), (0, self.bar_rect(s, 0)))
        self.assertEqual(s.call("drum_panel_rows", 0xaf, 8), 1)
        self.assertEqual(self.focus(s), (0, self.bar_rect(s, 0)))

    def test_engine_specific_group_headings_render(self):
        headings = {0: ("Body", "Sweep", "Transient"), 1: ("Body", "Snares"), 2: ("Body", "Noise"),
                    3: ("Body", "Spread"), 4: ("Body", "Sweep", "Drive")}  # Run 16: native-size mixed case
        for engine, words in headings.items():
            with self.subTest(engine=NAMES[engine]):
                p = Drums(engine)
                drawn = []
                def capture(u, address, size, data):
                    drawn.append(p.e.text(u.reg_read(UC_ARM_REG_R0)+0x31))
                hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
                p.paint()
                p.u.hook_del(hook)
                for word in words:
                    self.assertIn(word, drawn)
                for word in ("SOUND", "CHARACTER", "Sound", "Character", "BODY"):
                    self.assertNotIn(word, drawn)
                p.save(CANDIDATE/("screens/daisydrums-headings-"+NAMES[engine].lower()+".png"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
