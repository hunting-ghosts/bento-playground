"""R6.16 ratchets end to end: real UI -> real sequencer -> router packets.

One emulator instance on the built image: the one-shot SEQ page as the owner
uses it (fx_dispatch page entry, which here also opens the remembered Euclid
view, so the pad is a native Euclid pad played by the M7 live scheduler), the
real Steps view, a step selected, Right through fx_dispatch, the ratchet set
with native encoder turns (0xCF events -> locks_encoder -> EU7 record), then
the real sequencer renderer + live scheduler play it and the hits are
captured at the native router post (velocities). The audio half (voices,
levels, mono roll) is test_ratchet_mono_roll on the real sampler path.
Fails on R6.15: live-scheduled pads (Euclid, velocity modes, own Step Count)
played one hit. Software evidence only."""
import struct
import unittest

import test_eu8
import test_eu9
import test_ratchet_play as trp
from test_euclidean import note
from test_live import UU
from unicorn import UC_HOOK_CODE

KEEP = []


class E2E(trp.Play, test_eu9.Native):
    pass


def shaped(v, k, n, shape, depth):
    if not shape or not depth:
        return v
    steps = n - 1; pos = k if shape == 1 else steps - k
    out = (v * (100 * steps - depth * pos) + 50 * steps) // (100 * steps)
    return max(1, min(127, out))


def seq_page(vel=100):
    p = E2E(notes=[note(0, pad=2, vel=vel)]); KEEP.append(p)
    test_eu8.Tests().full_view(p); p.select(0); p.call(0x0815c27c, p.seqview)
    p.u.mem_write(p.model + 0x12c, b"\x27"); p.call(UU['fx_dispatch'], p.model, 0x3f, 0, 0)
    for at in (0x0813130c, 0x081257f0):  # native redraw / LED flush: fixture
        p.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: p.ret(), begin=at, end=at)
    # P168 exp3: a pad now opens on Steps (owner); these tests are about a Euclid pad, so the Euclid tab
    # is chosen as the user would (header action 1055 through the native view handler).
    if not p.call(UU['seq_eu_mode'], p.seqview):
        p.u.mem_write(0x2002e000, struct.pack('<5I', 0x1055, 0, 0, 0, 0)); p.call(0x0815d600, p.seqview, 0x2002e000)
    return p


def ui_ratchet(p, count, shape, depth):
    """Right (fx_dispatch), then native encoder turns on encoders 5..7."""
    p.call(UU['fx_dispatch'], p.model, 0xaf, 0, 9); p.call(UU['fx_dispatch'], p.model, 0xb0, 0, 9)
    p.call(0x0815c27c, p.seqview)

    def turn(i, steps, unit=12800):
        for _ in range(abs(steps)):
            p.w(0x30035f40, p.r(0x30035f40) + 10000)  # slow turn: native factor 1
            p.call(0x08171e44, p.seqview + 0xebf0 + 0x38 + i * 0x468, unit if steps > 0 else -unit & 0xffffffff)
        p.call(0x0815c27c, p.seqview)
    turn(4, count - 1); turn(5, shape)
    # P168 exp3: choosing a shape starts Depth at 60 (it was 0); turn from where the encoder now stands.
    # Run 6 (owner: our controls too slow): Depth 0..100 is a wide field and moves like a native percent
    # control, one sweep per 160,000 units, so one value is 1,600 units (it was one value per 12,800).
    start = (p.call(UU['locks_ratchet_get'], struct.unpack_from("<I", p.events()[0], 20)[0]) >> 8) & 127
    turn(6, depth - start, 1600)
    w = struct.unpack_from("<I", p.events()[0], 20)[0]
    r = p.call(UU['locks_ratchet_get'], w)
    assert ((r & 7) + 1, (r >> 3) & 3, (r >> 8) & 127) == (count, shape, depth), hex(r)
    return w


def pad2(p):
    bank = p.r(0x24041fc4); rec = bank + 32
    assert p.r(rec + 4) == p.owner
    return rec + 32 + 8 * 2


def play(p):
    p.sync_notes(p.events()); p.emitted.clear(); p.absolute.clear(); p.play(6000 * 3)
    return p.ons()


class EndToEnd(unittest.TestCase):
    def test_ui_made_shapes_play_on_the_seq_page_euclid_pad(self):
        for shape, depth in ((0, 0), (1, 100), (2, 100), (1, 50)):
            with self.subTest(shape=shape, depth=depth):
                p = seq_page()
                self.assertTrue(p.r(pad2(p)) >> 25 & 1)  # an enabled native Euclid pad
                ui_ratchet(p, 4, shape, depth)
                ons = play(p)
                self.assertEqual([f for f, _, _ in ons], [0, 1500, 3000, 4500])
                self.assertEqual([v for _, _, v in ons], [shaped(100, k, 4, shape, depth) for k in range(4)])

    def test_velocity_mode_pad_shapes_its_effective_velocity(self):
        p = seq_page(); at = pad2(p)
        p.w(at + 4, 100 | 1 << 8 | 60 << 16)  # velocity mode 1, depth 60
        ui_ratchet(p, 4, 1, 100)
        ons = play(p)
        self.assertEqual(len(ons), 4)
        first = ons[0][2]
        self.assertEqual([v for _, _, v in ons], [shaped(first, k, 4, 1, 100) for k in range(4)])

    def test_own_step_count_pad_plays_ratchets(self):
        p = seq_page(); at = pad2(p)
        p.w(at, 15 | 1 << 26 | 1 << 27); p.w(at + 4, 100)  # manual per-sound cycle, 16 steps
        ui_ratchet(p, 3, 2, 100)
        self.assertEqual([v for _, _, v in play(p)], [shaped(100, k, 3, 2, 100) for k in range(3)])

    def test_plain_live_step_stays_one_hit(self):
        p = seq_page()
        self.assertEqual([v for _, _, v in play(p)], [100])


if __name__ == "__main__":
    unittest.main(verbosity=2)
