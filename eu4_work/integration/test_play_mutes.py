"""W22 raw receiver ownership, native mutes and PLAY-bank LED packet parity.
Packet validation and display services are fixtures, not hardware acceptance.
"""
import gc
import struct
import sys
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
from test_integration import IMAGE, UU, Fixture
from test_previous_controls import m as controls

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "k16_work/bento_mods/tests"))
from receiver_fixture import Receiver, OBJ, ENGINE, UIQUEUE

MODEL = 0x30024b00
STATE = 0x24048ca0
KEEP = []


class Input(Receiver):
    def __init__(self, running=True):
        super().__init__(False)
        self.u.mem_map(0x30000000, 0x40000)
        self.u.mem_map(0x081c0000, 0x40000)
        self.u.mem_write(0x08040000, IMAGE)
        self.word(STATE, 0x31534d42)
        self.u.mem_write(STATE + 12, b"\1")
        self.u.mem_write(STATE + 16, bytes(range(16)))
        self.running(running)
        KEEP.append(self)

    def running(self, value):
        self.u.mem_write(ENGINE + 0x40, bytes([bool(value)]))

    def custom(self):
        return [struct.unpack("<6I", r) for d, r in self.records
                if d == "ui" and r[0] == 254 and struct.unpack_from("<I", r, 16)[0] != 11]

    def bank(self):
        return [struct.unpack("<6I", r)[3] for d, r in self.records
                if d == "ui" and r[0] == 254 and struct.unpack_from("<I", r, 16)[0] == 11]


class Mute(controls.Fixture):
    def __init__(self):
        super().__init__()
        self.u.mem_write(MODEL, bytes(self.u.mem_read(self.m, 0x200)))
        self.m = MODEL
        self.globalobj = MODEL + 4
        self.props[(self.globalobj, 0x131)] = 6
        self.engine = 0x30010000
        self.w(0x3000f650, self.engine)
        self.cells = [0x20018000 + i * 0x80 for i in range(16)]
        self.childvt = 0x20012a00
        self.w(self.vtable + 0x14, 0x081ff051)
        self.w(self.vtable + 0x18, 0x081ff031)
        self.w(self.childvt, 0x081ff041)
        self.errors = []
        self.notifications = []
        self.track_lookups = []
        self.flush_native = False
        self.lights = []
        self.stop = 0x0813f2fc
        self.u.mem_map(0xc0000000, 0x40000)
        self.w(0x3000004c, 0xc0010000)
        self.w(0x30000048, 0xc0040000)
        for i, o in enumerate(self.cells):
            self.w(o, self.childvt)
            self.w(o + 16, 501 + i)
            self.props[(o, 0x73)] = i
            self.props[(o, 0x1e0)] = 0
        KEEP.append(self)

    def hook(self, u, a, size, data):
        r = [u.reg_read(x) for x in controls.REGS[:4]]
        if a == 0x08133960:
            self.track_lookups.append(r[1])
        elif a == 0x08104c08:
            cursor = self.r(0x3000004c)
            self.w(0x3000004c, cursor + ((r[0] + 31) & ~31))
            self.ret(cursor)
        elif a == 0x081257f0 and self.flush_native:
            return
        elif a == 0x0810b7d4:
            packet = struct.unpack("<6I", u.mem_read(r[1], 24))
            if packet[0] & 255 == 0xb4:
                self.lights.append((packet[2] - 16, packet[3]))
            self.ret()
        elif a == 0x081ff050:
            self.w(r[2], self.cells[r[1] - 501] if 501 <= r[1] < 517 else 0)
            self.ret(int(501 <= r[1] < 517))
        elif a == 0x081ff030:
            if r[1] < len(self.cells):
                self.w(r[2], self.cells[r[1]])
                self.ret(1)
            else:
                self.ret(0)
        elif a == 0x081ff040:
            self.ret(1)
        elif a == 0x0812d80e and 501 <= r[1] < 517:
            self.w(r[2], self.cells[r[1] - 501])
            self.ret(1)
        elif a in (0x0813130c, 0x08139138):
            self.ret()
        elif a == 0x08133df8:
            self.w(r[1], 80)
            self.ret(1)
        elif a == 0x08173272:
            self.notifications.append(bytes(u.mem_read(r[1], 20)))
            self.ret()
        elif a == 0x0810b5c8:
            return
        elif a == 0x08104c00:
            self.errors.append(r[0])
            self.ret()
        else:
            super().hook(u, a, size, data)

    def request(self, pad, valid=True, action=10):
        sp = 0x20030000
        record = [254, 0x314d5442 if valid else 0, 0x31544d50,
                  pad, action, 0x31525442]
        self.u.mem_write(sp + 0x220, struct.pack("<6I", *record))
        before = [0x1010 + i for i in range(13)]
        before[4:8] = [self.m, 254, record[2], pad]
        for reg, value in zip(controls.REGS, before):
            self.u.reg_write(reg, value)
        self.u.reg_write(UC_ARM_REG_SP, sp)
        self.u.reg_write(UC_ARM_REG_LR, 0x20035001)
        self.u.emu_start(0x0813f98d, 0, count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC) == 0x0813f2fc
        assert self.u.reg_read(UC_ARM_REG_SP) == sp
        assert [self.u.reg_read(r) for r in controls.REGS] == before

    def property(self, handle, key):
        source, out = 0x2002a100, 0x2002a104
        self.w(source, handle)
        assert Fixture.call(self, 0x08133614, MODEL, source, key, out)
        return self.r(out)

class Tests(unittest.TestCase):
    def test_all_sixteen_pads_are_silent_full_index_requests(self):
        for pad in range(16):
            p = Input()
            levels = [0] * 16
            levels[pad] = 1000
            p.packet(1, levels)
            self.assertEqual(p.events(), [])
            self.assertEqual(p.custom(), [(254, 0x314d5442, 0x31544d50,
                                          pad, 10, 0x31525442)])

    def test_pressure_and_both_release_orders_do_not_retrigger_or_leak_notes(self):
        for play_first in (False, True):
            p = Input()
            p.packet(1, [1000] + [0] * 15)
            p.packet(1, [1500] + [0] * 15)
            self.assertEqual((p.events(), p.custom()), ([], []))
            if play_first:
                p.packet(0, [1500] + [0] * 15)
                self.assertEqual((p.events(), p.custom()), ([], []))
            p.packet(0 if play_first else 1)
            self.assertEqual(p.events(), [])
            self.assertEqual(p.readword(STATE + 4) & 65535, 0)

    def test_stopped_play_and_plain_running_pads_stay_native(self):
        for running, mask in ((False, 1), (True, 0), (False, 0)):
            p = Input(running)
            p.packet(mask, [1000] + [0] * 15)
            self.assertEqual(p.custom(), [])
            self.assertEqual(p.events(), [(172, 0, 1000), (174, 0, 1000)])

    def test_notes_started_before_play_keep_their_native_note_off(self):
        p = Input()
        p.packet(0, [1000] + [0] * 15)
        p.packet(1, [1500] + [0] * 15)
        self.assertEqual(p.custom(), [])
        self.assertEqual(p.events(), [(174, 0, 1500)])
        p.packet(1)
        self.assertEqual(p.events(), [(173, 0, 0), (174, 0, 0)])

    def test_stop_during_owned_pad_does_not_leak_pressure_or_release(self):
        p = Input()
        p.packet(1, [1000] + [0] * 15)
        p.running(False)
        p.packet(1, [1500] + [0] * 15)
        self.assertEqual((p.events(), p.custom()), ([], []))
        p.packet(0)
        self.assertEqual(p.events(), [])

    def test_full_queue_preserves_existing_records_and_counts_drop(self):
        p = Input()
        p.packet(1)
        p.word(UIQUEUE + 0x21a0, 225)
        p.word(UIQUEUE + 0x2180, 1)
        before = bytes(p.u.mem_read(UIQUEUE + 0x980, 256 * 24))
        p.packet(1, [1000] + [0] * 15)
        self.assertEqual((p.events(), p.custom()), ([], []))
        self.assertEqual(p.readword(STATE + 8), 1)
        self.assertEqual(bytes(p.u.mem_read(UIQUEUE + 0x980, 256 * 24)), before)
        p.packet()
        self.assertEqual(p.readword(STATE + 4) & 65535, 0)

    def test_existing_tracks_mixer_and_launch_modifiers_keep_their_routes(self):
        for mask, action in ((0x2001, 1), (0x401, 5)):
            p = Input()
            p.packet(mask, [1000] + [0] * 15)
            self.assertEqual(p.custom()[0][4], action)
        p = Input()
        p.packet(0x1001, [1000] + [0] * 15)
        self.assertEqual(p.custom(), [])
        self.assertEqual(p.events(), [(172, 0, 1000), (174, 0, 1000)])

    def test_native_model_engine_and_screen_toggle_same_track_one_slots(self):
        for pad in range(16):
            p = Mute()
            before = p.contexts()
            p.request(pad)
            self.assertEqual(struct.unpack("<6I", p.u.mem_read(p.engine, 24))[:5],
                             (0x3e, 0, 501 + pad, 0x1e0, 1))
            notification = struct.unpack("<5I", p.notifications[-1])
            self.assertEqual((notification[0] & 255,) + notification[1:],
                             (0xc3, 501 + pad, 0x1e0, 1, 0))
            p.request(pad)
            self.assertEqual(struct.unpack("<6I", p.u.mem_read(p.engine + 24, 24))[4], 0)
            self.assertEqual(p.contexts(), before)
            self.assertEqual(p.props[(p.globalobj, 0x131)], 6)
            self.assertEqual(p.errors, [])
            self.assertEqual(p.track_lookups, [0, 0])

    def test_pads_can_be_toggled_together_and_retriggered_after_release(self):
        p = Input()
        p.packet(1, [1000] * 16)
        self.assertEqual([r[3] for r in p.custom()], list(range(16)))
        self.assertEqual(p.events(), [])
        p.packet(1)
        p.packet(1, [1000] * 16)
        self.assertEqual([r[3] for r in p.custom()], list(range(16)))

    def test_native_mute_state_is_shared_with_touchscreen(self):
        p = Mute()
        event = 0x2002a000
        p.u.mem_write(event, struct.pack("<5I", 0xcf, 513, 0x1e0, 1, 0))
        p.u.reg_write(UC_ARM_REG_R0, p.m)
        p.u.reg_write(UC_ARM_REG_R1, event)
        p.u.reg_write(UC_ARM_REG_SP, 0x20030000)
        p.u.reg_write(UC_ARM_REG_LR, 0x0813f2fd)
        p.u.emu_start(0x0813bfb1, 0, count=100000)
        p.request(12)
        self.assertEqual(struct.unpack("<6I", p.u.mem_read(p.engine + 24, 24))[4], 0)

    def test_native_audio_mute_property_sets_existing_sample_flag(self):
        p = Fixture()
        KEEP.append(p)
        root, sp = 0x20010000, 0x2003e000
        for value in (1, 0, 1):
            p.w(sp + 0x38, value)
            p.u.reg_write(UC_ARM_REG_R4, root)
            p.u.reg_write(UC_ARM_REG_R3, 0x1e0)
            p.u.reg_write(UC_ARM_REG_SP, sp)
            p.u.emu_start(0x08091047, 0x0808e9e0, count=1000)
            self.assertEqual(bytes(p.u.mem_read(root + 0x600, 1)), bytes([value]))

    def test_non_one_shot_first_track_reports_error_without_changing_slots(self):
        p = Mute()
        p.kind = 18
        p.request(0)
        self.assertEqual(p.r(p.engine + 0x620), 0)
        self.assertEqual(len(p.errors), 1)

    def test_invalid_request_never_changes_a_slot(self):
        for pad, valid in ((16, True), (0, False)):
            p = Mute()
            p.request(pad, valid)
            self.assertEqual(p.r(p.engine + 0x620), 0)
            self.assertEqual(p.notifications, [])

    def test_native_transport_play_is_noop_while_running(self):
        p = Fixture()
        KEEP.append(p)
        obj, event = 0x20010000, 0x20030000
        p.u.mem_write(obj, bytes(0x9000))
        p.u.mem_write(obj + 0x40, b"\1")
        p.u.mem_write(event, struct.pack("<6I", 0x8f, 0, 0xfffffffe, 0, 1, 0))
        p.call(0x08059980, obj, event)
        self.assertEqual(p.r(obj + 0x40) & 255, 1)

    def test_button_only_bank_transitions_follow_running_and_exclusive_play(self):
        p = Input()
        p.packet(1)
        self.assertEqual(p.bank(), [1])
        p.packet(1)
        self.assertEqual(p.bank(), [])
        p.packet(0x2001)
        self.assertEqual(p.bank(), [0])
        p.packet(1)
        self.assertEqual(p.bank(), [1])
        p.running(False)
        p.packet(1)
        self.assertEqual(p.bank(), [0])
        p.packet(0)
        self.assertEqual(p.bank(), [])
        p = Input(False)
        p.packet(1)
        self.assertEqual(p.bank(), [])
        p.running(True)
        p.packet(1)
        self.assertEqual(p.bank(), [1])
        p.packet(0)
        self.assertEqual(p.bank(), [0])

    def test_disabled_or_missing_transport_publishes_palette_exit(self):
        for missing in (False, True):
            p = Input()
            p.packet(1)
            if missing:
                p.word(OBJ + 0x8c8, 0)
            else:
                p.u.mem_write(STATE + 12, b"\0")
            p.packet(1)
            self.assertEqual(p.bank(), [0])

    def test_full_queue_retries_palette_exit_without_sticking_bank_state(self):
        p = Input()
        p.packet(1)
        p.word(UIQUEUE + 0x21a0, 225)
        p.word(UIQUEUE + 0x2180, 1)
        p.packet(0)
        self.assertEqual(p.bank(), [])
        self.assertEqual(p.u.mem_read(STATE + 13, 1), b"\1")
        p.word(UIQUEUE + 0x2180, 225)
        p.packet(0)
        self.assertEqual(p.bank(), [0])
        self.assertEqual(p.u.mem_read(STATE + 13, 1), b"\0")

    def test_bank_lights_use_native_mutes_and_colour_without_overwriting_page_state(self):
        p = Mute()
        p.flush_native = True
        pads = MODEL + 0x19c4
        normal = []
        for i in range(16):
            normal.extend((0x112233 + i, 0x445566 + i, 0x778899 + i,
                           (1 if i % 2 else 0x100) if i < 6 else 0))
        p.u.mem_write(pads, struct.pack("<64I", *normal))
        for i in range(16):
            p.w(pads + 0x100 + i * 4, 0xdeadbeef)
        p.u.mem_write(pads + 0x140, b"\x64")
        before = bytes(p.u.mem_read(pads, 256))
        p.props[(p.cells[3], 0x1e0)] = 1
        p.props[(p.cells[12], 0x1e0)] = 1
        colour = Fixture.call(p, 0x08140f50, 0)
        # Native flush owns brightness/gamma and suppresses unchanged packets.
        p.w(pads + 7 * 16, 0xabcdef)
        Fixture.call(p, 0x081257f0, pads)
        normal_packets = dict(p.lights)
        p.w(pads, colour)
        p.w(pads + 12, 0)
        p.lights.clear()
        Fixture.call(p, 0x081257f0, pads)
        colour_packet = dict(p.lights)[0]
        p.u.mem_write(pads, before)
        for i in range(16):
            p.w(pads + 0x100 + i * 4, 0xdeadbeef)
        p.lights.clear()
        p.request(1, action=11)
        physical = dict(p.lights)
        self.assertEqual(physical, {i: 0 if i in (3, 12) else colour_packet for i in range(16)})
        self.assertEqual([p.r(pads + 0x100 + i * 4) for i in range(16)],
                         [0 if i in (3, 12) else colour for i in range(16)])
        self.assertEqual(bytes(p.u.mem_read(pads, 256)), before)
        p.lights.clear()
        p.request(3)
        self.assertEqual(p.lights, [(3, colour_packet)])
        self.assertEqual(bytes(p.u.mem_read(pads, 256)), before)
        # Native animation updates are held back physically, not destroyed.
        p.w(pads + 7 * 16, 0xabcdef)
        p.lights.clear()
        Fixture.call(p, 0x081257f0, pads)
        self.assertEqual(p.lights, [])
        p.request(0, action=11)
        self.assertEqual(dict(p.lights), normal_packets)
        self.assertEqual(p.props[(p.globalobj, 0x131)], 6)
        self.assertEqual(p.property(504, 0x1e0), 0)
        self.assertEqual(p.property(513, 0x1e0), 1)

    def test_empty_slots_are_dark_and_no_track_bank_uses_native_feedback(self):
        p = Mute()
        p.flush_native = True
        pads = MODEL + 0x19c4
        p.u.mem_write(pads + 0x140, b"\x64")
        p.cells = p.cells[:2]
        p.request(1, action=11)
        self.assertTrue(all(p.r(pads + 0x100 + i * 4) == 0 for i in range(2, 16)))
        self.assertNotEqual(p.r(pads + 0x100), 0)
        p.kind = 18
        p.w(pads, 0x123456)
        Fixture.call(p, 0x081257f0, pads)
        self.assertEqual(p.r(pads + 0x100), 0x123456)

    def test_invalid_bank_envelope_and_index_never_enable_feedback(self):
        p = Mute()
        p.request(1, valid=False, action=11)
        p.request(2, action=11)
        self.assertEqual(Fixture.call(p, UU["play_mute_bank"], 0xffffffff), 0)
        self.assertEqual(p.track_lookups, [])


if __name__ == "__main__":
    gc.disable()
    unittest.main(verbosity=2)
