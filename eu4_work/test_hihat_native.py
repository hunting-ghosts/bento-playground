"""No-build HiHat probes of an existing image, not SD-cache/hardware acceptance.

Unlike test_engines, this uses the native audio-root constructor and embedded
voice descriptor, executes the complete render entry including native fallback,
and verifies the retained DSP ELF against the image before using its symbols.
Only provider I/O and the hardware LFO clock service are substituted.
"""
import math
import os
from pathlib import Path
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M7, UC_ARM_REG_C1_C0_2,
                               UC_ARM_REG_FPEXC, UC_ARM_REG_FPSCR,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_SP)

BASE = 0x08040000
FRAMES = 144023
SIGNATURE = 0xb1e70a5c
DEFAULTS = (10, 70, 65, 65, 30, 0, 0)
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


def matched_symbols(image, elf):
    offset = struct.unpack_from('<I', elf, 32)[0]
    size, count = struct.unpack_from('<HH', elf, 46)
    sections = [struct.unpack_from('<10I', elf, offset + i * size)
                for i in range(count)]
    symbols = {}
    for section in sections:
        _, kind, flags, address, start, length, link, _, _, stride = section
        if flags & 2:
            if image[address-BASE:address-BASE+length] != elf[start:start+length]:
                raise ValueError(f'DSP ELF does not match image at {address:08X}')
        if kind != 2:
            continue
        strings = sections[link]
        names = elf[strings[4]:strings[4]+strings[5]]
        for i in range(0, length, stride):
            name, value, _, info, _, _ = struct.unpack_from('<IIIBBH', elf, start+i)
            if info & 15 == 2:
                symbols[names[name:].split(b'\0')[0].decode()] = value & ~1
    return symbols


class NativeHat:
    def __init__(self, image, symbols, values=DEFAULTS):
        self.symbols = symbols
        self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
        self.u.reg_write(UC_ARM_REG_C1_C0_2, 0xf << 20)
        self.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        for address, length in ((BASE, 0x1c0000), (0x10040000, 0x10000),
                                (0x20000000, 0x40000), (0x24000000, 0x50000),
                                (0x30000000, 0x40000), (0xe000e000, 0x2000)):
            self.u.mem_map(address, length)
        self.u.mem_write(BASE, image)
        self.root, self.voice = 0x20010000, 0x20018000
        self.desc = self.voice + 0x10
        self.provider, self.vtable = 0x100455e0, 0x2001b100
        self.temp, self.output, self.samples = 0x20024000, 0x20025000, 0x20026000
        self.stop = 0x081b0000
        self.ready, self.marker, self.rate, self.channels = True, True, 48000, 1
        self.frames = FRAMES
        self.reads = []
        self.hooks = []
        for address in (self.stop, 0x08064ac0, 0x081be010, 0x081be020,
                        0x081be030, 0x081be040):
            self.hooks.append(self.u.hook_add(UC_HOOK_CODE, self.service,
                                            begin=address, end=address))
        self.call(0x08095460, self.root)
        self.w(self.root+12, 101)
        self.call(0x08072a00, self.voice)
        self.call(0x08092f20, self.root, self.voice)
        self.w(self.provider, self.vtable)
        for offset, target in ((0x1c, 0x081be010), (8, 0x081be020),
                               (0x18, 0x081be030), (0x24, 0x081be040)):
            self.w(self.vtable+offset, target | 1)
        self.w(self.desc, self.provider)
        self.w(self.desc+4, 7)
        self.w(self.desc+0x14, 0)
        self.w(self.desc+0x18, self.frames)
        self.w(self.desc+0x24, self.frames)
        self.w(self.root+0x60, 1)
        self.w(self.root+0x20, self.voice)
        self.f(self.voice+0x48, 1)
        self.f(self.voice+0xb8, 1)
        self.u.mem_write(self.voice, b'\1')
        self.call(0x080639a0, self.voice+0x58)
        for buffer, samples in ((self.temp, self.samples),
                                (0x20022000, 0x2002c000)):
            self.w(buffer, 2048)
            self.w(buffer+8, samples)
            self.w(buffer+12, samples+0x2000)
        self.w(self.output, 64)
        self.w(self.output+4, 64)
        self.w(self.output+8, 0x20028000)
        self.w(self.output+12, 0x20029000)
        if values is not None:
            self.w(0x24043500, 0x35424e4b)
            self.w(0x24043504, 2)
            self.w(0x24043520, 2)
            self.w(0x24043524, 101)
            self.u.mem_write(0x24043528, bytes(values)+b'\5')

    def w(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def r(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def f(self, address, value):
        self.u.mem_write(address, struct.pack('<f', value))

    def ret(self, value=0):
        self.u.reg_write(UC_ARM_REG_R0, value)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR))

    def service(self, u, address, size, data):
        if address == self.stop:
            u.emu_stop()
        elif address == 0x08064ac0:
            self.ret()
        elif address == 0x081be010:
            self.ret(self.rate)
        elif address == 0x081be030:
            u.mem_write(u.reg_read(UC_ARM_REG_R0), struct.pack('<ii', self.frames, 0))
            self.ret()
        elif address == 0x081be040:
            self.ret(self.channels)
        elif address == 0x081be020:
            sp = u.reg_read(UC_ARM_REG_SP)
            dest, right, count = struct.unpack('<III', u.mem_read(sp+4, 12))
            position = u.reg_read(UC_ARM_REG_R2) | u.reg_read(UC_ARM_REG_R3) << 32
            if position & (1 << 63):
                position -= 1 << 64
            self.reads.append((position, count, self.ready))
            pcm = [((1 if SIGNATURE & (1 << i) else -1)/32768)
                   if self.ready and self.marker and 0 <= i < 32 else 0.0
                   for i in range(position, position+count)]
            packed = struct.pack(f'<{count}f', *pcm)
            if dest:
                u.mem_write(dest, packed)
            if right:
                u.mem_write(right, packed)
            self.ret(count if self.ready else 0)

    def call(self, address, *args):
        for register, value in zip(REGS, args):
            self.u.reg_write(register, value)
        self.u.reg_write(UC_ARM_REG_SP, 0x2003f000)
        self.u.reg_write(UC_ARM_REG_LR, self.stop | 1)
        self.u.emu_start(address | 1, 0, count=200000)
        if self.u.reg_read(UC_ARM_REG_PC) != self.stop:
            raise AssertionError(f'Native call stopped at {self.u.reg_read(UC_ARM_REG_PC):08X}')
        return self.u.reg_read(UC_ARM_REG_R0)

    def start(self):
        self.call(0x080d5800, self.voice, self.root)

    def render(self):
        for address in (0x20028000, 0x20029000):
            self.u.mem_write(address, bytes(256))
        self.w(0x2003f000, self.temp)
        self.w(0x2003f004, self.output)
        self.call(0x08091820, self.root, self.voice, 0x20022000, self.temp)
        return struct.unpack('<64f', self.u.mem_read(0x20028000, 256))

    def audio(self, blocks=32):
        self.start()
        return [sample for _ in range(blocks) for sample in self.render()]

    def close(self):
        for handle in self.hooks:
            self.u.hook_del(handle)
        self.hooks.clear()


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = Path(os.environ['BENTO_FX_CANDIDATE'])
        cls.image = (out/'bento1.bin').read_bytes()
        elf = Path(os.environ.get('BENTO_HIHAT_ELF',
                                  str(out/'workspace/eu4_work/drums/kick.elf')))
        cls.elf = elf.read_bytes()
        cls.symbols = matched_symbols(cls.image, cls.elf)

    def probe(self, values=DEFAULTS):
        p = NativeHat(self.image, self.symbols, values)
        self.addCleanup(p.close)
        return p

    def test_retained_symbols_cannot_be_used_with_a_changed_payload(self):
        changed = bytearray(self.image)
        changed[self.symbols['kick_render']-BASE] ^= 1
        with self.assertRaisesRegex(ValueError, 'does not match image'):
            matched_symbols(changed, self.elf)

    def test_real_native_descriptor_metadata_selects_only_the_exact_hat(self):
        p = self.probe()
        # Exercise the provider metadata path, not just the cached +24 count.
        p.w(p.desc+0x24, 0)
        self.assertEqual(p.call(0x08054e20, p.desc), 1)
        self.assertEqual(p.call(self.symbols['kick_marker'], p.desc), 5)
        for field, value in (('frames', FRAMES+1), ('rate', 44100),
                             ('marker', False), ('channels', 2)):
            with self.subTest(field=field):
                before = getattr(p, field)
                setattr(p, field, value)
                p.call(0x08054e20, p.desc)
                self.assertEqual(p.call(self.symbols['kick_marker'], p.desc), 0)
                setattr(p, field, before)

    def test_native_root_and_missing_knob_mailbox_keep_audible_hat_defaults(self):
        expected = self.probe().audio()
        actual = self.probe(None).audio()
        self.assertEqual(actual, expected)
        self.assertTrue(all(math.isfinite(x) for x in actual))
        self.assertGreater(max(map(abs, actual)), .01)

    def test_sparse_saved_hat_attributes_load_defaults_not_zeroes(self):
        from integration.test_integration import Fixture, UU
        ui = Fixture()
        for handle in ui.h:
            self.addCleanup(ui.u.hook_del, handle)
        obj, node = 0x20014000, 0x20017000
        ui.u.mem_write(obj+4, b'\1')
        ui.w(obj+0x10, 101)
        ui.attrs.update(bento_kick_version=1, bento_drum_model=5)
        ui.call(UU['kick_ui_load'], node, obj)
        self.assertEqual(bytes(ui.u.mem_read(0x24043528, 7)), bytes(DEFAULTS))
        self.assertEqual(ui.u.mem_read(0x2404352f, 1), b'\5')
        p = self.probe(None)
        p.u.mem_write(0x24043500, bytes(ui.u.mem_read(0x24043500, 0x820)))
        self.assertEqual(p.audio(), self.probe().audio())

    def test_nan_filled_recycled_pool_is_fully_initialized_before_audio(self):
        expected = self.probe().audio()
        for value in (0x55, 0xa5, 0xff):
            with self.subTest(fill=value):
                p = self.probe()
                p.call(self.symbols['kick_assignment'], p.root)
                for address, length in ((0x24045820, 7*288), (0x24047420, 9*288)):
                    p.u.mem_write(address, bytes([value])*length)
                self.assertEqual(p.audio(), expected)

    def test_hardware_fpu_modes_and_parameter_extremes_remain_finite(self):
        for values in (DEFAULTS, (0, 0, 0, 0, 0, 0, 0),
                       (100, 100, 100, 100, 100, 0, 0),
                       (100, 100, 100, 100, 0, 0, 0),
                       (0, 100, 0, 100, 100, 0, 0)):
            expected = self.probe(values).audio()
            for fpscr in (0x01000000, 0x03000000):
                with self.subTest(values=values, fpscr=fpscr):
                    p = self.probe(values)
                    p.u.reg_write(UC_ARM_REG_FPSCR, fpscr)
                    audio = p.audio()
                    self.assertTrue(all(math.isfinite(x) and abs(x) <= 1 for x in audio))
                    self.assertEqual(audio, expected)
                    self.assertGreater(max(map(abs, audio)), 1e-6)

    def test_native_cold_reader_fallback_recovers_when_signature_becomes_ready(self):
        p = self.probe()
        p.ready = False
        p.start()
        for _ in range(3):
            self.assertEqual(p.render(), (0.0,)*64)
            self.assertEqual(p.u.mem_read(p.voice, 1), b'\1')
        p.ready = True
        audio = [x for _ in range(4) for x in p.render()]
        self.assertGreater(max(map(abs, audio)), .01)
        self.assertTrue(any(pos == 0 and n == 32 and ready
                            for pos, n, ready in p.reads))
        self.assertEqual(p.r(0x24047e40) & 255, 5)

    def test_recycled_native_voice_stays_audible_after_envelope_and_smoother_reset(self):
        def scenario(old_velocity):
            p = self.probe()
            p.start()
            p.f(p.voice+0xb8, old_velocity)
            audio = [x for _ in range(32) for x in p.render()]
            # The real note setup clears these before our hook; native smoothing
            # initialization follows it, before the next render.
            p.u.mem_write(p.voice, b'\0\0')
            p.call(0x08063a00, p.voice+0x58)
            for offset in (0xcc, 0x94, 0xa4):
                p.f(p.voice+offset, 0)
            p.start()
            p.f(p.voice+0xb8, 1)
            p.w(0x24042004, 0x2545f491)  # same random state for both new hits
            p.call(0x080639a0, p.voice+0x58)
            p.u.mem_write(p.voice, b'\1')
            for offset in (0xcc, 0x94, 0xa4):
                p.f(p.voice+offset, 0)
            return audio[-2], audio[-1], [x for _ in range(8) for x in p.render()]
        prev, last, audio = scenario(1)
        fresh = scenario(0)[2]
        # R6.11: the old hat's part continues from its last value (the bridge is
        # additive; the new hat's own attack is not faded in).
        self.assertLess(abs((audio[0]-fresh[0]) - last), abs(last-prev) + abs(last)/8 + .002)
        self.assertTrue(all(math.isfinite(x) for x in audio))
        self.assertGreater(max(map(abs, audio)), .01)

    def test_open_hat_extends_lifetime_without_running_native_cursor_past_carrier(self):
        p = self.probe((10, 100, 65, 65, 30, 0, 0))
        p.start()
        self.assertEqual(p.r(0x24042028), 48000*8)
        p.w(0x24042028, 48000*4)
        p.render()
        self.assertLess(p.r(p.voice+0x40), FRAMES)
        self.assertEqual(p.u.mem_read(p.voice, 1), b'\1')
        closed = self.probe()
        closed.start()
        self.assertEqual(closed.r(0x24042028), FRAMES)


if __name__ == '__main__':
    unittest.main(verbosity=2)
