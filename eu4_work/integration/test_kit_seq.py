"""Kit/Seq: actual native editor/header, note storage, encoder and input routing.

Model resolution/publish/Undo and play position are controlled boundaries.
No firmware image is built by the optional M4-only development fixture.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import os
from pathlib import Path
import struct
import unittest
import test_integration as integration

if os.environ.get("BENTO_KIT_SEQ_FOCUSED") == "1":
    from kit_seq_fixture import current_ui
    integration.IMAGE, integration.UU = current_ui(
        integration.IMAGE, integration.MANIFEST,
        Path(__file__).resolve().parents[2] / "build/kit-seq-check")
    integration.Fixture.__init__.__defaults__ = (integration.IMAGE,)

from test_syncussion_ui import Panel, VIEW, POINT, render, emu
from test_play_mutes import Input as NativeInput, STATE
if os.environ.get("BENTO_KIT_SEQ_FOCUSED") == "1":
    from test_previous_controls import m as controls_fixture
    controls_fixture.IMAGE = integration.IMAGE
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

MODEL, NODE, PROJECT = 0x30024B00, 0xC0100000, 0x20014000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
KEEP = []


def note(step, ident=101, pad=2, word=0, velocity=100, offset=0, probability=0):
    return struct.pack("<BBHIIIHHI", 1, probability, pad, step*960+offset, 960, ident, 60, velocity, word)


class Fixture(Panel):
    def __init__(self, path=b"\\Drum Synths\\Kick.wav\0"):
        self.owner, self.seq, self.pad = 80, 77, 2
        self.length, self.position, self.row = 64, -1, 0
        self.undo, self.published, self.base_events = [], [], []
        self.base = {2: -12000, 3: 0, 4: 0, 0x32: 0, 0x33: 0,
                     0x1e: 100, 0x1f: 200, 0x20: 800, 0x21: 100,
                     0x36: 0, 0x37: 0}
        super().__init__(path)
        KEEP.append(self)
        self.e.w(MODEL, PROJECT)
        self.e.w(PROJECT+0x68, 200)
        self.e.w(MODEL+0x144, self.seq)
        self.e.w(MODEL+0x13c, 0x13e)
        self.e.w(STATE, 0x31534d42)
        self.u.mem_write(STATE+12, b"\1")
        self.u.mem_write(STATE+16, bytes(range(16)))
        self.u.mem_write(MODEL+0x12c, b"\10")
        addresses = [0x08133cfc, 0x081322ac, 0x0812dc74, 0x0813391a,
                     0x0812dfe8, 0x081338dc, 0x08136544, 0x08136fb4,
                     0x0812e070, 0x08173272, 0x081257f0, 0x0813bfb0,
                     0x08152acc]
        self.hooks.extend(self.u.hook_add(UC_HOOK_CODE, self.service, begin=a, end=a)
                          for a in addresses)
        self.setnotes([note(0), note(3, 102), note(0, 103, 3)])
        self.call("kit_seq_bind", VIEW)
        self.header()
        self.e.w(0x3001fe2c, 1000)

    def service(self, u, address, size, data):
        r = [u.reg_read(reg) for reg in REGS]
        result = 1
        if address == 0x08133f7c:
            result = 14 if self.e.r(r[1]) == self.owner else 24 if self.e.r(r[1]) == self.seq else 1
        elif address == 0x08133614:
            h = self.e.r(r[1])
            value = self.pad if r[2] == 0x73 and h == 0x13e else self.length if r[2] == 0x62 else self.row if r[2] == 0x73 else self.base.get(r[2], 0)
            self.e.w(r[3], value)
        elif address == 0x0813390e:
            u.mem_write(r[3], N.native_string(self.path if r[2] == 0x81 else
                        self.path.split(b"\\")[-1].split(b".")[0]))
        elif address == 0x08133cfc:
            self.e.w(r[1], self.owner)
        elif address == 0x081322ac:
            if self.position is None:
                return
            self.e.w(r[2], self.row)
            self.e.w(r[3], -1)
            result = self.position
        elif address == 0x0812dc74:
            result = 0
        elif address == 0x0813391a:
            self.e.w(r[3], self.seq if r[2] == 0 else 0)
            result = int(r[2] == 0)
        elif address == 0x0812dfe8:
            self.e.w(r[2], NODE)
            result = int(r[1] == self.seq)
        elif address == 0x081338dc:
            self.undo.append(self.notes())
        elif address == 0x08136544:
            self.published.append(r[2])
            notes = self.notes()
            for i in range(self.e.r(r[2]+0x3000)):
                raw = bytes(u.mem_read(r[2]+i*24, 24))
                ident = struct.unpack_from("<I", raw, 12)[0]
                for j, old in enumerate(notes):
                    if struct.unpack_from("<I", old, 12)[0] == ident:
                        notes[j] = raw
                        break
                else:
                    notes.append(raw)
            self.setnotes(notes)
        elif address == 0x08136fb4:
            self.undo.append(self.notes())
            ids = {self.e.r(r[2]+i*24+12) for i in range(self.e.r(r[2]+0x3000))}
            self.setnotes([n for n in self.notes() if struct.unpack_from("<I", n, 12)[0] not in ids])
        elif address == 0x0812e070:
            result = self.e.r(PROJECT+0x68)
            self.e.w(PROJECT+0x68, result+1)
        elif address == 0x0813bfb0:
            self.base_events.append(bytes(u.mem_read(r[1], 20)))
        elif address == 0x08152acc:
            self.pad = r[1]
        elif address not in (0x08173272, 0x081257f0):
            return super().service(u, address, size, data)
        u.reg_write(UC_ARM_REG_R0, result & 0xffffffff)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def setnotes(self, notes):
        self.u.mem_write(NODE+12, b"".join(notes))
        self.e.w(NODE+12+0x3000, len(notes))

    def notes(self):
        return [bytes(self.u.mem_read(NODE+12+i*24, 24))
                for i in range(self.e.r(NODE+12+0x3000))]

    def seqmode(self):
        self.u.mem_write(POINT, struct.pack("<4I", 0x107e, 0, 0, 0))
        self.call("seq_nav_global", MODEL, POINT)
        self.header()

    def generator(self, pad):
        address = POINT + 0x700 + pad * 64
        self.u.mem_write(address, struct.pack("<15I", self.seq, self.owner,
                         pad, 64, 4, 0, 100, 1, 0, 1, 0, 0, 0, 0, 0))
        self.assert_native_generator(address)
        return address

    def assert_native_generator(self, address):
        assert self.call("live_begin", address)
        assert self.call("live_generate", address, 2, 4)

    def generator_pattern(self, address):
        result = POINT + 0x600
        self.call("live_value", result, address)
        return self.e.r(result)

    def footer(self, action):
        self.u.mem_write(POINT, struct.pack("<4I", action, 0, 0, 0))
        self.call("seq_nav_global", MODEL, POINT)
        self.header()

    def pad_event(self, pad, down, elapsed=0, settle=True):
        self.e.w(0x3001fe2c, self.e.r(0x3001fe2c)+elapsed)
        held = self.e.h(STATE+6)
        held = held | (1 << pad) if down else held & ~(1 << pad)
        self.u.mem_write(STATE+6, struct.pack("<H", held))
        epoch = self.u.mem_read(STATE+15, 1)[0]
        self.u.mem_write(POINT, struct.pack("<6I", 0xfe, 0x314d5442,
                         0x3151534b, pad, 12 if down else 13, 0x31525400 | epoch))
        self.call("kit_seq_dispatch", 0xfe, pad, POINT)
        if not down and settle:
            # Taps commit after the 40 ms pad-bounce window.
            self.e.w(0x3001fe2c, self.e.r(0x3001fe2c)+40)
            self.call("kit_seq_periodic")
        self.header()

    def edit(self, key, value):
        self.u.mem_write(POINT, struct.pack("<4I", 0xcf, 0x13e, key, value & 0xffffffff))
        self.call("kick_ui_event", VIEW, POINT)

    def word(self, i=0):
        return struct.unpack_from("<I", self.notes()[i], 20)[0]

    def slots(self, i=0):
        return [self.call("locks_slot", self.word(i), n) for n in range(2)]

    def title(self):
        return self.e.text(render.ROOT+0x34, 32)

    def slot(self, column=0, row=0):
        return VIEW+0x70+row*0x23f8+column*0x468

    def reveal(self):
        if self.call("kit_seq_strip_snapshot", VIEW+0x4828, POINT+0x200):
            return
        self.e.w(0x3001fe2c, self.e.r(0x3001fe2c)+1000)
        self.call("kit_seq_periodic")
        self.call("kick_ui_after", VIEW)

    def snapshot(self):
        self.reveal()
        snapshot = POINT+0x200
        assert self.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot)
        values = struct.unpack("<5i9I", self.u.mem_read(snapshot, 56))
        return dict(values=values[:5], mixed=values[5], empty=values[6],
                    first=values[7], used=values[8], condition=values[9],
                    choosing=values[10], picks=values[11:13], pad=values[13])

    def texts(self):
        result = []
        def capture(u, address, size, data):
            result.append(self.e.text(u.reg_read(UC_ARM_REG_R0)+0x31, 32))
        hook = self.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
        try:
            self.paint()
        finally:
            self.u.hook_del(hook)
        return result

    def turn(self, column, delta=12800):
        group = self.e.r(VIEW+0x38+0x2c)
        row = self.e.r(group+0x39c)
        self.e.call(0x08171e44, self.slot(column, row), delta & 0xffffffff)

    def touch_field(self, column, top=60):
        self.finger(80+column*159, top, True)
        self.finger(80+column*159, top, False)


class Tests(unittest.TestCase):
    def test_last_played_kit_pad_is_selected_when_entering_seq(self):
        p = Fixture()
        p.call("kit_seq_dispatch", 0xac, 9, 0)
        p.seqmode()
        self.assertEqual(p.pad, 9)
        self.assertEqual(p.title(), "Kick Steps 1-16/64")

    def test_played_pad_does_not_leak_into_another_track_or_project(self):
        for change in ("track", "project"):
            p = Fixture()
            p.call("kit_seq_dispatch", 0xac, 9, 0)
            if change == "track":
                p.owner += 1
            else:
                p.e.w(MODEL, PROJECT+0x100)
            p.seqmode()
            self.assertEqual(p.pad, 2)

    def test_visual_strip_waits_one_second_without_delaying_parameter_locks(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        snapshot = POINT+0x200
        self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot), 0)
        self.assertEqual(p.call("kit_seq_step_focus", 1), 0)
        p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+999)
        p.call("kit_seq_periodic")
        self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot), 0)
        before = p.word()
        p.turn(0)
        self.assertNotEqual(p.word(), before)
        self.assertEqual(p.base_events, [])
        self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot), 0)
        p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+1)
        p.call("kit_seq_periodic")
        self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot), 1)
        p.pad_event(0, False)
        self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, snapshot), 0)

    def test_short_insert_delete_taps_never_show_the_held_strip(self):
        p = Fixture()
        p.seqmode()
        for _ in range(2):
            p.pad_event(1, True)
            self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, POINT+0x200), 0)
            p.pad_event(1, False, 100)
            self.assertEqual(p.call("kit_seq_strip_snapshot", VIEW+0x4828, POINT+0x200), 0)

    def test_successful_step_toggle_disables_only_its_euclidean_pad(self):
        for local in (0, 1):
            with self.subTest(local=local):
                p = Fixture()
                selected = p.generator(p.pad)
                other = p.generator(p.pad + 1)
                previous = p.generator_pattern(selected)
                other_pattern = p.generator_pattern(other)
                undo_count = len(p.undo)
                before = p.notes()
                p.seqmode()
                p.pad_event(local, True)
                p.pad_event(local, False, 50)
                self.assertEqual(p.generator_pattern(selected),
                                 previous & ~(1 << 25))
                self.assertEqual(p.generator_pattern(other), other_pattern)
                self.assertEqual(len(p.undo), undo_count + 1)
                if local == 0:
                    self.assertEqual(p.notes(), [n for n in before
                                     if struct.unpack_from("<H", n, 2)[0] != p.pad
                                     or struct.unpack_from("<I", n, 4)[0] != 0])
                else:
                    self.assertTrue(all(n in p.notes() for n in before))
                    self.assertEqual(len(p.notes()), len(before) + 1)

    def test_hold_or_failed_step_edit_keeps_euclidean_mode_and_notes(self):
        for action in ("hold", "no-memory"):
            with self.subTest(action=action):
                p = Fixture()
                selected = p.generator(p.pad)
                pattern = p.generator_pattern(selected)
                before = p.notes()
                undo_count = len(p.undo)
                p.seqmode()
                if action == "no-memory":
                    p.e.w(p.call("eu_shared_scratch"), 0)
                    p.e.w(0x30000048, p.e.r(0x3000004c))
                p.pad_event(0, True)
                p.pad_event(0, False, 600 if action == "hold" else 50)
                self.assertEqual(p.generator_pattern(selected), pattern)
                self.assertEqual(p.notes(), before)
                self.assertEqual(len(p.undo), undo_count)

    def test_physical_release_seen_before_queued_release_still_toggles(self):
        for local in (0, 1):
            with self.subTest(local=local):
                p = Fixture()
                p.seqmode()
                before = p.notes()
                p.pad_event(local, True)
                p.u.mem_write(STATE+6, b"\0\0")
                p.e.w(0x3001fe2c, 1100)
                p.call("kit_seq_periodic")
                self.assertEqual(p.call("kit_seq_holding"), 0)
                self.assertEqual(p.notes(), before)
                p.pad_event(local, False)
                hits = [n for n in p.notes()
                        if struct.unpack_from("<H", n, 2)[0] == p.pad
                        and struct.unpack_from("<I", n, 4)[0] == local * 960]
                self.assertEqual(len(hits), int(local == 1))
                self.assertEqual(len(p.undo), 1)

    def test_queued_release_after_periodic_never_deletes_an_edited_step(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.edit(N.NKEY(0x1a0), 90)
        before = p.notes()
        p.u.mem_write(STATE+6, b"\0\0")
        p.e.w(0x3001fe2c, 1100)
        p.call("kit_seq_periodic")
        p.pad_event(0, False)
        self.assertEqual(p.notes(), before)

    def test_native_step_registry_ranges_and_held_values_are_not_guessed(self):
        p = Fixture()
        reg = p.e.r(0x30031484)
        for key, lo, hi in ((N.NKEY(0x183), 1, 127), (N.NKEY(0x18c), -47, 47)):
            self.assertEqual(struct.unpack("<2i", p.u.mem_read(reg+key*32+16, 8)), (lo, hi))
        self.assertEqual(p.e.r(reg+N.NKEY(0x184)*32+12), 113)  # exp5: A:B up to 4:4 and 1ST..!PRE offered
        pair = p.call("locks_pack", 0x510c000a, 0x510d0014)
        conditional = p.call("locks_condition_word", pair, 103)
        p.setnotes([note(4, word=conditional, velocity=87, offset=-120, probability=100)])
        p.seqmode()
        p.pad_event(4, True)
        snap = p.snapshot()
        self.assertEqual(snap["values"][:3], (87, -12, 100))
        self.assertEqual((snap["first"], snap["used"], snap["condition"]), (5, 2, 103))
        self.assertEqual([p.e.h(p.slot(i, 2)+0x9c) for i in range(8)],
                         [N.NKEY(0x186), N.NKEY(0x183), N.NKEY(0x184), N.NKEY(0x18c), 0, N.NKEY(0x199), N.NKEY(0x1a0), N.NKEY(0x1a1)])
        self.assertIn("35 Hz", p.texts())
        self.assertIn("20%", p.texts())

    def test_native_lock_units_and_multiple_held_mixed_fields(self):
        p = Fixture()
        p.setnotes([note(0, word=0x51010348, velocity=70),
                    note(3, 102, word=0x51040064, velocity=80, offset=100, probability=50)])
        p.seqmode()
        p.pad_event(0, True)
        self.assertEqual(p.snapshot()["values"][3], 0x51010348)
        p.pad_event(3, True)
        snap = p.snapshot()
        self.assertEqual(snap["mixed"] & 15, 15)
        self.assertEqual(snap["values"][4], 0)
        self.assertEqual((snap["first"], snap["mixed"] & 64), (1, 64))

    def test_retained_other_engine_lock_is_not_relabelled_as_current_sound(self):
        p = Fixture(b"\\Drum Synths\\Snare.wav\0")
        p.setnotes([note(0, word=0x510f0028)])
        p.seqmode()
        p.pad_event(0, True)
        self.assertEqual(p.snapshot()["values"][3], 0x510f0028)
        self.assertIn("Inactive lock", p.texts())

    def test_step_encoder_events_edit_metadata_atomically_with_native_undo(self):
        p = Fixture()
        conditional = p.call("locks_condition_word", 0x510c000a, 103)
        p.setnotes([note(0, word=conditional), note(3, 102, word=conditional), note(3, 103, 3)])
        p.seqmode()
        p.pad_event(0, True)
        p.pad_event(3, True)
        p.reveal()
        base = bytes(p.u.mem_read(0x24043500, 0x880))
        p.call("drum_panel_rows", 0xaf, 1)
        p.edit(N.NKEY(0x183), 110)
        self.assertEqual([struct.unpack_from("<H", n, 18)[0] for n in p.notes()], [110, 110, 100])
        self.assertEqual(len(p.undo), 1)
        p.edit(N.NKEY(0x18c), -12)
        self.assertEqual([struct.unpack_from("<I", n, 4)[0] for n in p.notes()], [0, 3*960-120, 3*960])
        p.edit(N.NKEY(0x184), 100)
        self.assertEqual([n[1] for n in p.notes()], [100, 100, 0])
        self.assertEqual([p.call("locks_condition_get", p.word(i)) for i in range(2)], [103, 103])
        self.assertEqual(len(p.undo), 3)
        self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), base)
        self.assertEqual(p.base_events, [])
        before = p.notes()
        p.pad_event(0, False, 50)
        p.pad_event(3, False, 50)
        self.assertEqual(p.notes(), before)

    def test_r611_step_edits_keep_the_ratchet_and_the_old_record(self):
        # locks_step_edit runs from the bank-1 M4 cave (080DBCD0) in the image.
        p = Fixture()
        r = p.call("locks_ratchet_pack", 4, 1, 50, 0)
        t = p.call("locks_ratchet_word", p.call("locks_condition_word", 0x510c000a, 103), r)
        p.setnotes([note(0, word=t)])
        p.seqmode()
        p.pad_event(0, True)
        p.reveal()
        p.call("drum_panel_rows", 0xaf, 1)
        get = lambda w: (p.call("locks_condition_get", w), p.call("locks_ratchet_get", w), p.call("locks_slot", w, 0))
        self.assertEqual(p.call("locks_step_edit", p.seq, p.pad, 0, 1, 3, 50, 1), 1)
        self.assertEqual(get(p.word()), (51, r, 0x510c000a))
        self.assertEqual(p.call("locks_step_edit", p.seq, p.pad, 0, 1, 4, 0x510c0014, 1), 1)
        self.assertEqual(get(p.word()), (51, r, 0x510c0014))
        self.assertEqual(p.call("locks_step_edit", p.seq, p.pad, 0, 1, 3, 99, 1), 1) # Always: ratchet-only record
        self.assertEqual(get(p.word()), (0, r, 0x510c0014))
        self.assertEqual(get(t), (103, r, 0x510c000a)) # Undo keeps this exact token

    def test_native_step_ranges_clamp_and_noop_does_not_snapshot(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.reveal()
        p.call("drum_panel_rows", 0xaf, 1)
        for field, value, expected in ((0, 999, 127), (0, -999, 1), (2, 999, 138), (2, -999, 1)):  # exp5: !PRE is the last offered
            p.call("locks_step_edit", p.seq, p.pad, 0, 1, field, value, 1)
            self.assertEqual(struct.unpack_from("<H", p.notes()[0], 18)[0] if field == 0 else p.notes()[0][1], expected)
        before = len(p.undo)
        p.edit(N.NKEY(0x18c), -10)
        self.assertEqual(len(p.undo), before, "First-step negative offset remains zero")

    def test_touch_only_focuses_and_dragging_does_not_edit_step_values(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.reveal()
        before = p.notes()
        p.finger(96, 60, True)
        p.finger(96, 160, True)
        p.finger(96, 160, False)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 1)
        self.assertEqual(p.notes(), before)
        p.pad_event(3, True)
        p.touch_field(0)
        p.pad_event(3, False, 50)
        self.assertEqual(p.notes(), before, "Inspecting the focused row protects every held pad release")
        p.touch_field(0, 200)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 0)
        p.touch_field(6)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 1)
        p.e.w(0x3001fe2c, 1500)
        p.call("workflow_periodic")
        self.assertEqual(p.snapshot()["choosing"] & 1, 0, "A focus tap is not a lock-target tap")
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])

    def test_empty_step_memory_failure_and_selection_change_never_publish_partial_edits(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.pad_event(1, True)
        before = p.notes()
        self.assertEqual(p.snapshot()["empty"], 1)
        p.call("drum_panel_rows", 0xaf, 1)
        p.turn(0)
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])
        p.pad_event(1, False, 50)
        p.e.w(0x30000048, p.e.r(0x3000004c))
        p.turn(0)
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])

    def test_up_down_and_touch_focus_route_all_step_encoders_without_base_sound_changes(self):
        for name in ("Kick", "Syncussion"):
            p = Fixture(("\\Drum Synths\\"+name+".wav\0").encode())
            pair = p.call("locks_pack", 0x510c000a, 0x510d0014)
            p.setnotes([note(4, word=pair)])
            p.seqmode()
            p.pad_event(4, True)
            p.reveal()
            group = p.e.r(VIEW+0x38+0x2c)
            base = bytes(p.u.mem_read(0x24043500, 0x880))
            self.assertEqual(p.e.r(group+0x39c), 0)
            p.call("drum_panel_rows", 0xaf, 1)
            self.assertEqual(p.e.r(group+0x39c), 2)
            self.assertEqual(bytes(p.u.mem_read(group+0x208+4, 16)),
                             bytes(p.u.mem_read(VIEW+0x4828+4, 16)))
            self.assertEqual([p.e.h(p.slot(i, 2)+0x9c) for i in range(8)],
                             [N.NKEY(0x186), N.NKEY(0x183), N.NKEY(0x184), N.NKEY(0x18c), 0, N.NKEY(0x199), N.NKEY(0x1a0), N.NKEY(0x1a1)])
            # Group dispatch queues turns in the visible upper row only.
            p.e.call(0x08170cc8, group, 0, 3)
            self.assertEqual(p.e.r(VIEW+0x4828+0x2398), 3)
            self.assertEqual(p.e.r(VIEW+0x38+0x2398), 0)
            for column in (1, 3, 2, 5, 6, 7):
                p.turn(column)
            self.assertEqual(len(p.undo), 6)
            self.assertEqual(struct.unpack_from("<H", p.notes()[0], 18)[0], 127)
            self.assertEqual(struct.unpack_from("<I", p.notes()[0], 4)[0], 4*960+470)
            self.assertEqual(p.notes()[0][1], 100)
            self.assertEqual(p.call("locks_condition_get", p.word()), 100)
            self.assertEqual([w >> 16 & 255 for w in p.slots()], [12, 13])
            self.assertGreater(p.slots()[0] & 65535, 10)
            self.assertGreater(p.slots()[1] & 65535, 20)
            p.call("drum_panel_rows", 0xaf, 8)
            self.assertEqual(p.e.r(group+0x39c), 0)
            old = p.word()
            p.turn(0)
            self.assertNotEqual(p.word(), old, "Down restores sound-row direct p-locking")
            p.touch_field(0)
            self.assertEqual(p.e.r(group+0x39c), 2)
            p.touch_field(0, 200)
            self.assertEqual(p.e.r(group+0x39c), 0)
            self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), base)
            self.assertEqual(p.base_events, [])
            p.call("drum_panel_rows", 0xaf, 1)
            before = p.notes()
            p.pad_event(4, False, 50)
            self.assertEqual(p.notes(), before)
            self.assertEqual(p.e.r(group+0x39c), 0)
            self.assertEqual(p.call("kit_seq_step_focus", -1), 0)
            self.assertNotEqual(p.e.h(p.slot(0, 2)+0x9c), N.NKEY(0x183))
            p.pad_event(4, True)
            self.assertEqual(p.e.r(group+0x39c), 0)

    def test_upper_lock_controls_keep_native_target_picker_remove_and_atomic_duplicate_refusal(self):
        p = Fixture()
        a = p.call("locks_pack", 0x510c000a, 0x510d0014)
        b = p.call("locks_pack", 0x510c000a, 0x51010348)
        p.setnotes([note(0, word=a), note(3, 102, word=b)])
        p.seqmode()
        p.pad_event(0, True)
        p.pad_event(3, True)
        p.reveal()
        p.touch_field(6)  # Focus only, no target selection.
        self.assertEqual(p.snapshot()["choosing"] & 1, 0)
        p.touch_field(6)
        p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+400)
        p.call("workflow_periodic")
        self.assertEqual(p.snapshot()["choosing"] & 1, 1)
        self.assertEqual(p.e.h(p.slot(6, 2)+0x9c), N.NKEY(0x1da))
        p.edit(N.NKEY(0x1da), 1)  # Existing native picker: Level.
        p.touch_field(6)
        p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+400)
        p.call("workflow_periodic")
        self.assertEqual(p.e.h(p.slot(6, 2)+0x9c), 2)
        self.assertTrue(p.snapshot()["choosing"] & 4)
        before = p.notes()
        p.turn(6)
        self.assertEqual(p.notes(), before, "Other held note already owns Level in slot 8")
        self.assertEqual(p.undo, [])
        p.touch_field(7)
        p.touch_field(7)
        self.assertEqual([p.slots(i)[1] for i in range(2)], [0, 0])
        self.assertEqual(len(p.undo), 1)
        self.assertEqual([p.slots(i)[0] for i in range(2)], [0x510c000a]*2)

    def test_pending_step_target_tap_is_cancelled_by_release_and_project_or_mix_change(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.reveal()
        p.call("drum_panel_rows", 0xaf, 1)
        p.touch_field(6)
        p.pad_event(0, False, 50)
        p.pad_event(3, True)
        p.reveal()
        p.call("workflow_periodic")
        self.assertEqual(p.e.h(p.slot(6, 2)+0x9c), 2)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 0)
        p.call("drum_panel_rows", 0xaf, 1)
        p.footer(0x1068)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 0)
        p.footer(0x1067)
        p.call("drum_panel_rows", 0xaf, 1)
        p.e.w(MODEL, PROJECT+0x1000)
        p.call("kit_seq_periodic")
        self.assertEqual(p.call("kit_seq_holding"), 0)
        self.assertEqual(p.call("kit_seq_step_focus", -1), 0)
        group = p.e.r(VIEW+0x38+0x2c)
        self.assertEqual(p.e.r(group+0x39c), 0)
        self.assertNotEqual(p.e.h(p.slot(0, 2)+0x9c), N.NKEY(0x183))
        self.assertEqual(p.undo, [])

    def test_held_strip_restores_on_release_and_keeps_real_encoder_focus_on_faders(self):
        for name in ("Kick", "Syncussion"):
            p = Fixture(("\\Drum Synths\\"+name+".wav\0").encode())
            out = integration.CANDIDATE/"screens"
            out.mkdir(exist_ok=True)
            p.paint()
            p.save(out/("stepstrip-"+name.lower()+"-normal.png"))
            p.call("drum_panel_rows", 0xaf, 1)
            p.paint()
            p.save(out/("stepstrip-"+name.lower()+"-top-focus.png"))
            group = p.e.r(VIEW+0x38+0x2c)
            self.assertEqual(p.e.r(group+0x39c), 0)  # R6.3 (owner): Up never focuses the engine row
            p.seqmode()
            p.pad_event(0, True)
            self.assertEqual(p.e.r(group+0x39c), 0)
            before = bytes(p.u.mem_read(0x24043500, 0x880))
            p.e.call(0x08171e44, p.slot(), 12800)
            self.assertEqual(p.slots()[0] >> 16 & 255, 12)
            self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), before)
            p.reveal()
            texts = []
            def capture(u, a, size, data):
                texts.append(p.e.text(u.reg_read(UC_ARM_REG_R0)+0x31, 32))
            hook = p.u.hook_add(UC_HOOK_CODE, capture, begin=0x0817e448, end=0x0817e448)
            p.paint()
            p.save(out/("stepstrip-"+name.lower()+"-held.png"))
            self.assertIn("Velocity", texts)
            self.assert_visible_held_title(out/("stepstrip-"+name.lower()+"-held.png"))
            engine = "Kick" if name == "Kick" else "Metal"  # Run 16: the engine row is marked by the engine name
            self.assertNotIn(engine, texts)
            self.assertNotIn("ENGINE", texts)
            self.assertNotIn("DIRECTION -> PITCH", texts)
            p.call("drum_panel_rows", 0xaf, 1)
            self.assertEqual(p.e.r(group+0x39c), 2)
            p.paint()
            p.save(out/("stepstrip-"+name.lower()+"-held-step-focus.png"))
            texts.clear()
            p.pad_event(0, False, 50)
            p.paint(False)
            p.u.hook_del(hook)
            self.assertNotIn("Velocity", texts)
            self.assertIn(engine, texts)  # R6.3: Metal shows the same engine row (Run 16: name, no "ENGINE" title)
            self.assertEqual(p.e.r(group+0x39c), 0)

    def test_native_held_row_pixels_are_visible_on_other_drum_engines(self):
        for name in ("Snare", "HiHat", "Clap", "Tom"):
            with self.subTest(engine=name):
                p = Fixture(("\\Drum Synths\\"+name+".wav\0").encode())
                p.seqmode()
                p.pad_event(0, True)
                p.reveal()
                for frame in range(2):
                    p.paint()
                    path = integration.CANDIDATE/"screens"/("stepstrip-"+name.lower()+"-held.png")
                    p.save(path)
                    self.assert_visible_held_title(path)

    def assert_visible_held_title(self, path):
        from PIL import Image
        image = Image.open(path).convert("RGB")
        # Check exported RGB ink, not indexed pixels or intercepted text calls:
        # clipping and transparent/black glyphs can otherwise look like a pass.
        pixels = list(image.crop((190, 30, 300, 55)).getdata())
        self.assertGreater(sum(max(pixel) >= 100 for pixel in pixels), 100)

    def test_native_header_shifts_tabs_and_keeps_kit_left_of_battery(self):
        p = Fixture()
        # R6.3 (owner): no Pads/Steps footer button (Left+Right toggles it);
        # the native tabs stay where they are.
        for _ in range(3):
            p.header()
        self.assertNotIn(0x107e, [p.e.h(render.ROOT+0x34+N.HDR(0x74)+i*48+44) for i in range(6)])
        p.seqmode()
        self.assertEqual(p.u.mem_read(STATE+14, 1), b"\1")
        self.assertEqual(p.title(), "Kick Steps 1-16/64")
        p.paint()
        out = Path(__file__).resolve().parents[2]/"build/kit-seq-check"
        out.mkdir(parents=True, exist_ok=True)
        p.save(out/"kit-seq-kick.png")

    def test_pressure_bounce_is_one_tap_and_slow_tap_still_toggles(self):
        p = Fixture()
        p.seqmode()
        old = p.notes()
        # Pressure dips through zero mid-press: one physical tap, one toggle.
        p.pad_event(0, True)
        p.pad_event(0, False, 30, settle=False)
        p.pad_event(0, True, 10)
        p.pad_event(0, False, 60)
        self.assertNotEqual(p.notes(), old)
        self.assertEqual(len(p.undo), 1)
        # A deliberate 450 ms press is still a tap (old window was 300 ms).
        p.pad_event(1, True)
        p.pad_event(1, False, 450)
        self.assertEqual(len(p.undo), 2)
        # A bounce after a long hold never becomes a new tap.
        before = p.notes()
        p.pad_event(0, True)
        p.pad_event(0, False, 700, settle=False)
        p.pad_event(0, True, 10)
        p.pad_event(0, False, 30)
        self.assertEqual(p.notes(), before)
        self.assertEqual(len(p.undo), 2)
        # Two separate taps on the same step still toggle twice.
        p.pad_event(2, True)
        p.pad_event(2, False, 50)
        p.pad_event(2, True, 100)
        p.pad_event(2, False, 50)
        self.assertEqual(p.notes(), before)
        self.assertEqual(len(p.undo), 4)

    def test_tap_toggles_and_hold_never_removes_or_creates(self):
        p = Fixture()
        p.seqmode()
        old = p.notes()
        p.pad_event(0, True)
        p.pad_event(0, False, 600)
        self.assertEqual(p.notes(), old)
        p.pad_event(1, True)
        p.pad_event(1, False, 600)
        self.assertEqual(p.notes(), old)
        p.pad_event(0, True)
        p.pad_event(0, False, 50)
        self.assertEqual(len(p.notes()), 2)
        p.pad_event(1, True)
        p.pad_event(1, False, 50)
        self.assertEqual(len(p.notes()), 3)
        self.assertEqual(len(p.undo), 2)

    def test_native_footer_finger_toggles_without_changing_notes_or_base(self):
        p = Fixture()
        before, base = p.notes(), bytes(p.u.mem_read(0x24043500, 0x880))
        # R6.3 (owner): Left+Right together toggles; neither arrow acts alone.
        for enabled in (1, 0, 1):
            p.call("kit_seq_dispatch", 0xaf, 0, 0)
            p.call("kit_seq_dispatch", 0xaf, 9, 0)
            p.call("kit_seq_dispatch", 0xb0, 0, 0)
            p.call("kit_seq_dispatch", 0xb0, 9, 0)
            p.header()
            self.assertEqual(p.u.mem_read(STATE+14, 1), bytes([enabled]))
        self.assertEqual(p.notes(), before)
        self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), base)

    def test_direct_matching_free_slot_full_refusal_and_release_base_restore(self):
        p = Fixture()
        p.seqmode()
        p.paint()
        before = bytes(p.u.mem_read(0x24043500, 0x880))
        p.pad_event(0, True)
        p.edit(N.NKEY(0x1a0), 100)
        p.edit(N.NKEY(0x1a1), 80)
        self.assertEqual([x >> 16 & 255 for x in p.slots()], [12, 13])
        p.edit(N.NKEY(0x1a0), 120)
        self.assertEqual(p.slots()[0] & 65535, 95)
        p.header()
        p.paint()
        p.save(Path(__file__).resolve().parents[2]/"build/kit-seq-check/kit-seq-held.png")
        notes = p.notes()
        p.edit(N.NKEY(0x1a2), 20)
        self.assertEqual(p.notes(), notes)
        p.header()
        self.assertIn("2/2 locks used", p.title())
        self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), before)
        p.pad_event(0, False, 50)
        self.assertEqual(p.notes(), notes)
        self.assertEqual(p.e.r(p.slot()+0xa0), 55)
        self.assertEqual(p.base_events, [])

    def test_multistep_preflight_is_atomic_and_empty_selection_is_safe(self):
        p = Fixture()
        pair = p.call("locks_pack", 0x510c000a, 0x510d0014)
        p.setnotes([note(0), note(3, 102, word=pair)])
        p.seqmode()
        p.pad_event(0, True)
        p.pad_event(3, True)
        before = p.notes()
        p.edit(N.NKEY(0x1a2), 70)
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])
        p.edit(N.NKEY(0x1a1), 90)
        self.assertEqual([p.slots(i)[0] >> 16 & 255 for i in (0, 1)], [13, 12])
        self.assertEqual(p.slots(1)[1] & 65535, 90)
        self.assertEqual(len(p.undo), 1)
        p.pad_event(1, True)
        before = p.notes()
        p.edit(N.NKEY(0x1a1), 40)
        self.assertEqual(p.notes(), before)

    def test_targeted_double_tap_preserves_other_lock_and_condition(self):
        p = Fixture()
        packed = p.call("locks_pack", 0x510c000a, 0x510d0014)
        wrapped = p.call("locks_condition_word", packed, 103)
        p.setnotes([note(0, word=wrapped)])
        p.seqmode()
        p.pad_event(0, True)
        p.call("workflow_lock_tap", p.slot())
        p.e.w(0x3001fe2c, 1100)
        p.call("workflow_lock_tap", p.slot())
        self.assertEqual(p.slots(), [0, 0x510d0014])
        self.assertEqual(p.call("locks_condition_get", p.word()), 103)
        self.assertEqual(len(p.undo), 1)

    def test_page_navigation_is_sixteen_nonoverlapping_and_frozen_while_held(self):
        p = Fixture()
        p.seqmode()
        p.call("kit_seq_dispatch", 0xaf, 9, 0)
        p.call("kit_seq_dispatch", 0xb0, 9, 0)  # R6.3: arrows act on release
        p.header()
        self.assertEqual(p.title(), "Kick Steps 17-32/64")
        p.pad_event(0, True)
        p.call("kit_seq_dispatch", 0xaf, 9, 0)
        p.call("kit_seq_dispatch", 0xb0, 9, 0)
        p.pad_event(0, False, 50)
        p.header()
        self.assertEqual(p.title(), "Kick Steps 17-32/64")
        p.seqmode()
        p.seqmode()
        self.assertEqual(p.title(), "Kick Steps 17-32/64")

    def test_ordinary_samples_use_existing_native_lock_kinds(self):
        p = Fixture(b"\\Samples\\Ordinary.wav\0")
        p.seqmode()
        p.pad_event(0, True)
        p.edit(2, -18000)
        p.edit(0x1e, 300)
        self.assertEqual([x >> 16 & 255 for x in p.slots()], [1, 6])
        self.assertEqual(p.base[2], -12000)
        self.assertEqual(p.base[0x1e], 100)
        self.assertEqual(p.base_events, [])

    def test_native_encoder_pipeline_creates_lock_without_base_or_motion_event(self):
        p = Fixture()
        p.seqmode()
        p.u.mem_write(POINT, struct.pack("<5I", 0x1076, 0, 0, 0, 0))
        self.assertEqual(p.call("perf_navigation", POINT), 1)
        self.assertEqual(p.call("motion_active", 0), 1)
        before = bytes(p.u.mem_read(0x24043500, 0x880))
        p.pad_event(0, True)
        values = []
        for _ in range(12):
            p.e.w(0x3001fe2c, p.e.r(0x3001fe2c)+100)
            p.e.call(0x08171e44, p.slot(), 1600)
            values.append(p.e.r(p.slot()+0xa0))
        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], 55)
        self.assertEqual(p.slots()[0] >> 16 & 255, 12)
        self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x880)), before)
        self.assertEqual(p.base_events, [])
        p.pad_event(0, False)
        self.assertEqual(p.e.r(p.slot()+0xa0), 55)
        p.u.mem_write(POINT, struct.pack("<5I", 0x1076, 0, 0, 0, 0))
        p.call("perf_navigation", POINT)
        p.e.call(0x08171e44, p.slot(), 12800)
        self.assertGreater(p.u.mem_read(0x24043528, 1)[0], 55)

    def test_real_value_finger_double_tap_removes_only_matching_lock(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        p.edit(N.NKEY(0x1a0), 100)
        p.edit(N.NKEY(0x1a1), 80)
        top = 480 - (p.e.r(VIEW+0x38+8)+20)
        p.finger(80, top, True)
        p.finger(80, top, False)
        p.e.w(0x3001fe2c, 1100)
        p.finger(80, top, True)
        p.finger(80, top, False)
        self.assertEqual(p.slots(), [0, 0x510d0050])

    def test_all_engine_parameter_maps_and_explicit_unsupported_destinations(self):
        p = Fixture()
        keys = [N.NKEY(0x1a0), N.NKEY(0x1a1), N.NKEY(0x1a2), N.NKEY(0x1a4), N.NKEY(0x1a5), N.NKEY(0x1a6), N.NKEY(0x1a9)]
        for model, first, count in ((1, 12, 7), (3, 20, 5), (5, 25, 5),
                                     (7, 20, 5), (9, 12, 7), (15, 12, 7)):
            for i, key in enumerate(keys):
                self.assertEqual(p.call("locks_direct_kind", key, model),
                                 first+i if i < count else 0)
            self.assertEqual(p.call("locks_direct_kind", N.NKEY(0x1b0), model),
                             19 if model == 1 else 0)
            for key in (0x1e, 0x1f, 0x20, 0x21, N.NKEY(0x1aa), N.NKEY(0x1ad), 0xe5):
                self.assertEqual(p.call("locks_direct_kind", key, model), 0)
        for key in (N.NKEY(0x1aa), N.NKEY(0x1ad), 0xe5):
            self.assertEqual(p.call("locks_direct_kind", key, 0), 0)

    def test_mixed_and_inherited_values_and_empty_steps_are_distinct(self):
        p = Fixture()
        p.setnotes([note(0, word=0x510c000a), note(3, 102)])
        p.seqmode()
        p.pad_event(0, True)
        status = POINT+0x100
        self.assertEqual(p.call("kit_seq_value", N.NKEY(0x1a0), 55, status), 35)
        self.assertEqual(p.e.r(status), 2)
        p.call("kit_seq_value", N.NKEY(0x1a1), 65, status)
        self.assertEqual(p.e.r(status), 1)
        p.pad_event(3, True)
        p.call("kit_seq_value", N.NKEY(0x1a0), 55, status)
        self.assertEqual(p.e.r(status), 3)
        p.pad_event(1, True)
        p.call("kit_seq_value", N.NKEY(0x1a0), 55, status)
        self.assertEqual(p.e.r(status), 5)

    def test_dropped_release_and_navigation_cancel_without_toggling(self):
        p = Fixture()
        p.seqmode()
        p.pad_event(0, True)
        before = p.notes()
        p.u.mem_write(STATE+6, b"\0\0")
        p.e.w(0x3001fe2c, 1500)
        p.call("kit_seq_periodic")
        self.assertEqual(p.call("kit_seq_holding"), 0)
        self.assertEqual(p.notes(), before)
        p.pad_event(3, True)
        p.call("kit_seq_nav")
        self.assertEqual(p.u.mem_read(STATE+14, 1), b"\0")
        p.pad_event(3, False, 50)
        self.assertEqual(p.notes(), before)
        # R6.2: Seq mode is remembered per track (shared with SEQ), so the
        # editor's next header pass re-arms it; the dropped release toggled nothing.
        self.assertEqual(p.call("kit_seq_track_mode"), 1)

    def test_playhead_feedback_and_playing_clip_selection_do_not_move_page(self):
        p = Fixture()
        p.position = None
        engine = 0xc0500000
        p.e.w(0x3000f650, engine)
        p.u.mem_write(engine+0x4888, struct.pack("<4i", 3, 0, -1, 0))
        p.e.w(MODEL+0x144, 999)
        p.seqmode()
        p.header()
        self.assertEqual(p.title(), "Kick Steps 1-16/64")
        pads = MODEL+N.MODEL_PADS
        p.call("kit_seq_lights", pads)
        self.assertEqual(p.u.mem_read(pads+3*16+13, 1), b"\1")
        self.assertNotEqual(p.e.r(pads), 0)
        # The native flush shows word +8 for the playhead: it must be visible
        # and differ from both a lit and an empty step.
        # R6.4 (owner): only the track's own colours: a step dim, the playing
        # step and a held pad bright (no white playhead, no other hue).
        colour = p.e.r(pads)
        bright = p.e.r(pads+3*16+8)
        self.assertNotIn(bright, (0, colour, 0xffffff))
        self.assertEqual(bright, p.e.call(0x08140ef0, 0))
        self.assertEqual(p.e.r(pads+4), bright)
        self.assertEqual(p.e.r(pads+5*16+4), bright)
        p.u.mem_write(engine+0x4888, struct.pack("<4i", 20, 0, -1, 0))
        p.call("kit_seq_lights", pads)
        self.assertEqual(sum(p.u.mem_read(pads+i*16+13, 1)[0] for i in range(16)), 0)
        p.header()
        self.assertEqual(p.title(), "Kick Steps 1-16/64")
        self.assertEqual(p.e.r(MODEL+0x144), 999)

    def test_exp3_one_shot_instrument_pages_send_track_colours_not_the_native_white(self):
        # P168 exp3 (owner, for a while: on the INST page of a one-shot track the selected pad is bright
        # white). Oracle: what reaches the native pad-light flush body (081257F8) through our flush hook.
        # The native painter marks the selected pad in white (00888888, native 081258E0); on both
        # Instrument pages of a one-shot track (7 and 8) the flush must send the track's own colours.
        from unicorn import UC_HOOK_CODE
        from unicorn.arm_const import (UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                                       UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)
        for page in (8, 7):
            p = Fixture(); pads = MODEL + N.MODEL_PADS; sent = []
            native_white = 0x081258e0  # native "ldr r1,[pc,#0x34]": the white it paints a selected pad with
            white = p.e.r(((native_white + 4) & ~3) + 0x34); self.assertEqual(white, 0x00888888)
            def body(u, a, n, d):
                sp = u.reg_read(UC_ARM_REG_SP); sent.append([p.e.r(pads + i * 16) for i in range(16)])
                saved = struct.unpack("<9I", u.mem_read(sp + 44, 36))
                for reg, v in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8,
                                   UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11), saved): u.reg_write(reg, v)
                u.reg_write(UC_ARM_REG_SP, sp + 80); u.reg_write(UC_ARM_REG_PC, saved[8] | 1)
            p.u.hook_add(UC_HOOK_CODE, body, begin=0x081257f8, end=0x081257f8)
            p.u.mem_write(MODEL + 0x12c, bytes([page]))
            for i in range(16):
                for k in (0, 4, 8): p.e.w(pads + i * 16 + k, white if i == 5 else 0x00101010)
            p.call("play_mute_flush", pads)
            self.assertEqual(len(sent), 1, page)
            self.assertNotIn(white, sent[0], page)
            dim = p.e.call(0x08140f50, 0)
            self.assertTrue(all(c in (0, dim) or c == sent[0][max(range(16), key=lambda i: sent[0][i])] for c in sent[0]), (page, sent[0]))
            self.assertEqual(sum(c not in (0, dim) for c in sent[0]), 1, page)   # exactly one pad stronger: the selected one
            self.assertEqual([p.e.r(pads + i * 16) for i in range(16)], [white if i == 5 else 0x00101010 for i in range(16)])  # native state restored

    def test_stopped_clip_from_another_track_is_not_edited(self):
        p = Fixture()
        p.e.w(MODEL+0x144, 999)
        before = p.notes()
        p.seqmode()
        self.assertEqual(p.u.mem_read(STATE+14, 1), b"\0")
        p.pad_event(0, True)
        p.pad_event(0, False, 50)
        self.assertEqual(p.notes(), before)

    def test_input_gate_swallows_press_pressure_release_without_native_recording(self):
        p = NativeInput()
        p.u.mem_write(STATE+14, b"\1\7")
        p.packet(0, [1000]+[0]*15)
        self.assertEqual(p.events(), [])
        self.assertEqual(p.custom(), [(254, 0x314d5442, 0x3151534b, 0, 12, 0x31525407)])
        p.packet(0, [1800]+[0]*15)
        self.assertEqual((p.events(), p.custom()), ([], []))
        p.u.mem_write(STATE+14, b"\0")
        p.packet(0)
        self.assertEqual(p.events(), [])
        self.assertEqual(p.custom(), [(254, 0x314d5442, 0x3151534b, 0, 13, 0x31525407)])

    def test_notes_held_before_seq_keep_native_release_and_plain_kit_stays_native(self):
        p = NativeInput()
        p.packet(0, [1000]+[0]*15)
        self.assertEqual(p.events(), [(172, 0, 1000), (174, 0, 1000)])
        p.u.mem_write(STATE+14, b"\1\3")
        p.packet(0)
        self.assertEqual(p.events(), [(173, 0, 0), (174, 0, 0)])


if __name__ == "__main__":
    unittest.main()
