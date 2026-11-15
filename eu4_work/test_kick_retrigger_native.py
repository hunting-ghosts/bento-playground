"""R6.15: Kick retrigger on the REAL native sampler path (owner, hardware 9 Nov:
the Kick still clicked on a retrigger while the previous hit sounded, the same
on R6.10 and R6.14).

Events go through the real router queue into the sampler block process
0808E9A0: sequencer note (0x12 -> 08094760) and pad press (0x4E -> 08093BA0),
native voice allocation, our kick_voice hooks, the native render loop and the
native postprocess. Finding: the new hit gets ANOTHER voice; with the pad full
(polyphony 1, or all voices busy) the native note-on releases the old voice
through its per-voice ramp (voice+0x58, 256 samples) and switches it off at ~6 %
of its level: a one-sample step. kick_render now shapes a releasing voice to 0
by the ramp's end. Fixtures: sample lookup, sample provider status, clock and
voice-age objects (kick_native_path.py). Software evidence only."""
import hashlib
import struct
import sys
import unittest

sys.argv = sys.argv[:1]
import kick_native_path as nr

KICK0 = (55, 65, 45, 65, 0, 25, 0)    # Sweep 0: the worst case on hardware
KICK100 = (55, 65, 45, 65, 100, 25, 0)
ISOLATED = "2b4f8cd2f48ae781c2ddede56d66ce591b0e5125bc0d54bfa8d272050d9f8860"  # R6.14 = R6.15


def digest(x):
    return hashlib.sha256(struct.pack("<%df" % len(x), *x)).hexdigest()


class NativeRetrigger(unittest.TestCase):
    def test_full_pad_releases_the_old_voice_natively_and_plays_the_new_hit_on_another(self):
        for kind in (0x12, 0x4E):
            with self.subTest(kind=hex(kind)):
                n = nr.Native(KICK0, mode=1); p = n.p; k = 20
                for b in range(k + 6):
                    if b == 0:
                        n.post(kind)
                    if b == k:
                        n.post(kind)
                    n.block()
                    ramp = bytes(p.u.mem_read(p.voice + 0x58, 0x20))
                    if b == k:
                        self.assertEqual(n.active()[:2], [1, 1])       # new hit: another voice
                        self.assertEqual((ramp[4], ramp[0x18]), (4, 1))  # old: native release
                    if b == k + 4:
                        self.assertEqual(n.active()[:2], [0, 1])       # old switched off after 256

    def test_old_voice_reaches_zero_before_the_native_switch_off(self):
        # Fails on R6.14 (max step 0.009..0.018, HF 1.6e-5..6.5e-5).
        for kind in (0x12, 0x4E):
            for values in (KICK0, KICK100):
                for k in (15, 75):
                    with self.subTest(kind=hex(kind), sweep=values[4], ms=k * 64 // 48):
                        act, ideal, old, res, _ = nr.click(values, k, mode=1, kind=kind)
                        t0 = k * 64
                        step = max(abs(res[i] - res[i - 1]) for i in range(t0 + 200, t0 + 300))
                        self.assertLess(step, .002)
                        self.assertLess(act, 5e-6)

    def test_free_voices_overlap_without_any_cut(self):
        act, _, _, res, old = nr.click(KICK0, 38, mode=4)
        t0 = 38 * 64
        self.assertLess(max(abs(r - o) for r, o in zip(res[t0:t0 + 64], old[t0:t0 + 64])), .005)
        self.assertLess(act, 5e-6)

    def test_the_releasing_voice_is_made_by_native_code_of_this_firmware(self):
        # Port run 6 (owner, 1.6.8 hardware: the click is back). Everything kick_render reads on a
        # releasing voice must come from native code of this firmware version, not from numbers the
        # fixture shares with kick.cpp: the native constructor points voice+12 at the voice's own
        # descriptor object voice+0x10; the native note-on at a full pad writes the ramp voice+0x58
        # (state +4 = 4, flag +0x18 = 1, remaining +0x10 = total +0x14 = 256) from the native release.
        from unicorn import UC_HOOK_MEM_WRITE
        from unicorn.arm_const import UC_ARM_REG_PC
        n = nr.Native(KICK0, mode=1); p = n.p; v = 0x2001f000
        p.u.mem_write(v, bytes(0x800)); p.call(nr.VOICE_CTOR, v); p.call(nr.VOICE_ATTACH, p.root, v)
        self.assertEqual(p.r(v + 12), v + 0x10)
        ramp = p.voice + 0x58; writes = {}
        p.u.hook_add(UC_HOOK_MEM_WRITE, lambda u, acc, a, sz, val, d: writes.setdefault(
            a - ramp, (val, u.reg_read(UC_ARM_REG_PC))) if n.releasing else None, begin=ramp, end=ramp + 0x1b)
        n.releasing = False; n.post(0x4E); n.block()
        for _ in range(9):
            n.block()
        n.releasing = True; n.post(0x4E); n.block()
        native = range(nr.RAMP_RELEASE, nr.RAMP_RELEASE + 0x26)
        for offset, value in ((4, 4), (0x18, 1), (0x10, 256), (0x14, 256)):
            self.assertIn(offset, writes)
            self.assertEqual(writes[offset][0], value, hex(offset))
            self.assertIn(writes[offset][1], native, hex(offset))
        rendered = [e for e in n.log if e[0] == 'render' and p.voice in e[1:]]
        self.assertEqual(len(rendered), 1)   # the native loop still renders the releasing voice through our entry

    def test_isolated_hits_are_bit_identical(self):
        for kind in (0x12, 0x4E):
            self.assertEqual(digest(nr.run(KICK0, None, 60, mode=1, kind=kind)), ISOLATED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
