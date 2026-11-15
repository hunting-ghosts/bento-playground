"""Installed ARM regressions for drum transitions and bright snare stability."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import math
import struct
import unittest

from engine_test_support import engine, SYMS
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5,
                               UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_S11, UC_ARM_REG_S16, UC_ARM_REG_S17,
                               UC_ARM_REG_SP, UC_ARM_REG_PC)

ENGINES = (
    (1, (55, 65, 45, 65, 55, 25, 25)),
    (3, (10, 45, 50, 65, 70, 0, 0)),
    (5, (10, 70, 65, 65, 30, 0, 0)),
    (7, (40, 40, 50, 65, 40, 0, 0)),
    (9, (86, 50, 40, 65, 40, 30, 10)),
)


RANDOM, SEED = 0x24042004, 0x2545f491  # kick.cpp State.random; reseeded so new hits match


class Tests(unittest.TestCase):
    def continues(self, prev, last, first, fresh, tol=.002):
        """R6.11: the old voice's part of the first new sample (first minus the
        same retrigger with a silent old voice) continues the old waveform: it
        differs from the last old sample by at most the old waveform's own last
        step (slope continuation, bounded) plus tolerance. Replaces the R6.3
        "first sample equals last sample" check, which is the zero-slope kink."""
        old = first - fresh
        self.assertLess(abs(old - last), abs(last - prev) + abs(last) / 8 + tol,
                        (prev, last, first, fresh))

    def native_key(self, p, note, velocity=127):
        sp = 0x2003e000
        p.w(p.root + 0x18, 0x20030000)
        p.w(sp + 8, note)
        p.w(sp + 0x60, velocity)
        p.u.mem_write(sp + 0xc, struct.pack("<f", 1))
        p.u.reg_write(UC_ARM_REG_R4, p.voice)
        p.u.reg_write(UC_ARM_REG_R5, p.root)
        p.u.reg_write(UC_ARM_REG_R7, p.voice + 0x58)
        p.u.reg_write(UC_ARM_REG_S11, 0x3f800000)  # Native 48 kHz / 48 kHz carrier.
        p.u.reg_write(UC_ARM_REG_SP, sp)
        p.u.emu_start(0x08094b8d, 0x08094bf8, count=30000)
        self.assertEqual(p.u.reg_read(UC_ARM_REG_PC), 0x08094bf8)
        root_note = p.r(p.root + 0x604) or 60
        self.assertAlmostEqual(p.f(p.voice + 0x48), 2 ** ((note-root_note)/12), places=4)
        p.call(0x080639a0, p.voice + 0x58)

    def test_melodic_syncussion_project_plays_metal_at_the_native_key_pitch_and_ignores_tune_offsets(self):
        def capture(note, tune=25, lock=None, route=False, root_note=60):
            p = engine(15, (tune, 100, 100, 65, 0, 30, 0), lock)
            p.u.mem_write(0x24043d80, b"\0")
            p.w(p.desc + 0x24, 144035)
            p.native_postprocess()
            p.w(p.root + 0x604, root_note)
            if route:
                p.route(N.NKEY(0x1a0), 13, 1000)
            p.start()
            self.native_key(p, note)
            samples = []
            for _ in range(96):
                samples.extend(p.render()[1])
            return samples
        plain = capture(60)
        self.assertEqual(capture(60, 180, (12, 155), True), plain)
        self.assertEqual(capture(60, root_note=72), plain)
        # Run 14 (owner, 13 Nov): a melodic Syncussion track left in a project plays the Metal engine (inharmonic
        # FM, so no zero-crossing pitch): the played note still sets the pitch, an octave per 12 notes, and it is
        # audible. Measured as the power-weighted spectral centroid (Hz) of the steady part.
        import numpy as np
        def centroid(note):
            a = np.array(capture(note)[512:4608])
            self.assertGreater(float(np.sum(a*a)), 1e-3, note)
            power = abs(np.fft.rfft(a*np.hanning(len(a))))**2
            return float((power*np.arange(len(power))).sum()/power.sum())*48000/len(a)
        heights = [centroid(note) for note in (36, 48, 60, 72, 84)]
        for low, high in zip(heights, heights[1:]):
            self.assertAlmostEqual(high/low, 2, delta=.1)

    def test_melodic_retrigger_and_native_release_do_not_release_the_wrong_key(self):
        p = engine(15, (78, 100, 100, 65, 0, 30, 0))
        p.u.mem_write(0x24043d80, b"\0")
        p.w(p.desc + 0x24, 144035)
        p.native_postprocess()
        p.start()
        self.native_key(p, 60)
        for _ in range(32):
            p.render()
        old = p.voice
        self.replace_voice(p)
        self.native_key(p, 64)
        p.render()
        envelope = bytes(p.u.mem_read(p.voice + 0x58, 0x3c))
        p.call(0x08094640, p.root, 60, 0)
        self.assertEqual(bytes(p.u.mem_read(p.voice + 0x58, 0x3c)), envelope)
        self.assertEqual(p.u.mem_read(old, 1), b"\0")
        p.call(0x08094640, p.root, 64, 0)
        self.assertNotEqual(bytes(p.u.mem_read(p.voice + 0x58, 0x3c)), envelope)

    def native_finalize(self, p, path, pan):
        # Both native note paths initialize Level/Pan AFTER kick_voice.
        start, stop = ((0x08094400, 0x08093e22) if path == 0
                       else (0x08095040, 0x08094cb6))
        p.u.reg_write(UC_ARM_REG_R0, p.voice + 0x180)
        p.u.reg_write(UC_ARM_REG_R4, p.voice)
        p.u.reg_write(UC_ARM_REG_R5, p.root)
        p.u.reg_write(UC_ARM_REG_R6, 2)
        bits = struct.unpack("<I", struct.pack("<f", pan))[0]
        p.u.reg_write(UC_ARM_REG_S16, bits)
        p.u.reg_write(UC_ARM_REG_S17, bits)
        p.u.reg_write(UC_ARM_REG_SP, 0x2003e000)
        p.u.emu_start(start | 1, stop, count=30000)
        self.assertEqual(p.u.reg_read(UC_ARM_REG_PC), stop)

    def test_native_finalization_cannot_overwrite_handover_gain_and_pan(self):
        def scenario(model, defaults, path, frames, old_velocity):
            p = engine(model, defaults)
            p.native_postprocess()
            p.f(p.root + 0x134, .8)
            p.f(p.root + 0x174, -.5)
            self.native_finalize(p, path, -.5)
            p.start()
            p.f(p.voice + 0xb8, old_velocity)
            for _ in range(32):
                block = self.native_block(p, frames)
            p.u.mem_write(p.voice, b"\0\0")
            p.call(0x08063a00, p.voice + 0x58)
            p.call(SYMS["kick_voice"], p.voice, p.root)
            p.u.mem_write(p.voice, b"\1")
            p.f(p.voice + 0xb8, 1)
            p.w(RANDOM, SEED)
            p.call(0x080639a0, p.voice + 0x58)
            p.f(p.root + 0x134, .3)
            p.f(p.root + 0x174, .5)
            self.native_finalize(p, path, .5)
            return block[-2], block[-1], self.native_block(p, frames)
        for model, defaults in ENGINES + ((15, (78, 100, 50, 65, 35, 30, 0)),):
            for path in (0, 1):
                for frames in (64, 128):
                    with self.subTest(model=model, path=path, frames=frames):
                        prev, last, audio = scenario(model, defaults, path, frames, 1)
                        fresh = scenario(model, defaults, path, frames, 0)[2]
                        self.continues(prev, last, audio[0], fresh[0])
                        self.assertTrue(all(math.isfinite(x) for x in audio))

    def native_block(self, p, frames):
        p.w(p.output, frames)
        p.w(p.output + 4, frames)
        for address in (0x20028000, 0x20029000):
            p.u.mem_write(address, bytes(frames * 4))
        self.assertEqual(p.render()[0], 1)
        return struct.unpack("<%df" % frames,
                             p.u.mem_read(0x20028000, frames * 4))

    def test_native_reused_voice_reset_does_not_break_retrigger_bridge(self):
        def scenario(model, values, frames, old_velocity):
            p = engine(model, values)
            p.native_postprocess()
            p.start()
            p.f(p.voice + 0xb8, old_velocity)
            for _ in range(32):
                block = self.native_block(p, frames)
            # Native setup resets the recycled voice before our hook;
            # its active flag is set later, after the hook returns.
            p.u.mem_write(p.voice, b"\0\0")
            p.call(0x08063a00, p.voice + 0x58)
            p.f(p.voice + 0xcc, 0)
            p.f(p.voice + 0x94, 0)
            p.f(p.voice + 0xa4, 0)
            p.call(SYMS["kick_voice"], p.voice, p.root)
            p.u.mem_write(p.voice, b"\1")
            p.f(p.voice + 0xb8, 1)
            p.w(RANDOM, SEED)
            return block[-2], block[-1], self.native_block(p, frames)
        for model, values in ENGINES + ((15, (78, 55, 50, 65, 35, 30, 0)),):
            for frames in (64, 128):
                with self.subTest(model=model, frames=frames):
                    prev, last, audio = scenario(model, values, frames, 1)
                    fresh = scenario(model, values, frames, 0)[2]
                    self.continues(prev, last, audio[0], fresh[0])
                    self.assertTrue(all(math.isfinite(x) for x in audio))

    def test_recording_settings_survive_recycled_voice_with_changing_velocity(self):
        # Initial visible values in the owner's 3 November recording.
        for frames in (64, 128):
            with self.subTest(frames=frames):
                p = engine(15, (34, 44, 73, 43, 58, 30, 0))
                p.u.mem_map(0xc6000000, 0x1000)
                p.w(0x24043508, 0xc6000000)
                p.w(0xc6000000, 0x41594e53)
                p.u.mem_write(0xc6000020, bytes([6]))
                p.u.mem_write(0x24043d80, bytes([12]))  # Single, down sweep, LFO off.
                p.native_postprocess()
                p.start()
                for velocity in (1, .25, .75, .1):
                    for _ in range(32):
                        last = self.native_block(p, frames)[-1]
                    p.u.mem_write(p.voice, b"\0\0")
                    p.f(p.voice + 0xcc, 0)
                    p.f(p.voice + 0x94, 0)
                    p.f(p.voice + 0xa4, 0)
                    p.call(SYMS["kick_voice"], p.voice, p.root)
                    p.f(p.voice + 0xb8, velocity)
                    p.u.mem_write(p.voice, b"\1")
                    audio = self.native_block(p, frames)
                    self.assertLess(abs(audio[0] - last), .002)
                    self.assertTrue(all(math.isfinite(x) for x in audio))

    def replace_voice(self, p, velocity=.25):
        old = p.voice
        new = 0x20018800 if old == 0x20018000 else 0x20018000
        p.call(0x08072a00, new)
        p.call(0x08092f20, p.root, new)
        p.w(new + 12, p.desc)
        p.f(new + 0x48, 1)
        p.f(new + 0xb8, velocity)
        p.u.mem_write(new, b"\1")
        p.call(0x080639a0, new + 0x58)
        p.w(p.root + 0x60, 2)
        p.w(p.root + 0x20, old)
        p.w(p.root + 0x24, new)
        p.call(SYMS["kick_voice"], new, p.root)
        p.voice = new
        self.assertEqual(p.u.mem_read(old, 1), b"\0")

    def test_native_retrigger_remains_continuous_across_voices_and_velocity(self):
        def scenario(model, values, old_velocity):
            p = engine(model, values)
            p.native_postprocess()
            p.start()
            p.f(p.voice + 0xb8, old_velocity)
            for _ in range(32):
                p.render()
            prev, last = p.outputs()[0][-2:]
            self.replace_voice(p)
            p.w(RANDOM, SEED)
            ok, _ = p.render()
            self.assertEqual(ok, 1)
            return prev, last, p.outputs()[0]
        for model, values in ENGINES + ((15, (78, 55, 50, 65, 35, 30, 0)),):
            with self.subTest(model=model):
                prev, last, audio = scenario(model, values, 1)
                fresh = scenario(model, values, 0)[2]
                self.continues(prev, last, audio[0], fresh[0], tol=1e-5)
                self.assertTrue(all(math.isfinite(x) for x in audio))

    def test_short_and_long_decay_with_repeated_fast_and_spaced_hits(self):
        for model, defaults in (ENGINES[0], (15, (78, 55, 50, 65, 35, 30, 0))):
            for decay in (0, 100):
                for blocks in (1, 4, 16, 96):
                    with self.subTest(model=model, decay=decay, blocks=blocks):
                        values = list(defaults)
                        values[1] = decay
                        p = engine(model, values)
                        p.native_postprocess()
                        p.start()
                        for velocity in (1, .25, .75, .1):
                            for _ in range(blocks):
                                p.render()
                            prev, last = p.outputs()[0][-2:]
                            self.replace_voice(p, velocity)
                            p.render()
                            audio = p.outputs()[0]
                            # Kick and Metal start from zero output, so the first
                            # sample continues the old waveform (value and step);
                            # an in-progress native level ramp advances one sample.
                            self.continues(prev, last, audio[0], 0.)
                            self.assertTrue(all(math.isfinite(x) and abs(x) <= 1
                                                for x in audio))

    # R6.11 click regression (owner 8 Nov: retriggering before the decay ends
    # clicks, most on the Kick). Energy above 2 kHz (4-pole high-pass) of what
    # is left of the old voice after a retrigger, -0.3..+8 ms, must not exceed
    # twice that of a 5 ms cosine fade-out of the real old voice. R6.10 (hold
    # last sample + 1 ms linear ramp) leaves 100..10000x that on Kick and Tom.
    # The old voice's part is act minus the same retrigger with a silent old
    # voice; the random state is reseeded at the retrigger so both new hits are
    # identical. Metal keeps its state on a retrigger (new attack from the
    # current envelope), so there the retriggered onset is compared with a
    # fresh hit's onset instead.
    CLICK_ENGINES = ENGINES + ((1, (55, 100, 45, 65, 55, 25, 0)), (15, (78, 55, 50, 65, 35, 30, 0)))
    CLICK_TIMES = (15, 38, 75, 150, 225)  # blocks of 64: 20, 51, 100, 200, 300 ms

    @staticmethod
    def above_2khz(x, w0, w1, pre=256):
        a = math.exp(-2 * math.pi * 2000 / 48000)
        y = x[w0 - pre:w1]
        for _ in range(4):
            out, px, py = [], 0., 0.
            for v in y:
                py = a * (py + v - px)
                px = v
                out.append(py)
            y = out
        return sum(v * v for v in y[pre:])

    def retrigger_audio(self, model, values, blocks, at=None, old_velocity=1.):
        p = engine(model, values)
        p.native_postprocess()
        p.start()
        p.f(p.voice + 0xb8, old_velocity)
        out = []
        for b in range(blocks):
            if b == at:
                self.replace_voice(p, 1)
                p.w(RANDOM, SEED)
            ok, _ = p.render()
            self.assertEqual(ok, 1)
            out.extend(p.outputs()[0])
        return out

    def test_retrigger_adds_no_click_energy_above_2khz(self):
        for model, values in self.CLICK_ENGINES:
            old = self.retrigger_audio(model, values, max(self.CLICK_TIMES) + 8)
            for k in self.CLICK_TIMES:
                t0 = k * 64
                with self.subTest(model=model, values=values, ms=round(t0 / 48)):
                    act = self.retrigger_audio(model, values, k + 8, k)
                    fresh = self.retrigger_audio(model, values, k + 8, k, 0.)
                    if model == 15:
                        w0, w1 = t0 - 16, t0 + 48
                        e = self.above_2khz(act, w0, w1)
                        limit = 2 * self.above_2khz(fresh, w0, w1) + self.above_2khz(old, w0, w1) + 1e-10
                    else:
                        w0, w1 = t0 - 16, t0 + 384
                        left = [x - y for x, y in zip(act, fresh)]
                        fade = [old[i] if i < t0 else old[i] * .5 * (1 + math.cos(math.pi * (i - t0) / 240))
                                if i < t0 + 240 else 0. for i in range(len(act))]
                        e = self.above_2khz(left, w0, w1)
                        limit = 2 * self.above_2khz(fade, w0, w1) + 1e-10
                    self.assertLess(e, limit)

    def test_bright_snare_keeps_rendering_without_clipping_or_nan_silencing(self):
        for tone in (85, 90, 100):
            with self.subTest(tone=tone):
                p = engine(3, (10, 45, tone, 65, 100, 0, 0))
                p.start()
                samples = []
                for _ in range(48):
                    ok, block = p.render()
                    self.assertEqual(ok, 1)
                    samples.extend(block)
                self.assertTrue(all(math.isfinite(x) for x in samples))
                # R6.3: level matched to samples (default hit about -1 dBFS); still below clip.
                self.assertLess(max(abs(x) for x in samples), .99)
                self.assertGreater(sum(x*x for x in samples[-640:]), .001)

    def test_hat_is_audible_through_real_native_postprocessing(self):
        p = engine(5, ENGINES[2][1])
        p.native_postprocess()
        p.start()
        audio = []
        for _ in range(32):
            self.assertEqual(p.render()[0], 1)
            audio.extend(p.outputs()[0])
        self.assertGreater(sum(x*x for x in audio), .01)


if __name__ == "__main__":
    unittest.main(verbosity=2)
