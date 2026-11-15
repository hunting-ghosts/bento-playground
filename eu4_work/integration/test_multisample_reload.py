"""Native track reconstruction around project load: real native code, not SD/hardware proof.

P168 exp4: the former post-load workaround (a second rebuild of every Multisample/Wavetable track from the
completion event 3F) is gone. Native load completion 0813EF04 already rebuilds every track in
SessionMgr::FinalizeBankLoading (0813E618 -> 0813CCB8) before 3F is posted; since run 5 the workaround
really ran and the owner's exp3 Multisamples were silent and Wavetables lost their wave (hardware). The
expectations below changed from "rebuilt once more after 3F" to the stock behaviour, "not rebuilt after 3F"
(oracle: test_project_roundtrip, stock image round trip). The explicit rebuild after inserting a melodic
carrier (a user action, not a load) is unchanged.
Run 15: the melodic Syncussion insert is retired (run 14); the reconstruction oracle runs on an ordinary
Multisample zone, and the retired path's absence plus an old project's carrier zone are tested separately.

The native model tree, zone properties and Multisample reconstruction execute.
Only allocator, RTOS/audio queue and filesystem boundaries are controlled.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import unittest

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3
from test_syncussion_melodic_ui import TracksMenu
from test_drum_menu import EV
from test_integration import UU

MODEL = 0x30024b00


class Reload(TracksMenu):
    def __init__(self):
        self.rebuilding = False
        self.reloads = []
        self.opens = []
        super().__init__()

    def native(self, u, a, n, d):
        if self.rebuilding:
            args = [u.reg_read(reg) for reg in
                    (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            if a == 0x0813ccb8:
                self.reloads.append(args[1])
                return
            if a == 0x08132ccc:
                return
            if a == 0x081152c0:
                self.clock = getattr(self, "clock", 0) + 1
                self.ret(self.clock)
                return
            if a == 0x0810e0b8:
                self.opens.append((args[1], self.text(args[2]), args[3]))
                self.ret()
                return
            if a in (0x081082d8, 0x0810b782, 0x0810b7aa, 0x0810b7d4):
                self.ret()
                return
        super().native(u, a, n, d)

    def press(self, code):
        # R6.4: the Tracks-menu action is retired (owner); existing melodic
        # carrier tracks still reload. Build the same track through the native
        # calls the action used: native type-3 creation in the first empty slot,
        # select it, assign the melodic carrier.
        import struct
        assert code == 0x105a
        index = next(i for i in ((self.index+n) & 7 for n in range(8)) if not self.track(i))  # from the selected track, as the action did
        self.call(0x0813de80, MODEL, 3, index)  # native Multisample creation (type 3)
        self.call(0x0813bc3c, MODEL, index)
        self.call(UU["drum_assign"], 0, 0, 6)

    def object(self, handle):
        self.call(0x0812d80e, self.tree, handle, EV+104)
        return self.r(EV+104)

    def loaded(self, handle):
        self.call(UU["fx_load"], EV+200, self.object(handle))

    def finish(self, event=0x3f):
        self.w(EV, event)
        self.rebuilding = True
        try:
            self.call(UU["fx_finish"], 0, EV)
        finally:
            self.rebuilding = False


class Tests(unittest.TestCase):
    def test_ordinary_melodic_zone_reopens_through_real_native_reconstruction(self):
        # Run 15: the melodic Syncussion insert was retired in run 14 (owner); the reconstruction oracle now
        # runs on an ordinary Multisample zone. Native type-3 creation, native zone insert, native rebuild.
        p = Reload()
        p.call(0x0813de80, MODEL, 3, 2)
        p.call(0x0813bc3c, MODEL, 2)
        track = p.track(2)
        self.assertTrue(track)
        p.u.mem_write(EV+256, b"Samples\\low.wav\0")
        p.w(EV+100, 0)
        p.call(0x08139de0, MODEL, 2, EV+100, 1, EV+256, 0)
        p.rebuilding = True
        p.call(0x0813ccb8, MODEL, track)
        p.rebuilding = False
        self.assertEqual(p.reloads[-1], track)
        self.assertIn("Samples\\low.wav", [path for _, path, _ in p.opens])
        self.assertFalse(p.messages)
        self.assertEqual(p.index, 2)

    def test_retired_melodic_syncussion_insert_is_absent_and_an_old_carrier_zone_still_reloads(self):
        # The retired path: assigning the former melodic engine (6) on a Multisample track does nothing
        # (no zone, no rebuild, no carrier open, no error message, model unchanged).
        p = Reload()
        p.press(0x105a)
        track = p.track(2)
        self.assertTrue(track)
        before = bytes(p.u.mem_read(p.tree, p.tree_next-p.tree))
        p.rebuilding = True
        self.assertEqual(p.call(UU["drum_assign"], 0, 0, 6), 0)
        self.assertEqual(p.call(UU["drum_assign"], 0, 0, 5), 0)  # no drum carrier on a Multisample either
        p.rebuilding = False
        self.assertEqual(p.reloads, [])
        self.assertEqual(p.opens, [])
        self.assertFalse(p.messages)
        self.assertEqual(bytes(p.u.mem_read(p.tree, p.tree_next-p.tree)), before)
        # An old project: its zone still names the former carrier. The load's native rebuild reopens it like
        # any zone (it plays as pitched Metal: test_drum_audio), and the 3F completion adds no second rebuild.
        p.u.mem_write(EV+256, b"Drum Synths\\Syncussion Melodic.wav\0")
        p.w(EV+100, 0)
        p.call(0x08139de0, MODEL, 2, EV+100, 0, EV+256, 0)
        p.rebuilding = True
        p.call(0x0813ccb8, MODEL, track)
        p.rebuilding = False
        self.assertEqual(p.reloads, [track])
        self.assertIn("Drum Synths\\Syncussion Melodic.wav", [path for _, path, _ in p.opens])
        p.reloads.clear()
        p.loaded(track)
        p.finish()
        self.assertEqual(p.reloads, [])
        self.assertFalse(p.messages)

    def test_project_completion_leaves_the_native_rebuild_alone_and_preserves_model(self):
        p = Reload()
        p.press(0x105a)
        track = p.track(2)
        for pad, path in ((1, "Samples\\low.wav"), (2, "Samples\\high.wav")):
            p.u.mem_write(EV+256, path.encode()+b"\0")
            p.w(EV+100, 0)
            p.call(0x08139de0, MODEL, 2, EV+100, pad, EV+256, 0)
        # A real project load already runs this constructor, including lazy
        # default sequence names, before publishing its completion event.
        p.rebuilding = True
        p.call(0x0813ccb8, MODEL, track)
        p.rebuilding = False
        p.reloads.clear()
        p.opens.clear()
        p.loaded(track)
        before = bytes(p.u.mem_read(p.tree, p.tree_next-p.tree))
        selection = p.index
        p.finish()
        self.assertEqual(p.reloads, [])  # exp4: the native constructor above was the load's rebuild
        self.assertEqual(p.opens, [])
        self.assertEqual(bytes(p.u.mem_read(p.tree, p.tree_next-p.tree)), before)
        self.assertEqual(p.index, selection)
        p.finish()
        self.assertEqual(p.reloads, [])
        p.loaded(track)
        p.finish()
        self.assertEqual(p.reloads, [])

    def test_noncompletion_events_and_unloaded_tracks_do_not_reload(self):
        p = Reload()
        p.press(0x105a)
        track = p.track(2)
        p.finish()
        self.assertEqual(p.reloads, [])
        p.loaded(track)
        p.finish(0x40)
        self.assertEqual(p.reloads, [])
        p.finish()
        self.assertEqual(p.reloads, [])  # exp4: no rebuild after 3F either

    def test_wavetable_tracks_are_not_rebuilt_again_after_project_load(self):
        # R5 (owner: wavetables sometimes missing after a cold project load) added a rebuild here;
        # exp3 (owner, hardware) showed that a second rebuild loses the wave.
        p = Reload()
        p.call(0x0812d8d4, p.tree, 18, EV+104)
        obj = p.r(EV+104)
        p.call(0x0812ddce, obj, 0x73, 0)
        track = p.r(obj+0x10)
        p.w(EV+100, track)
        self.assertEqual(p.call(0x08133f7c, MODEL, EV+100), 18)
        p.loaded(track)
        p.finish()
        self.assertEqual(p.reloads, [])  # exp4: the native FinalizeBankLoading rebuild is the only one
        p.finish()
        self.assertEqual(p.reloads, [])

    def test_other_track_types_and_stale_project_handles_do_not_reload(self):
        p = Reload()
        p.call(0x0812d8d4, p.tree, 14, EV+104)
        obj = p.r(EV+104)
        p.call(0x0812ddce, obj, 0x73, 0)
        track = p.r(obj+0x10)
        p.w(EV+100, track)
        self.assertEqual(p.call(0x08133f7c, MODEL, EV+100), 14)
        p.loaded(track)
        p.finish()
        self.assertEqual(p.reloads, [])
        p.press(0x105a)
        p.loaded(p.track(2))
        p.w(MODEL, N.SDRAM_TOP+0x1f0000)
        p.finish()
        self.assertEqual(p.reloads, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
