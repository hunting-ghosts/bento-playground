"""Native capture/A-D playback and real send gains; queues/model/SD are fixtures."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE
from test_clip_motion import MotionPage, FILTER, SLOT
from test_integration import AA, UU, IMAGE

ROOT, PACKET = 0x20010000, 0x20031000
STRIP, INPUT, BUS, ROUTER = 0x20032000, 0x20033000, 0x20034000, 0xc0060000


class SendPage(MotionPage):
    def __init__(self):
        super().__init__()
        self.w(0x3000004c, self.next)
        self.w(0x30000048, 0xc0000000+N.SDRAM_MAP)
        self.u.hook_add(UC_HOOK_CODE,
                        lambda *args: self.w(0x3000004c, self.next),
                        begin=0x08104c08, end=0x08104c08)

    def prepare(self):
        if self.call(UU["mel_audio_prepare"], 0) != 1:
            raise AssertionError("real checked send allocation failed")

    def route(self, key, source=9, depth=1000, slot=0, sampler=False):
        self.u.mem_write(PACKET, struct.pack(
            "<6I", 0x3f, 0, 91, key, slot, source | (depth & 65535) << 16))
        if sampler:
            instruction = next(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(
                IMAGE[0x0808f38e - 0x08040000:0x0808f392 - 0x08040000], 0x0808f38e))  # as addresses: file offsets are invisible to the 1.6.8 translation
            self.call(int(instruction.op_str.lstrip("#"), 16), ROOT, PACKET)
        else:
            self.call(AA["motion_send_dispatch"], ROOT, PACKET)

    def gain(self, value):
        return self.call(0x080d33c0, value)

    def sample(self, address):
        return struct.unpack("<f", self.u.mem_read(address, 4))[0]

    def buffers(self):
        for obj, left in ((INPUT, 0xc0000000), (BUS, 0xc0001000)):
            self.u.mem_write(obj, struct.pack("<5I", 64, 64, left, left+0x200, 0))
            for at in (left, left+0x200):
                self.u.mem_write(at, struct.pack("<64f", *([1. if obj == INPUT else 0.] * 64)))

    def setup_audio_track(self, base=0):
        self.prepare()
        self.w(ROOT+12, 91)
        self.w(ROOT+0x284, 0)
        for j in range(2):
            self.u.mem_write(STRIP+0x50+j*0x18,
                            struct.pack("<6I", 0, 0, 0, int(base == 0),
                                        self.gain(base), self.gain(base)))

    def mix(self, key):
        self.buffers()
        self.call(AA["motion_send_begin"], ROOT, ROUTER)
        self.call(AA["motion_send_prepare"], STRIP, ROUTER+0x5ac)
        self.call(AA["motion_send_mix"], STRIP+0x50+(key-0x36)*0x18, INPUT, BUS, STRIP)
        return self.sample(0xc0001000)


class Tests(unittest.TestCase):
    def test_native_track_send_capture_preserves_base_routes_and_xml(self):
        for key in (0x36, 0x37):
            p = SendPage()
            p.call(0x08171c1c, SLOT, key, 500, 1)
            p.w(SLOT+0x34, p.track)
            self.assertEqual(p.toggle(), 1)
            p.turn(1000000)
            self.assertEqual(p.effective(key=key), 1000)
            self.assertEqual(p.r(SLOT+0xa0), 1000)
            self.assertNotIn((0xcf, p.track, key, 1000), p.model_events)
            self.assertEqual(p.routes, {(p.track, key, 0): (9, 1000)})
            self.assertEqual(p.read(0, 0), 500)
            _, encoded = p.encode_lane(0)
            p.decode_lane(0, encoded)
            self.assertEqual(p.read(0, 0), 500)
            source = p.deliver_audio(0)[0]
            self.assertAlmostEqual(source, .5)
            packet = p.route_packets[-1]
            p.setup_audio_track(500)
            p.u.mem_write(PACKET, packet[:24])
            p.call(AA["motion_send_dispatch"], ROOT, PACKET)
            p.f(ROOT+0x144, source)
            for _ in range(6):
                result = p.mix(key)
            self.assertAlmostEqual(result, 1., places=5)

    def test_generic_send_applies_native_gain_and_restores_both_base_controls(self):
        for key in (0x36, 0x37):
            p = SendPage()
            p.setup_audio_track()
            p.route(key)
            p.f(ROOT+0x144, 1)
            before = bytes(p.u.mem_read(STRIP+0x50, 0x30))
            p.mix(key)
            self.assertGreater(p.sample(0xc0001000+63*4), 0)
            self.assertEqual(bytes(p.u.mem_read(STRIP+0x50, 0x30)), before)
            for _ in range(6):
                result = p.mix(key)
            self.assertAlmostEqual(result, 1., places=5)

    def test_route_removal_returns_to_the_unchanged_native_base(self):
        p = SendPage()
        p.setup_audio_track(500)
        p.route(0x36)
        p.f(ROOT+0x144, .5)
        for _ in range(6):
            p.mix(0x36)
        p.route(0x36, 0, 0)
        self.assertAlmostEqual(p.mix(0x36),
                               struct.unpack("<f", struct.pack("<I", p.gain(500)))[0],
                               places=6)

    def test_replacement_root_on_same_bus_does_not_inherit_old_motion(self):
        p = SendPage()
        p.setup_audio_track()
        p.route(0x36)
        p.f(ROOT+0x144, 1)
        for _ in range(6):
            p.mix(0x36)
        replacement = ROOT+0x800
        p.w(replacement+12, 92)
        p.w(replacement+0x284, 0)
        p.buffers()
        p.call(AA["motion_send_begin"], replacement, ROUTER)
        p.call(AA["motion_send_prepare"], STRIP, ROUTER+0x5ac)
        p.call(AA["motion_send_mix"], STRIP+0x50, INPUT, BUS, STRIP)
        self.assertEqual(p.sample(0xc0001000+63*4), 0)

    def test_existing_route_follows_root_when_its_bus_moves(self):
        p = SendPage()
        p.setup_audio_track()
        p.route(0x36)
        p.f(ROOT+0x144, 1)
        for _ in range(6):
            p.mix(0x36)
        p.w(ROOT+0x284, 1)
        p.buffers()
        p.call(AA["motion_send_begin"], ROOT, ROUTER)
        p.call(AA["motion_send_prepare"], STRIP, ROUTER+0x5ac+20)
        other = ROOT+0x800
        p.w(other+12, 92)
        p.w(other+0x284, 0)
        p.call(AA["motion_send_begin"], other, ROUTER)
        p.call(AA["motion_send_mix"], STRIP+0x50, INPUT, BUS, STRIP)
        self.assertAlmostEqual(p.sample(0xc0001000+63*4), 1, places=5)

    def test_sampler_send_uses_native_route_list_and_restores_true_base(self):
        for key in (0x36, 0x37):
            p = SendPage()
            p.call(0x08095460, ROOT)
            p.w(ROOT+12, 91)
            p.route(key, sampler=True)
            self.assertEqual(p.r(ROOT+0x5fc), 1)
            p.f(ROOT+0x654, .5)
            p.w(ROOT+0x608, p.gain(250))
            p.w(ROOT+0x60c, p.gain(250))
            before = bytes(p.u.mem_read(ROOT+0x608, 0x20))
            p.call(AA["motion_pad_start"], ROOT)
            self.assertEqual(p.r(ROOT+0x608+(key-0x36)*4), p.gain(750))
            p.call(AA["motion_pad_finish"], ROOT)
            self.assertEqual(bytes(p.u.mem_read(ROOT+0x608, 0x20)), before)

    def test_explicit_step_send_lock_wins_then_the_true_base_is_restored(self):
        p = SendPage()
        p.call(0x08095460, ROOT)
        p.w(ROOT+12, 91)
        p.route(0x36, sampler=True)
        p.f(ROOT+0x654, .5)
        p.w(ROOT+0x608, p.gain(250))
        p.w(0x24044000, 0x37535042)
        seq = 0xc0080000
        p.w(seq+12, 80)
        p.u.mem_write(seq+0x20, b"\1")
        p.w(seq+0x86c0, 77)
        p.w(seq+0x14, 3)
        p.u.mem_write(0x24044010, struct.pack(
            "<12I", 91, ROOT, seq, 80, 77, 3, 0x510a0000 | 900, 0, 0, 0, 0, 0))
        p.call(AA["motion_pad_start"], ROOT)
        self.assertEqual(p.r(ROOT+0x608), p.gain(900))
        p.call(AA["motion_pad_finish"], ROOT)
        self.assertEqual(p.r(ROOT+0x608), p.gain(250))

    def test_signed_depth_and_all_three_routes_share_the_native_normalized_range(self):
        p = SendPage()
        p.setup_audio_track(500)
        p.route(0x36, 9, 1000, 0)
        p.route(0x36, 10, -500, 1)
        p.route(0x36, 11, 250, 2)
        p.f(ROOT+0x144, 1)
        p.f(ROOT+0x14c, 1)
        p.f(ROOT+0x154, 1)
        for _ in range(6):
            result = p.mix(0x36)
        self.assertAlmostEqual(result, 1., places=5)

    def test_full_sampler_route_list_does_not_claim_a_silent_send_capture(self):
        p = SendPage()
        p.types[FILTER] = 1
        p.routes = {(FILTER, key, 0): (13, 1000)
                    for key in (2, 3, 4, 0x1e, 0x1f, 0x20, 0x21, 0x32, 0x33)}
        p.sync_native_tree()
        p.call(0x08171c1c, SLOT, 0x36, 0, 1)
        p.w(SLOT+0x34, FILTER)
        self.assertEqual(p.toggle(), 1)
        before = p.routes.copy()
        p.turn(1000000)
        self.assertEqual(p.routes, before)
        self.assertEqual(p.commands, [])
        self.assertIsNone(p.effective(key=0x36))
        self.assertEqual(p.label(), "Check route")


if __name__ == "__main__":
    unittest.main(verbosity=2)
