"""Added drum DSP stability; these checks do not establish device sound quality."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parent


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "drum_audio.so"
        source = r'''
#include "snare909.h"
#include "drum_transition.h"
extern "C" void bridge_render(float last, float value, unsigned retrigger,
                              float *out, unsigned count) {
    bento::DrumTransition bridge = {};
    bridge.last = last;
    bridge.Start(retrigger != 0);
    for (unsigned i = 0; i < count; ++i)
        out[i] = bridge.Process(value);
}
extern "C" void bridge_after(const float *old, unsigned n, float value,
                             float *out, unsigned count) {
    bento::DrumTransition bridge = {};
    bridge.End(old, n);
    bridge.Start(true);
    for (unsigned i = 0; i < count; ++i)
        out[i] = bridge.Process(value);
}
extern "C" void snare_render(float tone, float decay, float snappy,
                             float *out, unsigned count) {
    bento::Snare909 drum;
    drum.Init(48000);
    drum.SetTone(tone);
    drum.SetDecay(decay);
    drum.SetSnappy(snappy);
    drum.Trig();
    auto coefficients = drum.PrepareBlock();
    for (unsigned i = 0; i < count; ++i)
        out[i] = drum.ProcessPrepared(coefficients);
}
'''
        subprocess.run(["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", "-I" + str(ROOT / "drums"),
                        "-x", "c++", "-", "-o", str(lib)],
                       input=source, text=True, check=True)
        cls.lib = ctypes.CDLL(str(lib))
        cls.lib.bridge_after.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_uint, ctypes.c_float,
                                         ctypes.POINTER(ctypes.c_float), ctypes.c_uint]
        cls.lib.bridge_after.restype = None
        cls.lib.snare_render.argtypes = [ctypes.c_float] * 3 + [
            ctypes.POINTER(ctypes.c_float), ctypes.c_uint]
        cls.lib.snare_render.restype = None
        cls.lib.bridge_render.argtypes = [ctypes.c_float, ctypes.c_float,
            ctypes.c_uint, ctypes.POINTER(ctypes.c_float), ctypes.c_uint]
        cls.lib.bridge_render.restype = None

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def render(self, tone, decay=.45, snappy=.7, frames=48000):
        out = (ctypes.c_float * frames)()
        self.lib.snare_render(tone, decay, snappy, out, frames)
        return np.array(out)

    def test_complete_tone_range_stays_finite_and_audible(self):
        for tone in range(101):
            with self.subTest(tone=tone):
                audio = self.render(tone / 100)
                self.assertTrue(np.all(np.isfinite(audio)))
                self.assertLess(np.max(np.abs(audio)), 1)
                self.assertGreater(np.sum(audio[:4800] ** 2), 1)
                self.assertLess(np.sum(audio[-4800:] ** 2),
                                np.sum(audio[:4800] ** 2) * .001)

    def test_bright_noise_extremes_decay_without_a_saturated_burst(self):
        for tone in (.85, .9, 1):
            for decay in (0, .45, 1):
                with self.subTest(tone=tone, decay=decay):
                    audio = self.render(tone, decay, 1, frames=48000 * 4)
                    self.assertTrue(np.all(np.isfinite(audio)))
                    self.assertLess(np.max(np.abs(audio)), 1)
                    self.assertLess(np.mean(audio[-4800:] ** 2), 1e-8)

    def test_retrigger_bridge_adds_the_old_level_smoothly_for_2_5_ms(self):
        # R6.11: additive (the new hit is never ducked), smoothstep over 120
        # samples (zero slope at both ends); R6.10 crossfaded over 48 samples.
        for last in (-.6, 0, .6):
            for value in (-.6, 0, .6):
                out = (ctypes.c_float * 240)()
                self.lib.bridge_render(last, value, 1, out, len(out))
                old = np.array(out) - np.float32(value)
                self.assertAlmostEqual(old[0], last, places=6)
                np.testing.assert_array_equal(np.array(out)[120:], np.float32(value))
                self.assertLessEqual(np.max(np.abs(old)), abs(last) + 1e-6)
                self.assertLessEqual(np.max(np.abs(np.diff(old))), abs(last) * 1.5 / 120 + 1e-6)
                self.assertLess(abs(old[1] - old[0]), abs(last) * 1e-3 + 1e-7)  # no kink at the start

    def test_retrigger_bridge_continues_the_old_slope_bounded(self):
        for step in (-.004, .004, .3):
            old = np.float32(.5) + np.float32(step) * np.arange(-32, 0, dtype=np.float32)
            src = (ctypes.c_float * 32)(*old)
            out = (ctypes.c_float * 240)()
            self.lib.bridge_after(src, 32, 0, out, len(out))
            audio = np.array(out)
            expected = min(abs(step), abs(old[-1]) / 8) * np.sign(step)
            self.assertAlmostEqual(audio[0] - old[-1], expected, places=5)
            self.assertLessEqual(np.max(np.abs(audio)), abs(old[-1]) * 2 + 1e-6)
            np.testing.assert_array_equal(audio[120:], np.float32(0))

    def test_bridge_does_not_change_isolated_hits_or_inherit_another_sound(self):
        out = (ctypes.c_float * 96)()
        self.lib.bridge_render(.6, -.2, 0, out, len(out))
        np.testing.assert_array_equal(np.array(out), np.float32(-.2))

    def test_tone_still_changes_noise_and_not_shells(self):
        dark, bright = self.render(0), self.render(1)
        self.assertGreater(np.sum(np.diff(bright[:4800]) ** 2),
                           np.sum(np.diff(dark[:4800]) ** 2) * 2)
        np.testing.assert_array_equal(self.render(0, snappy=0),
                                      self.render(1, snappy=0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
