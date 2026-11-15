"""Minimalist tiles on the matched firmware, with real native bank children."""
import importlib.util
from pathlib import Path
import unittest

from test_tracks import emu
from test_integration import IMAGE, UU, CANDIDATE

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "native_bank_fixture", ROOT / "research/display_emulator/test_inst_bank.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Tests(fixture.BankPaint):
    image = IMAGE
    symbols = UU
    output = CANDIDATE / "screens"
    original = (CANDIDATE / "baseline/bento1.bin").read_bytes()

    def setUp(self):
        self.output.mkdir(exist_ok=True)
        super().setUp()
        self.slot = self.call("inst_bank_state_slot")
        self.assertNotEqual(self.slot, 0)

    def test_exact_native_scope_and_touch_encoder_ownership(self):
        # Audio has separate tests; this renderer replaces only tile paint/walk,
        # leaving the native bank's touch/encoder methods and geometry intact.
        original = self.original
        self.original = self.image
        try:
            super().test_exact_native_scope_and_touch_encoder_ownership()
        finally:
            self.original = original
        for vt in (0x081b2e88, 0x0819e5c4):
            for slot in range(14):
                if vt == 0x081b2e88 and slot in (1, 2):
                    self.assertEqual(
                        self.e.r(vt + slot*4) & ~1,
                        self.symbols["inst_bank_paint" if slot == 1 else "inst_bank_walk"])
                else:
                    import struct
                    self.assertEqual(self.e.r(vt + slot*4),
                                     struct.unpack_from("<I", original,
                                                        vt + slot*4 - emu.BASE)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
