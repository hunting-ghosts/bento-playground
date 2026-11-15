"""Drum capture uses real native encoders, routes, A-D storage and XML lanes.

The sample editor is constructed by native code; model children/files and the
event queue are fixtures. Full SD project reopen and hardware remain unproven.
"""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R3, UC_ARM_REG_PC

from test_clip_motion import MotionPage, FILTER, SLOT, CLIP, MODEL, NODE_BYTES, NODE
from test_perf import EV, OUT
from test_integration import UU
from test_syncussion_ui import no_card_carrier
from unicorn import UC_HOOK_CODE

VIEW = 0xc0080000
FILE = FILTER + 1
KEYS = (N.NKEY(0x1a0), N.NKEY(0x1a1), N.NKEY(0x1a2), N.NKEY(0x1a4), N.NKEY(0x1a5), N.NKEY(0x1a6), N.NKEY(0x1a9), N.NKEY(0x1b0))
NAMES = {1: "Kick", 3: "Snare", 5: "HiHat", 7: "Clap", 9: "Tom", 15: "Syncussion"}


class DrumPage(MotionPage):
    def __init__(self, engine=1, melodic=False):
        self.path = ("\\Drum Synths\\" + NAMES[engine] +
                     (" Melodic" if melodic else "") + ".wav\0").encode()
        self.drum_delivery = False
        super().__init__()
        no_card_carrier(self.u)
        self.types.update({self.track: 15 if melodic else 14, FILTER: 1, FILE: 5})
        self.children[self.track] = [CLIP, FILTER, FILE]
        self.sync_native_tree()
        self.page(8)
        self.call(0x08153560, VIEW)
        self.call(0x081639a8, 0)
        self.w(0x3000004c, self.next)
        self.u.hook_add(UC_HOOK_CODE, lambda *args: self.w(0x3000004c, self.next),
                        begin=0x08104c08, end=0x08104c08)
        self.w(VIEW + 0x87bc, FILTER)
        self.w(VIEW + 0x87c4, FILE)
        self.u.mem_write(VIEW + 0x87cc, bytes([15 if melodic else 14]))
        self.call(0x08152144, VIEW)
        self.call(self.symbol("kick_ui_before"), VIEW)
        self.call(self.symbol("kick_ui_after"), VIEW)

    def symbol(self, name):
        return self.speed_symbols.get(name, UU.get(name))

    def native(self, u, address, size, data):
        if address == 0x0813390e:
            u.mem_write(u.reg_read(UC_ARM_REG_R3), N.native_string(self.path))
            self.ret(1)
            return
        if address == 0x08133614 and self.r(u.reg_read(UC_ARM_REG_R1)) == FILTER:
            self.w(u.reg_read(UC_ARM_REG_R3), 0)
            self.ret(1)
            return
        super().native(u, address, size, data)

    def model(self, u, address, size, data):
        if address == 0x0816fc34 and self.drum_delivery:
            event = u.reg_read(UC_ARM_REG_R1)
            self.posted.append(tuple(struct.unpack("<5I", u.mem_read(event, 20))))
            u.reg_write(UC_ARM_REG_R0, VIEW)
            u.reg_write(UC_ARM_REG_PC, self.symbol("kick_ui_event") | 1)
            return
        super().model(u, address, size, data)

    def turn(self, delta, slot=SLOT, deliver=True):
        self.drum_delivery = True
        try:
            return super().turn(delta, slot, deliver)
        finally:
            self.drum_delivery = False

    def knob(self, key, value):
        self.call(0x08171c1c, SLOT, key, value, 1)
        self.w(SLOT + 0x34, FILTER)

    def visible_slot(self, key):
        slots = [VIEW + 0x70 + index * 0x468 for index in range(8)]
        matches = [slot for slot in slots
                   if self.r(slot + 0x34) == FILTER and
                   self.r(slot + 0x9c) & 0xffff == key]
        if len(matches) != 1:
            raise AssertionError(f"expected one native slot for {key:#x}, found {matches}")
        return matches[0]

    def base(self, key):
        self.call(self.symbol("kick_base_value"), VIEW, key, OUT)
        return self.r(OUT)

    def motion_label(self):
        self.u.mem_write(OUT, bytes(N.HDR_SIZE))
        self.call(self.symbol("motion_one_shot_toolbar"), OUT)
        return self.text(OUT + N.HDR(0x74) + 5 * 48)


class Tests(unittest.TestCase):
    def test_all_exposed_drum_parameters_capture_full_range_without_changing_base(self):
        for engine, name in NAMES.items():
            count = 8 if engine in (1, 15) else 7 if engine == 9 else 5
            for index, key in enumerate(KEYS[:count]):
                with self.subTest(engine=name, key=hex(key)):
                    p = DrumPage(engine)
                    base = p.base(key)
                    low = 25 if index == 0 and engine in (1, 9, 15) else 0
                    span = 155 if low else 100
                    slot = p.visible_slot(key)
                    self.assertEqual(p.r(slot + 0x34), FILTER)
                    self.assertEqual(p.r(slot + 0x9c) & 0xffff, key)
                    self.assertEqual(p.toggle(), 1)
                    before = bytes(p.u.mem_read(0x24043500, 0x900))
                    p.turn(1000000, slot=slot)
                    self.assertEqual(p.effective(slot, key), low + span)
                    self.assertEqual(p.read(0, 0), int((low + span - base) * 1000 / span))
                    self.assertEqual(p.routes, {(FILTER, key, 0): (9, 1000)})
                    self.assertEqual(p.base(key), base)
                    self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x900)), before)
                    p.position(1)
                    p.turn(-1000000, slot=slot)
                    self.assertEqual(p.effective(slot, key), low)
                    self.assertEqual(p.read(0, 1), int((low - base) * 1000 / span))
                    self.assertEqual(p.base(key), base)
                    self.assertAlmostEqual(p.deliver_audio(0)[0], p.read(0, 0) / 1000,
                                           places=6)
                    self.assertAlmostEqual(p.deliver_audio(1)[0], p.read(0, 1) / 1000,
                                           places=6)
                    p.toggle()
                    self.assertIsNone(p.effective(key=key))

    def test_retired_melodic_syncussion_page_offers_no_drum_synth_targets(self):
        # Run 14 (owner, 13 Nov): melodic Syncussion is retired; its Multisample page is the native one, so none
        # of the drum synth controls (and no motion route for them) exists there any more.
        p = DrumPage(15, melodic=True)
        for key in (KEYS[0], KEYS[1], KEYS[7]):
            with self.assertRaises(AssertionError):
                p.visible_slot(key)
        self.assertEqual(len(p.routes), 0)

    def test_ordinary_samples_selectors_and_other_engine_routes_are_not_targets(self):
        for kind in ("sample", "selector", "old-routes", "other-cell"):
            with self.subTest(kind=kind):
                p = DrumPage()
                key = N.NKEY(0x1ad) if kind == "selector" else KEYS[1]
                p.knob(key, 50)
                if kind == "sample":
                    p.path = b"\\Samples\\ordinary.wav\0"
                elif kind == "old-routes":
                    p.u.mem_write(0x2404352f, b"\x31")
                elif kind == "other-cell":
                    p.w(SLOT + 0x34, FILE)
                p.toggle()
                p.turn(1600)
                self.assertEqual(p.routes, {})
                self.assertEqual(p.motion_label(), "Not a motion target")

    def test_negative_depth_fractional_turns_and_native_lane_xml_roundtrip(self):
        p = DrumPage(9)
        key, depth, base = KEYS[0], -333, 86
        p.routes[FILTER, key, 0] = (9, depth)
        p.knob(key, base)
        p.toggle()
        value, remainder, before = 0, 0, base
        for i, delta in enumerate([3200] * 8 + [-3200] * 8):
            p.position(i)
            events = p.turn(delta)
            if not events:
                self.assertEqual(p.read(0, i), 0)
                continue
            event = events[0]
            numerator = (event[3] - before) * 1000000 + remainder
            divisor = depth * 155
            quotient = abs(numerator) // abs(divisor)
            if (numerator < 0) != (divisor < 0):
                quotient = -quotient
            remainder = numerator - quotient * divisor
            value += quotient
            self.assertEqual(p.read(0, i), value)
            before = event[3]
        self.assertEqual(value, 0)
        count, encoded = p.encode_lane(0)
        self.assertEqual(count, 16)
        q = DrumPage(9)
        q.decode_lane(0, encoded)
        self.assertEqual([q.read(0, i) for i in range(256)],
                         [p.read(0, i) for i in range(256)])

    def test_fifth_native_target_reports_the_four_lane_limit_without_overwriting(self):
        p = DrumPage(1)
        slots = [p.visible_slot(key) for key in KEYS[:5]]
        p.toggle()
        for slot in slots[:4]:
            p.turn(1000000, slot=slot)
        before = bytes(p.u.mem_read(NODE, NODE_BYTES))
        p.turn(1000000, slot=slots[4])
        self.assertEqual(p.motion_label(), "No free A-D")
        self.assertEqual(len(p.routes), 4)
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), before)

    def test_occupied_lanes_are_not_overwritten(self):
        p = DrumPage()
        p.knob(KEYS[1], p.base(KEYS[1]))
        for lane in range(4):
            p.write(lane, 0, 200)
        p.toggle()
        before = bytes(p.u.mem_read(NODE, NODE_BYTES))
        p.turn(3200)
        self.assertEqual(p.motion_label(), "No free A-D")
        self.assertEqual(p.routes, {})
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), before)

    def test_capture_display_uses_motion_value_and_button_is_idempotent(self):
        p = DrumPage()
        key = KEYS[1]
        p.knob(key, p.base(key))
        p.toggle()
        p.turn(3200)
        value = p.effective(key=key)
        p.call(p.symbol("kick_ui_after"), VIEW)
        self.assertEqual(p.r(VIEW + 0x70 + 0x468 + 0xa0), value)
        template = bytes(p.u.mem_read(0x08199008 + 2 * N.HDR_SIZE, N.HDR_SIZE))
        p.u.mem_write(OUT, template)
        for _ in range(3):
            p.call(UU["device_header_prepare"], OUT)
            ids = [struct.unpack("<H", p.u.mem_read(OUT + N.HDR(0x74) + i * 48 + 44, 2))[0]
                   for i in range(6)]
            # R6.3 (owner): no Pads/Steps footer button any more (Left+Right).
            self.assertNotIn(0x107e, ids)
            self.assertIn(0x1076, ids)
            m = ids.index(0x1076)
            self.assertEqual(p.u.mem_read(OUT + N.HDR(0x74) + m * 48 + 0x21, 1), b"\1")
        p.toggle()
        p.call(UU["device_header_prepare"], OUT)
        self.assertEqual(p.u.mem_read(OUT + N.HDR(0x74) + m * 48 + 0x21, 1), b"\0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
