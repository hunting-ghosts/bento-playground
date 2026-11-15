"""Run 18 (owner FINAL 13 Nov; design/native/native_kit.png, native_pad.png, design/oneshot_inst_v4.png): one-shot INST.
Real flash footer templates (Bank = Kit view page 07, Sample Dashboard = Pad view page 08, Waveform = WAV page 11)
through device_header_prepare and the native header apply; the native bank view (ctor 081505D8) for the footer label;
INST through fx_dispatch; the model events the Kit action posts. Emulator evidence only."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R3
from test_perform_ui import Perform, MODEL, POINT
import render

KIT, PAD, REC, MUTE, LOAD, EDIT, DASH, WAV, MIX, SYNTH, KIT_ACTION, MOTION = 0x44, 0x40, 0x43, 0x45, 0x3f, 0x40, 0x3, 0x8, 0x1068, 0x1067, 0x1088, 0x1076
BANK_VIEW, BUF = 0xC0400000, 0xC1C00000
NAMES = ['Kick_2_LoFi', 'Snare_2_LoFi', 'Rim_2_LoFi', 'Snap_2_LoFi', 'CH_2_LoFi', 'Snap_1_LoFi', 'Shaker_1_LoFi', 'Shaker_2_LoFi',
         'Kick_1_LoFi', 'Snare_1_LoFi', 'Rim_1_LoFi', 'Clap_LoFi', 'CH_1_LoFi', 'OH_LoFi', 'Ride_LoFi', 'A_Very_Long_Sample_Name_For_Pad_16']
KEEP = []


class Shot(Perform):
    """Perform fixture (real root, templates, fonts) with names from the native name getter 0813390E."""
    def __init__(self):
        self.names = {100: 'LoFi Kit'}
        self.taps, self.bank_events = [], []
        super().__init__()
        self.types[0] = 14
        self.call('nav_inst_tabs')  # the workflow state exists on the device (workflow ticks create it)
        self.u.hook_add(UC_HOOK_CODE, self.on_tap, begin=0x0817fe70, end=0x0817fe70)
        self.u.hook_add(UC_HOOK_CODE, self.on_bank, begin=0x081512a4, end=0x081512a4)
        KEEP.append(self)

    def hook(self, u, address, size, data):
        if address == 0x0813390e:
            h = self.e.r(u.reg_read(UC_ARM_REG_R1))
            u.mem_write(u.reg_read(UC_ARM_REG_R3), N.native_string(self.names.get(h, '').encode()))
            self.ret(1)
            return
        super().hook(u, address, size, data)

    def on_tap(self, u, a, n, d):
        self.taps.append(struct.unpack('<5I', u.mem_read(u.reg_read(UC_ARM_REG_R1), 20))[2]);self.ret()

    def on_bank(self, u, a, n, d):
        self.bank_events.append(struct.unpack('<H', u.mem_read(u.reg_read(UC_ARM_REG_R1), 2))[0]);self.ret(0)

    def bank(self, selected=2, loaded=True):
        self.call(0x081505D8, BANK_VIEW)
        for pad in range(16):
            t = BANK_VIEW + 0x50 + pad * 0x400
            self.call(0x081793A2, t, 0)
            if loaded: self.u.mem_write(BUF, NAMES[pad].encode() + b'\0'); self.call(0x081797C4, t, BUF)  # a name = a loaded pad (+3F9)
        self.w(BANK_VIEW + 0x6B34, selected)
        self.u.mem_write(MODEL + 0x12c, b'\7')
        self.u.mem_write(render.CTX, struct.pack('<II', 0x101, render.SURF)); render.paint(self.e, BANK_VIEW)  # binds the bank state

    def footer(self, template, page, title, recording=False, drum=False, mix=False):
        self.u.mem_write(MODEL + 0x12c, bytes([page]))
        self.u.mem_write(POINT, render.tpl(self.e, template))
        self.u.mem_write(POINT, title.encode() + b'\0')
        if recording:  # the native Recording tab lit, Mix off
            for slot in range(6):
                r = POINT + N.HDR(0x74) + slot * 48; ident = self.e.h(r + 44)
                if ident in (REC, KIT): self.u.mem_write(r + 0x21, bytes([int(ident == REC)]))
        if drum:  # what drum_panel_toolbar leaves on a drum synth pad
            for slot, (ident, label, lit) in ((3, (SYNTH, 'Synth', not mix)), (4, (MIX, 'Mix', mix))):
                r = POINT + N.HDR(0x74) + slot * 48
                self.u.mem_write(r, label.encode().ljust(32, b'\0') + bytes([0, int(lit), 1])); self.u.mem_write(r + 44, struct.pack('<H', ident))
        self.call('device_header_prepare', POINT)
        self.u.mem_write(POINT + N.HDR(0x68), b'\xf2')
        self.call(0x08180198, render.ROOT); self.call(0x0817faf8, render.ROOT, POINT)
        slots = []
        for i in range(6):
            r = POINT + N.HDR(0x74) + i * 48
            if self.u.mem_read(r + 0x20, 1)[0]: slots.append(None); continue
            slots.append((self.e.h(r + 44), bytes(self.u.mem_read(r, 32)).split(b'\0')[0].decode(), self.u.mem_read(r + 0x21, 1)[0]))
        return slots, bytes(self.u.mem_read(POINT, 32)).split(b'\0')[0].decode()


class Footers(unittest.TestCase):
    def test_kit_footer_is_kit_pad_recording_mute_without_load_and_edit(self):
        p = Shot()
        slots, title = p.footer(1, 7, 'LoFi Kit: One-Shots')
        self.assertEqual(slots, [None, None, (KIT, 'Kit', 1), (PAD, 'Pad', 0), (REC, 'Recording', 0), (MUTE, 'Mute', 0)])
        slots, title = p.footer(1, 7, 'LoFi Kit: One-Shots', recording=True)
        self.assertEqual(slots[2:5], [(KIT, 'Kit', 0), (PAD, 'Pad', 0), (REC, 'Recording', 1)])
        for i in range(2, 6):  # no tab dividers on these footers (the mockup)
            self.assertEqual(p.u.mem_read(render.ROOT + N.ROOT_TABS + i * 0xd0 + 0xce, 1), b'\0')

    def test_pad_and_wav_footers_and_drum_synth_pad(self):
        p = Shot()
        slots, title = p.footer(2, 8, 'LoFi Kit: Pad 3')
        self.assertEqual(slots, [None, None, (KIT_ACTION, 'Kit', 0), (DASH, 'Pad', 1), (WAV, 'WAV', 0), None])
        self.assertEqual(title, 'LoFi Kit: Pad 3')
        slots, title = p.footer(3, 0x11, 'LoFi Kit: WAV 3')
        self.assertEqual(slots, [None, None, (KIT_ACTION, 'Kit', 0), (DASH, 'Pad', 0), (WAV, 'WAV', 1), None])
        self.assertEqual(title, 'LoFi Kit: Pad 3')  # one label for the Pad views
        slots, title = p.footer(2, 8, 'LoFi Kit: Pad 1', drum=True)
        self.assertEqual(slots[2:5], [(KIT_ACTION, 'Kit', 0), (SYNTH, 'Pad', 1), (MIX, 'Mix', 0)])
        slots, title = p.footer(2, 8, 'LoFi Kit: Pad 1', drum=True, mix=True)
        self.assertEqual(slots[3:5], [(SYNTH, 'Pad', 0), (MIX, 'Mix', 1)])

    def test_other_track_types_keep_the_native_footer(self):
        p = Shot(); p.types[0] = 15
        slots, title = p.footer(2, 8, 'Keys: Zone 1')
        self.assertEqual(slots[4:], [(DASH, 'Dashboard', 1), (WAV, 'WAV', 0)])
        self.assertEqual(title, 'Keys: Zone 1')

    def test_kit_label_names_kit_pad_and_sample_in_one_line(self):
        p = Shot(); p.bank(2)
        self.assertEqual(p.footer(1, 7, 'LoFi Kit: One-Shots')[1], 'LoFi Kit: Pad 3: Rim_2_LoFi')
        p.w(BANK_VIEW + 0x6B34, 15)
        title = p.footer(1, 7, 'LoFi Kit: One-Shots')[1]
        self.assertEqual(title, 'LoFi Kit: Pad 16: A_Very_Long_S'); self.assertLessEqual(len(title), 31)
        p = Shot(); p.bank(0, loaded=False)
        self.assertEqual(p.footer(1, 7, 'LoFi Kit: One-Shots')[1], 'LoFi Kit: Pad 1')  # nothing loaded: no sample part


class Actions(unittest.TestCase):
    def test_kit_action_sets_mix_mode_and_opens_the_bank(self):
        p = Shot(); p.events.clear()
        p.u.mem_write(POINT, struct.pack('<5I', KIT_ACTION, 0, 0, 0, 0))
        self.assertEqual(p.call('seq_nav_global', MODEL, POINT), 1)
        self.assertEqual(p.events[-2:], [(0xd3, 100, N.NKEY(0x1bb), 0, 0), (0x1, 0, 0, 0, 0)])
        p.types[0] = 15; p.events.clear()
        self.assertEqual(p.call('oneshot_event', POINT), 0); self.assertEqual(p.events, [])

    def inst(self, p, ms):
        for code, t in ((0xaf, ms), (0xb0, ms + 100)):
            p.w(0x3001fe2c, t); p.call('fx_dispatch', MODEL, code, 0, 10)

    def test_inst_switches_kit_and_pad_recording_to_kit_wav_to_pad(self):
        p = Shot()
        p.footer(1, 7, 'LoFi Kit: One-Shots'); self.inst(p, 5000)
        self.assertEqual(p.taps, [PAD])                       # Kit -> Pad (native Edit)
        p.footer(1, 7, 'LoFi Kit: One-Shots', recording=True); self.inst(p, 6000)
        self.assertEqual(p.taps, [PAD, KIT])                  # Recording -> Kit
        p.events.clear(); p.footer(2, 8, 'LoFi Kit: Pad 3'); self.inst(p, 7000)
        self.assertIn((0x1, 0, 0, 0, 0), p.events)             # Pad -> Kit
        self.assertIn((0xd3, 100, N.NKEY(0x1bb), 0, 0), p.events)
        p.events.clear(); p.footer(3, 0x11, 'LoFi Kit: WAV 3'); self.inst(p, 8000)
        self.assertIn((0x3, 0, 0, 0, 0), p.events)             # WAV -> Pad (model 03 = Dashboard)

    def test_bank_burger_gets_load_in_its_empty_cell(self):
        p = Shot(); p.call('seq_nav_menus_tick')
        for m in range(20):
            menu = 0x30030168 + m * 0xe0
            if p.e.r(menu) == 0xf4:
                self.assertEqual(p.e.r(menu + 4 + 2 * 20), LOAD)
                self.assertEqual(p.e.text(p.e.r(menu + 8 + 2 * 20)), 'Load')
                self.assertEqual([p.e.r(menu + 4 + i * 20) for i in (0, 1, 3, 4, 5)], [N.NUI(0x102b), N.NUI(0x1039), N.NUI(0x103f), N.NUI(0x103e), N.NUI(0x1040)])
                return
        self.fail('bank burger F4 not found')

    def test_footer_label_tap_loads(self):
        p = Shot(); p.bank(2); p.footer(1, 7, 'LoFi Kit: One-Shots')
        x0 = p.e.r(render.ROOT + (0x240 if N.BENTO_FW != 168 else 0x258))
        p.w(POINT + 64, x0 + 20); p.w(POINT + 68, 10)
        self.assertEqual(p.call('oneshot_label_tap', POINT + 64), 1)
        self.assertEqual(p.bank_events, [LOAD])               # the bank's own Load (3F)
        p.w(POINT + 64, 1270)
        self.assertEqual(p.call('oneshot_label_tap', POINT + 64), 0)  # outside the label


if __name__ == '__main__':
    unittest.main(verbosity=2)
