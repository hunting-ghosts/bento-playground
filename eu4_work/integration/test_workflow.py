"""Shift-free navigation and the real native footer/parameter widgets."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import json
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
        return self.call(UU["seq_nav_global"], perf.M, perf.EV)

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
        self.assertEqual(p.u.mem_read(perf.OUT, 1), b"\3")
        self.assertEqual(p.keys(1)[0], [0] * 8)
        self.assertEqual(p.button(0xaf, 15), 0)
        self.assertEqual(p.button(0xb0, 15), 0)
        # Run 18: Left on Perform selects the previous track (consumed; track 1 has none), still never shift.
        self.assertEqual(p.button(0xaf, 0), 1)
        self.assertEqual(p.r(perf.LOCK + 8), 0)
        self.assertEqual(p.r(perf.MASK), 0)

    def test_four_views_preserve_project_file_actions(self):
        p = self.page()
        p.call(0x08180198, ROOT)
        for key, page in [(0x1072, 0x1a), (0x1074, 0x1a),
                          (0x1071, 0x1a), (0x1075, 0x13)]:
            self.assertEqual(p.tab(key), 1)
            self.assertEqual(p.u.mem_read(perf.M + 0x12c, 1)[0], page)
            index = 5 if page == 0x13 else 20
            p.u.mem_write(perf.OUT, IMAGE[0x08199008 - 0x08040000 + index * N.HDR_SIZE:][:N.HDR_SIZE])
            p.call(UU["device_header_prepare"], perf.OUT)
            p.call(0x0817faf8, ROOT, perf.OUT)
            ids = [struct.unpack("<H", p.u.mem_read(perf.OUT + N.HDR(0x74) + i * 48 + 44, 2))[0] for i in range(6)]
            # exp6 (owner, exp5 photos): one footer on all four PROJ views: the four tabs in slots 0..3 (the
            # current one lit), the view's actions beside them (Projects Save/Load, Settings Set Time (exp7: slot 5 empty),
            # Perform/Macro Motion). Earlier layouts (R6.4 browser Save/Load only, exp5 label) are replaced.
            tabs = [0x1071, 0x1072, 0x1074, 0x1075]
            actions = {0x1075: [0x8f, 0x8b], 0x1074: [0x36, 0], 0x1072: [0, 0x1076]}.get(key, [0x1073, 0x1076])  # exp7: Settings slot 5 empty; run 18: Perform Tap | Motion
            self.assertEqual(ids, tabs + actions)
            active = tabs.index(key)
            self.assertEqual([p.u.mem_read(ROOT + N.ROOT_TABS + i * 0xd0 + 0xac, 1)[0]
                              if p.u.mem_read(ROOT + N.ROOT_TABS + i * 0xd0 + 0x30, 1) == b"\0" else 0
                              for i in range(6)],
                             [int(i == active) for i in range(6)])
        p.w(0x3001fe2c,p.r(0x3001fe2c)+1000)
        p.button(0xaf, 7)
        self.assertEqual(p.u.mem_read(perf.M + 0x12c, 1)[0], 0x1a)

    def test_native_fx_defaults_to_settings_and_remembers_xy_until_reboot(self):
        # P168 exp8 FX views: the footer taps are Mod FX (1066), Send FX (1067), XY Pads (1068).
        # 1.6.1 keeps the original footer (no FX views): xy (1067) and FX Settings (1068).
        xy,fx=(0x1068,0x1066) if N.BENTO_FW==168 else (0x1067,0x1068)
        p=self.page()
        self.assertEqual(p.call(UU["native_fx_page"],0x0c),0x0b)
        p.u.mem_write(perf.M+0x12c,b"\x0b")
        self.assertEqual(p.tab(xy),1)                           # XY Pads -> page 0C
        self.assertEqual(p.u.mem_read(perf.M+0x12c,1),b"\x0c")
        self.assertEqual(p.call(UU["native_fx_page"],0x0c),0x0c)
        self.assertEqual(p.call(UU["native_fx_page"],2),2)
        self.assertEqual(p.call(UU["native_fx_page"],0x0c),0x0c)
        self.assertEqual(p.tab(fx),1)                           # Mod FX (1.6.1: FX Settings) -> page 0B
        self.assertEqual(p.call(UU["native_fx_page"],0x0c),0x0b)
        fresh=self.page()
        self.assertEqual(fresh.call(UU["native_fx_page"],0x0c),0x0b)

    def test_native_fx_real_templates_have_independent_white_view_tabs(self):
        # P168 exp8 FX views footer Mod FX | Send FX | XY Pads in slots 3,4,5; page 0B (active section 0) marks
        # Mod FX, page 0C marks XY Pads.
        p=self.page()
        p.call(0x08180198,ROOT)
        # 1.6.1 (no FX views): the original xy (slot 4) / FX Settings (slot 5) tabs.
        views=((0x0b,16,3),(0x0c,17,5)) if N.BENTO_FW==168 else ((0x0b,16,5),(0x0c,17,4))
        tabs=((3,0x1066),(4,0x1067),(5,0x1068)) if N.BENTO_FW==168 else ((4,0x1067),(5,0x1068))
        for page,index,lit in views:
            p.u.mem_write(perf.M+0x12c,bytes([page]))
            start=0x08199008-0x08040000+index*N.HDR_SIZE
            p.u.mem_write(perf.OUT,IMAGE[start:start+N.HDR_SIZE])
            p.call(UU["device_header_prepare"],perf.OUT)
            p.call(0x0817faf8,ROOT,perf.OUT)
            for slot,key in tabs:
                rec=perf.OUT+N.HDR(0x74)+slot*48
                self.assertEqual(p.u.mem_read(rec+44,2),struct.pack("<H",key))
                self.assertEqual(p.u.mem_read(rec+0x21,1),bytes([slot==lit]))
                self.assertEqual(p.u.mem_read(ROOT+N.ROOT_TABS+slot*0xd0+0xac,1),
                                 bytes([slot==lit]))

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
                expected=[N.NUI(0x1014), N.NUI(0x1013), N.NUI(0x1018), 0x1062, 0x1063, N.NUI(0x101d)]
                diagnostic=perf.CANDIDATE/"DIAGNOSTIC_MANIFEST.json"
                if diagnostic.exists() and json.loads(diagnostic.read_text()).get("matched_candidate"):
                    expected.append(0x107e)
                self.assertEqual([p.r(m + 4 + j * 20) for j in range(p.u.mem_read(m + 0xcc, 1)[0])],expected)

    def test_settings_scopes_and_native_date_apply_row(self):
        p = self.page()
        p.tab(0x1074)
        p.header()
        rows = p.keys(3)
        self.assertEqual(rows[0], [0x83, 0xa2, 0xa3, 0xe1, 0x67, 0xa4, 0xa8, 0])
        self.assertEqual(rows[1], [N.NKEY(0x1d4), N.NKEY(0x1d5), N.NKEY(0x1d6), 0, 0, 0, N.NKEY(0x1d7), N.NKEY(0x1d8)])
        self.assertEqual(rows[2], [0x102, 0x11c, N.NKEY(0x178), 0, 0, 0, 0, 0])
        self.assertEqual(p.text(p.r(perf.OUT + 4)), "Global Settings")  # exp6: the label is plain text in the footer
        self.assertEqual(p.text(p.r(perf.OUT + 8)), "Date and Time")
        self.assertEqual(p.text(p.r(perf.OUT + 12)), "Pads / Track 1")
        p.edit(0x83, 1)
        self.assertEqual(p.model_events[-1], (0xcf, 0xfffffffe, 0x83, 1))
        p.edit(0x11c, 87)
        self.assertEqual(p.get(0x11c), 87)
        p.edit(N.NKEY(0x178), 2)
        self.assertEqual(p.model_events[-1], (0xcf, p.track, N.NKEY(0x178), 2))
        p.track = 0x92
        self.assertEqual(p.get(0x11c), 100)

    def test_real_native_three_row_construction_stays_in_bounds(self):
        p = self.page()
        p.tab(0x1071)
        v = p.real_view()
        self.assertEqual(p.u.mem_read(v + 0x93c4, 1), b"\3")
        self.assertEqual(p.r(v + 0x9018 + 0x204), 3)
        bars = [v + 0x38 + 0x23f8 * i for i in range(3)]
        rects = []
        for b in bars:
            rect = [p.r(b + o) for o in (4, 8, 12, 16)]
            rects.append(rect)
            self.assertGreater(rect[2], 0)
            self.assertGreater(rect[3], 0)
            self.assertGreaterEqual(rect[1], 60)
            self.assertLessEqual(rect[1] + rect[3], 480)
        self.assertEqual(len(set(r[1] for r in rects)), 3)
        # Run 18 (native_perform.png): top area (strip, chord name, piano) 0..200, Chord row 206, Arp row 314.
        self.assertEqual([r[1] for r in rects], [280, 185, 77])
        self.assertEqual([r[3] for r in rects], [200, 89, 89])
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
        self.assertEqual(p.r(ROOT + N.ROOT_SLOTS + 12), 157)
        p.page(7)
        p.call(UU["workflow_periodic"])
        self.assertEqual(p.r(ROOT + N.ROOT_SLOTS + 12), 157)

    def test_undo_in_sequence_burgers_without_duplicate_or_overflow(self):
        p = self.page()
        p.call(0x081412ec)
        # R6: mode 1 (sequencer pages) writes the shared burger, mode 2 the
        # Performance burger; mode 0 leaves the menus as they are.
        p.u.mem_write(0x30024b00 + 0x12c, b"\x17")
        for mode in [1, 1, 2, 1, 0]:
            p.call(UU["seq_nav_menus"], mode)
            for i in range(20):
                menu = 0x30030168 + i * 0xe0
                if p.r(menu) != 0xf9:
                    continue
                count = p.u.mem_read(menu + 0xcc, 1)[0]
                keys = [p.r(menu + 4 + j * 20) for j in range(count)]
                self.assertLessEqual(count, 9)
                self.assertEqual(keys.count(N.NUI(0x1032)), 1 if mode == 1 else 0)  # R6.10: stock F9 outside the sequencers

    def test_no_retired_recorder_payload_or_native_hook_changes(self):
        baseline = Path(os.environ["BENTO_K16_IMAGE"]).read_bytes()
        for symbols in (UU, AA):
            self.assertFalse([name for name in symbols if name.startswith(("nm_", "native_motion_", "workflow_header_"))])
        # R6.13: the retired recorder's gap holds only the ratchet player (M7):
        # unchanged K16 bytes around exactly the "R6.13 ratchet playback" write.
        import json
        writes = json.loads((Path(os.environ["BENTO_FX_CANDIDATE"]) / "manifest.json").read_text())["writes"]
        ratchet = [w for w in writes if w["reason"].startswith("R6.13 ratchet playback")]
        lo, hi = 0x080cf4a0, 0x080cf4a0 + 0xb60
        if ratchet and N.FW168:
            # 1.6.8 port: the stock image uses most of that gap, so the player is split over three
            # checked zero slots (HANDOVER section 6). Same guarantees per slot: both entry points
            # inside a slot, and nothing else changed in the old gap range.
            self.assertEqual(len(ratchet), 3)
            slots = sorted((w["address"], w["address"] + w["size"]) for w in ratchet)
            self.assertTrue(all(a_end <= b_start for (_, a_end), (b_start, _) in zip(slots, slots[1:])))
            self.assertTrue(all(any(start <= AA[n] < end for start, end in slots) for n in ("rt_note", "rt_block")))
            cursor = lo
            for start, end in [x for x in slots if lo <= x[0] < hi] + [(hi, hi)]:
                self.assertEqual(IMAGE[cursor - 0x08040000:start - 0x08040000], baseline[cursor - 0x08040000:start - 0x08040000], hex(cursor))
                cursor = end
        elif ratchet:
            self.assertEqual(len(ratchet), 1)
            start, end = ratchet[0]["address"], ratchet[0]["address"] + ratchet[0]["size"]
            self.assertTrue(lo + 0x20 <= start and end <= 0x080cfff0)
            self.assertTrue(all(start <= AA[n] < end for n in ("rt_note", "rt_block")))
            for a, b in [(lo, start), (end, hi)]:
                self.assertEqual(IMAGE[a - 0x08040000:b - 0x08040000], baseline[a - 0x08040000:b - 0x08040000], hex(a))
        else:
            self.assertEqual(IMAGE[lo - 0x08040000:hi - 0x08040000], baseline[lo - 0x08040000:hi - 0x08040000])
        for address, size in [
            (0x08058500, 32), (0x080d15f0, 16),
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
