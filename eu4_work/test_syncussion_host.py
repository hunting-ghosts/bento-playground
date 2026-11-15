"""Host DSP checks. Neither elapsed host time nor instructions imply device CPU."""
import ctypes
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parent
DEFAULT = (78, 55, 50, 65, 35, 30, 0)
METAL = 1 + 6*2 + 18*0 + 54*1  # the fixed Metal switch word of kick.cpp (R6.4): B Metallic, sweep down, LFO off, S&H on


class Tests(unittest.TestCase):
    """Run 14 (item 5b, owner 13 Nov): the engine is specialised to Metal. The tests of the other five modes and of
    the switch word (test_switch_encoding_is_lossless_and_independent, test_all_modes_are_distinct_finite_and_audible,
    mode loops) went with that code (owner-approved removal of Syncussion leftovers); the bit-identity tests below
    compare the Metal engine with the six-mode reference at the Metal switch word."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / "syncussion.so"
        subprocess.run(["c++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", "-I", str(ROOT), str(ROOT / "test_syncussion_host.cpp"),
                        "-o", str(lib)], check=True)
        cls.lib = ctypes.CDLL(str(lib))
        p, f, u = ctypes.c_void_p, ctypes.c_float, ctypes.c_uint
        for prefix in ("sync", "ref"):
            getattr(cls.lib, prefix+"_size").restype = u
            getattr(cls.lib, prefix+"_init").argtypes = [p, u]
            getattr(cls.lib, prefix+"_trigger").argtypes = [p]
            getattr(cls.lib, prefix+"_active").argtypes = [p]
            getattr(cls.lib, prefix+"_dormant").argtypes = [p, u]
        cls.lib.sync_render.argtypes = [p, ctypes.POINTER(f), f, f, f, ctypes.POINTER(f), u]
        cls.lib.ref_render.argtypes = [p, ctypes.POINTER(f), u, f, f, f, ctypes.POINTER(f), u]
        cls.lib.sync_exp2.argtypes = [f]
        cls.lib.sync_exp2.restype = f
        cls.lib.sync_attack_coefficient.argtypes = [f]
        cls.lib.sync_attack_coefficient.restype = f

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def voice(self, seed=123, ref=False):
        prefix = "ref" if ref else "sync"
        state = ctypes.create_string_buffer(getattr(self.lib, prefix+"_size")())
        getattr(self.lib, prefix+"_init")(state, seed)
        getattr(self.lib, prefix+"_trigger")(state)
        return state

    def render(self, state=None, values=DEFAULT, ratio=1, velocity=1, frames=4800, attack=0):
        if state is None:
            state = self.voice()
        out = (ctypes.c_float * frames)()
        self.lib.sync_render(state, (ctypes.c_float * 7)(*values), ratio, velocity, attack, out, frames)
        return np.array(out)

    def reference(self, state=None, values=DEFAULT, ratio=1, velocity=1, frames=4800, attack=0, flags=METAL):
        if state is None:
            state = self.voice(ref=True)
        out = (ctypes.c_float * frames)()
        self.lib.ref_render(state, (ctypes.c_float * 7)(*values), flags, ratio, velocity, attack, out, frames)
        return np.array(out)

    def same_bits(self, a, b, what):
        self.assertEqual(a.astype(np.float32).tobytes(), b.astype(np.float32).tobytes(), what)

    def test_state_fits_existing_pool(self):
        self.assertLessEqual(self.lib.sync_size(), 288)
        self.assertLessEqual(self.lib.sync_size(), self.lib.ref_size())

    def test_metal_is_bit_identical_to_the_six_mode_engine_at_the_metal_switches(self):
        rng = np.random.default_rng(14)
        cases = [(DEFAULT, 1, 1, 0), ((78, 55, 50, 65, 0, 30, 0), 1, 1, 0), ((25, 0, 0, 0, 0, 0, 0), 1/64, .2, 0),
                 ((180, 100, 100, 100, 100, 100, 100), 64, 1, 100), ((104, 70, 30, 40, 80, 60, 90), 1.5, .7, 35)]
        for _ in range(40):
            cases.append((tuple(int(x) for x in rng.integers(0, 101, 7)), float(2**rng.uniform(-3, 3)),
                          float(rng.uniform(0, 1)), int(rng.integers(0, 101))))
        for values, ratio, velocity, attack in cases:
            seed = int(rng.integers(1, 1 << 31))
            a, b = self.voice(seed), self.voice(seed, ref=True)
            for block in range(6):
                self.same_bits(self.render(a, values, ratio, velocity, 512, attack),
                               self.reference(b, values, ratio, velocity, 512, attack), (values, ratio, block))
                if block == 2:
                    self.lib.sync_trigger(a)
                    self.lib.ref_trigger(b)
            self.assertEqual(self.lib.sync_active(a), self.lib.ref_active(b))

    def test_metal_dormant_clock_is_bit_identical_to_the_reference(self):
        values = (78, 0, 50, 65, 35, 30, 100)
        a, b = self.voice(7), self.voice(7, ref=True)
        self.render(a, values, frames=48000)
        self.reference(b, values, frames=48000)
        for frames in (64, 1, 960, 64, 48000):
            self.lib.sync_dormant(a, frames)
            self.lib.ref_dormant(b, frames)
        self.lib.sync_trigger(a)
        self.lib.ref_trigger(b)
        self.same_bits(self.render(a, values), self.reference(b, values), "dormant")

    def test_attack_rise_time_and_monotonic_range(self):
        previous = 1
        for attack in range(101):
            coefficient = self.lib.sync_attack_coefficient(attack)
            self.assertGreater(coefficient, 0)
            self.assertLess(coefficient, previous)
            previous = coefficient
            frames = math.ceil(math.log(.2)/math.log(1-coefficient))
            expected = 48*(2**(attack*.089657843))
            self.assertAlmostEqual(frames/expected, 1, delta=.04)

    def test_attack_zero_preserves_audio_and_slow_attack_reduces_onset_energy(self):
        np.testing.assert_array_equal(self.render(attack=0), self.render())
        fast, slow = self.render(attack=0), self.render(attack=70)
        self.assertLess(np.sum(slow[:480]**2), np.sum(fast[:480]**2)*.05)
        self.assertGreater(np.sum(slow**2), 1e-5)
        self.assertTrue(np.all(np.isfinite(slow)))

    def test_slow_attack_retrigger_preserves_bridge_and_remains_finite(self):
        s = self.voice()
        before = self.render(state=s)
        self.lib.sync_trigger(s)
        out = self.render(state=s, frames=128, attack=100)
        # R6.11: the bridge continues the last value and its last step.
        self.assertAlmostEqual(out[0], 2*before[-1]-before[-2], places=6)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_pitch_exponent_matches_math_over_full_operating_range(self):
        for x in np.linspace(-24, 24, 4097):
            self.assertLess(abs(self.lib.sync_exp2(float(x)) / 2**float(x) - 1), 8e-7)

    def test_filter_tangent_approximation_matches_reference(self):
        for fc in np.linspace(12, 20160, 1000):
            a = math.pi * fc / 96000
            q = a*a
            g = a*(105-10*q)/(105-45*q+q*q)
            self.assertLess(abs(g/math.tan(a)-1), 1e-6)

    def test_metal_is_finite_and_audible(self):
        a = self.render()
        self.assertTrue(np.all(np.isfinite(a)))
        self.assertLess(np.max(np.abs(a)), 1.5)
        self.assertGreater(np.mean(a*a), 1e-5)

    def test_parameter_extremes_and_transposition_are_stable(self):
        for values, ratio in [((25, 0, 0, 0, 0, 0, 0), 1/64),
                              ((180, 100, 100, 100, 100, 100, 100), 64)]:
            audio = self.render(values=values, ratio=ratio, frames=2048)
            self.assertTrue(np.all(np.isfinite(audio)), values)
            self.assertLess(np.max(np.abs(audio)), 1.5, values)

    def test_keyboard_pitch_and_tune_both_transpose(self):
        def pitch(values, ratio):
            a = self.render(values=values, ratio=ratio, frames=16384)[512:]
            # Metal is inharmonic FM (450/440): the strongest bin of a 3 Hz grid does not double exactly
            # (22 -> 43), so compare power-weighted spectral centroids (46.45 -> 92.89 bins).
            power = abs(np.fft.rfft(a*np.hanning(len(a))))**2
            return float((power*np.arange(len(power))).sum()/power.sum())
        values = (78, 100, 0, 0, 0, 0, 0)
        base = pitch(values, 1)
        self.assertAlmostEqual(pitch(values, 2)/base, 2, delta=.02)
        self.assertGreater(pitch((104,)+values[1:], 1)/base, 1.9)
        self.assertNotEqual(pitch(values, 16), base)

    def test_every_continuous_control_changes_audio(self):
        values = (78, 55, 50, 65, 35, 80, 50)
        # Metal's pitch modulation is sample & hold: the held value changes once per LFO cycle (0.6 s at
        # LFO Speed 30), so run it fast (LFO Speed 80) and render one second.
        original = self.render(values=values, frames=48000)
        for index in range(7):
            changed = list(values)
            changed[index] = 170 if index == 0 else 95
            self.assertFalse(np.array_equal(self.render(values=changed, frames=48000), original), index)

    def test_zero_range_and_depth_really_remove_their_modulation(self):
        a = self.render(values=(78, 55, 50, 0, 0, 0, 0))
        b = self.render(values=(78, 55, 50, 100, 0, 100, 0))
        np.testing.assert_array_equal(a, b)

    def test_noise_is_repeatable_but_different_between_pads(self):
        values = (78, 55, 50, 65, 35, 60, 100)  # the S&H draw is the noise of the Metal engine (one per LFO cycle)
        a = self.render(state=self.voice(1), values=values, frames=48000)
        np.testing.assert_array_equal(a, self.render(state=self.voice(1), values=values, frames=48000))
        self.assertFalse(np.array_equal(a, self.render(state=self.voice(2), values=values, frames=48000)))

    def test_velocity_is_louder_and_brighter_without_double_scaling(self):
        a, b = self.render(velocity=.3), self.render(velocity=1)
        self.assertGreater(np.sum(b*b), np.sum(a*a)*4)
        np.testing.assert_array_equal(self.render(velocity=0), np.zeros(4800))

    def test_retrigger_bridges_velocity_changes(self):
        state = self.voice()
        before = self.render(state=state)
        self.lib.sync_trigger(state)
        after = self.render(state=state, velocity=.1, frames=128)
        self.assertAlmostEqual(after[0], 2*before[-1]-before[-2], places=6)  # R6.11: value and step continue
        self.assertGreater(np.sum(after*after), 0)

    def test_finished_voice_stops_and_idle_output_is_exact_zero(self):
        state = self.voice()
        self.render(state=state, values=(78, 0, 50, 65, 35, 30, 0), frames=48000)
        self.assertEqual(self.lib.sync_active(state), 0)
        np.testing.assert_array_equal(self.render(state=state), np.zeros(4800))

    def test_longest_decay_finishes_inside_guarded_ten_second_lifetime(self):
        state = self.voice()
        self.render(state=state, values=(78, 100, 100, 65, 35, 30, 0), frames=480000)
        self.assertEqual(self.lib.sync_active(state), 0)

    def test_processing_is_independent_of_host_block_partition(self):
        a = self.render(frames=4096)
        state = self.voice()
        b = np.concatenate([self.render(state=state, frames=64) for _ in range(64)])
        np.testing.assert_array_equal(a, b)

    def test_dormant_phase_advances_but_active_phase_is_not_double_advanced(self):
        values = (78, 0, 50, 65, 35, 90, 100)  # fast S&H: the dormant clock passes several LFO cycles
        a, b = self.voice(), self.voice()
        for state in (a, b):
            self.render(state=state, values=values, frames=48000)
            self.assertEqual(self.lib.sync_active(state), 0)
        for _ in range(75):
            self.lib.sync_dormant(b, 64)
        for state in (a, b):
            self.lib.sync_trigger(state)
        self.assertFalse(np.array_equal(self.render(state=a, values=values, frames=48000),
                                        self.render(state=b, values=values, frames=48000)))
        a, b = self.voice(), self.voice()
        for state in (a, b):
            self.render(state=state, frames=64)
        self.lib.sync_dormant(b, 64)
        np.testing.assert_array_equal(self.render(state=a), self.render(state=b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
