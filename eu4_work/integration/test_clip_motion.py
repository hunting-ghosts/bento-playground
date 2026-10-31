"""Native capture checks against the candidate, or current-source M4 probes.

Native encoder, route setter/lookup, position getter, A-D writer, XML codec and
M7 evaluator execute. Object child/type services, allocation and queues are
fixtures. They do not prove full-device Undo or project SD reopen.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

from test_encoder_speed import install_probe
from test_native_automation import Automation, MODEL, HANDLE, NODE, NODE_BYTES, SEQUENCE, TIME
from test_perf import Page, EV, OUT, PROJECT
from test_integration import UU

CLIP = 55
FILTER = 0x205
SLOT = 0xc0040070
ENGINE = 0xc0060000
KEEP = []


class MotionPage(Page):
    def registry(self):
        install_probe(self, force="motion_capture_event" not in UU)
        super().registry()

    def __init__(self):
        self.clip = CLIP
        self.row = 0
        self.steps = 16
        self.children = {}
        self.types = {}
        self.routes = {}
        super().__init__()
        KEEP.append(self)
        self.children = {self.track: [CLIP, FILTER]}
        self.types = {self.track: 18, CLIP: 24, FILTER: 10}
        self.undo = 0
        self.commands = []
        self.lookups = []
        self.present = True
        self.posted = []
        self.route_packets = []
        self.route_allocation_fails = False
        self.extra_nodes = {}
        self.deliver_events = False
        self.w(MODEL, 0xc0020000)
        self.w(0x3000f650, ENGINE)
        self.position(0)
        self.w(HANDLE, CLIP)
        self.u.mem_write(NODE - 16, b"\xa5" * 16)
        self.u.mem_write(NODE + NODE_BYTES, b"\xa5" * 16)
        for address in (0x0812ea72, 0x081338dc, 0x08133d84,
                        0x0813650c, 0x08136668, 0x08173272):
            self.u.hook_add(UC_HOOK_CODE, self.service, begin=address, end=address)
        for address in (0x0813391a, 0x08131244, 0x0816fc34):
            self.u.hook_add(UC_HOOK_CODE, self.model, begin=address, end=address)
        for address in (0x081ff180, 0x081ff190, 0x081ff1a0,
                        0x0812e7dc, 0x0812e518, 0x0810b7d4):
            self.u.hook_add(UC_HOOK_CODE, self.route_service, begin=address, end=address)
        self.sync_native_tree()
        self.open()
        self.header()
        self.call(0x08145b7c, SLOT - 0x70)
        self.call(0x08171c1c, SLOT, 0x33, 500, 1)
        self.w(SLOT + 0x34, FILTER)

    def service(self, u, address, size, data):
        if address == 0x0812ea72 and u.reg_read(UC_ARM_REG_R1) != CLIP:
            node = self.extra_nodes.get(u.reg_read(UC_ARM_REG_R1))
            if node:
                self.w(u.reg_read(UC_ARM_REG_R2), node)
            self.ret(int(bool(node)))
        else:
            Automation.service(self, u, address, size, data)

    read = Automation.read
    write = Automation.write

    def sync_native_tree(self):
        tree, vt = 0xc0020000, 0xc0020800
        self.objects = {h: 0xc0021000 + i * 0x80
                        for i, h in enumerate(self.types)}
        self.w(tree, self.objects[self.track])
        self.w(tree + 0x30, 1)
        self.w(tree + 0x34, self.objects[self.track])
        self.w(tree + 0x54, 1)
        for off, address in ((0, 0x081ff180), (0x14, 0x081ff190),
                             (0x18, 0x081ff1a0)):
            self.w(vt + off, address | 1)
        for h, obj in self.objects.items():
            self.u.mem_write(obj, bytes(0x80))
            self.w(obj, vt)
            self.w(obj + 4, self.types[h])
            self.w(obj + 0x10, h)
        self.route_next = 0xc0030000
        for (h, key, slot), (source, depth) in self.routes.items():
            obj = self.objects[h]
            record = self.allocate_route(obj)
            self.w(record + 0xc, depth)
            self.u.mem_write(record + 0x10, struct.pack("<3H", source, key, slot))

    def allocate_route(self, obj):
        record = self.route_next
        self.route_next += 0x18
        self.u.mem_write(record, bytes(0x18))
        self.w(record + 4, self.r(obj + 0x14))
        self.u.mem_write(record + 8, b"\1")
        self.w(obj + 0x14, record)
        return record

    def stored_routes(self):
        routes = {}
        for h, obj in self.objects.items():
            record = self.r(obj + 0x14)
            while record:
                source, key, slot = struct.unpack(
                    "<3H", self.u.mem_read(record + 0x10, 6))
                depth = struct.unpack("<i", self.u.mem_read(record + 0xc, 4))[0]
                routes[h, key, slot] = source, depth
                record = self.r(record + 4)
        return routes

    def route_service(self, u, address, size, data):
        r = [u.reg_read(reg) for reg in
             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        if address == 0x081ff180:
            self.ret(self.r(r[0] + 4))
        elif address in (0x081ff190, 0x081ff1a0):
            children = self.children.get(self.r(r[0] + 0x10), [])
            h = r[1] if address == 0x081ff190 else (
                children[r[1]] if r[1] < len(children) else 0)
            obj = self.objects.get(h, 0) if h in children else 0
            self.w(r[2], obj)
            self.ret(int(bool(obj)))
        elif address == 0x0812e7dc:
            self.assert_route_type = r[1]
            if self.route_allocation_fails:
                self.ret(0)
            else:
                self.w(r[3], self.allocate_route(r[2]))
                self.ret(1)
        elif address == 0x0812e518:
            obj = self.objects[r[1]]
            link = obj + 0x14
            while self.r(link) and self.r(link) != r[2]:
                link = self.r(link) + 4
            if self.r(link):
                self.w(link, self.r(r[2] + 4))
            self.ret(1)
        else:
            self.route_packets.append(bytes(u.mem_read(r[1], 0x30)))
            self.ret()

    def native(self, u, a, n, data):
        if a == 0x08133614:
            handle = self.r(u.reg_read(UC_ARM_REG_R1))
            key = u.reg_read(UC_ARM_REG_R2)
            out = u.reg_read(UC_ARM_REG_R3)
            if handle == self.track and key == 0x133:
                self.w(out, self.row)
                self.ret(1)
                return
            if handle == self.clip and key in (0x73, 0x62):
                self.w(out, self.row if key == 0x73 else self.steps)
                self.ret(1)
                return
        if a == 0x08133f7c:
            self.ret(self.types.get(self.r(u.reg_read(UC_ARM_REG_R1)), 0))
            return
        super().native(u, a, n, data)

    def model(self, u, a, n, data):
        if a == 0x0816fc34 and getattr(self, "native_synth_events", False):
            return
        r = [u.reg_read(reg) for reg in
             (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        if a == 0x0813391a:
            children = self.children.get(self.r(r[1]), [])
            if r[2] < len(children):
                self.w(r[3], children[r[2]])
                self.ret(1)
            else:
                self.ret(0)
        elif a == 0x08131244:
            return  # Actual native lookup walks the fixture-backed objects.
        else:
            self.posted.append(tuple(struct.unpack("<5I", u.mem_read(r[1], 20))))
            if getattr(self, "footer_dispatch", False):
                if r[0] == 0x30034d48:
                    u.reg_write(UC_ARM_REG_R0, MODEL)
                    u.reg_write(UC_ARM_REG_PC, UU["analog_model_event"] | 1)
                else:
                    u.reg_write(UC_ARM_REG_R0, 0x30034d48)
                    u.reg_write(UC_ARM_REG_PC, 0x0817fe71)
                return
            if self.deliver_events:
                # Stand in for the native parent handler, without returning
                # from 08171E44 first: A0 is updated AFTER the parent event.
                u.reg_write(UC_ARM_REG_R0, MODEL)
                u.reg_write(UC_ARM_REG_PC, UU["analog_model_event"] | 1)
            else:
                self.ret()

    def position(self, position, row=None):
        # Native 081322AC -> 0810BB8C reads this existing status cache.
        self.u.mem_write(ENGINE + 0x4888, struct.pack(
            "<4i", position, self.row if row is None else row, -1, 0))

    def toggle(self):
        self.u.mem_write(EV, struct.pack("<5I", 0x1076, 0, 0, 0, 0))
        return self.call(UU["perf_navigation"], EV)

    def footer(self):
        self.page(0x1a)
        self.u.mem_write(OUT, bytes(0x1c4))
        self.call(UU["perf_toolbar"], MODEL, OUT)
        return [struct.unpack("<H", self.u.mem_read(OUT + 0x74 + i * 48 + 44, 2))[0]
                for i in range(6)]

    def label(self):
        self.footer()
        self.call(UU["perf_readout"], OUT)
        return self.text(OUT + 0x196).removeprefix("Motion: ")

    def turn(self, delta, slot=SLOT, deliver=True):
        self.sync_native_tree()
        self.w(0x3001fe2c, self.r(0x3001fe2c) + 10)
        count = len(self.posted)
        self.deliver_events = deliver
        self.call(0x08171e44, slot, delta & 0xffffffff)
        self.deliver_events = False
        self.routes = self.stored_routes()
        events = self.posted[count:]
        return events

    def effective(self, slot=SLOT, key=0x33):
        self.w(HANDLE, self.r(slot + 0x34))
        self.w(OUT, 0xdead)
        ok = self.call(self.speed_symbols["motion_capture_get"],
                       HANDLE, key, OUT)
        self.w(HANDLE, CLIP)
        return self.r(OUT) if ok else None

    def deliver_audio(self, position):
        engine, packet_at = 0xc00d0000, 0x20038000
        self.call(0x08062a80, SEQUENCE)
        self.w(engine + 0x15ba4, 1)
        self.w(engine + 0x15b84, SEQUENCE)
        # 08133D84 is fixture-backed: it publishes audio handle 100, row 0.
        self.w(SEQUENCE + 0xc, 100)
        self.w(SEQUENCE + 0x14, position)
        self.u.mem_write(SEQUENCE + 0x20, b"\1")
        self.w(SEQUENCE + 0x86c0, SEQUENCE + 0x240)
        self.w(SEQUENCE + 0x244, self.steps)
        self.u.mem_write(TIME, bytes(8))
        for packet in self.commands:
            self.u.mem_write(packet_at, packet)
            self.call(0x0805a340, engine, packet_at)
        self.call(0x08061040, SEQUENCE, TIME)
        return struct.unpack("<4f", b"".join(
            self.u.mem_read(SEQUENCE + 0x8720 + lane * 8, 4)
            for lane in range(4)))

    def encode_lane(self, lane):
        obj = 0x20010000
        self.w(obj + 0x10, CLIP)
        self.u.reg_write(UC_ARM_REG_R8, obj)
        self.u.reg_write(UC_ARM_REG_R6, NODE)
        stop = self.stop
        self.stop = 0x0812f88e
        self.call(0x0812f860)
        count = self.u.reg_read(UC_ARM_REG_R7)
        self.w(self.r(0x0812fa88), 0xc0069000)
        self.u.reg_write(UC_ARM_REG_R9, lane)
        self.u.reg_write(UC_ARM_REG_R10, NODE + 10 + lane * 512)
        self.u.reg_write(UC_ARM_REG_R2, 0)
        self.stop = 0x0812f91a
        self.call(0x0812f890)
        self.stop = stop
        return count, bytes(self.u.mem_read(0xc0069000, 1537)).split(b"\0")[0]

    def decode_lane(self, lane, encoded, slide=0):
        self.attrs = {"idx": lane, "slide": slide}
        self.u.mem_write(0x20034000, encoded + b"\0")

        def xml(u, address, size, data):
            if address == 0x0812dfc0:
                self.w(u.reg_read(UC_ARM_REG_R3), NODE)
                self.ret(1)
            elif address == 0x08109cc4:
                self.ret(0x20034000)
            else:
                self.ret(0)

        hooks = [self.u.hook_add(UC_HOOK_CODE, xml, begin=a, end=a)
                 for a in (0x0812dfc0, 0x08109cc4, 0x081092aa)]
        try:
            self.call(0x0812ffa8, 0x20011000, 0xc0070000, 0x20010000)
        finally:
            for hook in hooks:
                self.u.hook_del(hook)

    def hook(self, u, address, size, data):
        if address == 0x0812dc74 and u.reg_read(UC_ARM_REG_R1) == 0x62:
            self.ret(self.steps)
        else:
            super().hook(u, address, size, data)


class ClipMotionTests(unittest.TestCase):
    def test_reduced_integer_conversion_preserves_fractional_signed_depth(self):
        for depth in (333, -333):
            with self.subTest(depth=depth):
                p = self.armed(depth=depth)
                expected, remainder, before = 0, 0, 500
                divisor = depth * 1000
                for step, delta in enumerate([160] * 20 + [-160] * 20):
                    position = step % 16
                    p.position(position)
                    event = p.turn(delta)[0]
                    numerator = (event[3] - before) * 1000000 + remainder
                    quotient = abs(numerator) // abs(divisor)
                    if (numerator < 0) != (divisor < 0):
                        quotient = -quotient
                    expected += quotient
                    remainder = numerator - quotient * divisor
                    before = event[3]
                    self.assertEqual(p.read(0, position), expected)
                self.assertEqual(p.read(0, position), 0)

    def test_synth_echo_only_consumes_the_matching_immediate_cf(self):
        for field, value, delay in ((0, 0xcf, 0), (0, 0xd0, 0),
                                     (4, FILTER + 1, 0), (8, 0xce, 0),
                                     (12, 601, 0), (0, 0xcf, 101)):
            with self.subTest(field=field, value=value, delay=delay):
                p = MotionPage()
                p.toggle()
                p.call(p.speed_symbols["motion_capture_begin"], SLOT, 1000)
                p.u.mem_write(EV, struct.pack("<5I", 0xd0, FILTER, 0x33, 600, 0))
                self.assertEqual(p.call(p.speed_symbols["motion_capture_event"], EV), 1)
                p.u.mem_write(EV, struct.pack("<5I", 0xcf, FILTER, 0x33, 600, 0))
                p.w(EV + field, value)
                p.w(0x3001fe2c, p.r(0x3001fe2c) + delay)
                match = field == 0 and value == 0xcf and not delay
                self.assertEqual(p.call(p.speed_symbols["motion_capture_event"], EV),
                                 int(match))
                self.assertEqual(p.effective(), 600 if match else None)
                self.assertEqual(p.read(0, 0), 100)

    def test_native_synth_d0_then_cf_keeps_take_and_accumulates_across_steps(self):
        p = MotionPage()
        view, app, vt = 0xc0400000, 0xc00b0000, 0xc00b0800
        p.u.mem_map(view, 0x40000)
        p.w(0x3000004c, p.next)
        p.w(0x30000048, 0xc0200000)
        p.call(0x0815e228, view)
        p.w(view + 0x2430, p.track)
        p.u.mem_write(view + 0x10238, b"\x05")
        p.w(view + 0x2c, app)
        p.w(app, vt)
        p.w(vt + 0x30, 0x081ff1b1)
        slot = view + 0x70
        p.call(0x08171c1c, slot, 0xce, 500, 1)
        p.w(slot + 0x34, FILTER)
        events = []

        def sink(u, address, size, data):
            event = u.reg_read(UC_ARM_REG_R1)
            events.append(tuple(struct.unpack("<5I", u.mem_read(event, 20))))
            u.reg_write(UC_ARM_REG_R0, event)
            u.reg_write(UC_ARM_REG_PC, p.speed_symbols["motion_capture_event"] | 1)

        p.u.hook_add(UC_HOOK_CODE, sink, begin=0x081ff1b0, end=0x081ff1b0)
        p.native_synth_events = True
        p.toggle()
        shown = []
        for step in range(10):
            p.position(step)
            p.turn(8000, slot=slot)
            self.assertEqual([e[0] & 0xffff for e in events[-2:]], [0xd0, 0xcf])
            expected = events[-1][3]
            shown.append((p.effective(slot, 0xce), expected))
            self.assertEqual(p.read(0, step), expected - 500)
            self.assertEqual(len(p.commands), step + 1)
        self.assertTrue(all(actual == expected for actual, expected in shown))
        self.assertEqual(p.undo, 1)

    def test_idle_transport_passes_do_not_overwrite_existing_points_or_base(self):
        p = self.armed()
        for step in range(16):
            p.write(0, step, 100 + 10 * step)
        p.commands.clear()
        p.position(7)
        p.turn(1000)
        captured = bytes(p.u.mem_read(NODE, NODE_BYTES))
        commands = len(p.commands)
        for _ in range(2):
            for step in range(16):
                p.position(step)
                p.call(UU["perf_tick"])
                p.call(UU["macro_readout"], OUT)
                p.call(0x08171c1c, SLOT, 0x33, p.effective(), 0)
                self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), captured)
        self.assertEqual(len(p.commands), commands)
        for step in range(16):
            if step != 7:
                self.assertEqual(p.read(0, step), 100 + 10 * step)
        self.assertEqual(p.routes, {(FILTER, 0x33, 0): (9, 1000)})

    def test_full_encoder_sweep_matches_native_signed_source_and_graph_units(self):
        for key in (0xce, 0x33):
            p = MotionPage()
            p.call(0x08171c1c, SLOT, key, 500, 1)
            p.w(SLOT + 0x34, FILTER)
            p.toggle()
            graph = 0xc0070000
            for step, delta in enumerate((80000, -160000, 80000)):
                p.position(step)
                event = p.turn(delta)[0]
                expected = (1000, 0, 500)[step]
                self.assertEqual(event[3], expected)
                self.assertEqual(p.read(0, step), expected - 500)
                self.assertAlmostEqual(p.deliver_audio(step)[0],
                                       (expected - 500) / 1000, places=6)
            # Native editor copies the same signed samples into its graph,
            # which is bipolar -1000..1000 rather than parameter 0..1000.
            for step in range(3):
                p.call(0x08174ffc, graph, step, p.read(0, step) & 0xffffffff)
                self.assertEqual(p.r(graph + 0x54 + step * 4),
                                 p.read(0, step) & 0xffffffff)

    def test_lower_left_motion_indicator_persists_and_tap_disarms_without_erasing(self):
        p = self.armed()
        p.turn(1000)
        captured = bytes(p.u.mem_read(NODE, NODE_BYTES))
        root, app, point, hit = 0x30034d48, 0x20036000, 0x20036100, 0x20036110
        p.u.mem_write(app, bytes(0x60))
        p.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: p.ret(0),
                     begin=0x0816e0fc, end=0x0816e0fc)
        p.call(0x08180198, root)
        p.footer()
        p.call(UU["device_header_prepare"], OUT)
        self.assertEqual(p.text(OUT), "MOTION ON")
        p.call(0x0817faf8, root, OUT)
        x, width, height = p.r(root + 0x240), p.r(root + 0x248), p.r(root + 0x10)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        for page in (0x17, 0x0a, 2):
            p.page(page)
            p.call(UU["macro_readout"], OUT)
            self.assertEqual(p.text(OUT), "MOTION ON")
        for xpoint, ypoint in ((x + width + 1, height // 2),
                              (x + 1, height + 1)):
            p.w(point, xpoint)
            p.w(point + 4, ypoint)
            p.call(UU["macro_app_hit"], app, point, hit)
            self.assertEqual(p.call(p.speed_symbols["motion_active"], 0), 1)
        p.w(point, x + width // 2)
        p.w(point + 4, height // 2)
        p.w(hit, 0xffffffff)
        self.assertEqual(p.call(UU["macro_app_hit"], app, point, hit), 0)
        self.assertEqual(p.r(hit), 0)
        self.assertEqual(p.call(p.speed_symbols["motion_active"], 0), 0)
        p.u.mem_write(OUT, bytes(0x1c4))
        p.call(UU["macro_readout"], OUT)
        self.assertEqual(p.text(OUT), "")
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), captured)

    def test_motion_indicator_retains_mapping_state_when_stopping_motion(self):
        p = self.armed()
        p.w(0x3000004c, p.next)
        p.u.hook_add(UC_HOOK_CODE, lambda u, a, n, d: p.w(0x3000004c, p.next),
                     begin=0x08104c08, end=0x08104c08)
        p.call(UU["macro_touch"], 2)
        p.call(UU["macro_readout"], OUT)
        self.assertEqual(p.text(OUT), "MOTION ON")
        self.assertEqual(p.call(p.speed_symbols["motion_active"], 1), 1)
        p.call(UU["macro_readout"], OUT)
        self.assertEqual(p.text(OUT), "MAP M3 0/3")

    def bind_cutoff(self, p, lane=0, slot=SLOT):
        p.call(0x08171c1c, slot, 0xce, 500, 1)
        p.w(slot + 0x34, FILTER)
        p.routes[FILTER, 0xce, 0] = (9 + lane, 1000)
        self.assertEqual((p.r(slot + 0x450), p.r(slot + 0x454)), (0, 1000))

    def test_cutoff_native_encoder_records_and_replays_both_directions(self):
        p = MotionPage()
        self.bind_cutoff(p)
        p.toggle()
        before = bytes(p.u.mem_read(NODE, NODE_BYTES))
        p.position(3)
        up = p.turn(10000)[0][3]
        self.assertGreater(up, 500)
        self.assertEqual(p.read(0, 3), up - 500)
        self.assertEqual(p.effective(key=0xce), up)
        p.position(9)
        down = p.turn(-20000)[0][3]
        self.assertLess(down, 500)
        self.assertEqual(p.read(0, 9), down - 500)
        self.assertAlmostEqual(p.deliver_audio(3)[0], (up - 500) / 1000, places=6)
        self.assertAlmostEqual(p.deliver_audio(9)[0], (down - 500) / 1000, places=6)
        self.assertEqual(p.undo, 1)
        self.assertEqual(p.routes, {(FILTER, 0xce, 0): (9, 1000)})
        expected = bytearray(before)
        struct.pack_into("<h", expected, 10 + 3 * 2, up - 500)
        struct.pack_into("<h", expected, 10 + 9 * 2, down - 500)
        expected[0x80a] = 1
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), bytes(expected))
        _, encoded = p.encode_lane(0)
        q = MotionPage()
        q.decode_lane(0, encoded)
        self.assertEqual([q.read(0, i) for i in range(256)],
                         [p.read(0, i) for i in range(256)])
        p.toggle()
        self.assertEqual(p.effective(key=0xce), None)

    def test_cutoff_and_resonance_use_distinct_existing_lanes(self):
        p = self.armed(lane=1)
        cutoff = SLOT + 0x468
        self.bind_cutoff(p, slot=cutoff)
        p.position(4)
        res = p.turn(1000)[0][3] - 500
        cut = p.turn(2000, slot=cutoff)[0][3] - 500
        self.assertEqual((p.read(0, 4), p.read(1, 4)), (cut, res))
        self.assertEqual(p.undo, 1)

    def test_cutoff_cannot_share_recorded_resonance_lane(self):
        p = self.armed()
        p.turn(1000)
        cutoff = SLOT + 0x468
        self.bind_cutoff(p, slot=cutoff)
        count = len(p.commands)
        p.turn(1000, slot=cutoff)
        self.assertEqual(len(p.commands), count)
        self.assertEqual(p.label(), "Check route")

    def test_sampler_cutoff_is_not_claimed_as_a_native_synth_filter(self):
        p = MotionPage()
        self.bind_cutoff(p)
        p.types[FILTER] = 2
        p.toggle()
        p.turn(1000)
        self.assertEqual(p.commands, [])
        self.assertEqual(p.label(), "Not a motion target")

    def armed(self, lane=0, depth=1000):
        p = MotionPage()
        p.routes[FILTER, 0x33, 0] = (9 + lane, depth)
        self.assertEqual(p.toggle(), 1)
        return p

    def test_native_position_getter_matches_piano_row_and_signed_idle(self):
        p = MotionPage()
        for position, row in ((0, 0), (15, 0), (255, 7), (-1, 2)):
            p.position(position, row)
            got = p.call(0x081322ac, MODEL, 0, OUT, OUT + 4)
            self.assertEqual(got, position & 0xffffffff)
            self.assertEqual(p.r(OUT), row)
            self.assertEqual(p.r(OUT + 4), 0xffffffff)

    def test_native_encoder_to_lane_to_real_audio_at_nonzero_step(self):
        p = self.armed()
        p.position(7)
        routes = p.routes.copy()
        before = bytearray(p.u.mem_read(NODE, NODE_BYTES))
        events = p.turn(1000)
        self.assertEqual(len(events), 1)
        value = events[0][3] - 500
        self.assertGreater(value, 0)
        self.assertEqual(p.read(0, 7), value)
        self.assertEqual(p.effective(), events[0][3])
        struct.pack_into("<h", before, 10 + 7 * 2, value)
        before[0x80a] = 1
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), bytes(before))
        self.assertEqual(p.routes, routes)
        self.assertEqual(p.undo, 1)
        self.assertAlmostEqual(p.deliver_audio(7)[0], value / 1000, places=6)
        self.assertEqual(p.deliver_audio(6)[0], 0)

    def test_footer_preserves_tabs_and_project_save_load(self):
        p = self.armed()
        self.assertEqual(p.footer()[:5], [0x1071, 0x1072, 0x1074, 0x1075, 0x1076])
        self.assertEqual(p.u.mem_read(OUT + 0x74 + 4 * 48 + 0x21, 1), b"\1")
        p.u.mem_write(EV, struct.pack("<5I", 0x1075, 0, 0, 0, 0))
        p.call(UU["perf_navigation"], EV)
        p.u.mem_write(OUT, bytes(0x1c4))
        p.call(UU["perf_toolbar"], MODEL, OUT)
        ids = [struct.unpack("<H", p.u.mem_read(OUT + 0x74 + i * 48 + 44, 2))[0]
               for i in range(6)]
        self.assertEqual(ids, [0x1075, 0x1076, 0, 0, 0x8f, 0x8b])
        p.call(UU["perf_nav"], 0x17)
        p.page(0x17)
        p.turn(1000)
        self.assertGreater(p.read(0, 0), 0)
        self.assertEqual(p.button(0xaf, 14), 0)
        self.assertEqual(p.button(0xb0, 14), 0)

    def test_off_does_not_capture_or_claim_a_recorded_value(self):
        p = self.armed()
        p.toggle()
        p.turn(1000)
        self.assertEqual(p.commands, [])
        self.assertEqual(p.effective(), None)

    def test_native_footer_release_routes_action_to_motion_toggle(self):
        p = MotionPage()
        root = 0x30034d48
        p.call(0x08180198, root)
        p.footer()
        p.call(UU["device_header_prepare"], OUT)
        p.call(0x0817faf8, root, OUT)
        button = root + 0x54c + 4 * 0xd0
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: p.ret(0),
                            begin=0x08134800, end=0x08134800)
        p.footer_dispatch = True
        p.call(0x0816a29a, button)
        p.footer_dispatch = False
        p.u.hook_del(hook)
        self.assertEqual([event[0] for event in p.posted[-2:]], [0x7a, 0x1076])
        p.footer()
        self.assertEqual(p.u.mem_read(OUT + 0x74 + 4 * 48 + 0x21, 1), b"\1")

    def test_unrelated_edit_ends_take_before_another_native_snapshot(self):
        p = self.armed()
        p.turn(1000)
        p.u.mem_write(EV, struct.pack("<5I", 0xd1, FILTER, 0x33, 9, 500))
        p.call(p.speed_symbols["motion_capture_event"], EV)
        self.assertEqual(p.effective(), None)
        p.turn(1000)
        self.assertEqual(p.undo, 2)

    def test_invalid_clip_lengths_cannot_arm(self):
        for steps in (0, 257, 0xffffffff):
            p = MotionPage()
            p.steps = steps
            p.toggle()
            self.assertEqual(p.label(), "Select clip")
            p.turn(1000)
            self.assertEqual(p.commands, [])

    def test_late_encoder_event_and_changed_route_do_not_write(self):
        p = self.armed()
        event = p.turn(1000, deliver=False)[0]
        p.w(0x3001fe2c, p.r(0x3001fe2c) + 101)
        p.u.mem_write(EV, struct.pack("<5I", *event))
        self.assertEqual(p.call(p.speed_symbols["motion_capture_event"], EV), 0)
        self.assertEqual(p.commands, [])
        p.turn(1000)
        count = len(p.commands)
        p.routes[FILTER, 0x33, 0] = (10, 1000)
        p.turn(1000)
        self.assertEqual(len(p.commands), count)
        self.assertEqual(p.label(), "Check route")

    def test_first_turn_creates_a_native_route_and_groups_it_with_capture(self):
        p = MotionPage()
        p.toggle()
        p.position(7)
        event = p.turn(1000)[0]
        self.assertEqual(p.routes, {(FILTER, 0x33, 0): (9, 1000)})
        self.assertEqual(p.assert_route_type, 1)
        self.assertEqual(p.read(0, 7), event[3] - 500)
        self.assertEqual(p.undo, 1)
        packet = p.route_packets[-1]
        self.assertEqual(packet[0], 0x3f)
        self.assertEqual(struct.unpack_from("<3I2H", packet, 8),
                         (p.track, 0x33, 0, 9, 1000))
        p.turn(1000)
        self.assertEqual(p.undo, 1)
        self.assertEqual(len(p.routes), 1)
        self.assertEqual(len(p.route_packets), 1)

    def test_normalized_native_synth_and_sampler_destinations_capture(self):
        destinations = {
            6: (0xc4,), 8: (0xc4, 0xc5), 9: (0x1e, 0x1f, 0x21),
            10: (0xce, 0x33), 11: (0x4b, 0x4c),
            7: (0xc4, 0x53, 0x50, 0x56, 0x146, 0x14c),
            1: (0x1e, 0x1f, 0x21, 0x33, 0x4b, 0x4c),
            2: (0x1e, 0x1f, 0x21, 0x33, 0x4b, 0x4c),
        }
        for kind, keys in destinations.items():
            for key in keys:
                with self.subTest(kind=kind, key=key):
                    p = MotionPage()
                    p.types[FILTER] = kind
                    if kind in (1, 2):
                        p.types[p.track] = 14
                    p.call(0x08171c1c, SLOT, key, 500, 1)
                    p.w(SLOT + 0x34, FILTER)
                    p.toggle()
                    event = p.turn(1000)[0]
                    self.assertGreater(p.read(0, 0), 0)
                    self.assertEqual(p.read(0, 0), event[3] - 500)
                    self.assertEqual(p.effective(key=key), event[3])
                    self.assertEqual(p.routes, {(FILTER, key, 0): (9, 1000)})

    def test_all_four_lanes_are_assigned_without_overwriting_other_modulators(self):
        p = MotionPage()
        p.toggle()
        keys = (0xce, 0x33, 0x1f, 0x4b)
        kinds = (10, 10, 9, 11)
        for lane, (kind, key) in enumerate(zip(kinds, keys)):
            h = FILTER + lane
            p.types[h] = kind
            if h not in p.children[p.track]:
                p.children[p.track].append(h)
            p.routes[h, key, 0] = (4, 250)
            slot = SLOT + lane * 0x468
            p.call(0x08171c1c, slot, key, 500, 1)
            p.w(slot + 0x34, h)
            p.position(7)
            p.turn(1000 * (lane + 1), slot=slot)
            self.assertEqual(p.routes[h, key, 0], (4, 250))
            self.assertEqual(p.routes[h, key, 1], (9 + lane, 1000))
            self.assertGreater(p.read(lane, 7), 0)
        self.assertEqual(p.undo, 1)
        self.assertEqual(len(p.routes), 8)

    def test_routes_and_clip_data_both_reserve_lanes_before_auto_assignment(self):
        p = MotionPage()
        p.routes[FILTER, 0xce, 0] = (9, 0)  # Muted route still belongs to cutoff.
        p.write(1, 200, -300)
        p.commands.clear()
        p.u.mem_write(NODE + 0x80e + 2, b"\1")  # Smoothing-only lane.
        p.toggle()
        p.turn(1000)
        self.assertEqual(p.routes[FILTER, 0x33, 0], (12, 1000))
        self.assertEqual(p.routes[FILTER, 0xce, 0], (9, 0))
        self.assertEqual(p.read(1, 200), -300)
        self.assertEqual(p.read(0, 0), 0)
        self.assertEqual(p.read(2, 0), 0)

    def test_data_in_another_clip_and_inactive_points_are_not_repurposed(self):
        p = MotionPage()
        other_clip, other_node = 56, 0xc0190000
        p.children[p.track].append(other_clip)
        p.types[other_clip] = 24
        p.extra_nodes[other_clip] = other_node
        p.u.mem_write(other_node + 10, struct.pack("<h", 123))
        p.u.mem_write(NODE + 0x80b, b"\1")
        p.u.mem_write(NODE + 0x80c, b"\1")
        p.u.mem_write(NODE + 0x80d, b"\1")
        before = bytes(p.u.mem_read(NODE, NODE_BYTES))
        p.toggle()
        p.turn(1000)
        self.assertEqual(p.label(), "No free A-D")
        self.assertEqual(p.commands, [])
        self.assertEqual(p.routes, {})
        self.assertEqual(p.undo, 0)
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), before)
        self.assertEqual(p.u.mem_read(other_node + 10, 2), struct.pack("<h", 123))

    def test_full_destination_routes_are_never_replaced(self):
        p = MotionPage()
        p.routes = {(FILTER, 0x33, i): (source, 200)
                    for i, source in enumerate((1, 4, 13))}
        before = p.routes.copy()
        p.toggle()
        p.turn(1000)
        self.assertEqual(p.label(), "No free A-D")
        self.assertEqual(p.routes, before)
        self.assertEqual(p.commands, [])
        self.assertEqual(p.undo, 0)

    def test_existing_lane_shared_with_another_destination_cannot_be_overwritten(self):
        p = self.armed()
        p.routes[FILTER, 0xce, 2] = (9, -500)
        before = p.routes.copy()
        p.turn(1000)
        self.assertEqual(p.label(), "Check route")
        self.assertEqual(p.routes, before)
        self.assertEqual(p.commands, [])

    def test_disabled_existing_assignment_is_not_replaced_or_duplicated(self):
        p = self.armed(depth=0)
        p.turn(1000)
        self.assertEqual(p.label(), "Check route")
        self.assertEqual(p.routes, {(FILTER, 0x33, 0): (9, 0)})
        self.assertEqual(p.commands, [])

    def test_failed_native_route_allocation_and_missing_node_do_not_claim_recording(self):
        for failure in ("route", "node"):
            p = MotionPage()
            p.route_allocation_fails = failure == "route"
            p.present = failure != "node"
            p.toggle()
            p.turn(1000)
            self.assertEqual(p.label(), "Motion memory")
            self.assertEqual(p.routes, {})
            self.assertEqual(p.commands, [])
            self.assertEqual(p.effective(), None)

    def test_failed_capture_removes_only_the_newly_assigned_route(self):
        p = MotionPage()
        p.routes[FILTER, 0x33, 1] = (4, 250)
        p.toggle()
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *args: p.ret(),
                            begin=0x0813706c, end=0x0813706c)
        try:
            p.turn(1000)
        finally:
            p.u.hook_del(hook)
        self.assertEqual(p.label(), "Motion memory")
        self.assertEqual(p.routes, {(FILTER, 0x33, 1): (4, 250)})
        self.assertEqual(p.commands, [])
        self.assertEqual(p.effective(), None)
        self.assertEqual(len(p.route_packets), 2)

    def test_unsupported_scales_are_not_recorded_or_auto_assigned(self):
        for kind, key in ((6, 3), (7, 0x57)):
            p = MotionPage()
            p.types[FILTER] = kind
            p.call(0x08171c1c, SLOT, key, 0, 1)
            p.w(SLOT + 0x34, FILTER)
            p.toggle()
            p.turn(100000)
            self.assertEqual(p.label(), "Motion range")
            self.assertEqual(p.routes, {})
            self.assertEqual(p.commands, [])
            self.assertEqual(p.undo, 0)

    def test_wavetable_position_captures_native_255_scale_with_signed_remainder(self):
        for depth in (1000, 333, -333):
            with self.subTest(depth=depth):
                p = MotionPage()
                p.types[FILTER] = 6
                p.call(0x08171c1c, SLOT, 0xc9, 128, 1)
                p.w(SLOT + 0x34, FILTER)
                p.routes[FILTER, 0xc9, 0] = (9, depth)
                p.toggle()
                source, remainder, before = 0, 0, 128
                for step, delta in enumerate([800] * 8 + [-800] * 8):
                    p.position(step)
                    event = p.turn(delta)[0]
                    numerator = (event[3] - before) * 1000000 + remainder
                    divisor = depth * 255
                    change = abs(numerator) // abs(divisor)
                    if (numerator < 0) != (divisor < 0):
                        change = -change
                    source += change
                    remainder = numerator - change * divisor
                    self.assertEqual(p.read(0, step), source)
                    self.assertEqual(p.effective(key=0xc9), event[3])
                    self.assertEqual(p.label(), "writing")
                    before = event[3]
                self.assertEqual(p.undo, 1)
                self.assertEqual(p.routes, {(FILTER, 0xc9, 0): (9, depth)})

    def test_wavetable_position_full_span_uses_normalized_lane_not_255_depth(self):
        p = MotionPage()
        p.types[FILTER] = 6
        p.call(0x08171c1c, SLOT, 0xc9, 0, 1)
        p.w(SLOT + 0x34, FILTER)
        p.toggle()
        self.assertEqual(p.turn(1000000)[0][3], 255)
        self.assertEqual(p.read(0, 0), 1000)
        self.assertEqual(p.routes, {(FILTER, 0xc9, 0): (9, 1000)})
        p.position(1)
        self.assertEqual(p.turn(-1000000)[0][3], 0)
        self.assertEqual(p.read(0, 1), 0)
        self.assertEqual(p.undo, 1)

    def test_transport_stop_or_different_playing_clip_blocks_writes(self):
        for position, row in ((-1, 0), (0, 1), (16, 0)):
            with self.subTest(position=position, row=row):
                p = self.armed()
                p.position(position, row)
                p.turn(1000)
                self.assertEqual(p.commands, [])
                self.assertEqual(p.label(), "Play clip")

    def test_selected_clip_project_and_length_changes_disarm(self):
        for change in ("clip", "tree", "length", "track"):
            with self.subTest(change=change):
                p = self.armed()
                events = p.turn(1000, deliver=False)
                if change == "clip":
                    p.row = 1
                elif change == "tree":
                    p.w(MODEL, p.r(MODEL) + 32)
                elif change == "length":
                    p.steps = 32
                else:
                    p.proj[0x131] = 1
                p.u.mem_write(EV, struct.pack("<5I", *events[0]))
                self.assertEqual(p.call(p.speed_symbols["motion_capture_event"], EV), 1)
                self.assertEqual(p.commands, [])
                self.assertEqual(p.label(), "Clip changed")
                self.assertEqual(p.u.mem_read(OUT + 0x74 + 4 * 48 + 0x21, 1), b"\0")

    def test_signed_depth_and_preexisting_source_are_preserved(self):
        p = self.armed(lane=2, depth=-500)
        p.write(2, 3, 250)
        p.commands.clear()
        p.position(3)
        event = p.turn(1000)[0]
        self.assertEqual(p.read(2, 3), 250 - (event[3] - 500) * 2)
        self.assertEqual(p.routes[FILTER, 0x33, 0], (11, -500))

    def test_no_note_or_native_node_overrun(self):
        p = self.armed()
        p.u.mem_write(0xc0190000, b"\x7e" * 256)
        p.turn(1000)
        self.assertEqual(p.u.mem_read(NODE - 16, 16), b"\xa5" * 16)
        self.assertEqual(p.u.mem_read(NODE + NODE_BYTES, 16), b"\xa5" * 16)
        self.assertEqual(p.u.mem_read(0xc0190000, 256), b"\x7e" * 256)

    def test_multiple_routes_or_missing_storage_do_not_claim_success(self):
        p = self.armed()
        p.routes[FILTER, 0x33, 1] = (10, 1000)
        p.turn(1000)
        self.assertEqual(p.commands, [])
        self.assertEqual(p.label(), "Check route")
        p = self.armed()
        p.present = False
        p.turn(1000)
        self.assertEqual(p.commands, [])
        self.assertEqual(p.effective(), None)
        self.assertEqual(p.label(), "Motion memory")

    def test_native_m7_status_publisher_reports_the_exact_automation_index(self):
        p = self.armed()
        p.call(0x08062a80, SEQUENCE)
        p.w(SEQUENCE + 0xc, p.track)
        p.w(SEQUENCE + 0x86c0, SEQUENCE + 0x240)
        p.u.mem_write(SEQUENCE + 0x20, b"\1")
        packets = []

        def packet(u, address, size, data):
            packets.append(bytes(u.mem_read(u.reg_read(UC_ARM_REG_R1), 24)))
            p.ret()

        hook = p.u.hook_add(UC_HOOK_CODE, packet, begin=0x08065600, end=0x08065600)
        for step in (0, 7, 15):
            p.w(SEQUENCE + 0x14, step)
            p.call(0x08060740, SEQUENCE, 0, 0xc0030000)
            self.assertEqual(packets[-1][0], 0x53)
            self.assertEqual(struct.unpack_from("<i", packets[-1], 12)[0], step)
            p.position(step)
            p.turn(1000)
            self.assertGreater(p.read(0, step), 0)
            self.assertGreater(p.deliver_audio(step)[0], 0)
        p.u.hook_del(hook)

    def test_four_existing_lanes_capture_separately_and_round_trip_native_codec(self):
        p = self.armed()
        slots = []
        for lane in range(4):
            h = FILTER + lane
            p.types[h] = 10
            if h not in p.children[p.track]:
                p.children[p.track].append(h)
            p.routes[h, 0x33, 0] = (9 + lane, 1000)
            slot = SLOT + lane * 0x468
            if lane:
                p.call(0x08171c1c, slot, 0x33, 500, 1)
            p.w(slot + 0x34, h)
            slots.append(slot)
        routes = p.routes.copy()
        for lane, slot in enumerate(slots):
            p.position(7)
            p.turn((lane + 1) * 1000, slot=slot)
        values = [p.read(lane, 7) for lane in range(4)]
        self.assertTrue(all(value > 0 for value in values))
        self.assertEqual(len(set(values)), 4)
        self.assertEqual(p.routes, routes)
        self.assertEqual(p.undo, 1)
        for lane, value in enumerate(values):
            self.assertAlmostEqual(p.deliver_audio(7)[lane], value / 1000, places=6)
        q = MotionPage()
        for lane in range(4):
            p.write(lane, 15, -100 - lane)
            count, encoded = p.encode_lane(lane)
            self.assertEqual(count, 16)
            q.decode_lane(lane, encoded, slide=lane % 2)
            self.assertEqual([q.read(lane, i) for i in range(256)],
                             [p.read(lane, i) for i in range(256)])
            self.assertEqual(q.u.mem_read(NODE + 0x80e + lane, 1), bytes([lane % 2]))
        self.assertEqual(q.u.mem_read(NODE - 16, 16), b"\xa5" * 16)
        self.assertEqual(q.u.mem_read(NODE + NODE_BYTES, 16), b"\xa5" * 16)

    def test_stop_observation_ends_take_and_project_load_disarms(self):
        p = self.armed()
        p.turn(1000)
        p.position(-1)
        p.call(UU["perf_tick"])
        p.position(0)
        p.turn(1000)
        self.assertEqual(p.undo, 2)
        obj = 0x20031200
        p.w(obj + 0x10, p.track)
        p.call(UU["perf_load"], 0x20017100, obj)
        before = bytes(p.u.mem_read(NODE, NODE_BYTES))
        p.turn(1000)
        self.assertEqual(bytes(p.u.mem_read(NODE, NODE_BYTES)), before)
        self.assertEqual(p.effective(), None)

    def test_native_footer_buttons_appear_and_toggle_selected_state(self):
        p = self.armed()
        root = 0x30034d48
        p.call(0x08180198, root)
        for on in (True, False, True):
            p.footer()
            p.call(UU["device_header_prepare"], OUT)
            p.call(0x0817faf8, root, OUT)
            button = root + 0x54c + 4 * 0xd0
            self.assertEqual(p.u.mem_read(button + 0x30, 1), b"\0")
            self.assertEqual(p.u.mem_read(button + 0xac, 1), bytes([int(on)]))
            self.assertEqual(p.text(OUT + 0x74 + 4 * 48), "Motion")
            p.toggle()

    def test_native_wavetable_filter_destination_receives_recorded_full_sweep(self):
        # Native construction/binding/evaluation; allocation, zero descriptor
        # status page and the sequence-provider transfer remain fixtures.
        for key, base in ((0x33, 500), (0xce, 500), (0xc9, 128),
                          (0xc9, 0), (0xc9, 255)):
            with self.subTest(key=hex(key), base=base):
                p = MotionPage()
                if key == 0xc9:
                    p.types[FILTER] = 6
                self.assertEqual(p.toggle(), 1)
                p.call(0x08171c1c, SLOT, key, base, 1)
                span = 255 if key == 0xc9 else 1000
                normalized_base = base / span
                root, packet_at = 0xc00c0000, 0x20038000
                p.u.mem_map(0, 0x1000)

                def allocate(u, address, size, data):
                    count = u.reg_read(UC_ARM_REG_R2)
                    ptr = p.next
                    p.next += (count + 31) & ~31
                    p.ret(ptr)

                p.u.hook_add(UC_HOOK_CODE, allocate,
                             begin=0x0809f9c0, end=0x0809f9c0)
                p.call(0x0809bf20, root)
                bindings = []

                def attach(u, address, size, data):
                    bindings.append(tuple(u.reg_read(reg) for reg in
                                          (UC_ARM_REG_R0, UC_ARM_REG_R1,
                                           UC_ARM_REG_R2)))

                p.u.hook_add(UC_HOOK_CODE, attach,
                             begin=0x0809fd00, end=0x0809fd00)
                turns = ((1000000, 1.), (-1000000, 0.), (20480, 128 / 255)) if key == 0xc9 else (
                    (80000, 1.), (-160000, 0.), (80000, .5))
                if key == 0xc9 and base == 255:
                    turns = ((-1000000, 0.), (1000000, 1.), (-20320, 128 / 255))
                for delta, expected in turns:
                    p.turn(delta)
                    if not bindings:
                        p.u.mem_write(packet_at, p.route_packets[-1])
                        p.call(0x0807c120, root, packet_at)
                        self.assertEqual(len(bindings), 10)
                        for param, source, slot in bindings:
                            self.assertEqual((source, slot), (root + 0x140, 3))
                            p.u.mem_write(p.r(param) + 4, struct.pack("<f", normalized_base))
                    p.deliver_audio(0)
                    for _ in range(24):
                        p.call(0x08061040, SEQUENCE, TIME)
                    current = p.r(SEQUENCE + 0x875c)
                    source = bytes(p.u.mem_read(current + 4, 4))
                    self.assertAlmostEqual(struct.unpack("<f", source)[0],
                                           expected - normalized_base, delta=.001001)
                    p.u.mem_write(root + 0x144, source)
                    for param, _, _ in bindings:
                        p.call(0x0809fd80, param)
                        value = struct.unpack("<f", struct.pack(
                            "<I", p.u.reg_read(UC_ARM_REG_S0)))[0]
                        self.assertAlmostEqual(value, expected, delta=.001001, msg=(
                            hex(param), bytes(p.u.mem_read(param, 64)).hex(),
                            bytes(p.u.mem_read(p.r(param) + 4, 4)).hex(),
                            bytes(p.u.mem_read(root + 0x140, 8)).hex()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
