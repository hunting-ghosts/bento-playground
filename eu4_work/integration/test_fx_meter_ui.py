import native_ids as N # run 17: version-dependent Track FX expectations
import struct
import unittest

import numpy as np

from test_integration import DEFAULT, Fixture
from test_perform_ui import Perform, render

MODEL = 0x30024B00
METER = 0x24041974
METER_TRACK_OFFSET = 0x240416A8


def compressor_measurement(signal):
    p = Fixture()
    p.direct_open()
    p.u.mem_write(MODEL + 0x12C, b"\x1a")
    settings = DEFAULT.copy()
    settings[8:14] = [1, -30, 10, 1, 120, 0]
    p.mailbox({0: settings})
    p.mixer()
    for _ in range(120):
        p.audio(0, signal, None)
    return bytes(p.u.mem_read(METER, 12))

def transfer_reading(p, reading, track=0):
    serial, _, reduction = struct.unpack("<IIf", reading)
    tag = ((p.e.r(0x24041444) & 0x0FFFFFFF) << 4) | track
    p.u.mem_write(METER, struct.pack("<IIf", serial, tag, reduction))


class FxMeterUiTests(unittest.TestCase):
    def test_real_reduction_draws_meter_and_closed_request_is_unavailable(self):
        loud = np.full(128, 0.8, dtype=np.float32)
        published = compressor_measurement(loud)
        serial, track, reduction = struct.unpack("<IIf", published)
        self.assertNotEqual(serial, 0)
        self.assertEqual(serial & 1, 0)
        self.assertEqual(track & 15, 0)
        self.assertNotEqual(track >> 4, 0)
        self.assertGreater(reduction, 15.0)

        p = Perform()
        p.open_track_fx()
        p.fx_values()
        transfer_reading(p, published)
        p.e.w(0x3001FE2C, 1000)
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.call("pg_perform_tick", p.bar(), render.CTX)
        self.assertEqual(p.u.mem_read(render.CTX + 1, 1), b"\1")

        p.labels.clear()
        p.fills.clear()
        p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        p.call("pg_bar_paint", p.bar(), render.CTX)
        expected = f"{int(reduction * 10 + 0.5) // 10}."
        expected += f"{int(reduction * 10 + 0.5) % 10} dB"
        if N.FW168: # run 17 Track FX v5: the meter bar only (no value text), 246 px for 24 dB, in the track colour at 60 %
            self.assertNotIn(expected, [label for label, _ in p.labels])
            tenths = min(240, int(reduction * 10 + 0.5))
            self.assertTrue(any(rect[0] == 894 and rect[2] == 17 and abs(rect[3] - tenths * 246 // 240) <= 1
                                and colour == 0x97 for rect, colour in p.fills))
        else:
            self.assertIn(expected, [label for label, _ in p.labels])
            self.assertTrue(any(rect[0] == 942 and rect[2] == 12 and rect[3] > 0
                                and colour == 0xF7 for rect, colour in p.fills))

        serial = (serial + 2) & 0xFFFFFFFE
        p.e.w(METER, serial | 1)
        p.e.w(METER + 4,
              ((p.e.r(0x24041444) & 0x0FFFFFFF) << 4) | 8)
        p.e.w(METER, serial)
        p.labels.clear()
        p.fills.clear()
        p.call("pg_bar_paint", p.bar(), render.CTX)
        if N.FW168: # run 17: an unavailable reading leaves the meter empty (no text)
            self.assertNotIn("Unavailable", [label for label, _ in p.labels])
            self.assertFalse(any(rect[0] == 894 and rect[2] == 17 and rect[3] > 0 for rect, colour in p.fills))
        else:
            self.assertIn("Unavailable", [label for label, _ in p.labels])
            self.assertFalse(any(rect[0] == 942 and rect[2] == 12 and rect[3] > 0
                                 and colour == 0xF7 for rect, colour in p.fills))
        p.call("fx_nav", MODEL, 0x17)
        self.assertEqual(p.e.r(METER_TRACK_OFFSET), 8)

    def test_meter_tick_repaints_no_faster_than_33ms(self):
        loud = np.full(128, 0.8, dtype=np.float32)
        quiet = np.full(128, 0.1, dtype=np.float32)
        first = compressor_measurement(loud)
        second = compressor_measurement(quiet)
        self.assertNotEqual(struct.unpack_from("<f", first, 8)[0],
                            struct.unpack_from("<f", second, 8)[0])

        p = Perform()
        p.open_track_fx()
        p.fx_values()
        transfer_reading(p, first)
        p.e.w(0x3001FE2C, 2000)
        p.u.mem_write(render.CTX, struct.pack("<II", 0, render.SURF))
        p.call("pg_perform_tick", p.bar(), render.CTX)
        p.u.mem_write(render.CTX + 1, b"\0")

        transfer_reading(p, second)
        p.e.w(0x3001FE2C, 2032)
        p.call("pg_perform_tick", p.bar(), render.CTX)
        self.assertEqual(p.u.mem_read(render.CTX + 1, 1), b"\0")

        p.e.w(0x3001FE2C, 2033)
        p.call("pg_perform_tick", p.bar(), render.CTX)
        self.assertEqual(p.u.mem_read(render.CTX + 1, 1), b"\1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
