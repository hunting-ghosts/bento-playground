"""R6.16b/c: without an armed ratchet the ratchet code is inert, on the real path.

Owner (hardware, b7d1b93 = R6.16 mono roll): Perform-page chords on a
multisample track gave short notes instead of the patch's sustain and the
Bento crashed several times; no ratchet was set anywhere. b0ec1a9 was fine.
In b7d1b93 the sampler voice start (every chord voice) ran rt_voice, which
acts on RtBlock contents (requests, recorded voices) without any armed
ratchet, and rt_block wrote the block on every call. Stale or reused RtBlock
contents then release chord voices or dereference garbage. R6.16b reverts the
voice hook; R6.16c brings it back safe: requests carry a check word over a
per-init epoch, handle, entry, generation, tick and order; the hook is
read-only unless a valid recent request is pending; every voice pointer is
checked against the root's live voice list before any read; rt_block is inert
unless a ratchet is armed or a valid request of one is outstanding.

Real path: router queue -> sampler block process 0808E9A0 -> key note-on
(chord notes are type 2 records, several per block) -> native voice
allocation/stealing -> voice-start endpoint -> render. Fails on b7d1b93
(rt_m3). Software evidence only."""
import hashlib
import struct
import sys
import unittest

sys.argv = sys.argv[:1]
import kick_native_path as nr

KICK = (55, 65, 45, 65, 0, 25, 0)
RTB = nr.RTB
# R6.16 stress output on b0ec1a9 (no mono roll, no live arming): must not change.
STRESS = "c82173a79bcc409ef1a2599cb8dc8d9e6a6940fd5e14ba179f3bb1c55168e53e"


def post(c, kind, pitch, vel=100):
    c.p.u.mem_write(nr.EVT, struct.pack("<B3xIIIi4x", kind, 0, 101, pitch, vel)); c.p.call(0x08065600, nr.Q, nr.EVT)


def stress(c):
    out = []
    for rep in range(10):
        chord = [48 + rep, 52 + rep, 55 + rep, 59 + rep, 62 + rep, 65 + rep][:4 + rep % 3]
        for pitch in chord:  # every chord tone in the same block (chord_start)
            post(c, 2, pitch)
        for _ in range(2 + rep % 3):
            out.extend(c.run_block())
        for pitch in chord:
            post(c, 3, pitch)
        out.extend(c.run_block())
    return hashlib.sha256(struct.pack("<%df" % len(out), *out)).hexdigest()


class Inert(unittest.TestCase):
    def test_chord_voices_ignore_stale_ratchet_data(self):
        c = nr.Chain(KICK, mode=4); p = c.p
        post(c, 2, 60); c.run_block()          # a held note on voice 0
        voice0 = c.voices[0]
        self.assertEqual(c.active()[0], 1)
        # Leftover data in the block, nothing armed: a request for this track
        # naming voice 0 (as a reused or stale block could hold).
        cuts, voices = RTB + 2656, RTB + 2656 + 32
        p.w(cuts + 8, 1)                        # pending
        p.w(cuts + 16, 1)                       # cut count
        p.u.mem_write(voices, struct.pack("<4I", voice0, p.root, p.r(voice0 + 8), 0))
        p.u.mem_write(voices + 16 * 32, struct.pack("<8I", 101, 0, 0, 0, 1, 1, 0x12345678, 0))
        before = bytes(p.u.mem_read(RTB, 0x1000))
        for pitch in (64, 67, 71):               # chord tones, same block
            post(c, 2, pitch)
        for _ in range(4):
            c.run_block()
        self.assertEqual(c.active(), [1, 1, 1, 1])
        self.assertEqual([p.u.mem_read(v + 0x70, 1)[0] for v in c.voices], [0, 0, 0, 0])  # nothing released
        self.assertEqual(bytes(p.u.mem_read(RTB, 0x1000)), before)                     # nothing written

    def test_project_reload_mid_roll_is_safe(self):
        # A roll is running when the block is re-initialised (project reload:
        # the M7 area starts over) and the root's voices are replaced. Nothing
        # crashes, no request of the old roll can cut anything, and a chord
        # afterwards is untouched.
        c = nr.Chain(KICK, mode=4); p = c.p
        c.note(c.token(8, 1, 100), 100)
        for _ in range(30):
            c.run_block()
        p.w(RTB + 64, 0)                      # M7 area re-initialised (m7_magic gone)
        n = p.r(p.root + 0x60)
        for i in range(n):                    # the root's voices replaced
            p.u.mem_write(c.voices[i], b"\0")
        for _ in range(60):
            c.run_block()
        for pitch in (60, 64, 67):
            post(c, 2, pitch)
        for _ in range(4):
            c.run_block()
        self.assertGreaterEqual(sum(c.active()), 1)
        # (the fixture's global voice pool is not modelled: finished voices leave
        #  the root's list natively, so not every chord tone gets a voice here)
        self.assertEqual([p.u.mem_read(v + 0x70, 1)[0] for v in c.voices if p.u.mem_read(v, 1)[0]],
                         [0] * sum(c.active()))           # no voice released by the old roll
        self.assertEqual([p.r(RTB + 2656 + 4 * i) for i in (2, 4)], [0, 0])  # nothing pending, no cut

    def test_chord_stress_with_stealing_is_unchanged(self):
        c = nr.Chain(KICK, mode=4)
        digest = stress(c)
        if STRESS:
            self.assertEqual(digest, STRESS)
        else:
            print("STRESS", digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
