"""Launch rendering/layout checks using the native page and widget classes."""
from pathlib import Path
import struct
import sys
import unittest

from test_integration import IMAGE, K16_IMAGE, UU, Fixture
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/display_emulator"))
import emu
import render

VIEW = 0xC0F00000
POINT = 0x24070000
COLUMN_STRIDE = 0x15C0
CELL_STRIDE = 0x28C
BASE = 0x08040000
LAUNCH_VT = 0x0819DCE0
CELL_VT = 0x081B2944
BG = 0xF1
TEXT = 0xF2
SELECTED = 0xA3
KEEP = []
MODEL = 0x30024B00
ROOT_HEADER = 0x30034D48
OUT = 0x24071000
EVENT = 0x24071200
ENGINE = 0xC1800000


class Launch:
    def __init__(self):
        KEEP.append(self)
        self.e = emu.Emu(IMAGE)
        render.boot_gfx(self.e)
        self.e.call(0x08149B84, VIEW, count=50_000_000)
        self.tick()
        self.runtime = {}
        self.e.w(0x3000F650, ENGINE)
        def status(u, address, size, data):
            track = u.reg_read(UC_ARM_REG_R1)
            pos, row, queued = self.runtime.get(track, (-1, -1, -1))
            self.e.w(u.reg_read(UC_ARM_REG_R2), row)
            self.e.w(u.reg_read(UC_ARM_REG_R3), queued)
            u.reg_write(UC_ARM_REG_R0, pos & 0xFFFFFFFF)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        self.status_hook = self.e.u.hook_add(UC_HOOK_CODE, status, begin=0x081322AC, end=0x081322AC)
        self.e.u.ctl_remove_cache(0x081322AC, 0x081322D2)
        for track in range(8):
            self.e.w(self.column(track) + 0x124, 100 + track)

    def tick(self):
        self.e.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        self.e.call(self.e.r(LAUNCH_VT), VIEW, render.CTX, count=50_000_000)

    def column(self, track):
        return VIEW + 0x34 + track * COLUMN_STRIDE

    def cell(self, track, row):
        return self.column(track) + 0x12C + row * CELL_STRIDE

    def paint(self):
        self.e.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        render.paint(self.e, VIEW)
        return render.ui(self.e)

    def point_hit(self, cell, x, screen_y):
        self.e.w(POINT, x)
        self.e.w(POINT + 4, 480 - screen_y)
        return self.e.call(0x0816FA5C, cell, POINT)

    def set_clip(self, track, row, name, status, selected=False):
        cell = self.cell(track, row)
        self.e.w(cell + 0x278, 0x20001000 + track * 0x100 + row * 4)
        self.e.u.mem_write(cell + 0xE5, name.encode() + b"\0")
        self.e.u.mem_write(cell + 0x68 + 0x31, name.encode() + b"\0")
        self.e.w(cell + 0x34 + 0xA8, status)
        self.e.u.mem_write(cell + 0x288, bytes([int(selected)]))

    def event(self, code, track=None, row=0):
        self.e.u.mem_write(EVENT, struct.pack("<5I", code, 0, row, 0, 0))
        widget = VIEW if track is None else self.column(track)
        return self.e.call(self.e.r(self.e.r(widget) + 12 * 4), widget, EVENT)

    def select(self, track, row):
        self.event(0x79, track, row)

    def queue(self):
        return [struct.unpack("<6I", self.e.u.mem_read(ENGINE + i * 24, 24))
                for i in range(self.e.r(ENGINE + 0x620))]


class Tests(unittest.TestCase):
    def test_native_launch_grid_geometry_and_hit_targets_match(self):
        p = Launch()
        for track in range(8):
            column = p.column(track)
            x = 6 + 159 * track
            rect = lambda w: tuple(p.e.r(w + o) for o in (4, 8, 12, 16))
            self.assertEqual(rect(column), (x, 49, 159, 358))
            self.assertEqual(rect(column + 0x34)[2:], (0, 0))
            self.assertEqual(rect(column + 0x78), (x, 339, 159, 68))
            self.assertEqual(rect(column + 0xE8), (x, 339, 159, 68))
            for row in range(8):
                cell = p.cell(track, row)
                screen_top = 142 + row * 36
                self.assertEqual(rect(cell), (x, 480 - screen_top - 36, 159, 36))
                self.assertEqual(p.point_hit(cell, x + 74, screen_top + 10), 1)
                self.assertEqual(p.point_hit(cell, x + 160, screen_top + 10), 0)

    def test_relayout_of_single_column_is_corrected_next_tick(self):
        p = Launch()
        column = p.column(5)
        p.e.w(column + 8, 50)
        p.e.w(p.cell(5, 3) + 8, 219)
        p.tick()
        self.assertEqual(p.e.r(column + 8), 49)
        self.assertEqual(p.e.r(p.cell(5, 3) + 8), 480 - (142 + 3 * 36) - 36)

    def test_launch_cells_draw_native_names_selection_and_playback_state(self):
        p = Launch()
        p.set_clip(0, 0, "Kick", 0, selected=True)
        p.set_clip(1, 2, "Queued", 0x44C)
        p.set_clip(2, 3, "Running", 750)
        p.e.u.mem_write(p.column(0) + 0x78 + 0x31, b"Atmosphere\0")
        pixels = p.paint()

        self.assertEqual(int(pixels[150, 12]), SELECTED)
        self.assertEqual(int(pixels[150, 171]), BG)
        self.assertEqual(int(pixels[152, 10]), p.e.call(0x08140EBC, 0))
        running_top = 142 + 3 * 36
        self.assertEqual(int(pixels[running_top + 32, 333]), TEXT)
        self.assertEqual(int(pixels[running_top + 32, 451]), BG)
        queued_top = 142 + 2 * 36
        queued_x = 6 + 159 + 12
        queued_y = queued_top + 17
        queued_colour = p.e.call(0x08140EBC, 1)
        self.assertEqual(int(pixels[queued_y, queued_x - 1]), queued_colour)
        self.assertEqual(int(pixels[queued_y, queued_x + 2]), BG)
        self.assertEqual(int(pixels[queued_y, queued_x + 5]), queued_colour)
        name_region = pixels[142:178, 6:165]
        self.assertGreater(int((name_region == TEXT).sum()), 20)
        header_region = pixels[73:141, 6:165]
        self.assertGreater(int((header_region == TEXT).sum()), 20)
        self.assertEqual(int(pixels[73, 30]), p.e.call(0x08140EBC, 0))

    def test_only_justified_launcher_event_slots_are_hooked(self):
        original = Path(K16_IMAGE).read_bytes()
        candidate = IMAGE

        def word(image, address):
            return struct.unpack_from("<I", image, address - BASE)[0]

        self.assertNotEqual(word(candidate, LAUNCH_VT), word(original, LAUNCH_VT))
        self.assertEqual(word(candidate, LAUNCH_VT + 13 * 4),
                         word(original, LAUNCH_VT + 13 * 4))
        self.assertEqual(word(candidate, LAUNCH_VT + 12 * 4), UU["pg_launch_event"] | 1)
        self.assertEqual(word(candidate, 0x081B298C + 12 * 4), UU["pg_launch_column_event"] | 1)
        for slot in list(range(3, 14)):
            self.assertEqual(word(candidate, CELL_VT + slot * 4),
                             word(original, CELL_VT + slot * 4))
        table = 0x0819D418 - BASE
        self.assertEqual(candidate[table:table + 32],
                         original[table:table + 32])

    def test_select_does_not_launch_and_replaces_same_track_selection(self):
        p = Launch()
        p.set_clip(0, 0, "A", 0xFFFFFF9C)
        p.set_clip(0, 2, "B", 0xFFFFFF9C)
        p.set_clip(3, 5, "C", 0xFFFFFF9C)
        p.event(0x107A)
        p.select(0, 0)
        p.select(3, 5)
        p.select(0, 2)
        p.event(0x7B, 0, 2)
        self.assertEqual(p.queue(), [])
        pixels = p.paint()
        self.assertEqual(int(pixels[150, 12]), BG)
        self.assertEqual(int(pixels[150 + 2 * 36, 12]), SELECTED)
        self.assertEqual(int(pixels[150 + 5 * 36, 12 + 159 * 3]), SELECTED)
        p.event(0x107B)
        self.assertEqual([(e[0] & 255, e[2], e[3], e[4]) for e in p.queue()],
                         [(0x3E, 100, 0x64, 1), (0x3E, 100, 0x63, 2),
                          (0x3E, 103, 0x64, 1), (0x3E, 103, 0x63, 5)])

    def test_group_stop_uses_native_queue_and_skips_stopped_tracks(self):
        p = Launch()
        p.event(0x107A)
        for track in range(8):
            p.set_clip(track, track, str(track), 0xFFFFFF9C)
            p.select(track, track)
        p.runtime = {0: (40, 0, -1), 2: (-1, -1, 2), 5: (60, 3, 5)}
        p.event(0x107C)
        self.assertEqual([(e[2], e[3], e[4]) for e in p.queue()],
                         [(100, 0x64, 0), (102, 0x64, 0), (105, 0x64, 0)])
        self.assertEqual(p.runtime[0], (40, 0, -1))

    def test_group_play_does_not_restart_playing_or_already_queued_selection(self):
        p = Launch()
        p.event(0x107A)
        for track in range(4):
            p.set_clip(track, track, "Clip", 0)
            p.select(track, track)
        p.runtime = {0: (40, 0, -1), 1: (-1, -1, 1), 2: (60, 0, -1),
                     3: (90, 3, 5)}
        p.event(0x107B)
        self.assertEqual([(e[2], e[3], e[4]) for e in p.queue()],
                         [(102, 0x64, 1), (102, 0x63, 2),
                          (103, 0x64, 1), (103, 0x63, 3)])

    def test_empty_replaced_and_other_project_clips_cannot_be_launched(self):
        p = Launch()
        p.set_clip(0, 0, "A", 0)
        p.event(0x107A)
        p.select(0, 0)
        p.select(0, 4)
        p.e.w(p.cell(0, 0) + 0x278, 0x20002000)
        p.event(0x107B)
        self.assertEqual(p.queue(), [])
        p.select(0, 0)
        p.e.w(MODEL, 0x20004000)
        p.event(0x107B)
        self.assertEqual(p.queue(), [])

    def test_real_native_header_places_actions_immediately_left_of_song(self):
        p = Launch()
        p.e.call(0x08180198, ROOT_HEADER)
        p.e.u.mem_write(MODEL + 0x12C, b"\x1e")
        template = 0x08199008 - BASE + 23 * 0x1C4
        p.e.u.mem_write(OUT, IMAGE[template:template + 0x1C4])
        p.e.call(UU["device_header_prepare"], OUT)
        p.e.call(0x0817FAF8, ROOT_HEADER, OUT)
        for slot, code, label in [(2, 0x107A, "Select"), (3, 0x107B, "Play"),
                                  (4, 0x107C, "Stop"), (5, 0x56, "Song")]:
            button = ROOT_HEADER + 0x54C + slot * 0xD0
            self.assertEqual(p.e.r(button + 0x14), code)
            self.assertEqual(p.e.text(button + 0x6D), label)
            self.assertEqual(bytes(p.e.u.mem_read(button + 0x30, 1)), b"\0")
        p.e.w(ROOT_HEADER + 0x2C, VIEW)
        p.e.u.mem_write(EVENT, struct.pack("<5I", 0x7A, 0, 0x107A, 0, 0))
        p.e.call(0x0817FE70, ROOT_HEADER, EVENT)
        self.assertEqual(bytes(p.e.u.mem_read(MODEL + 0x14D, 1)), b"\1")
        p.e.call(UU["device_header_prepare"], OUT)
        p.e.call(0x0817FAF8, ROOT_HEADER, OUT)
        self.assertEqual(bytes(p.e.u.mem_read(ROOT_HEADER + 0x54C + 2 * 0xD0 + 0xAC, 1)), b"\1")
        p.set_clip(2, 4, "Group", 0xFFFFFF9C)
        p.select(2, 4)
        p.e.u.mem_write(EVENT, struct.pack("<5I", 0x7A, 0, 0x107B, 0, 0))
        p.e.call(0x0817FE70, ROOT_HEADER, EVENT)
        p.runtime[2] = (100, 4, -1)
        p.e.u.mem_write(EVENT, struct.pack("<5I", 0x7A, 0, 0x107C, 0, 0))
        p.e.call(0x0817FE70, ROOT_HEADER, EVENT)
        self.assertEqual([(e[2], e[3], e[4]) for e in p.queue()],
                         [(102, 0x64, 1), (102, 0x63, 4), (102, 0x64, 0)])

    def test_native_column_events_are_unchanged_outside_select_mode(self):
        p = Launch()
        calls = []
        def original(u, address, size, data):
            calls.append(u.reg_read(UC_ARM_REG_R0))
            u.reg_write(UC_ARM_REG_R0, 17)
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        hook = p.e.u.hook_add(UC_HOOK_CODE, original, begin=0x08172A08, end=0x08172A08)
        self.assertEqual(p.event(0x79, 3, 2), 17)
        p.event(0x107A)
        self.assertEqual(p.event(0x79, 3, 0x48), 17)
        p.e.w(VIEW, 0x08190000)
        self.assertEqual(p.event(0x79, 3, 2), 17)
        self.assertEqual(calls, [p.column(3)] * 3)
        p.e.u.hook_del(hook)

    def test_scene_header_retains_its_native_actions(self):
        p = Launch()
        p.e.call(0x08180198, ROOT_HEADER)
        p.e.u.mem_write(MODEL + 0x12C, b"\x21")
        template = 0x08199008 - BASE + 26 * 0x1C4
        native = IMAGE[template:template + 0x1C4]
        p.e.u.mem_write(OUT, native)
        p.e.call(UU["device_header_prepare"], OUT)
        self.assertEqual(bytes(p.e.u.mem_read(OUT + 0x74, 6 * 48)),
                         native[0x74:0x74 + 6 * 48])

    def test_native_audio_launch_quantizer_keeps_playing_clip_until_deadline(self):
        p = Fixture()
        KEEP.append(p)
        track, clock = 0xC0000000, 0xC0010000
        playing, next_clip = track + 0x240, track + 0xA88
        p.w(track + 0x86C0, playing)
        p.w(track + 0x86C4, playing)
        p.w(playing + 4, 1)
        p.u.mem_write(track + 0x20, b"\1")
        p.u.mem_write(next_clip + 0x28, b"\1\0")
        p.f(clock + 0x18, 1.0)
        p.w(clock + 0x30, 100)
        p.w(playing + 0x20, 50)
        # Native property 63 dispatch at 0806259C enters this quantizer.
        p.call(0x0805FA40, track, clock, 1)
        self.assertEqual(p.r(track + 0x86C0), playing)
        self.assertEqual(p.r(track + 0x86C4), next_clip)
        self.assertGreater(p.r(track + 0x86C8), p.r(clock + 0x30))

    def test_queued_outline_pulses_while_playing_triangle_remains_solid(self):
        p = Launch()
        p.set_clip(0, 0, "Play", 500)
        p.set_clip(1, 0, "Queue", 0xFFFFFF38)
        p.runtime[1] = (-1, -1, 0)
        p.e.w(0x3001FE2C, 0)
        pixels = p.paint()
        self.assertEqual(int(pixels[158, 20]), TEXT)
        self.assertEqual(int(pixels[158, 179]), BG)
        self.assertEqual(int(pixels[158, 176]), p.e.call(0x08140EBC, 1))
        p.e.w(0x3001FE2C, 250)
        p.e.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.e.call(p.e.r(LAUNCH_VT), VIEW, render.CTX)
        self.assertEqual(p.e.u.mem_read(render.CTX + 1, 1), b"\1")
        p.e.call(p.e.r(CELL_VT + 4), p.cell(1, 0), render.CTX)
        pixels = render.ui(p.e)
        self.assertEqual(int(pixels[158, 176]), TEXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
