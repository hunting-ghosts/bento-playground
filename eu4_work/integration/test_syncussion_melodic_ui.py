"""Melodic carrier selection, native menu capacity and sample-editor routing."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest
import os
from pathlib import Path

if os.environ.get("BENTO_UI_FOCUSED") == "1":
    import test_integration as integration
    from kit_seq_fixture import current_ui
    integration.IMAGE, integration.UU = current_ui(
        integration.IMAGE, integration.MANIFEST,
        Path(__file__).resolve().parents[2] / "build/next-ui-check")
    integration.Fixture.__init__.__defaults__ = (integration.IMAGE,)

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

from test_drum_menu import Drum, CELL, EV, FILE, TRACK, VIEW
from test_integration import UU, IMAGE, CANDIDATE
from test_syncussion_ui import Panel, VIEW as PANEL_VIEW, POINT


class Tests(unittest.TestCase):
    """Run 14 (owner, 13 Nov): melodic Syncussion is retired. The Multisample menu no longer offers it, a
    Multisample carrier is not a drum-synth editor, and drum_assign only serves one-shot tracks (engine<=5).
    The tests of the removed melodic editor/menu/assignment went with the feature; an old project's melodic
    carrier still plays (audible, pitched) - covered by test_drum_audio and the project roundtrip, not here."""
    def test_multisample_menu_has_no_drum_synth_entry(self):
        p = Drum()
        p.track_type = 15
        p.pad = 3
        p.model_event(0xf1)
        self.assertNotIn(0x1056, [c[0] for c in p.menu(0xf1)])
        self.assertNotIn("Syncussion", [c[1] for c in p.menu(0xf1)])

    def test_one_shot_menu_label_is_drum_synth_and_never_duplicates(self):
        p = Drum()
        for track_type, present in ((14, True), (15, False), (14, True), (15, False)):
            p.track_type = track_type
            p.model_event(0xf1)
            ours = [c for c in p.menu(0xf1) if c[0] == 0x1056]
            self.assertEqual(ours, [(0x1056, "Drum Synth", 1)] if present else [])

    def test_drum_assign_rejects_multisample_tracks_and_the_melodic_engine(self):
        p = Drum()
        p.track_type = 15
        self.assertEqual(p.call(UU["drum_assign"], 0, 0, 0), 0)
        self.assertEqual(p.assigned, [])
        self.assertEqual(p.files, {})
        p = Drum()
        p.track_type = 14
        self.assertEqual(p.call(UU["drum_assign"], 0, 0, 6), 0)  # engine 6 (melodic carrier) no longer exists

    def test_multisample_carrier_is_not_a_drum_editor(self):
        p = Drum()
        p.path = "Drum Synths\\Syncussion Melodic.wav"
        p.w(VIEW + 0x87bc, CELL)
        p.w(VIEW + 0x87c4, FILE)
        p.u.mem_write(VIEW + 0x87cc, b"\x0f")
        self.assertEqual(p.call(UU["kick_ui_supported"], VIEW), 0)
        p.path = "Drum Synths\\Metal.wav"
        p.u.mem_write(VIEW + 0x87cc, b"\x0e")
        self.assertEqual(p.call(UU["kick_ui_supported"], VIEW), 15)  # Metal on a one-shot track still is


class TracksMenu(Drum):
    """Real model dispatcher, track constructor, property tree and assignment.

    Allocation, audio/worker notifications, SD files and navigation are the
    external boundaries. No view-parent or track-creation success is invented.
    """

    def __init__(self, occupied=()):
        self.posted = []
        super().__init__()
        self.tree, self.tree_next = N.SDRAM_TOP+0x100000, N.SDRAM_TOP+0x110000
        self.u.mem_map(self.tree, 0x100000)
        self.w(0x30024b00, self.tree)
        self.w(0x30000088, 100)
        self.created = []
        self.messages = []
        for index in occupied:
            self.call(0x0813de80, 0x30024b00, 3, index)
        self.created.clear()
        self.index = 2

    def native(self, u, a, n, d):
        if not hasattr(self, "tree"):
            return super().native(u, a, n, d)
        r = [u.reg_read(reg) for reg in
             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)]
        if a == 0x08101fb4:
            self.w(r[2], self.tree_next)
            self.tree_next += (r[1]+31) & ~31
            self.ret(1)
            return
        if a == 0x081283cc:
            u.mem_write(r[0], self.text(r[2]).encode()+b"\0")
            self.ret()
            return
        if a == 0x08133614 and r[1] == 0x30030164 and r[2] == 0x131:
            return super().native(u, a, n, d)
        if a in (0x08133614, 0x08133960, 0x08133cfc, 0x08133f7c,
                 0x0813391a, 0x0813390e):
            return
        if a == 0x0813de80:
            self.created.append((r[1], r[2]))
            return
        if a == 0x081403ec:
            self.posted.append(struct.unpack("<5I", u.mem_read(r[1], 20)))
            return
        if a == 0x08139de0:
            return
        if a == 0x0813bc3c:
            self.index = r[1]
            self.ret()
            return
        if a in (0x0813ccb8, 0x0813130c, 0x081361b4, 0x0810b5c8,
                 0x0810b650, 0x0810b6fc, 0x0810bc98, 0x0810bca6,
                 0x0810bcb4, 0x0810bcd0, 0x0810e0b8, 0x0810b960,
                 0x08139138, 0x08132ccc):
            self.ret()
            return
        if a == 0x081420ec:
            self.opened = tuple(u.reg_read(reg) for reg in
                                (UC_ARM_REG_R1, UC_ARM_REG_R2))
            self.ret()
            return
        if a == 0x0816085c:
            self.native_tracks = getattr(self, "native_tracks", 0) + 1
            self.ret(1)
            return
        if a == 0x08104c00:
            self.messages = getattr(self, "messages", []) + [self.text(u.reg_read(UC_ARM_REG_R0))]
            self.ret()
            return
        super().native(u, a, n, d)

    def hook(self, u, a, n, d):
        if hasattr(self, "tree") and a in (0x08133960, 0x0812dc74):
            return
        super().hook(u, a, n, d)

    def track(self, index):
        self.call(0x08133960, 0x30024b00, index, EV+100)
        return self.r(EV+100)


class TracksEntry(unittest.TestCase):
    def test_tracks_menu_no_longer_offers_syncussion(self):
        # R6.3/R6.4 (owner): Syncussion removed; its metallic sound lives on as
        # Metal. The Tracks view keeps its native event handler.
        p = TracksMenu()
        cells = p.menu(0xf0)
        self.assertEqual(len(cells), 8)
        self.assertNotIn("Syncussion", [c[1] for c in cells])
        self.assertNotEqual(cells[-1][0], 0x105a)
        self.assertEqual([c[0] for c in cells[:-1]],
                         [0x1004, 0x2d, 0x1006, 0x1005, 0x1001, 0x1002, 0x1003])
        self.assertEqual(struct.unpack_from("<I", IMAGE, 0x0819eaf8 - 0x08040000)[0], 0x0816085d)
        self.assertEqual(len(p.menu(0xf6)), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
