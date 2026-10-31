"""Shift-free navigation and the real native footer/parameter widgets."""
import struct
import unittest
import os
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
import test_perf as perf
from test_integration import IMAGE, UU, AA
from test_encoder_speed import install_probe

KEEP = []
ROOT = 0x30034d48


class Page(perf.Page):
    def registry(self):
        install_probe(self)
        super().registry()

    def __init__(self):
        super().__init__()
        self.h.append(self.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: self.w(0x3000004c, self.next),
                                     begin=0x08104c08, end=0x08104c08))

    def open(self):
        self.button(0xaf, 7)
        self.button(0xb0, 7)

    def tab(self, key):
        self.u.mem_write(perf.EV, struct.pack("<5I", key, 0, 0, 0, 0))
        return self.call(UU["perf_navigation"], perf.EV)

    def real_view(self):
        self.view = 0xc0000000
        self.call(0x08145b7c, self.view)
        self.w(0x20016000, 0xfffffffe)
        self.call(0x08145efc, self.view, 0x20016000)
        return self.view


class Tests(unittest.TestCase):
    def test_idle_workflow_does_not_allocate_perform_before_first_use(self):
        p = Page()
        KEEP.append(p)
        cursor = p.next
        slot = p.call(UU["perf_state_slot"])
        self.assertEqual(p.r(slot), 0)
        for _ in range(8):
            p.call(UU["workflow_periodic"])
            p.call(UU["workflow_nav"])
        self.assertEqual(p.next, cursor)
        self.assertEqual(p.r(slot), 0)
        p.open()
        self.assertNotEqual(p.r(slot), 0)
        allocated = p.next
        p.call(UU["workflow_periodic"])
        self.assertEqual(p.next, allocated)

    def page(self):
        p = Page()
        KEEP.append(p)
        p.open()
        return p

    def test_proj_press_opens_perform_release_never_sets_shift(self):
        p = self.page()
        self.assertEqual(p.navs, [0x1a])
        self.assertEqual(p.r(perf.LOCK + 8), 0)
        self.assertEqual(p.r(perf.MASK), 0)
        p.header()
        self.assertEqual(p.u.mem_read(perf.OUT, 1), b"\2")
        self.assertEqual(p.keys(2)[0], [0] * 8)
        self.assertEqual(p.keys(2)[1], [0x132, 0x14a, 0x144, 0xa7, 0xaa, 0xb2, 0xb3, 0xa6])
        self.assertEqual(p.button(0xaf, 15), 0)
        self.assertEqual(p.button(0xb0, 15), 0)
        self.assertEqual(p.button(0xaf, 0), 0)

    def test_four_views_preserve_project_file_actions(self):
        p = self.page()
        p.call(0x08180198, ROOT)
        for key, page in [(0x1072, 0x1a), (0x1074, 0x1a),
                          (0x1071, 0x1a), (0x1075, 0x13)]:
            self.assertEqual(p.tab(key), 1)
            self.assertEqual(p.u.mem_read(perf.M + 0x12c, 1)[0], page)
            index = 5 if page == 0x13 else 20
            p.u.mem_write(perf.OUT, IMAGE[0x08199008 - 0x08040000 + index * 0x1c4:][:0x1c4])
            p.call(UU["device_header_prepare"], perf.OUT)
            p.call(0x0817faf8, ROOT, perf.OUT)
            ids = [struct.unpack("<H", p.u.mem_read(perf.OUT + 0x74 + i * 48 + 44, 2))[0] for i in range(6)]
            if page == 0x13:
                self.assertEqual(ids, [0x1075, 0x1076, 0, 0, 0x8f, 0x8b])
            else:
                self.assertEqual(ids[:4], [0x1071, 0x1072, 0x1074, 0x1075])
            active = 1 if key == 0x1072 else 2 if key == 0x1074 else 0
            self.assertEqual([p.u.mem_read(ROOT + 0xa2c + i * 0xd0 + 0xac, 1)[0]
                              for i in range(4)],
                             [int(i == active) for i in range(4)])
            if key == 0x1074:
                self.assertEqual(ids[5], 0x36)
        p.button(0xaf, 7)
        self.assertEqual(p.u.mem_read(perf.M + 0x12c, 1)[0], 0x1a)

    def test_macro_overview_and_detail_share_one_encoder_row(self):
        p = self.page()
        self.assertEqual(p.tab(0x1072), 1)
        self.assertEqual(p.header(), 1)
        self.assertEqual(p.u.mem_read(perf.OUT, 1), b"\1")
        self.assertEqual(p.keys(1), [[0] * 8])
        self.assertEqual(p.button(0xaf, 8), 1)
        self.assertEqual(p.call(UU["perf_macro_targets"]), 1)
        self.assertEqual(p.button(0xb0, 8), 1)
        self.assertEqual(p.button(0xaf, 9), 1)
        self.assertEqual(p.call(UU["perf_macro_focus"], 0xffffffff), 1)
        self.assertEqual(p.button(0xb0, 9), 1)
        self.assertEqual(p.button(0xaf, 1), 1)
        self.assertEqual(p.call(UU["perf_macro_targets"]), 0)
        self.assertEqual(p.button(0xb0, 1), 1)
        p.call(0x081412ec)
        p.call(UU["seq_nav_menus"], 2)
        for i in range(20):
            m = 0x30030168 + i * 0xe0
            if p.r(m) == 0xf5:
                self.assertEqual([p.r(m + 4 + j * 20) for j in range(p.u.mem_read(m + 0xcc, 1)[0])],
                                 [0x1014, 0x1013, 0x1018, 0x100a])

    def test_settings_scopes_and_native_date_apply_row(self):
        p = self.page()
        p.tab(0x1074)
        p.header()
        rows = p.keys(3)
        self.assertEqual(rows[0], [0x83, 0xa2, 0xa3, 0xe1, 0x67, 0xa4, 0xa8, 0])
        self.assertEqual(rows[1], [0x1d4, 0x1d5, 0x1d6, 0, 0, 0, 0x1d7, 0x1d8])
        self.assertEqual(rows[2], [0x102, 0x11c, 0x178, 0, 0, 0, 0, 0])
        self.assertEqual(p.text(p.r(perf.OUT + 4)), "Global Settings")
        self.assertEqual(p.text(p.r(perf.OUT + 8)), "Date and Time")
        self.assertEqual(p.text(p.r(perf.OUT + 12)), "Pads / Track 1")
        p.edit(0x83, 1)
        self.assertEqual(p.model_events[-1], (0xcf, 0xfffffffe, 0x83, 1))
        p.edit(0x11c, 87)
        self.assertEqual(p.get(0x11c), 87)
        p.edit(0x178, 2)
        self.assertEqual(p.model_events[-1], (0xcf, p.track, 0x178, 2))
        p.track = 0x92
        self.assertEqual(p.get(0x11c), 100)

    def test_real_native_two_row_construction_stays_in_bounds(self):
        p = self.page()
        v = p.real_view()
        self.assertEqual(p.u.mem_read(v + 0x93c4, 1), b"\2")
        self.assertEqual(p.r(v + 0x9018 + 0x204), 2)
        bars = [v + 0x38 + 0x23f8 * i for i in range(2)]
        rects = []
        for b in bars:
            rect = [p.r(b + o) for o in (4, 8, 12, 16)]
            rects.append(rect)
            self.assertGreater(rect[2], 0)
            self.assertGreater(rect[3], 0)
            self.assertGreaterEqual(rect[1], 64)
            self.assertLessEqual(rect[1] + rect[3], 480)
        self.assertEqual(len(set(r[1] for r in rects)), 2)
        self.assertEqual([r[1] for r in rects], [278, 178])
        self.assertEqual([r[3] for r in rects], [194, 90])
        for a, b in zip(rects, rects[1:]):
            self.assertGreaterEqual(a[1], b[1] + b[3])

    def test_native_footer_geometry_is_unchanged_without_motion_widget(self):
        p = self.page()
        p.call(0x08180198, ROOT)
        p.page(0x27)
        p.call(UU["workflow_periodic"])
        before = bytes(p.u.mem_read(ROOT, 0x11a0))
        cursor = p.next
        for _ in range(128):
            p.call(UU["workflow_periodic"])
        self.assertEqual(bytes(p.u.mem_read(ROOT, 0x11a0)), before)
        self.assertEqual(p.next, cursor)
        self.assertEqual(p.r(ROOT + 0x54c + 12), 157)
        p.page(7)
        p.call(UU["workflow_periodic"])
        self.assertEqual(p.r(ROOT + 0x54c + 12), 157)

    def test_undo_in_sequence_burgers_without_duplicate_or_overflow(self):
        p = self.page()
        p.call(0x081412ec)
        for mode in [1, 1, 2, 0, 0]:
            p.call(UU["seq_nav_menus"], mode)
            for i in range(20):
                menu = 0x30030168 + i * 0xe0
                if p.r(menu) != 0xf9:
                    continue
                count = p.u.mem_read(menu + 0xcc, 1)[0]
                keys = [p.r(menu + 4 + j * 20) for j in range(count)]
                self.assertLessEqual(count, 9)
                self.assertEqual(keys.count(0x1032), 0 if mode == 2 else 1)

    def test_no_retired_recorder_payload_or_native_hook_changes(self):
        baseline = Path(os.environ["BENTO_K16_IMAGE"]).read_bytes()
        for symbols in (UU, AA):
            self.assertFalse([name for name in symbols if name.startswith(("nm_", "native_motion_", "workflow_header_"))])
        for address, size in [
            (0x080cf4a0, 0xb60), (0x08058500, 32), (0x080d15f0, 16),
            (0x08062216, 4), (0x0812ea2a, 4), (0x081366ca, 4),
            (0x0812f864, 4), (0x081367e8, 4),
            (0x081b3680, 4), (0x081b3688, 4), (0x081b36a8, 4),
        ]:
            offset = address - 0x08040000
            self.assertEqual(IMAGE[offset:offset + size], baseline[offset:offset + size], hex(address))
        offset = 0x081b283c - 0x08040000
        expected = struct.pack("<I", UU["pg_bar_paint"] | 1) if "pg_bar_paint" in UU else baseline[offset:offset + 4]
        self.assertEqual(IMAGE[offset:offset + 4], expected)
        self.assertIn(IMAGE[0x0818bad4 - 0x08040000:][:7],
                      (b"1.6W2\0\0", b"1.6W3\0\0", b"1.6W4\0\0", b"1.6W5\0\0", b"1.6W6\0\0", b"1.6W7\0\0", b"1.6W8\0\0", b"1.6W9\0\0", b"1.6W10\0", b"1.6W11\0", b"1.6W13\0", b"1.6W14\0", b"1.6W15\0", b"1.6W16\0", b"1.6W17\0", b"1.6W18\0", b"1.6W19\0", b"1.6W20\0", b"1.6W21\0", b"1.6W22\0"))


if __name__ == "__main__":
    unittest.main()
