"""Real native sample-editor construction, switch gestures and cached paint."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
from pathlib import Path
import unittest

from test_tracks import emu, render, UC_HOOK_CODE
from test_integration import IMAGE, UU, CANDIDATE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC

VIEW, POINT = 0xc0400000, 0x24070000
MANAGER, REPORT = 0x20010000, 0x20011000
KEEP = []


def no_card_carrier(u):
    """Panel fixtures model named carriers without an SD card: content checks
    of a carrier .wav fail to open, so recognition keeps the name result."""
    def hook(u, address, size, data):
        path = bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1), 260)).split(b"\0")[0]
        if u.reg_read(UC_ARM_REG_R2) == 1 and path.lower().endswith(b".wav"):
            u.reg_write(UC_ARM_REG_R0, 4)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
    return u.hook_add(UC_HOOK_CODE, hook, begin=0x08120148, end=0x08120148)


class Panel:
    def __init__(self, path=b"\\Drum Synths\\Syncussion.wav\0"):
        KEEP.append(self)
        self.path = path
        self.e = emu.Emu(IMAGE)
        self.u = self.e.u
        render.boot_gfx(self.e)
        self.hooks = [self.u.hook_add(UC_HOOK_CODE, self.service, begin=a, end=a)
                      for a in (0x08133f7c, 0x0813390e, 0x08133614, 0x0813130c, 0x08134800)]
        self.hooks.append(no_card_carrier(self.u))
        self.e.call(0x08153560, VIEW)
        self.e.call(0x081639a8, 0)
        self.context()
        self.e.call(0x08152144, VIEW)
        self.context()
        self.call("kick_ui_before", VIEW)
        self.call("kick_ui_after", VIEW)
        self.u.mem_write(0x30024b00+0x14c, b"\1")
        flags = POINT+0x100
        self.u.mem_write(flags, b"\1\1"+bytes(6))
        for offset in (0x38, 0x2430, 0x4828):
            bar = VIEW+offset
            self.e.call(self.e.r(self.e.r(bar)), bar, flags)
        self.call("kick_ui_after", VIEW)
        self.u.mem_write(VIEW+4, struct.pack("<4i", 0, 0, 1280, 480))
        self.u.mem_write(MANAGER, bytes(0x500))
        self.e.call(0x0816fb28, MANAGER+0x470)
        self.e.call(0x0816fb64, MANAGER+0x470, VIEW)
        self.e.w(MANAGER+0x470+0x3c, VIEW)
        if self.panel_path():
            template = render.tpl(self.e, 2)
            self.u.mem_write(0x30024b00+0x12c, template[N.HDR(0x1c2):N.HDR(0x1c3)])
            self.e.call(0x08180198, render.ROOT)
            self.e.call(0x0816fb64, VIEW, render.ROOT)
            self.header()

    def header(self):
        self.u.mem_write(POINT, render.tpl(self.e, 2))
        self.e.call(0x0817faf8, render.ROOT, POINT)

    def panel_path(self):
        return self.path in [("\\Drum Synths\\"+name+".wav\0").encode()
                             for name in ("Kick", "Snare", "HiHat", "Clap", "Tom", "Syncussion")]

    def select_view(self, mix):
        self.u.mem_write(POINT, struct.pack("<4I", 0x1068 if mix else 0x1067, 0, 0, 0))
        self.call("seq_nav_global", 0x30024b00, POINT)
        self.header()

    def context(self):
        self.e.w(VIEW+0x87bc, 0x13e)
        self.e.w(VIEW+0x87c4, 0x13f)
        self.u.mem_write(VIEW+0x87cc, b"\x0e")

    def service(self, u, address, size, data):
        r = [u.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        result = 1
        if address == 0x0813390e:
            u.mem_write(r[3], N.native_string(self.path))
        elif address == 0x08133614:
            self.e.w(r[3], 0)
        elif address == 0x08134800:
            result = 0  # Model snapshot unavailable; keep the applied real template.
        u.reg_write(UC_ARM_REG_R0, result)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def call(self, name, *args):
        result = self.e.call(UU[name], *args)
        if self.u.reg_read(UC_ARM_REG_PC) != emu.RET:
            raise AssertionError("Native call did not complete: "+name)
        return result

    def paint(self, full=True):
        self.e.w(render.CTX, 0x101 if full else 0x100)
        render.paint(self.e, VIEW)
        if self.panel_path():
            render.paint(self.e, render.ROOT)

    def save(self, path):
        from PIL import Image
        prefix = struct.pack("<4I", 0xff000000, 0xff000000, 0xffe9eeea, 0xff3b4142)
        at = IMAGE.find(prefix)
        assert at >= 0 and IMAGE.find(prefix, at+1) < 0, "Exact Playground CLUT required"
        colours = struct.unpack_from("<15I", IMAGE, at)
        palette = []
        for index in range(256):
            colour = colours[index & 15] if (index & 15) < 15 else 0
            palette.extend(round(((colour >> shift) & 255)*(index >> 4)/15)
                           for shift in (16, 8, 0))
        image = Image.fromarray(render.ui(self.e))
        image.putpalette(palette)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(path)

    def tap(self, index, move=False):
        bar = VIEW+0x4828
        x, top = self.button(index)
        self.e.w(POINT, x)
        self.e.w(POINT+4, 480-top)
        self.call("macro_bar_down", bar, POINT, 1)
        if move:
            self.e.w(POINT+4, 480-430)
            self.call("macro_bar_move", bar, POINT, 1)
        self.call("macro_bar_up", bar, POINT, 1)

    def button(self, index):
        if index >= 7:
            mode = index-7
            return 6+12+mode*104+30, 8+30+16
        x = 6+(646+index*102 if index < 3 else 964+(index-3)*76 if index < 6 else 1192)
        top = 8+30
        return x+30, top+16

    def mode(self, mode):
        self.tap(7+mode)
        self.call("kick_ui_after", VIEW)

    def finger(self, x, top, down):
        report = bytearray(16)
        if down:
            struct.pack_into("<h", report, 0, 1)
            struct.pack_into("<hhB", report, 4, x, 480-top, 1)
        self.u.mem_write(REPORT, bytes(report))
        self.e.call(0x0816332c, MANAGER, REPORT)


class Tests(unittest.TestCase):
    def test_drum_turns_follow_native_acceleration_and_fractional_quantization(self):
        from test_encoder_speed import SpeedPage
        gains = []
        for elapsed in (1000, 1):
            p, native = Panel(), SpeedPage()
            native.native_slot(0x1e, 500)
            slot = VIEW+0x70+2*0x468
            initial = p.e.r(slot+0xa0)
            for _ in range(40):
                p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+elapsed)
                p.e.w(0x30035f40, p.e.r(0x30035f40)+elapsed)
                p.e.call(0x08171e44, slot, 160)
                native.turn(160, elapsed)
            gained = p.e.r(slot+0xa0)-initial
            self.assertAlmostEqual(gained/100, (native.r(0xc0180070+0xa0)-500)/1000,
                                   delta=.01)
            self.assertGreater(gained, 0)
            gains.append(gained)
        self.assertGreater(gains[1], gains[0])

    def test_panel_meets_footer_and_native_footer_baseline(self):
        p = Panel()
        self.assertEqual(struct.unpack("<4i", p.u.mem_read(VIEW+0x38+4, 16)),
                         (6, 49, 1268, 333))
        self.assertEqual(struct.unpack("<4i", p.u.mem_read(VIEW+0x80b4+4, 16)),
                         (6, 8, 780, 39))
        p.paint()
        p.save(CANDIDATE/"screens/syncussion-footer-aligned.png")

    def test_header_applied_before_editor_binding_is_repaired_after_refresh(self):
        p = Panel()
        state = 0x24043d20
        p.u.mem_write(state, bytes(20))
        p.header()
        self.assertNotEqual(p.e.r(render.ROOT+0x34+N.HDR(0x74)+3*48+44), 0x1067)
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        for index, key in ((3, 0x1067), (4, 0x1068)):  # R6.3: Synth · Mix · Motion
            self.assertEqual(p.e.r(render.ROOT+0x34+N.HDR(0x74)+index*48+44), key)
            self.assertEqual(p.u.mem_read(render.ROOT+N.ROOT_TABS+index*0xd0+0x30, 1), b"\0")
        applications = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: applications.append(1),
                            begin=0x0817faf8, end=0x0817faf8)
        try:
            p.call("kick_ui_after", VIEW)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(applications, [], "Settled header must not be reapplied")

    def test_sound_edits_do_not_rebuild_editor_or_reset_encoder_state(self):
        p = Panel()
        p.paint()
        before = render.ui(p.e).copy()
        calls = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: calls.append(1),
                            begin=0x08152144, end=0x08152144)
        try:
            for value in (79, 80, 81, 80, 79):
                p.u.mem_write(POINT, struct.pack("<4I", 0xcf, 0, N.NKEY(0x1a0), value))
                p.call("kick_ui_event", VIEW, POINT)
                self.assertEqual(p.u.mem_read(0x24043528, 1)[0], value)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(calls, [])
        p.paint(False)
        self.assertFalse((render.ui(p.e) == before).all(), "Changed Tune must repaint")

    def test_native_slow_turns_accumulate_reversibly_without_editor_rebuilds(self):
        p = Panel()
        slot = VIEW+0x70+2*0x468
        initial = p.u.mem_read(0x24043529, 1)[0]
        rebuilds = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: rebuilds.append(1),
                            begin=0x08152144, end=0x08152144)
        def turn(delta, elapsed=10000):
            p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+elapsed)
            p.e.w(0x30035f40, p.e.r(0x30035f40)+elapsed)
            p.e.call(0x08171e44, slot, delta & 0xffffffff)
            value = p.u.mem_read(0x24043529, 1)[0]
            self.assertEqual(value, p.e.r(slot+0xa0))
            return value
        try:
            forward = [turn(1600) for _ in range(12)]
            self.assertEqual(forward, sorted(forward))
            self.assertGreaterEqual(forward[-1]-initial, 6)
            reverse = [turn(-1600) for _ in range(12)]
            self.assertEqual(reverse, sorted(reverse, reverse=True))
            self.assertEqual(reverse[-1], initial)
            fast = [turn(1600, 1) for _ in range(12)]
            self.assertEqual(fast, sorted(fast))
            self.assertGreater(fast[-1], initial)
            self.assertEqual(turn(1280000), 100)
            self.assertEqual(turn(-1280000), 0)
            self.assertGreater(turn(12800), 0)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(rebuilds, [])

    def test_dragging_off_a_toggle_cancels_the_tap(self):
        p = Panel()
        p.tap(1, move=True)
        self.assertEqual(p.u.mem_read(0x24043d80, 1), b"\0")

    def test_unrelated_widgets_and_mode_button_gaps_are_not_claimed(self):
        p = Panel()
        p.e.w(POINT, 20)
        p.e.w(POINT+4, 480-100)
        self.assertEqual(p.call("drum_panel_point", VIEW+0x38, POINT, POINT+16), 0)
        self.assertEqual(p.call("drum_panel_point", VIEW+0x2430, POINT, POINT+16), 0)

    def test_point_helper_returns_owning_native_bar(self):
        p = Panel()
        x, top = p.button(0)
        p.e.w(POINT, x)
        p.e.w(POINT+4, 480-top)
        self.assertEqual(p.call("drum_panel_point", VIEW+0x4828, POINT, POINT+16), 1)
        self.assertEqual(p.e.r(POINT+16), VIEW+0x4828)

    def test_pad_change_cancels_pending_switch_tap(self):
        p = Panel()
        bar = VIEW+0x4828
        x, top = p.button(1)
        p.e.w(POINT, x)
        p.e.w(POINT+4, 480-top)
        p.call("macro_bar_down", bar, POINT, 1)
        p.e.w(VIEW+0x87bc, 0x222)
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        p.call("macro_bar_up", bar, POINT, 1)
        self.assertEqual(bytes(p.u.mem_read(0x24043d80, 2)), bytes(2))

    def test_switching_back_to_sample_restores_native_bar_layout(self):
        p = Panel(b"\\Piano.wav\0")
        def rects():
            return [bytes(p.u.mem_read(VIEW+offset+4, 16))
                    for offset in (0x38, 0x2430, 0x4828)]
        native = rects()
        p.path = b"\\Drum Synths\\Syncussion.wav\0"
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        self.assertNotEqual(rects(), native)
        p.path = b"\\Piano.wav\0"
        p.call("kick_ui_before", VIEW)
        self.assertEqual(rects(), native)

    def test_attack_encoder_is_continuous_and_does_not_change_mode(self):
        p = Panel()
        # Owner: one slow full encoder turn (160000 raw units) sweeps the
        # whole native range of every drum/Syncussion control.
        for slot in (VIEW+0x38+0x38+0x468, VIEW+0x38+0x38):
            span = (p.e.r(slot+0x454)-p.e.r(slot+0x450))*p.e.r(slot+0x88)
            self.assertGreater(span, 0)
            self.assertEqual(sum(p.call("kick_ui_increment", slot, 160) for _ in range(1000)), span)
        slot = VIEW+0x38+0x38+0x468
        changes = []
        def capture(u, address, size, data):
            event = u.reg_read(UC_ARM_REG_R1)
            changes.append(bytes(u.mem_read(event, 16)))
            u.reg_write(UC_ARM_REG_R0, 1)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0816fc34, end=0x0816fc34)
        try:
            for value in range(1, 6):
                p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+100)
                p.e.call(0x08171e44, slot, 1600)
                self.assertEqual(struct.unpack("<4I", changes[-1])[2:], (N.NKEY(0x1b0), value))
                p.u.mem_write(POINT, changes[-1])
                p.call("kick_ui_event", VIEW, POINT)
                p.call("kick_ui_after", VIEW)
                self.assertEqual(p.u.mem_read(0x24043d80, 1)[0], 0)
                table = p.e.r(0x24043508)
                self.assertGreaterEqual(table, 0xc0000000)
                self.assertEqual(p.u.mem_read(table+32, 1)[0], value)
        finally:
            p.u.hook_del(hook)

    def test_native_track_colour_reaches_faders_and_symbols_and_invalidates_cache(self):
        p = Panel()
        fills = []
        def capture(u, address, size, data):
            rect = u.reg_read(UC_ARM_REG_R0)
            fills.append((struct.unpack("<4i", u.mem_read(rect, 16)),
                          u.reg_read(UC_ARM_REG_R1)))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x08166ef6, end=0x08166ef6)
        try:
            def set_track(track):
                # Real property getter; the unrelated model byte +131 stays zero.
                p.e.w(0x30024b0c, 0x20018000)
                p.e.w(0x30024b10, 1)
                p.u.mem_write(0x20018000, struct.pack("<IHBB", track, 0x131, 1, 0))
            set_track(7)
            p.paint()
            previous = None
            for track in range(8):
                set_track(track)
                self.assertEqual(p.u.mem_read(0x30024b00+0x131, 1), b"\0")
                colour = p.e.call(0x08140ebc, track)
                self.assertNotIn(colour, (0xf1, 0xf2))
                fills.clear()
                p.e.w(render.CTX, 0x100)
                p.call("pg_bar_paint", VIEW+0x38, render.CTX)
                p.call("pg_bar_paint", VIEW+0x4828, render.CTX)
                if colour == previous:
                    self.assertEqual(fills, [])
                    continue
                previous = colour
                # Run 15: Metal uses the shared drum fader (track-colour fill and handle stripe on all 8)
                self.assertEqual(sum(r[2:] == (30, 2) and c == colour for r, c in fills), 8)
                self.assertEqual(sum(r[2] == 8 and c == (colour & 15) | 0x80 for r, c in fills), 8)
                self.assertTrue(any(c == colour and r[1] >= 402 and r[1]+r[3] <= 442
                                    for r, c in fills), track)
            p.paint()
            p.save(CANDIDATE/"screens/syncussion-colour-symbols.png")
        finally:
            p.u.hook_del(hook)

    def test_native_focus_box_matches_tall_sound_row(self):
        p = Panel()
        group = p.e.r(VIEW+0x38+0x2c)
        self.assertEqual(p.e.r(group+0x204), 3)
        self.assertEqual(p.e.r(group+0x208+16), 333)

    def test_mix_uses_native_encoder_keys_and_restores_sample_visibility(self):
        p = Panel()
        p.select_view(True)
        mix = VIEW+0x2430
        self.assertEqual(struct.unpack("<8H", p.u.mem_read(VIEW+0x703c+0x50, 16)),
                         (2, 3, 4, 0xe5, 0x36, 0x37, 0x32, 0x33))
        events = []
        def capture(u, address, size, data):
            event = u.reg_read(UC_ARM_REG_R1)
            events.append(struct.unpack("<4I", u.mem_read(event, 16)))
            u.reg_write(UC_ARM_REG_R0, 0)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0816fc34, end=0x0816fc34)
        try:
            for index, key in ((3, 0xe5), (4, 0x36), (5, 0x37), (7, 0x33)):
                slot = mix+0x38+index*0x468
                p.e.w(0x3001fe2c, 1000+index*100)
                p.e.call(0x08171c1c, slot, key, 500, 1)
                p.e.call(0x08171e44, slot, p.e.r(slot+0x88)*32)
                self.assertEqual(events[-1][2], key)
        finally:
            p.u.hook_del(hook)
        p.e.w(VIEW+0x87bc, 0x222)
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        self.assertEqual(p.u.mem_read(mix+0x30, 1), b"\0")
        p.path = b"\\Piano.wav\0"
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        for offset in (0x38, 0x2430):
            self.assertEqual(p.u.mem_read(VIEW+offset+0x30, 1), b"\0")

    def test_footer_tabs_are_scoped_to_active_syncussion_editor(self):
        p = Panel()
        for page in (2, 7, 0xb, 0x11, 0x17, 0x1a):
            p.u.mem_write(0x30024b00+0x12c, bytes([page]))
            p.u.mem_write(POINT, struct.pack("<4I", 0x1068, 0, 0, 0))
            self.assertEqual(p.call("drum_panel_navigation", 0x30024b00, POINT), 0)
        p.u.mem_write(0x30024b00+0x12c, b"\x08")
        p.u.mem_write(VIEW+0x30, b"\1")
        self.assertEqual(p.call("drum_panel_navigation", 0x30024b00, POINT), 0)

    def test_returning_to_sample_restores_real_dashboard_wav_template(self):
        p = Panel()
        self.assertEqual(p.u.mem_read(0x30024b00+0x12c, 1), b"\x08")
        p.path = b"\\Piano.wav\0"
        p.call("kick_ui_before", VIEW)
        p.call("kick_ui_after", VIEW)
        p.header()
        self.assertEqual([p.e.r(render.ROOT+0x34+N.HDR(0x74)+i*48+44) for i in (2, 3, 4, 5)],
                         [0, 3, 8, 0x1076])


if __name__ == "__main__":
    unittest.main(verbosity=2)
