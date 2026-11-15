"""R6.17 trigger conditions 1ST, !1ST, PRE, !PRE (owner) on the built image.

Codes appended to the condition list: 135 1ST, 136 !1ST, 137 PRE, 138 !PRE
(0 Always, 1..99 %, 100..134 A:B unchanged). They gate a note's locks (EU7
lock condition) and a ratchet (Prob). Semantics as Elektron / romanjeff's
bento_enhanced v3.40 (GPL-3.0, reference only): 1ST = first pass after
launch/restart (pass counter = the T2 counter at 24048A60), PRE = the most
recent A:B/1ST/!1ST decision on the same sequence passed (false until one;
PRE steps and % don't change it). Notes play through the installed native
renderer and the patched note-on adapter (locks_native_filter, rt_note);
packets and the lock word applied to each are captured at the router."""
import struct
import unittest

import test_ratchet_play as trp
from test_euclidean import note
from test_integration import UU, IMAGE

LOCK = 0x5101030c
FIRST, NOT_FIRST, PRE, NOT_PRE = 135, 136, 137, 138


def fixture(loop):
    p = trp.Play(); c = 0x24048a60
    for off, v in ((0, p.audioseq), (4, p.r(p.audioseq + 12)), (8, p.clip), (12, loop)):
        p.w(c + off, v)
    return p


def cond(p, c, lock=LOCK):
    w = p.call(UU['locks_condition_word'], lock, c)
    assert w not in (0, 0xffffffff), (c, hex(w))
    return w


def locks_per_note(p, notes, until):
    p.notes = notes; p.sync_notes(p.notes); p.play(until)
    return [lt for lt, pk in zip(p.locktrace, p.emitted) if pk[0] == 0x12]


class TriggerConditions(unittest.TestCase):
    def test_codes_labels_and_ranges(self):
        p = trp.Play()
        for c in range(139):
            self.assertEqual(p.call(UU['locks_condition_get'], cond(p, c) if c else LOCK), c)
        self.assertEqual(p.call(UU['locks_condition_word'], LOCK, 139), 0xffffffff)
        self.assertNotIn(p.call(UU['locks_ratchet_pack'], 4, 0, 0, 138), (0, 0xffffffff))
        self.assertEqual(p.call(UU['locks_ratchet_pack'], 4, 0, 0, 139), 0xffffffff)
        t = 0x081b6000 - 0x08040000; ptr = struct.unpack_from("<139I", IMAGE, t)
        text = lambda a: IMAGE[a - 0x08040000:IMAGE.index(b"\0", a - 0x08040000)].decode()
        # P168 exp5 (owner, 12 Nov): picker order. Offered: 0..98 %, Always, A:B up to 4:4, 1ST..!PRE (113);
        # older A:B 1:5..8:8 follow (shown for saved values, never offered). Stored codes unchanged.
        self.assertEqual([text(ptr[i]) for i in (99, 100, 108, 109, 110, 111, 112, 113, 138)],
                         ["Always", "1:2", "4:4", "1ST", "!1ST", "PRE", "!PRE", "1:5", "8:8"])

    def test_exp5_native_note_list_offers_113_entries(self):
        # the native note condition list builder (K16 T2 count 135) offers A:B up to 4:4 and 1ST..!PRE
        import test_integration as ti
        from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
        k = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
        self.assertEqual(IMAGE[0x08165d40 - 0x08040000:0x08165d40 + 4 - 0x08040000], bytes(k.asm('movs r3,#113; str r3,[sp]', 0x08165d40)[0]))

    def test_exp5_native_note_editors_use_the_picker_order(self):
        # The native drum/piano note editors (K16 T2 adapters, native code before and after them runs):
        # stored byte -> list position -> stored byte in picker order; saved older A:B (109..134) are
        # shown at 113..138 and a turn from there lands in the offered list.
        from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_R6
        p = trp.Play(); sp = 0x2003c000; dest = 0x20027000

        def run(a, stop, regs=()):
            p.u.reg_write(UC_ARM_REG_SP, sp)
            for r, v in regs:
                p.u.reg_write(r, v)
            p.u.emu_start(a | 1, stop, count=10000); assert p.u.reg_read(UC_ARM_REG_PC) == stop
        pos = lambda raw: 99 if raw == 0 or raw > 138 else raw - 1 if raw < 100 else raw if raw < 109 else raw + 4 if raw < 135 else raw - 26
        code = lambda q: 0 if q == 99 else q + 1 if q < 99 else q if q < 109 else q + 26 if q < 113 else q - 4
        for raw in range(140):
            p.u.mem_write(sp + 0x49, bytes([raw])); run(0x08159b74, 0x08159b18, ((UC_ARM_REG_R6, dest),))
            self.assertEqual(p.r(dest), pos(raw), raw)
            p.u.mem_write(sp + 1, bytes([raw])); run(0x0815c3bc, 0x0815c352, ((UC_ARM_REG_R1, dest),))
            self.assertEqual(p.r(dest), pos(raw), raw)
        for q in range(139):
            run(0x0815c8b4, 0x0815c8be, ((UC_ARM_REG_R1, q),)); self.assertEqual(p.u.reg_read(UC_ARM_REG_R6), code(q), q)
        edit = lambda raw: 100 if raw == 0 or raw > 138 else raw if raw < 100 else raw + 1 if raw < 109 else raw + 5 if raw < 135 else raw - 25
        stored = lambda e: 0 if e == 100 else e if e < 100 else e - 1 if e <= 109 else e + 25
        for raw in (0, 1, 50, 99, 100, 108, 109, 134, 135, 138):
            p.u.mem_write(sp + 0x25, bytes([raw])); run(0x08158f1c, 0x08158f26)
            current = p.u.reg_read(UC_ARM_REG_R3); self.assertEqual(current, edit(raw), raw)
            for target in (1, 50, 99, 100, 101, 109, 110, 113, 120):
                p.u.mem_write(sp + 0x19, bytes([raw])); p.w(sp + 0x84, (target - current) & 0xffffffff)
                run(0x08158a7c, 0x08158aac)
                want = raw if target == current else stored(min(113, target))
                self.assertEqual(p.u.mem_read(sp + 0x31, 1)[0], want, (raw, target))

    def test_exp5_the_notes_own_condition_plays_1st_and_not_1st(self):
        # owner: 1ST/!1ST/PRE/!PRE "especially on the note itself" (the note's condition byte, native note path)
        for loop in range(4):
            for c, want in ((FIRST, loop == 0), (NOT_FIRST, loop != 0)):
                with self.subTest(loop=loop, cond=c):
                    p = fixture(loop); p.notes = [note(1, cond=c, ident=11)]; p.sync_notes(p.notes); p.play(6000 * 3)
                    self.assertEqual(len(p.ons()), 1 if want else 0)

    def test_exp5_note_pre_follows_the_notes_own_a_b(self):
        for loop in range(4):
            with self.subTest(loop=loop):
                p = fixture(loop)
                p.notes = [note(1, cond=100, ident=11, pad=2), note(2, cond=PRE, ident=12, pad=3),
                           note(3, cond=NOT_PRE, ident=13, pad=4)]
                p.sync_notes(p.notes); p.play(6000 * 5)
                a = loop % 2 == 0
                got = sorted(o[1] for o in p.ons())
                self.assertEqual(len(p.ons()), 2 if a else 1, (loop, p.ons()))

    def test_exp5_old_note_a_b_codes_keep_their_meaning(self):
        for loop in range(3):
            for c in (100, 108, 109, 134):
                with self.subTest(loop=loop, cond=c):
                    i, b = c - 100, 2
                    while i >= b:
                        i -= b; b += 1
                    p = fixture(loop); p.notes = [note(1, cond=c, ident=11)]; p.sync_notes(p.notes); p.play(6000 * 3)
                    self.assertEqual(len(p.ons()), 1 if loop % b == i else 0)

    def test_1st_and_not_1st_across_loops(self):
        for loop in range(4):
            for c, want in ((FIRST, loop == 0), (NOT_FIRST, loop != 0)):
                with self.subTest(loop=loop, cond=c):
                    p = fixture(loop)
                    self.assertEqual(locks_per_note(p, [note(1, lock=cond(p, c), ident=11)], 6000 * 3),
                                     [LOCK if want else 0])

    def test_pre_follows_the_latest_conditional_step_of_the_sequence(self):
        for loop in range(4):
            with self.subTest(loop=loop):
                p = fixture(loop)
                # step 1: 1:2 (passes on even passes); steps 2/3: PRE, !PRE; step 4: PRE again
                got = locks_per_note(p, [note(1, lock=cond(p, 100), ident=11), note(2, lock=cond(p, PRE), ident=12),
                                         note(3, lock=cond(p, NOT_PRE), ident=13), note(4, lock=cond(p, PRE), ident=14)],
                                     6000 * 6)
                a = loop % 2 == 0
                self.assertEqual(got, [LOCK if a else 0, LOCK if a else 0, 0 if a else LOCK, LOCK if a else 0])

    def test_pre_chain_through_1st_and_reset_state(self):
        p = fixture(0)
        got = locks_per_note(p, [note(1, lock=cond(p, PRE), ident=11),        # no decision yet: false
                                 note(2, lock=cond(p, 50), ident=12),         # % does not count
                                 note(3, lock=cond(p, PRE), ident=13),
                                 note(4, lock=cond(p, NOT_FIRST), ident=14),  # loop 0: !1ST fails
                                 note(5, lock=cond(p, NOT_PRE), ident=15)], 6000 * 7)
        self.assertEqual([got[0], got[2], got[3], got[4]], [0, 0, 0, LOCK])

    def test_ratchets_with_the_new_prob_values(self):
        for loop in range(3):
            for prob, want in ((FIRST, loop == 0), (NOT_FIRST, loop != 0)):
                with self.subTest(loop=loop, prob=prob):
                    p = fixture(loop); tok = p.token(LOCK, p.rt(3, 0, 0, prob))
                    p.notes = [note(1, lock=tok, ident=11)]; p.sync_notes(p.notes); p.play(6000 * 3)
                    self.assertEqual(len(p.ons()), 3 if want else 1)
        for loop in range(2):  # PRE after the note's own 1:2 lock condition
            with self.subTest(loop=loop, prob=PRE):
                p = fixture(loop); tok = p.token(LOCK, p.rt(3, 0, 0, PRE), 100)
                p.notes = [note(1, lock=tok, ident=11)]; p.sync_notes(p.notes); p.play(6000 * 3)
                self.assertEqual(len(p.ons()), 3 if loop == 0 else 1)

    def test_old_codes_keep_their_meaning(self):
        for loop in range(3):
            for c in (100, 101, 102, 134):
                with self.subTest(loop=loop, cond=c):
                    i, b = c - 100, 2
                    while i >= b:
                        i -= b; b += 1
                    p = fixture(loop)
                    self.assertEqual(locks_per_note(p, [note(1, lock=cond(p, c), ident=11)], 6000 * 3),
                                     [LOCK if loop % b == i else 0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
