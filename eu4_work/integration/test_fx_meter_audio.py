import struct
import unittest

import numpy as np

from test_integration import DEFAULT, Fixture, KEYS, UU

MODEL = 0x30024B00
METER = 0x24041974


class FxMeterAudioTests(unittest.TestCase):
    def test_selected_track_publishes_real_compressor_reduction(self):
        p = Fixture()
        p.direct_open()
        p.u.mem_write(MODEL + 0x12C, b"\x1a")
        p.event(KEYS[8], 1)
        p.event(KEYS[9], -30)
        p.event(KEYS[10], 10)
        p.event(KEYS[11], 1)
        p.event(KEYS[13], 0)
        p.mixer()

        signal = np.full(128, 0.8, dtype=np.float32)
        for _ in range(120):
            p.audio(0, signal, None)

        sequence, request_tag, reduction = struct.unpack(
            "<IIf", p.u.mem_read(METER, 12)
        )
        self.assertNotEqual(sequence, 0)
        self.assertEqual(sequence & 1, 0)
        self.assertEqual(request_tag,
                         ((p.r(0x24041444) & 0x0FFFFFFF) << 4))
        self.assertGreater(reduction, 15.0)

        out = 0x20016000
        self.assertEqual(p.call(UU["fx_screen_meter_snapshot"], out), 1)
        self.assertAlmostEqual(struct.unpack("<f", p.u.mem_read(out, 4))[0],
                               reduction, places=5)

    def test_meter_follows_selected_track_and_clears_stale_track_value(self):
        p = Fixture()
        p.direct_open()
        p.u.mem_write(MODEL + 0x12C, b"\x1a")
        p.event(KEYS[8], 1)
        p.event(KEYS[9], -30)
        p.event(KEYS[10], 10)
        p.event(KEYS[11], 1)
        p.event(KEYS[13], 0)
        p.mixer()
        signal = np.full(128, 0.8, dtype=np.float32)
        for _ in range(120):
            p.audio(0, signal, None)

        p.event(KEYS[18], 2)
        p.audio(1, signal, None)
        sequence, request_tag, reduction = struct.unpack(
            "<IIf", p.u.mem_read(METER, 12)
        )
        self.assertEqual(sequence & 1, 0)
        self.assertEqual(request_tag,
                         ((p.r(0x24041444) & 0x0FFFFFFF) << 4) | 1)
        self.assertEqual(reduction, 0.0)

        out = 0x20016000
        self.assertEqual(p.call(UU["fx_screen_meter_snapshot"], out), 1)
        self.assertEqual(struct.unpack("<f", p.u.mem_read(out, 4))[0], 0.0)

    def test_tracks_sentinel_stops_meter_publication_when_fx_is_closed(self):
        p = Fixture()
        p.direct_open()
        p.u.mem_write(MODEL + 0x12C, b"\x1a")
        settings = DEFAULT.copy()
        settings[8:14] = [1, -30, 10, 1, 120, 0]
        p.mailbox({0: settings})
        p.mixer()
        signal = np.full(128, 0.8, dtype=np.float32)
        for _ in range(120):
            p.audio(0, signal, None)

        before = struct.unpack("<IIf", p.u.mem_read(METER, 12))
        self.assertEqual(before[1],
                         ((p.r(0x24041444) & 0x0FFFFFFF) << 4))
        serial = (p.r(0x24041444) + 2) & 0xFFFFFFFE
        p.w(0x24041444, serial | 1)
        p.w(0x240416A8, 8)
        p.w(0x24041444, serial)
        p.audio(0, signal, None)
        closed = struct.unpack("<IIf", p.u.mem_read(METER, 12))
        self.assertEqual(closed[1],
                         ((serial & 0x0FFFFFFF) << 4) | 8)
        self.assertEqual(closed[2], 0.0)
        closed_serial = closed[0]

        for _ in range(8):
            p.audio(0, signal, None)
        self.assertEqual(struct.unpack("<I", p.u.mem_read(METER, 4))[0],
                         closed_serial)


if __name__ == "__main__":
    unittest.main(verbosity=2)
