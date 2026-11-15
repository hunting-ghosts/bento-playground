"""R6.16c: the mono roll is back in the safe form (see test_ratchet_inert). R6.16 ratchet mono roll on the REAL native sampler path (owner, hardware 9 Nov:
Shapes inaudible; decision: hits 2..n of a note cut that note's previous hit).

kick_native_path.Chain: the M7 player arms a note (rt_live, same arm() as the
native renderer's adapter), the real rt_block plays the later hits through the
native note-on 0805F8E0 and router post 0809F040, the sampler block process
0808E9A0 starts voices (native allocation, free voices or polyphony 1), and
the voice-start endpoint runs rt_voice (release the note's previous hit with
the native 5 ms ramp) before kick_voice. Fails on R6.15 (no rt_live/rt_voice;
with free voices a Fade roll there peaks 0.109/0.096/0.128/0.112 = Flat).
Software evidence only."""
import sys
import unittest

sys.argv = sys.argv[:1]
import kick_native_path as nr

KICK = (55, 65, 45, 65, 0, 25, 0)
RTB = nr.RTB
CUTS = RTB + 2656  # RtBlock.tick, order, cut_count, cut_diag[5]


def roll(shape, depth, mode=4, count=4, **kw):
    c = nr.Chain(KICK, mode=mode, **kw)
    c.note(c.token(count, shape, depth) if count > 1 else 0, 100)
    out = []
    for _ in range(120):
        out.extend(c.run_block())
    peaks = [max(abs(x) for x in out[k * 1500 + 200:k * 1500 + 1400]) for k in range(4)]
    return c, peaks


class MonoRoll(unittest.TestCase):
    def test_shapes_are_distinct_with_free_voices_and_polyphony_one(self):
        for mode in (4, 1):
            with self.subTest(polyphony=mode):
                _, flat = roll(0, 0, mode)
                _, fade = roll(1, 100, mode)
                _, swell = roll(2, 100, mode)
                for f in flat:
                    self.assertAlmostEqual(f, flat[0], delta=.003)
                for got, want in ((fade, (1, .67, .33, .01)), (swell, (.01, .33, .67, 1))):
                    for g, w in zip(got, want):
                        self.assertAlmostEqual(g / flat[0], w, delta=.03)

    def test_each_hit_cuts_the_previous_one(self):
        c, _ = roll(1, 100, 4)
        p = c.p
        self.assertEqual(sum(c.active()), 1)  # only the last hit still sounds
        self.assertEqual([p.r(CUTS + 4 * i) for i in (2, 4, 5, 6)], [0, 3, 4, 4])  # pending, cuts, posted, consumed

    def test_overlapping_sample_hits_are_released_natively(self):
        # 1/64 grid, 8 hits 187 frames apart: sample voices would overlap.
        c = nr.Chain(KICK, mode=4, sample=True, grid=14); p = c.p; p.reader_gain = 16384
        c.note(c.token(8, 1, 100), 100)
        most = 0
        for _ in range(40):
            c.run_block()
            # released = the native ramp's release flag (voice+0x58+0x18, set by 08063960)
            ramps = [(p.u.mem_read(v, 1)[0], p.u.mem_read(v + 0x58 + 0x18, 1)[0]) for v in c.voices]
            most = max(most, sum(1 for on, released in ramps if on and not released))
        self.assertEqual(most, 1)  # never two un-released hits of the note at once
        self.assertGreaterEqual(p.r(CUTS + 16), 3)  # still-sounding previous hits were cut
        self.assertEqual(p.r(RTB + 72 + 8), 7)  # all later hits played

    def test_plain_notes_post_nothing_and_never_cut(self):
        c, _ = roll(0, 0, 4, count=1)
        self.assertEqual([c.p.r(CUTS + 4 * i) for i in (2, 4, 5)], [0, 0, 0])  # nothing pending, cut or posted

    def test_voice_start_endpoint_calls_rt_voice_first(self):
        image = nr.engine.__globals__['image']; at = 0x080d5800 - 0x08040000
        self.assertEqual(image[at:at + 2], bytes.fromhex("13b5"))  # push {r0,r1,r4,lr}; bl rt_voice; ...


if __name__ == "__main__":
    unittest.main(verbosity=2)
