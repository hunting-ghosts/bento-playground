"""Regression checks that the retired Subtractive engine is not claimed."""
import unittest

from engine_test_support import engine, SYMS
from unicorn.arm_const import UC_ARM_REG_R0


class Tests(unittest.TestCase):
    def test_legacy_subtractive_marker_is_not_a_supported_drum_engine(self):
        p = engine(11, (20, 50, 35, 60, 25, 35, 45))
        p.call(SYMS["kick_marker"], p.desc)
        self.assertEqual(p.u.reg_read(UC_ARM_REG_R0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
