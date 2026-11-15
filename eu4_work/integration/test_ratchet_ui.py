"""R6.14 ratchet UI (M4): Steps view and melodic piano page, in the emulator.

Reuses test_lock_touch's fixture: stock 1.6.1 native registry, encoder slots,
note selection and note container run unchanged; step_lock_ui.c,
melodic_lock_ui.c and ratchet_ui.c are compiled from source. Model lookup,
heap, publish/Undo storage and repaint are fixtures. rt_ui_arrows is called
the way fx_dispatch calls it (button code 0xAF press / 0xB0 release, index
0 = Left, 9 = Right). Software evidence only; not a hardware result.
"""
from pathlib import Path
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

import test_lock_touch as lt
from test_lock_touch import Fixture, MODEL

COUNT, SHAPE, DEPTH, PROB = 0x9F, 0xA0, 0xA1, 0xA5
RT_KEYS = [COUNT, SHAPE, DEPTH, PROB]
LEFT, RIGHT, PRESS, RELEASE = 0, 9, 0xAF, 0xB0
BLOCK = 0xC0700000
TR_KEY, TR_MODE_KEY = 0x9D, 0x9E


def setUpModule():
    lt.setUpModule()


def make(pitched):
    """Fixture whose header runs like production: the native header body
    (0815C27C Steps view / 081599BC piano page) runs between the patched
    before/after hooks, so slots the native header leaves empty are rebuilt."""
    p = Fixture(pitched)
    p.u.hook_del(p.hooks[7 if pitched else 6])
    p.grid = None

    def header():
        if pitched:
            p.call(0x081599BC, p.view)
            if p.grid is not None:
                # The native header reads the clip's Step Len from the model
                # (getter 081336xx); this fixture model has none, so stand in.
                p.w(p.view + 0x11CD14, p.grid)
            p.call("melodic_locks_header", p.view)
        else:
            p.call("locks_header_before", p.view)
            p.call(0x0815C27C, p.view)
            p.call("locks_header_after", p.view)
    p.header = header
    p.header()
    return p


def ratchet(p, i=0):
    return p.call("locks_ratchet_get", p.word(i))


def fields(r):
    """(count, shape, depth, prob) of a ratchet word; no ratchet = (1, 0, 0, 0)."""
    if not r:
        return (1, 0, 0, 0)
    return ((r & 7) + 1, (r >> 3) & 3, (r >> 8) & 127, (r >> 16) & 255)


def arrow(p, index, release_too=True):
    pressed = p.call("rt_ui_arrows", PRESS, index)
    released = p.call("rt_ui_arrows", RELEASE, index) if release_too else None
    p.header()
    return pressed, released


def keys(p):
    return [p.key(i) for i in range(4, 8)]


def block(p):
    """An RtBlock (magic RTB1) in SDRAM, its pointer in EuControl.reserved[3]."""
    p.u.mem_write(BLOCK, bytes(2048))
    p.w(BLOCK, 0x31425452)
    p.w(0x24041FDC, BLOCK)


def cfg(p):
    raw = bytes(p.u.mem_read(BLOCK, 64))
    owner = struct.unpack_from("<8I", raw, 8)
    return owner, list(raw[40:48]), list(struct.unpack_from("<8H", raw, 48))


class StepsView(unittest.TestCase):
    def test_arrows_without_a_held_step_stay_native(self):
        p = make(False)
        p.select([])
        before = keys(p)
        self.assertEqual(arrow(p, RIGHT), (0, 0))
        self.assertEqual(arrow(p, LEFT), (0, 0))
        self.assertEqual(keys(p), before)
        self.assertNotIn(COUNT, keys(p))

    def test_right_switches_encoders_5_to_8_and_left_switches_back(self):
        p = make(False)
        lock_keys = keys(p)
        self.assertNotIn(COUNT, lock_keys)
        self.assertEqual(arrow(p, RIGHT), (1, 1))
        self.assertEqual(keys(p), RT_KEYS)
        self.assertEqual([p.r(p.slot(i) + 0xA0) for i in range(4, 8)][0], 1)
        self.assertEqual(arrow(p, LEFT), (1, 1))
        self.assertEqual(keys(p), lock_keys)

    def test_release_without_swallowed_press_is_not_taken(self):
        p = make(False)
        self.assertEqual(p.call("rt_ui_arrows", RELEASE, RIGHT), 0)
        self.assertEqual(p.call("rt_ui_arrows", PRESS, 5), 0)  # other buttons untouched

    def test_k16_modifier_keeps_native_arrows(self):
        p = make(False)
        p.w(0x24048CC0 + 8, 1)
        self.assertEqual(arrow(p, RIGHT), (0, 0))
        self.assertNotIn(COUNT, keys(p))

    def test_edits_build_the_ratchet_with_one_undo_snapshot_each(self):
        p = make(False)
        arrow(p, RIGHT)
        p.value(4, 4)
        self.assertEqual(fields(ratchet(p)), (4, 0, 0, 0))
        self.assertEqual(len(p.undo), 1)
        p.value(5, 2)
        p.value(6, 50)
        p.value(7, 49)  # encoder 49 = 50 % (condition 50)
        self.assertEqual(fields(ratchet(p)), (4, 2, 50, 50))
        self.assertEqual(len(p.undo), 4)
        self.assertEqual([p.r(p.slot(i) + 0xA0) for i in range(4, 8)], [4, 2, 50, 49])
        # untouched steps keep no ratchet
        self.assertEqual(ratchet(p, 1), 0)
        self.assertEqual(ratchet(p, 2), 0)

    def test_prob_always_and_a_b_codes(self):
        p = make(False)
        arrow(p, RIGHT)
        p.value(4, 2)
        p.value(7, 99)
        self.assertEqual(fields(ratchet(p))[3], 0)  # Always
        p.value(7, 105)
        self.assertEqual(fields(ratchet(p))[3], 105)  # an A:B condition (3:4)
        # exp5 picker order: 1ST..!PRE follow 4:4 (positions 109..112); older A:B are not offered
        p.value(7, 110)
        self.assertEqual(fields(ratchet(p))[3], 136)  # !1ST
        p.value(7, 120)
        self.assertEqual(fields(ratchet(p))[3], 138)  # beyond the offered list: the last entry (!PRE)
        p.value(7, 0)
        self.assertEqual(fields(ratchet(p))[3], 1)  # 1 %

    def test_edit_applies_to_every_held_step_with_one_snapshot(self):
        p = make(False)
        p.select([101, 102])
        arrow(p, RIGHT)
        p.value(4, 3)
        self.assertEqual(fields(ratchet(p, 0))[0], 3)
        self.assertEqual(fields(ratchet(p, 1))[0], 3)
        self.assertEqual(ratchet(p, 2), 0)
        self.assertEqual(len(p.undo), 1)

    def test_exp3_choosing_a_shape_starts_with_a_depth_that_changes_the_hits(self):
        # P168 exp3 (owner: ratchet Shape does not change velocity). Fade/Swell scale by Depth
        # (ratchet_shared.h rt_velocity: depth 0 = every hit at the note's velocity) and Depth started
        # at 0. Choosing a shape while Depth is 0 sets 60 %; a Depth the user set is kept; Flat keeps 0.
        def hits(word, v=100):  # the player's rule, restated from ratchet_shared.h for the check below
            n, shape, depth, _ = fields(word)
            out = []
            for k in range(n):
                pos = k if shape == 1 else n - 1 - k
                out.append(v if not shape or not depth else max(1, min(127, (v * (100 * (n - 1) - depth * pos) + 50 * (n - 1)) // (100 * (n - 1)))))
            return out
        p = make(False); arrow(p, RIGHT); p.value(4, 4)
        self.assertEqual(fields(ratchet(p)), (4, 0, 0, 0)); self.assertEqual(hits(ratchet(p)), [100] * 4)
        p.value(5, 1)                                    # Fade
        self.assertEqual(fields(ratchet(p)), (4, 1, 60, 0))
        self.assertEqual(hits(ratchet(p)), [100, 80, 60, 40])
        p.value(5, 2); self.assertEqual(hits(ratchet(p)), [40, 60, 80, 100])   # Swell keeps the depth
        p.value(6, 25); p.value(5, 1); self.assertEqual(fields(ratchet(p)), (4, 1, 25, 0))  # a chosen depth stays
        p.value(6, 0); p.value(5, 0); self.assertEqual(fields(ratchet(p)), (4, 0, 0, 0))    # Flat: nothing set
        p.value(6, 0); self.assertEqual(fields(ratchet(p)), (4, 0, 0, 0))

    def test_count_one_forgets_shape_depth_prob(self):
        p = make(False)
        arrow(p, RIGHT)
        p.value(4, 4)
        p.value(5, 1)
        p.value(6, 70)
        p.value(4, 1)
        self.assertEqual(ratchet(p), 0)
        p.value(4, 2)
        self.assertEqual(fields(ratchet(p)), (2, 0, 0, 0))

    def test_shape_depth_prob_do_nothing_while_count_is_one(self):
        p = make(False)
        arrow(p, RIGHT)
        before = p.notes()
        p.value(5, 2)
        p.value(6, 80)
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])

    def test_ratchet_keeps_the_condition_and_survives_condition_edits(self):
        p = make(False)
        p.call("locks_encoder", p.view, 0x198, 49)  # condition 50 %
        p.header()
        condition = p.call("locks_condition_get", p.word())
        arrow(p, RIGHT)
        p.value(4, 3)
        self.assertEqual(p.call("locks_condition_get", p.word()), condition)
        arrow(p, LEFT)
        p.call("locks_encoder", p.view, 0x198, 120)
        p.header()
        self.assertEqual(fields(ratchet(p))[0], 3)

    def test_ratchet_keys_are_ignored_off_the_ratchet_page(self):
        p = make(False)
        before = p.notes()
        self.assertEqual(p.call("locks_encoder", p.view, COUNT, 4), 1)
        self.assertEqual(p.notes(), before)

    def test_page_is_remembered_until_changed(self):
        p = make(False)
        arrow(p, RIGHT)
        p.select([])
        p.select([102])
        self.assertEqual(keys(p), RT_KEYS)
        arrow(p, LEFT)
        p.select([])
        p.select([101])
        self.assertNotIn(COUNT, keys(p))

    def test_no_lock_memory_is_atomic(self):
        p = make(False)
        p.select([101, 102])
        arrow(p, RIGHT)
        p.w(0x30000048, p.r(0x3000004C))  # heap exhausted: no new record
        before = p.notes()
        p.value(4, 4)
        self.assertEqual(p.notes(), before)
        self.assertEqual(p.undo, [])


class MelodicViews(unittest.TestCase):
    def seq_view(self, p):
        p.u.mem_write(p.view + 0x125DAC, b"\1")
        p.header()

    def test_event_tab_ratchet_page(self):
        p = make(True)
        before = keys(p)
        self.assertEqual(arrow(p, RIGHT), (1, 1))
        self.assertEqual(keys(p), RT_KEYS)
        p.value(4, 3)
        p.value(5, 1)
        self.assertEqual(fields(ratchet(p)), (3, 1, 60, 0))  # exp3: a chosen shape starts at depth 60 (was 0 = no audible change)
        self.assertEqual(ratchet(p, 1), 0)
        arrow(p, LEFT)
        self.assertEqual(keys(p), before)

    def test_seq_view_keeps_transpose_unless_the_ratchet_page_is_active(self):
        p = make(True)
        self.seq_view(p)
        native = [p.key(i) for i in range(5)]
        self.assertEqual([p.key(6), p.key(7)], [TR_KEY, TR_MODE_KEY])
        arrow(p, RIGHT)
        self.assertEqual(keys(p), RT_KEYS)
        self.assertEqual([p.key(i) for i in range(4)], native[:4])
        p.value(4, 2)
        self.assertEqual(fields(ratchet(p))[0], 2)
        arrow(p, LEFT)
        self.assertEqual([p.key(6), p.key(7)], [TR_KEY, TR_MODE_KEY])
        self.assertEqual(fields(ratchet(p))[0], 2)

    def test_melodic_arrows_need_a_selected_note(self):
        p = make(True)
        p.select([])
        self.assertEqual(arrow(p, RIGHT), (0, 0))
        self.assertNotIn(COUNT, keys(p))

    def test_melodic_edit_applies_to_all_selected_notes(self):
        p = make(True)
        p.select([101, 103])
        arrow(p, RIGHT)
        p.value(4, 5)
        self.assertEqual(fields(ratchet(p, 0))[0], 5)
        self.assertEqual(ratchet(p, 1), 0)
        self.assertEqual(fields(ratchet(p, 2))[0], 5)
        self.assertEqual(len(p.published), 1)
        p.value(4, 1)
        self.assertEqual(ratchet(p, 0), 0)
        self.assertEqual(ratchet(p, 2), 0)

    def test_seq_view_publishes_step_len_into_the_rt_block(self):
        p = make(True)
        block(p)
        for grid in range(15):
            bits = struct.unpack_from("<I", lt.IMAGE, 0x080BDBEC - lt.BASE + grid * 4)[0]
            value = struct.unpack("<f", struct.pack("<I", bits))[0] * 960
            if value <= 0 or value > 30720 or abs(value - round(value)) > 1e-3:
                continue
            p.grid = grid
            self.seq_view(p)
            owner, amount, step = cfg(p)
            at = owner.index(p.owner)
            self.assertEqual(step[at], round(value), grid)
            self.assertEqual(amount[at], 100)
            self.assertEqual(owner.count(p.owner), 1)

    def test_event_tab_does_not_publish_step_len(self):
        p = make(True)
        block(p)
        p.grid = 5
        p.header()
        self.assertNotIn(p.owner, cfg(p)[0])


class NoteTicks(unittest.TestCase):
    """Piano-roll dividers (rt_note_ticks, called from lane_paint after the
    native grid paint): count-1 thin lines across each ratchet note, colour
    F1, inside the native note rectangle (0817566A)."""
    def paint(self, p):
        fills = []

        def fill(u, a, n, d):
            r = u.reg_read(UC_ARM_REG_R0)
            fills.append((tuple(p.r(r + i * 4) for i in range(4)), u.reg_read(UC_ARM_REG_R1)))
            p.ret()
        hook = p.u.hook_add(UC_HOOK_CODE, fill, begin=0x08166EF6, end=0x08166EF6)
        ctx = 0x2002F000
        p.w(ctx, 1)
        p.w(ctx + 4, 0x20020000)
        p.call("rt_note_ticks", p.view + 0x38, ctx)
        p.u.hook_del(hook)
        return fills

    def test_dividers_split_only_ratchet_notes_evenly(self):
        p = make(True)
        self.assertEqual(self.paint(p), [])
        arrow(p, RIGHT)
        for count in (2, 4, 8):
            p.value(4, count)
            fills = self.paint(p)
            self.assertEqual(len(fills), count - 1, count)
            self.assertEqual({c for r, c in fills}, {0xF1})
            self.assertEqual(len({(r[1], r[2], r[3]) for r, c in fills}), 1)
            xs = [r[0] for r, c in fills]
            self.assertEqual(xs, sorted(xs))
            gaps = [b - a for a, b in zip(xs, xs[1:])]
            if gaps:
                self.assertLessEqual(max(gaps) - min(gaps), 1)
        p.value(4, 1)
        self.assertEqual(self.paint(p), [])

    def test_partial_or_hidden_grid_draws_nothing(self):
        p = make(True)
        arrow(p, RIGHT)
        p.value(4, 3)
        ctx = 0x2002F000
        p.w(ctx, 0)  # neither paint flag
        p.w(ctx + 4, 0x20020000)
        calls = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *a: calls.append(1), begin=0x08166EF6, end=0x08166EF6)
        p.call("rt_note_ticks", p.view + 0x38, ctx)
        p.u.hook_del(hook)
        self.assertEqual(calls, [])



if __name__ == "__main__":
    unittest.main(verbosity=2)
