"""Ordinary per-sound lengths replay unchanged native notes on the M7 clock."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest

from test_editable_eu import Edit, EU, UU, EC, note
from test_integration import AA
from test_syncussion_melodic_ui import TracksMenu, EV
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R1


class NativeCycle(TracksMenu):
    """Keep actual model snapshots/Undo; substitute only heap and I/O services."""
    def __init__(self):
        super().__init__()
        self.blocked = False
        self.model = 0x30024b00
        self.editor = EV+200
        self.call(0x0813de80, self.model, 4, self.index)
        self.owner = self.track(self.index)
        self.sequence()
        self.u.mem_write(self.editor, struct.pack(
            "<15I", self.seq, self.owner, 2, 32, 0, 0, 100, 1, 0, 1,
            0, 0, 0, 0, 0))

    def native(self, u, a, n, d):
        if hasattr(self, "tree") and a == 0x08101e9c:
            # Paired with TracksMenu's substituted tree allocator.
            address = u.reg_read(UC_ARM_REG_R1)
            assert not address or self.tree <= address < self.tree_next
            self.ret(1)
            return
        if hasattr(self, "blocked") and a == 0x081361b4:
            self.ret(int(self.blocked))
            return
        super().native(u, a, n, d)

    def sequence(self):
        self.w(EV+100, self.owner)
        assert self.call(0x0813391a, self.model, EV+100, 0, EV+104)
        self.seq = self.r(EV+104)
        return self.seq

    def cycle(self, length, pad=2):
        self.w(self.editor, self.sequence())
        self.w(self.editor+8, pad)
        assert self.call(UU["live_cycle"], self.editor, length)

    def length(self, pad=2):
        return self.call(UU["live_cycle_steps"], self.owner,
                         self.sequence(), pad, 32)

    def undo_native(self):
        self.u.mem_write(EV, struct.pack("<5I", N.NUI(0x1032), self.sequence(), 0, 0, 0))
        self.call(0x0813b21c, self.model, EV)


class RecordingUndo(NativeCycle):
    """NativeCycle with the real native recording check (081361B4) and real notes in the clip.

    Undo while a take is being recorded is the part of native Undo that changed in 1.6.8: 1.6.1 refuses
    it; 1.6.8 discards the take (it deletes every note that is not in the list saved when the take
    started) and returns before the snapshot clone-back, where our cycle restore is hooked. Nothing of
    the native path is substituted here; only the model fields that say "recording" are set by hand.
    """
    TAKE = N.SDRAM_TOP+0x200000

    def __init__(self):
        super().__init__()
        self.project = self.r(self.model)
        self.scratch = self.TAKE+0x4000
        self.u.mem_map(self.TAKE, 0x8000)
        self.restores = []
        self.commands = []
        self._restore_hook = lambda u, a, n, d: self.restores.append(a)
        self._command_hook = lambda u, a, n, d: self.commands.append(
            struct.unpack("<12I", u.mem_read(u.reg_read(UC_ARM_REG_R1), 0x30)))
        at = UU["live_cycle_restore"] & ~1
        self.u.hook_add(UC_HOOK_CODE, self._restore_hook, begin=at, end=at)
        self.u.hook_add(UC_HOOK_CODE, self._command_hook, begin=0x0813650c, end=0x0813650c)
        self.real_check = True

    def native(self, u, a, n, d):
        if getattr(self, "real_check", False) and a == 0x081361b4:
            return
        super().native(u, a, n, d)

    def add(self, time, ident, pad=2):
        self.u.mem_write(EV+300, struct.pack("<BBH5I", 1, 0, pad, time, 240, ident, 100, 0))
        self.call(0x0812e0ce, self.project, self.sequence(), EV+300)

    def idents(self, at=None):
        at = at or self.scratch
        self.call(0x0812e6d8, self.project, self.sequence(), at)
        return [struct.unpack("<6I", self.u.mem_read(at+24*i, 24))[3]
                for i in range(self.r(at+0x3000))]

    def take_start(self, owner):
        """A take by `owner` starts now: the native state, and in 1.6.8 the note list of this moment."""
        self.w(self.model+N.MODEL_REC_OWNER, owner)
        if N.FW168:
            self.idents(self.TAKE)
            self.w(self.model+N.MODEL_REC_NOTES, self.TAKE)
            self.w(self.model+N.MODEL_REC_SEQ, self.sequence())
        self.u.mem_write(self.model+N.MODEL_REC_STATE, b"\1")

    def take_stop(self):
        self.u.mem_write(self.model+N.MODEL_REC_STATE, b"\0")


class Tests(unittest.TestCase):
    def cycle(self, probe, length):
        self.assertEqual(probe.call(UU["live_cycle"], EU, length), 1)

    def test_shortening_repeats_only_selected_sound_and_retains_outside_notes(self):
        p = Edit(notes=[note(0, pad=2, ident=101, vel=37),
                        note(3, pad=2, ident=102, vel=88),
                        note(12, pad=2, ident=103),
                        note(2, pad=3, ident=104)])
        before = p.events()
        self.cycle(p, 5)
        p.sync()
        p.across(16)
        self.assertEqual(p.events(), before)
        self.assertEqual([(pad, round(t/6000)) for pad, t in p.absolute],
                         [(2, 0), (2, 3), (2, 5), (2, 8),
                          (2, 10), (2, 13), (2, 15)])
        self.assertEqual([velocity for _, _, velocity in p.hits()],
                         [37, 88, 37, 88, 37, 88, 37])
        self.assertEqual(p.call(AA["live_skip"], p.audioseq, 2, 60), 1)
        self.assertEqual(p.call(AA["live_skip"], p.audioseq, 3, 60), 0)
        self.assertEqual(len(p.undo), 1)

    def test_expanding_restores_the_still_stored_notes(self):
        p = Edit(notes=[note(0, pad=2, ident=101), note(12, pad=2, ident=102)])
        self.cycle(p, 5)
        self.cycle(p, 16)
        p.sync()
        p.across(16)
        self.assertEqual([round(t/6000) for _, t in p.absolute if t < 16*6000], [0, 12])

    def test_two_manual_cycles_are_independent_across_native_clip_wrap(self):
        p = Edit(notes=[note(0, pad=2, ident=101), note(1, pad=3, ident=102)])
        self.cycle(p, 5)
        p.edit(0, 4)
        self.cycle(p, 7)
        p.sync()
        for start in range(0, 35*6000, 1024):
            if start >= 96000:
                p.w(p.clip+0x20, 16*240)
            p.render(start, min(1024, 35*6000-start))
        actual = {pad: [round(t/6000) for sound, t in p.absolute if sound == pad]
                  for pad in (2, 3)}
        self.assertEqual(actual, {2: list(range(0, 35, 5)), 3: list(range(1, 35, 7))})

    def test_native_step_count_dispatch_is_consumed_without_shared_length_mutation(self):
        p = Edit(notes=[note(0, pad=2, ident=101)])
        before = p.steps
        self.assertEqual(p.call(UU["seq_eu_encoder"], p.seqview, 0x62, 7), 1)
        self.assertEqual(p.steps, before)
        self.assertEqual(p.call(UU["live_cycle_steps"], p.owner, p.seq, 2, 32), 7)
        self.assertEqual(p.call(UU["live_cycle_steps"], p.owner, p.seq, 3, 32), 32)
        self.assertFalse(any(message[0] == 0xd7 for message in p.messages))

    def test_settings_xml_roundtrip_and_manual_note_edits_keep_cycle(self):
        p = Edit(notes=[note(0, pad=2, ident=101)])
        self.cycle(p, 7)
        obj = 0x20024000
        p.u.mem_write(obj+4, b"\x0e")
        p.w(obj+0x10, p.owner)
        p.call(UU["live_save"], obj, 0x20017000)
        saved = dict(p.attrs)
        self.assertEqual(saved["bento_eu2_00_02_0"] & (1 << 27), 1 << 27)
        p.call(UU["live_finish"])
        p.call(UU["live_load"], 0x20025000, obj)
        p.call(UU["live_finish"])
        self.assertEqual(p.call(UU["live_cycle_steps"], p.owner, p.seq, 2, 32), 7)
        self.assertEqual(p.call(UU["live_manual_steps"], p.owner, p.seq, 2, 1), 1)
        self.assertEqual(p.call(UU["live_cycle_steps"], p.owner, p.seq, 2, 32), 7)

    def test_old_disabled_euclidean_record_does_not_become_a_manual_cycle(self):
        p = Edit()
        p.generated(7, 3)
        p.generate(5, 0)
        p.render(0)
        self.assertEqual(p.call(AA["live_skip"], p.audioseq, 2, 60), 0)
        self.assertEqual(p.call(UU["live_cycle_steps"], p.owner, p.seq, 2, 32), 32)

    def test_low_memory_and_invalid_length_do_not_mutate_or_snapshot(self):
        p = Edit()
        before = p.events()
        p.w(0x30000048, p.r(0x3000004c)+32)
        for length in (0, 257, 7):
            self.assertEqual(p.call(UU["live_cycle"], EU, length), 0)
        self.assertEqual(p.events(), before)
        self.assertEqual(p.undo, [])
        self.assertEqual(p.r(EC), 0)

    def test_native_undo_restores_cycle_and_preserves_other_sound(self):
        p = NativeCycle()
        p.cycle(9, pad=3)
        p.cycle(7)
        p.cycle(5)
        p.undo_native()
        self.assertEqual((p.length(), p.length(3)), (7, 9))
        self.assertEqual(p.messages, [])

    def test_native_undo_of_first_cycle_returns_to_shared_clip_length(self):
        p = NativeCycle()
        p.cycle(7)
        p.undo_native()
        self.assertEqual(p.length(), 32)
        self.assertEqual(p.messages, [])

    def test_later_native_snapshot_replaces_old_cycle_snapshot(self):
        p = NativeCycle()
        p.cycle(7)
        p.cycle(5)
        p.w(EV+100, p.sequence())
        p.call(0x081338dc, p.model, EV+100)
        p.undo_native()
        self.assertEqual(p.length(), 5)
        self.assertEqual(p.messages, [])

    def test_refused_native_undo_does_not_restore_cycle(self):
        p = NativeCycle()
        p.cycle(7)
        p.cycle(5)
        p.blocked = True
        p.undo_native()
        self.assertEqual(p.length(), 5)
        p.blocked = False
        p.undo_native()
        self.assertEqual(p.length(), 7)
        self.assertEqual(p.messages, [])

    def test_undo_while_recording_follows_the_native_rule_and_keeps_the_cycle_snapshot(self):
        p = RecordingUndo()
        p.add(0, 101)
        p.add(960, 102)
        p.cycle(7)
        p.cycle(5)
        p.take_start(p.owner)
        p.add(1920, 103)                    # played into the take
        self.assertEqual(p.idents(), [101, 102, 103])
        p.undo_native()
        # Our cycle restore sits on the snapshot clone-back, which neither version reaches here.
        self.assertEqual(p.restores, [])
        self.assertEqual((p.length(), p.length(3)), (5, 32))
        if N.FW168:
            # 1.6.8: the take is discarded by the native function, the notes from before it stay.
            self.assertEqual(p.idents(), [101, 102])
            deleted = [c for c in p.commands if c[6] & 255 == 2]
            self.assertEqual([(c[3], c[7]) for c in deleted], [(103, p.owner)])
            self.assertEqual([c for c in p.commands if c[6] & 255 == 1], [])
        else:
            # 1.6.1: Undo is refused while the take runs.
            self.assertEqual(p.idents(), [101, 102, 103])
            self.assertEqual(p.commands, [])
        # The Undo snapshot and our saved cycle survive the take: Undo after it restores both.
        p.take_stop()
        del p.commands[:]
        p.undo_native()
        self.assertEqual(len(p.restores), 1)
        self.assertEqual((p.length(), p.length(3)), (7, 32))
        self.assertEqual(p.idents(), [101, 102])
        self.assertEqual(p.messages, [])

    def test_undo_while_another_track_records_is_an_ordinary_undo(self):
        p = RecordingUndo()
        p.add(0, 101)
        p.cycle(7)
        p.cycle(5)
        p.take_start(p.owner+0x40)              # a take on a different track
        p.undo_native()
        self.assertEqual(len(p.restores), 1)
        self.assertEqual(p.length(), 7)
        self.assertEqual(p.idents(), [101])
        self.assertEqual(p.messages, [])

    def test_project_completion_discards_old_cycle_snapshot(self):
        p = NativeCycle()
        p.cycle(7)
        p.cycle(5)
        p.call(UU["live_finish"])
        p.undo_native()
        self.assertEqual(p.length(), 32)
        self.assertEqual(p.messages, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
